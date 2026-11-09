#requires -Version 5.1
# Inactive F2.7 runtime build. Never installs SCM, keys or audit_only policy.
[CmdletBinding()]
param([switch]$SelfTest,[switch]$Build,[string]$SourceCommit)
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
 Write-Host 'PASS: F2.7 offline runtime build static selftest'
 Write-Host 'NO CHANGE: protected bin, SCM, policy, Windows identities and Ubuntu VM'
 exit 0
}
Check $Build 'Explicit -Build required'
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
$Target=Join-Path $Bin ('f27-'+$Short)
$Proof=Join-Path $OperatorRoot ('F27-build-'+$Short)
Check (-not (Test-Path -LiteralPath $Target)) 'F2.7 target already exists'
Check (-not (Test-Path -LiteralPath $Proof)) 'F2.7 evidence directory already exists'
[IO.Directory]::CreateDirectory($Proof,(CanonicalAcl $true $BrokerSid $true))|Out-Null
Seal $Proof $BrokerSid $true
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
& $Git -C $Repo fetch --no-tags --no-recurse-submodules 'https://github.com/ArdaNTM/JAS.git' 'refs/heads/feat/f27-scm-ubuntu-live-audit'
Check ($LASTEXITCODE -eq 0) 'Git fetch failed'
$Fetched=(& $Git -C $Repo rev-parse 'FETCH_HEAD^{commit}').Trim()
Check ($Fetched -ceq $SourceCommit) 'Git HEAD differs from pinned commit'
$Zip=Join-Path $Proof 'f27-source.zip'
$Paths=@($Overlay.Keys|ForEach-Object{[string]$_})
& $Git -C $Repo archive --format=zip "--output=$Zip" $SourceCommit @Paths
Check ($LASTEXITCODE -eq 0) 'Git archive failed'
$Extracted=Join-Path $Proof 'source'
Expand-Archive -LiteralPath $Zip -DestinationPath $Extracted -ErrorAction Stop
$OverlaySha=[collections.generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
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
 foreach($Key in $Paths){
  $DestName=[string]$Overlay[$Key]
  $Dst=Join-Path $Stage $DestName.Replace('/','\')
  ParentDirs $Stage $DestName $BrokerSid
  [IO.File]::Copy((Join-Path $Extracted $Key.Replace('/','\')),$Dst,$true)
  Seal $Dst $BrokerSid $false
  Sha $Dst $OverlaySha[$Key]
  $Index[$DestName]=$OverlaySha[$Key]
 }
 VerifyTree $Stage $Index $BrokerSid
 $Python=Join-Path $Stage 'python.exe'
 $Code=@'
import importlib, pathlib, sys
root=pathlib.Path(sys.executable).resolve().parent
sys.path.insert(0,str(root))
for name in ("cryptography","win32api","win32service","aura_core.osworld.audit_broker_f27_activation","aura_core.osworld.audit_broker_f27_bridge","aura_core.osworld.audit_broker_ubuntu_transport","aura_core.osworld.audit_broker_scm_identity"):
    mod=importlib.import_module(name)
    if name.startswith("aura_core.") and not pathlib.Path(mod.__file__).resolve().is_relative_to(root):
        raise SystemExit("STOP: module outside trusted runtime")
print("PASS: F2.7 isolated Python import closure")
'@
 & $Python -I -c $Code
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
