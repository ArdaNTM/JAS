#requires -Version 5.1
# Inactive F2.7 runtime build. Never installs SCM, keys or audit_only policy.
[CmdletBinding()]
param([switch]$SelfTest,[switch]$Build,[switch]$CleanupStale,[string]$StaleStageName,[string]$SourceCommit)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Repo='D:\AURA\JAS'
$Git='C:\Program Files\Git\cmd\git.exe'
$Trust='D:\AURA\Trust\DockerBroker'
$Bin=Join-Path $Trust 'bin'
$Base=Join-Path $Bin 'f26-38c42d1'
$Evidence='D:\AURA\JAS\artifacts\aura-f26-runtime-38c42d1\runtime-inventory.json'
$EvidenceSha='cb897595b79b9d2599ed90a12a60383ea9abd9b50a8eebe05dd929f094dd88a7'
$OperatorRoot=Join-Path $env:ProgramFiles 'AURA-F26-Operator'
$Admin=[Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$System=[Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$Full=[int][Security.AccessControl.FileSystemRights]::FullControl
$RX=[int][Security.AccessControl.FileSystemRights]::ReadAndExecute
$Sync=[int][Security.AccessControl.FileSystemRights]::Synchronize
$Overlay=[ordered]@{
 'core/src/aura_core/__init__.py'='aura_core/__init__.py'
 'core/src/aura_core/osworld/__init__.py'='aura_core/osworld/__init__.py'
 'core/src/aura_core/evolution/__init__.py'='aura_core/evolution/__init__.py'
 'core/src/aura_core/evolution/windows_owner_storage.py'='aura_core/evolution/windows_owner_storage.py'
 'core/src/aura_core/osworld/isolation.py'='aura_core/osworld/isolation.py'
 'core/src/aura_core/osworld/network_audit.py'='aura_core/osworld/network_audit.py'
 'core/src/aura_core/osworld/audit_broker_protocol.py'='aura_core/osworld/audit_broker_protocol.py'
 'core/src/aura_core/osworld/audit_broker_service.py'='aura_core/osworld/audit_broker_service.py'
 'core/src/aura_core/osworld/audit_broker_windows.py'='aura_core/osworld/audit_broker_windows.py'
 'core/src/aura_core/osworld/audit_broker_scm_identity.py'='aura_core/osworld/audit_broker_scm_identity.py'
 'core/src/aura_core/osworld/audit_broker_boundary.py'='aura_core/osworld/audit_broker_boundary.py'
 'core/src/aura_core/osworld/audit_broker_docker.py'='aura_core/osworld/audit_broker_docker.py'
 'core/src/aura_core/osworld/audit_broker_f27_activation.py'='aura_core/osworld/audit_broker_f27_activation.py'
 'core/src/aura_core/osworld/audit_broker_f27_bridge.py'='aura_core/osworld/audit_broker_f27_bridge.py'
 'core/src/aura_core/osworld/audit_broker_ubuntu_transport.py'='aura_core/osworld/audit_broker_ubuntu_transport.py'
 'core/scripts/aura_docker_broker_service.py'='aura_docker_broker_service.py'
}
function Check([bool]$Ok,[string]$Reason) {if(-not $Ok){throw "STOP: $Reason"}}
function Relative([string]$Value) {
 Check (-not [string]::IsNullOrWhiteSpace($Value) -and $Value -notmatch '(^[\\/]|^[A-Za-z]:|:|[<>|?*]|[\x00-\x1f])') "Unsafe path $Value"
 foreach($Part in $Value.Replace('\','/').Split('/')){
  Check ($Part -notin @('','.','..') -and -not $Part.EndsWith('.') -and -not $Part.EndsWith(' ')) "Ambiguous path $Value"
 }
}
function NoLink([string]$Path){
 $Item=Get-Item -LiteralPath $Path -Force -ErrorAction Stop
 Check (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) "Reparse point $Path"
}
function Sha([string]$Path,[string]$Digest){
 Check ($Digest -cmatch '^[0-9a-f]{64}$') 'Malformed SHA256'
 NoLink $Path
 Check ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $Digest) "SHA mismatch $Path"
}
function DirectoryGuard([string]$Path){
 NoLink $Path
 $Acl=Get-Acl -LiteralPath $Path
 Check $Acl.AreAccessRulesProtected "Inherited directory ACL $Path"
 Check ($Acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ceq $Admin.Value) "Bad owner $Path"
}
function CanonicalAcl([bool]$IsDir,[string]$BrokerSid,[bool]$OperatorOnly){
 $Acl=if($IsDir){[Security.AccessControl.DirectorySecurity]::new()}else{[Security.AccessControl.FileSecurity]::new()}
 $Acl.SetAccessRuleProtection($true,$false)
 $Acl.SetOwner($Admin)
 $Inherit=if($IsDir){[Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'}else{[Security.AccessControl.InheritanceFlags]::None}
 $Grants=@(
  [PSCustomObject]@{SID=$System;Rights=[Security.AccessControl.FileSystemRights]::FullControl},
  [PSCustomObject]@{SID=$Admin;Rights=[Security.AccessControl.FileSystemRights]::FullControl}
 )
 if(-not $OperatorOnly){$Grants += [PSCustomObject]@{SID=[Security.Principal.SecurityIdentifier]::new($BrokerSid);Rights=[Security.AccessControl.FileSystemRights]::ReadAndExecute}}
 foreach($G in $Grants){
  $Acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
   $G.SID,$G.Rights,$Inherit,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow))
 }
 return $Acl
}
function VerifyAcl([string]$Path,[string]$BrokerSid,[bool]$OperatorOnly){
 NoLink $Path
 $Acl=Get-Acl -LiteralPath $Path
 Check $Acl.AreAccessRulesProtected "Inherited ACL $Path"
 Check ($Acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ceq $Admin.Value) "Wrong owner $Path"
 $Expected=@($System.Value,$Admin.Value)
 if(-not $OperatorOnly){$Expected += $BrokerSid}
 $Seen=[collections.generic.HashSet[string]]::new([StringComparer]::Ordinal)
 foreach($ACE in $Acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
  $Sid=$ACE.IdentityReference.Value
  Check ($ACE.AccessControlType -eq 'Allow' -and -not $ACE.IsInherited -and $Sid -in $Expected -and $Seen.Add($Sid)) "Unknown ACL ACE $Path ($Sid)"
  $Rights=[int]$ACE.FileSystemRights
  if($Sid -ceq $BrokerSid) {
   $Allowed=$RX -bor $Sync
   Check (($Rights -band (-bnot $Allowed)) -eq 0 -and ($Rights -band $RX) -eq $RX) "Broker elevated ACL $Path"
  }else {Check (($Rights -band $Full) -eq $Full) "Trusted principal missing FullControl $Path"}
 }
 Check ($Seen.Count -eq $Expected.Count) "Incomplete ACL $Path"
}
# The existing independently managed operator root is NOT a runtime directory.
# Its BUILTIN\Users ACE may have read-only rights. Never rewrite that ACL;
# strictly deny any mutation-capable right or any other unexpected principal.
function Test-OperatorUsersReadOnly([string]$Sid,[int]$Rights){
 $Allowed=$RX -bor $Sync
 return ($Sid -ceq 'S-1-5-32-545' -and ($Rights -band (-bnot $Allowed)) -eq 0)
}
function VerifyOperatorRoot([string]$Path){
 DirectoryGuard $Path
 $Acl=Get-Acl -LiteralPath $Path
 $Seen=[collections.generic.HashSet[string]]::new([StringComparer]::Ordinal)
 foreach($Ace in $Acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){
  $Sid=$Ace.IdentityReference.Value
  Check ($Ace.AccessControlType -eq 'Allow' -and -not $Ace.IsInherited -and
   $Seen.Add($Sid)) "Unexpected/inherited/duplicate operator root ACE $Path ($Sid)"
  $Rights=[int]$Ace.FileSystemRights
  if($Sid -ceq $Admin.Value -or $Sid -ceq $System.Value){
   Check (($Rights -band $Full) -eq $Full) "SYSTEM/Admin lacks FullControl on $Path"
  }else {
   Check (Test-OperatorUsersReadOnly $Sid $Rights) "Untrusted operator root ACE $Path ($Sid; rights=$Rights)"
  }
 }
 Check ($Seen.Contains($Admin.Value) -and $Seen.Contains($System.Value)) "Missing SYSTEM/Admin ACE on $Path"
 Check ($Seen.Count -ge 2 -and $Seen.Count -le 3) "Unexpected operator root ACL count $Path"
}
function Seal([string]$Path,[string]$BrokerSid,[bool]$OperatorOnly){
 NoLink $Path
 $Dir=(Get-Item -LiteralPath $Path -Force).PSIsContainer
 $New=CanonicalAcl $Dir $BrokerSid $OperatorOnly
 $Old=Get-Acl -LiteralPath $Path
 $Old.SetAccessRuleProtection($true,$false)
 foreach($ACE in @($Old.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))){$Old.PurgeAccessRules($ACE.IdentityReference)}
 $Old.SetOwner($Admin)
 foreach($ACE in $New.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])){$Old.AddAccessRule($ACE)}
 Set-Acl -LiteralPath $Path -AclObject $Old -ErrorAction Stop
 VerifyAcl $Path $BrokerSid $OperatorOnly
}
function ParentDirs([string]$Root,[string]$Relative,[string]$BrokerSid){
 $Parts=$Relative.Replace('\','/').Split('/')
 $Current=$Root
 if($Parts.Count -gt 1){
  foreach($Part in $Parts[0..($Parts.Count-2)]){
   $Current=Join-Path $Current $Part
   if(-not (Test-Path -LiteralPath $Current)){
    [IO.Directory]::CreateDirectory($Current,(CanonicalAcl $true $BrokerSid $false))|Out-Null
    Seal $Current $BrokerSid $false
   }else{VerifyAcl $Current $BrokerSid $false}
  }
 }
}
function ValidateOverlayDestination([string]$Stage,[string]$Key,[string]$BrokerSid){
 Check ($Overlay.Contains($Key)) "Non-overlay source used as runtime destination: $Key"
 $Relative=[string]$Overlay[$Key]
 Check (-not [string]::IsNullOrWhiteSpace($Relative)) "Empty runtime relative target for $Key"
 Relative $Relative
 $StageRoot=[IO.Path]::GetFullPath($Stage).TrimEnd('\')+'\'
 $Target=[IO.Path]::GetFullPath((Join-Path $Stage $Relative.Replace('/','\')))
 Check ($Target.StartsWith($StageRoot,[StringComparison]::OrdinalIgnoreCase)) "Destination escaped staging root: $Key"
 $Parent=[IO.Path]::GetDirectoryName($Target)
 Check (-not [string]::IsNullOrWhiteSpace($Parent) -and
   $Parent.StartsWith($StageRoot,[StringComparison]::OrdinalIgnoreCase)) "Invalid destination parent for $Key"
 ParentDirs $Stage $Relative $BrokerSid
 Check ([IO.Directory]::Exists($Parent)) "Parent directory was not created for $Key"
 VerifyAcl $Parent $BrokerSid $false
 return $Target
}
function VerifyTree([string]$Root,[collections.generic.Dictionary[string,string]]$Index,[string]$BrokerSid){
 VerifyAcl $Root $BrokerSid $false
 $Files=@(Get-ChildItem -LiteralPath $Root -Recurse -File -Force -ErrorAction Stop)
 Check ($Files.Count -eq $Index.Count) "Unexpected runtime file count $Root"
 foreach($File in $Files){
  $Rel=$File.FullName.Substring($Root.TrimEnd('\').Length+1).Replace('\','/')
  Check ($Index.ContainsKey($Rel)) "Unexpected file $Rel"
  Sha $File.FullName $Index[$Rel]
  VerifyAcl $File.FullName $BrokerSid $false
 }
 foreach($Dir in @(Get-ChildItem -LiteralPath $Root -Recurse -Directory -Force -ErrorAction Stop)){VerifyAcl $Dir.FullName $BrokerSid $false}
}
if($SelfTest){
 Check ($Overlay.Count -eq 16) 'Overlay closure count changed'
 $Unique=[collections.generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
 foreach($K in $Overlay.Keys){Relative $K;Relative $Overlay[$K];Check ($Unique.Add($Overlay[$K])) 'Duplicate output'}
 foreach($Bad in @('..\evil','a//b','C:\x','dir/../x','a:ads')){
  $Denied=$false;try{Relative $Bad}catch{$Denied=$true};Check $Denied "Path traversal accepted $Bad"
 }
 Check ($EvidenceSha.Length -eq 64) 'Truncated baseline SHA'
 Check ('.f27-staging-3921783feff1470e9ed927898fe815d0' -cmatch '^\.f27-staging-[0-9a-f]{32}$') 'Rejected exact stale stage name'
 Check ('.f27-staging-05a452e270324f82982a2055f032c282' -cmatch '^\.f27-staging-[0-9a-f]{32}$') 'Rejected new failed stage name'
 Check ($Overlay.Count -eq 16) 'Runtime overlay count changed'
 $ArchivePaths=@($Overlay.Keys|ForEach-Object{[string]$_})
 $ArchivePaths+= 'scripts/verify_f27_runtime_imports.py'
 Check ($ArchivePaths.Count -eq 17 -and
    $ArchivePaths[-1] -notin @($Overlay.Keys)) 'Import-only verifier accidentally entered runtime overlay'
 foreach($Source in $Overlay.Keys) {
  $Relative=[string]$Overlay[$Source]
  Check (-not [string]::IsNullOrWhiteSpace($Relative)) "Empty overlay target: $Source"
  Relative $Relative
 }
 Check (-not $Overlay.Contains('scripts/verify_f27_runtime_imports.py')) 'Python verifier must never be copied as a runtime overlay'
 Check ('..\wrong' -cnotmatch '^\.f27-staging-[0-9a-f]{32}$') 'Accepted traversal stale stage name'
 Check ($null -eq $PSBoundParameters['Build'] -or -not $PSBoundParameters['Build']) 'SelfTest cannot build runtime'
 # Root is a different security tier from sealed runtime/receipt files.
 # Read/Execute (+ optional Synchronize) is safe; no Write/Delete/DAC/Owner.
 Check (Test-OperatorUsersReadOnly 'S-1-5-32-545' $RX) 'Read-only Users ACE rejected'
 Check (Test-OperatorUsersReadOnly 'S-1-5-32-545' ($RX -bor $Sync)) 'Read-only Users + SYNCHRONIZE rejected'
 foreach($Bad in @(
  [int][Security.AccessControl.FileSystemRights]::WriteData,
  [int][Security.AccessControl.FileSystemRights]::AppendData,
  [int][Security.AccessControl.FileSystemRights]::Delete,
  [int][Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles,
  [int][Security.AccessControl.FileSystemRights]::ChangePermissions,
  [int][Security.AccessControl.FileSystemRights]::TakeOwnership
 )){
  Check (-not (Test-OperatorUsersReadOnly 'S-1-5-32-545' ($RX -bor $Sync -bor $Bad))) "Mutating Users ACE accepted ($Bad)"
 }
 Check (-not (Test-OperatorUsersReadOnly 'S-1-5-11' $RX)) 'Unexpected untrusted operator ACE accepted'
 Write-Host 'PASS: F2.7 offline runtime build static selftest'
 Write-Host 'NO CHANGE: protected bin, SCM, policy, Windows identities and Ubuntu VM'
 exit 0
}
Check ($Build -xor $CleanupStale) 'Specify exactly one of -Build or -CleanupStale'
Check (-not $CleanupStale -or $StaleStageName -cmatch '^\.f27-staging-[0-9a-f]{32}$') 'Invalid exact F2.7 stale staging directory name'
Check ($CleanupStale -or [string]::IsNullOrWhiteSpace($StaleStageName)) 'Stale name forbidden without -CleanupStale'
Check ($SourceCommit -cmatch '^[0-9a-f]{40}$') 'Pinned 40hex reviewed commit required'
$Short=$SourceCommit.Substring(0,12)
$Principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
Check ($Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) 'Elevated independent operator required'
$Broker=Get-LocalUser -Name 'AuraDockerBroker' -ErrorAction Stop
Check (-not $Broker.Enabled) 'Broker must remain disabled'
Check ($null -eq (Get-CimInstance Win32_Service -Filter "Name='AuraOSWorldAuditBroker'")) 'SCM already installed'
foreach($Rel in @('policy\service.json','policy\operator-approval.json','keys\operator-approval-ed25519.pub','state\f27-nonces.sqlite3')){
 Check (-not (Test-Path -LiteralPath (Join-Path $Trust $Rel))) "Activation artifact present: $Rel"
}
$BrokerSid=$Broker.SID.Value
foreach($D in @($Trust,$Bin,$Base,$OperatorRoot)){DirectoryGuard $D}
VerifyOperatorRoot $OperatorRoot
$Target=Join-Path $Bin ('f27-'+$Short)
$Proof=Join-Path $OperatorRoot ('F27-build-'+$Short)
Check (-not (Test-Path -LiteralPath $Target)) 'F2.7 target already exists'
if($CleanupStale){
 Check (Test-Path -LiteralPath $Proof) 'Pinned prior build evidence absent'
 VerifyAcl $Proof $BrokerSid $true
}else{
 Check (-not (Test-Path -LiteralPath $Proof)) 'F2.7 evidence directory already exists'
 [IO.Directory]::CreateDirectory($Proof,(CanonicalAcl $true $BrokerSid $true))|Out-Null
 Seal $Proof $BrokerSid $true
}
Sha $Evidence $EvidenceSha
$Raw=ConvertFrom-Json -InputObject (Get-Content -LiteralPath $Evidence -Raw -Encoding UTF8)
$Rows=if($Raw -is [array]){@($Raw)}elseif($null -ne $Raw.files -and $Raw.files -is [array]){@($Raw.files)}else{throw 'STOP: Invalid base inventory schema'}
Check ($Rows.Count -eq 9028) 'Expected 9028 F2.6 inventory files'
$Index=[collections.generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach($Row in $Rows){
 $Path=([string]$Row.path).Replace('\','/')
 if($Path.StartsWith('bin/',[StringComparison]::OrdinalIgnoreCase)){$Path=$Path.Substring(4)}
 Relative $Path
 $Digest=[string]$Row.sha256
 Check ($Digest -cmatch '^[0-9a-f]{64}$' -and -not $Index.ContainsKey($Path)) "Duplicate/invalid base entry $Path"
 $Index.Add($Path,$Digest)
}
VerifyTree $Base $Index $BrokerSid
Write-Host 'PASS: Protected F2.6 baseline 9028-file inventory and ACL'
if($CleanupStale){
 # Only the previously reviewed 3df2158 commit is accepted for this
 # interrupted stage: no branch fallback, no wildcard cleanup, no new fetch.
 $KnownOld=$SourceCommit -ceq '3df215826216131ea82826fa3b491ecd97f8625b' -and
   $StaleStageName -ceq '.f27-staging-3921783feff1470e9ed927898fe815d0'
 $KnownNew=$SourceCommit -ceq '3f518d003bded08e93908b8f47747f9dc6e6a260' -and
   $StaleStageName -ceq '.f27-staging-05a452e270324f82982a2055f032c282'
 Check ($KnownOld -or $KnownNew) 'Stale stage/commit pair is not explicitly approved'
 $CommitExists=(& $Git -C $Repo rev-parse ($SourceCommit+'^{commit}')).Trim()
 Check ($LASTEXITCODE -eq 0 -and $CommitExists -ceq $SourceCommit) 'Pinned stale source commit absent'
}else{
 & $Git -C $Repo fetch --no-tags --no-recurse-submodules 'https://github.com/ArdaNTM/JAS.git' 'refs/heads/feat/f27-scm-ubuntu-live-audit'
 Check ($LASTEXITCODE -eq 0) 'Git fetch failed'
 $Fetched=(& $Git -C $Repo rev-parse 'FETCH_HEAD^{commit}').Trim()
 Check ($Fetched -ceq $SourceCommit) 'Git HEAD differs from pinned commit'
}
$Zip=Join-Path $Proof 'f27-source.zip'
$OverlayPaths=@($Overlay.Keys|ForEach-Object{[string]$_})
$Paths=@($OverlayPaths)
# Verifier belongs to source archive only; never to the runtime overlay.
if(-not $CleanupStale -or $SourceCommit -ceq '3f518d003bded08e93908b8f47747f9dc6e6a260'){
 $Paths += 'scripts/verify_f27_runtime_imports.py'
}
if(-not $CleanupStale){
 & $Git -C $Repo archive --format=zip "--output=$Zip" $SourceCommit @Paths
 Check ($LASTEXITCODE -eq 0) 'Git archive failed'
 $Extracted=Join-Path $Proof 'source'
 Expand-Archive -LiteralPath $Zip -DestinationPath $Extracted -ErrorAction Stop
}else {
 $Extracted=Join-Path $Proof 'source'
 Check (Test-Path -LiteralPath $Zip) 'Pinned original Git archive missing'
 Check (Test-Path -LiteralPath $Extracted) 'Pinned extracted source missing'
}
$OverlaySha=[collections.generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
Check (@(Get-ChildItem -LiteralPath $Extracted -Recurse -File -Force -ErrorAction Stop).Count -eq $Paths.Count) 'Unexpected files in Git source archive'
foreach($Node in @(Get-ChildItem -LiteralPath $Extracted -Recurse -Force -ErrorAction Stop)){NoLink $Node.FullName}
foreach($Key in $Paths){
 $From=Join-Path $Extracted $Key.Replace('/','\')
 NoLink $From
 $Blob=(& $Git -C $Repo hash-object -- $From).Trim()
 Check ($LASTEXITCODE -eq 0) "Git blob failure $Key"
 $Expected=(& $Git -C $Repo rev-parse ($SourceCommit+':'+$Key)).Trim()
 Check ($LASTEXITCODE -eq 0 -and $Blob -ceq $Expected) "Git tree mismatch $Key"
 $OverlaySha.Add($Key,(Get-FileHash -LiteralPath $From -Algorithm SHA256).Hash.ToLowerInvariant())
}
Write-Host 'PASS: Pinned 16-file F2.7 SCM/SSH source closure'
if($CleanupStale){
 # Only delete a fully inventory-matched, sealed, interrupted stage.
 # The 16 F2.7 source bytes have just been reverified against the old
 # commit tree; the old 9028-file baseline was rehashed in VerifyTree.
 foreach($Key in $OverlayPaths){
  Check ($Overlay.Contains($Key)) "Missing original overlay mapping: $Key"
  $DestName=[string]$Overlay[$Key]
  Relative $DestName
  Check ($OverlaySha.ContainsKey($Key)) "Missing archived overlay SHA: $Key"
  $Index[$DestName]=$OverlaySha[$Key]
 }
 $Stage=Join-Path $Bin $StaleStageName
 Check (-not (Test-Path -LiteralPath $Target)) 'Previous final target unexpectedly exists'
 VerifyTree $Stage $Index $BrokerSid
 Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction Stop
 Check (-not (Test-Path -LiteralPath $Stage)) 'Interrupted stage not removed'
 Write-Host "PASS: Verified F2.7 interrupted stage removed: $Stage" -ForegroundColor Green
 Write-Host 'NO CHANGE: F2.6 candidate, future F2.7 target, SCM, Ubuntu, policy, keys'
 exit 0
}
$VerifierFrom=Join-Path $Extracted 'scripts\verify_f27_runtime_imports.py'
$Verifier=Join-Path $Proof 'verify_f27_runtime_imports.py'
Check (-not (Test-Path -LiteralPath $Verifier)) 'Verifier already present'
[IO.File]::Copy($VerifierFrom,$Verifier,$false)
Seal $Verifier $BrokerSid $true
Sha $Verifier $OverlaySha['scripts/verify_f27_runtime_imports.py']
$Stage=Join-Path $Bin ('.f27-staging-'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($Stage,(CanonicalAcl $true $BrokerSid $false))|Out-Null
try {
 Seal $Stage $BrokerSid $false
 foreach($Item in @($Index.GetEnumerator())){
  $Dst=Join-Path $Stage $Item.Key.Replace('/','\')
  ParentDirs $Stage $Item.Key $BrokerSid
  [IO.File]::Copy((Join-Path $Base $Item.Key.Replace('/','\')),$Dst,$false)
  Seal $Dst $BrokerSid $false
  Sha $Dst $Item.Value
 }
 Write-Host 'PASS: F2.6 runtime bytes copied to new F2.7 protected staging'
 # Explicitly iterate ONLY the 16 overlay entries; the seventeenth
 # Git source is an operator-only Python import verifier.
 Check ($OverlayPaths.Count -eq 16) 'Runtime overlay entry count mismatch'
 foreach($Key in $OverlayPaths){
  Check ($OverlaySha.ContainsKey($Key)) "Overlay source not pinned: $Key"
  $DestName=[string]$Overlay[$Key]
  $Dst=ValidateOverlayDestination $Stage $Key $BrokerSid
  $From=Join-Path $Extracted $Key.Replace('/','\')
  Sha $From $OverlaySha[$Key]
  [IO.File]::Copy($From,$Dst,$true)
  Seal $Dst $BrokerSid $false
  Sha $Dst $OverlaySha[$Key]
  $Index[$DestName]=$OverlaySha[$Key]
 }
 Write-Host 'PASS: 16 F2.7 overlay files copied to verified parent directories'
 VerifyTree $Stage $Index $BrokerSid
 $Python=Join-Path $Stage 'python.exe'
 # Pass a pinned, protected .py file, never Windows PowerShell -c text.
 & $Python -I -B $Verifier
 Check ($LASTEXITCODE -eq 0) 'F2.7 isolated Python import failure'
 $Entries=@(foreach($Item in @($Index.GetEnumerator()|Sort-Object Key)){
  [PSCustomObject][ordered]@{path=$Item.Key.Replace('\','/');sha256=$Item.Value}
 })
 $Manifest=[PSCustomObject][ordered]@{schema='aura.osworld.f27-runtime-inventory.v1';files=$Entries}
 $ManifestPath=Join-Path $Proof 'f27-runtime-inventory.json'
 $JSON=(ConvertTo-Json -InputObject $Manifest -Depth 8 -Compress)+[Environment]::NewLine
 [IO.File]::WriteAllText($ManifestPath,$JSON,[Text.UTF8Encoding]::new($false))
 Seal $ManifestPath $BrokerSid $true
 $Digest=(Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
 [IO.Directory]::Move($Stage,$Target)
 VerifyTree $Target $Index $BrokerSid
 $Receipt=[ordered]@{schema='aura.osworld.f27-inactive-candidate.v1';git_commit=$SourceCommit;f26_inventory_sha256=$EvidenceSha;f27_inventory_sha256=$Digest;file_count=$Index.Count;runtime_directory=$Target;activated=$false}
 $ReceiptPath=Join-Path $Proof 'build-receipt.json'
 [IO.File]::WriteAllText($ReceiptPath,(ConvertTo-Json -InputObject $Receipt -Depth 4)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
 Seal $ReceiptPath $BrokerSid $true
 Write-Host "PASS: protected inactive F2.7 runtime: $Target" -ForegroundColor Green
 Write-Host "PASS: file count $($Index.Count), manifest SHA256 $Digest"
 Write-Host "OPERATOR EVIDENCE: $Proof"
 Write-Host 'NO CHANGE: F2.6, SCM, service.json, SSH keys or Ubuntu VM'
}catch{
 Write-Warning "F2.7 build STOP: $($_.Exception.Message)"
 Write-Warning "Manual review of protected staging: $Stage"
 throw
}
