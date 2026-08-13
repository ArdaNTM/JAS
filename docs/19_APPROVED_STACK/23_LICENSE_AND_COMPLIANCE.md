# 23 — LICENSE AND COMPLIANCE

**Document ID:** JAS-AS-23  
**Document:** `23_LICENSE_AND_COMPLIANCE.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Version:** v1.0  
**Authority:** JAS v1  
**Status:** APPROVED  
**Primary Domain:** Licensing, Intellectual Property, Legal Compliance, Dependency Governance, Model Compliance, Distribution Compliance

**Depends On:**

```text
JAS v1
00_APPROVED_STACK_OVERVIEW.md
01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md
19_APPROVED_MODELS.md
20_APPROVED_MCP_SERVERS.md
21_APPROVED_SOFTWARE_MATRIX.md
22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md
```

**Feeds Into:**

```text
24_VERSION_SUPPORT_POLICY.md
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md
Version Lock
Manifest
Bootstrap
Architecture Compliance Checker
Dependency Auditing
Release Engineering
Distribution
Commercialization Review
```

---

# 1. PURPOSE

This document defines the licensing and compliance framework for the JARVIS / JAS project.

Its purpose is to ensure that:

```text
Source Code
+
Dependencies
+
Models
+
Model Weights
+
Datasets
+
MCP Servers
+
Plugins
+
Container Images
+
Browser Components
+
Fonts
+
Assets
+
Documentation
+
External Services
```

can be used, modified, distributed, deployed, and potentially commercialized in a legally controlled manner.

---

# 2. CORE PRINCIPLE

JARVIS must never assume:

```text
Open Source
=
No Restrictions
```

or:

```text
Free to Download
=
Free to Commercialize
```

or:

```text
Public GitHub Repository
=
Public Domain
```

These assumptions are prohibited.

---

# 3. LICENSE COMPLIANCE IS AN ARCHITECTURAL REQUIREMENT

License compliance is not a final legal cleanup step.

It is part of architecture.

The architecture therefore follows:

```text
Technology Selection
        ↓
License Identification
        ↓
License Compatibility
        ↓
Compliance Classification
        ↓
Approval
        ↓
Version Lock
        ↓
Manifest
        ↓
Bootstrap
        ↓
Release Compliance
```

---

# 4. LEGAL DISCLAIMER

This document defines the project's engineering compliance policy.

It is not a substitute for legal advice.

For:

```text
Commercial Distribution
Enterprise Licensing
Acquisition
Investment
Patent Disputes
Copyright Disputes
Trademark Disputes
Model Licensing
Large-Scale Commercial Deployment
```

a qualified legal professional should review the applicable facts, licenses, contracts, jurisdictions, and distribution model.

---

# 5. COMPLIANCE OBJECTIVES

JARVIS compliance has the following objectives:

```text
1. Know what software is used.
2. Know who owns it.
3. Know its license.
4. Know the obligations created by that license.
5. Know whether the license is compatible with JARVIS.
6. Know whether the exact version changes those obligations.
7. Preserve required notices.
8. Preserve required attribution.
9. Track model-specific terms.
10. Track commercial restrictions.
11. Track distribution restrictions.
12. Track network/hosted-service implications.
13. Track source-disclosure obligations.
14. Prevent prohibited dependencies from entering production.
15. Produce an auditable compliance record.
```

---

# 6. FUNDAMENTAL LICENSE DISTINCTIONS

The project explicitly distinguishes:

```text
Copyright
License
Trademark
Patent
Terms of Service
Terms of Use
Acceptable Use Policy
Privacy Policy
Data Processing Agreement
Model License
Dataset License
Software License
Commercial Agreement
```

These are not interchangeable.

---

# 7. COPYRIGHT

Copyright determines ownership of protected creative/software works.

A license grants permissions from the rights holder.

Therefore:

```text
Copyright
≠
License
```

---

# 8. LICENSE

A license defines what the recipient may do with a work.

Typical permissions include:

```text
Use
Copy
Modify
Distribute
Sublicense
Create Derivatives
```

depending on the license.

---

# 9. TRADEMARK

A permissive software license generally does not automatically grant trademark rights.

JARVIS must not assume that using an open-source project permits:

```text
Logo Usage
Trademark Usage
Endorsement Claims
Brand Implication
Product Naming
```

---

# 10. PATENTS

Some licenses contain explicit patent grants.

Others may not.

Patent analysis must therefore be treated separately from copyright analysis.

---

# 11. TERMS OF SERVICE

Cloud AI services are frequently governed by:

```text
Terms of Service
Commercial Terms
API Terms
Usage Policies
```

rather than a traditional open-source software license.

Therefore:

```text
Cloud API
≠
Open-source dependency
```

---

# 12. MODEL LICENSES

AI model weights may have:

```text
Apache-2.0
MIT
Custom Model License
Responsible AI License
Community License
Research License
Non-commercial License
Provider Terms
```

or other conditions.

A model must never be classified solely based on the repository's software license.

---

# 13. DATASET LICENSES

Datasets are independently governed.

A model may have a permissive license while the dataset used to train it has different restrictions.

Therefore:

```text
Model License
≠
Training Dataset License
```

---

# 14. OUTPUT RIGHTS

The right to use model output is governed by the applicable model/service terms and applicable law.

JARVIS must not make universal assumptions such as:

```text
"All AI output is automatically owned by JARVIS."
```

or:

```text
"All model output is automatically public."
```

---

# 15. SOFTWARE LICENSE CATEGORIES

JAS recognizes at minimum:

```text
MIT
BSD-2-Clause
BSD-3-Clause
Apache-2.0
ISC
MPL-2.0
LGPL
GPL
AGPL
SSPL
Source-Available Licenses
Commercial Licenses
Proprietary Terms
Custom Model Licenses
```

---

# 16. PERMISSIVE LICENSES

Typical permissive licenses include:

```text
MIT
BSD
Apache-2.0
ISC
```

These generally permit broad use subject to their respective conditions.

However, exact obligations must still be preserved.

---

# 17. APACHE-2.0

Apache-2.0 is generally permissive and includes an express patent license.

JARVIS may use Apache-2.0 components subject to the license requirements.

Typical compliance requirements include:

```text
Copyright notices
License text
NOTICE requirements where applicable
Modification notices where applicable
Patent provisions
```

---

# 18. MIT

MIT is a permissive license.

JARVIS may generally incorporate MIT software subject to its notice and warranty/disclaimer requirements.

---

# 19. BSD

BSD licenses are permissive but have specific notice and attribution requirements depending on the exact variant.

The project must record:

```text
BSD-2-Clause
BSD-3-Clause
```

separately.

---

# 20. ISC

ISC is a permissive license.

The exact license text must still be retained in compliance artifacts.

---

# 21. MPL-2.0

Mozilla Public License 2.0 is a file-level copyleft license.

It must not be treated as equivalent to MIT or Apache-2.0.

If MPL-2.0 code is modified, the relevant source-disclosure requirements must be evaluated.

---

# 22. LGPL

LGPL introduces additional obligations that depend on how the library is linked and distributed.

LGPL dependencies therefore require explicit review.

---

# 23. GPL

GPL is a strong copyleft license.

A GPL dependency must not automatically be incorporated into a proprietary JARVIS distribution.

The exact dependency relationship and distribution model require legal analysis.

---

# 24. AGPL

AGPL introduces network-use considerations in addition to traditional distribution considerations.

JARVIS must therefore treat AGPL as a high-risk license for components integrated into network-facing production systems.

---

# 25. SSPL

SSPL is not treated as equivalent to Apache-2.0, MIT, BSD, or GPL.

SSPL-based software requires separate compliance review.

---

# 26. SOURCE-AVAILABLE LICENSES

Source availability does not mean open source.

A source-available project may impose:

```text
Commercial Restrictions
Hosting Restrictions
Redistribution Restrictions
Competitive Use Restrictions
Revenue Thresholds
Field-of-Use Restrictions
```

Such software requires explicit approval.

---

# 27. COMMERCIAL LICENSES

Commercial software may be approved if:

```text
License Terms
+
Cost
+
Usage Rights
+
Deployment Rights
+
Distribution Rights
+
Seat / User Limits
+
Server Limits
+
Model Limits
```

are compatible with JARVIS.

---

# 28. DUAL LICENSING

A project may provide:

```text
Open-source license
OR
Commercial license
```

JARVIS must select the appropriate license path explicitly.

---

# 29. NO IMPLIED LICENSE

The project must never infer a license from:

```text
GitHub repository
README
Package name
Source availability
Downloadability
Popularity
```

unless the actual license is identifiable.

---

# 30. NO LICENSE = NO APPROVAL

If a production dependency has no identifiable license:

```text
STATUS:
NOT APPROVED
```

until its legal status is clarified.

---

# 31. LICENSE FILE PRIORITY

When identifying a license, the compliance process should inspect:

```text
LICENSE
LICENSE.md
LICENSE.txt
SPDX metadata
Package metadata
Repository metadata
Official project documentation
Official commercial terms
Model card
Terms of Use
```

---

# 32. EXACT VERSION REQUIREMENT

License analysis must be performed against the exact version being used.

The fact that:

```text
Project X
```

uses Apache-2.0 today does not prove that:

```text
Project X version 2 years later
```

uses the same terms.

---

# 33. VERSION LOCK RELATIONSHIP

License compliance therefore depends on:

```text
Technology
+
Version
+
Artifact
+
License
```

not only:

```text
Technology
```

---

# 34. LICENSE SNAPSHOT

The Version Lock system should retain enough information to reconstruct the licensing state of the release.

---

# 35. SOFTWARE BILL OF MATERIALS

JARVIS should maintain an SBOM.

Preferred conceptual formats:

```text
SPDX
CycloneDX
```

---

# 36. SBOM PURPOSE

The SBOM should identify:

```text
Package
Version
Supplier
License
Dependency Relationship
Hash
Component Identifier
```

where supported.

---

# 37. SBOM GENERATION

SBOM generation should occur during release preparation.

---

# 38. SBOM VALIDATION

A release should fail compliance if critical dependency metadata is missing without an approved exception.

---

# 39. DEPENDENCY LICENSE GRAPH

JARVIS should conceptually maintain:

```text
JARVIS
 │
 ├── Dependency A
 │      ├── Dependency C
 │      └── Dependency D
 │
 ├── Dependency B
 │      └── Dependency E
 │
 └── Model F
```

with licensing metadata attached to every relevant component.

---

# 40. DIRECT DEPENDENCIES

Every direct dependency must be:

```text
Approved
License-identified
Version-locked
Audited
```

---

# 41. TRANSITIVE DEPENDENCIES

Transitive dependencies must be audited.

They do not necessarily require manual approval one by one if the compliance tooling can establish their license and compatibility automatically.

---

# 42. UNKNOWN TRANSITIVE LICENSE

If a transitive dependency has an unknown or incompatible license:

```text
Compliance Review Required
```

---

# 43. DEPENDENCY INTRODUCTION RULE

A developer must not add a dependency to JARVIS simply because:

```text
pip install X
```

works.

The dependency must pass:

```text
Technical Review
Security Review
License Review
```

---

# 44. LICENSE COMPATIBILITY MATRIX

| License / Category | Default JAS Status | Notes |
|---|---|---|
| MIT | APPROVED | Preserve notices |
| BSD-2-Clause | APPROVED | Preserve notices |
| BSD-3-Clause | APPROVED | Preserve notices |
| Apache-2.0 | APPROVED | Preserve notices / applicable NOTICE |
| ISC | APPROVED | Preserve license |
| MPL-2.0 | CONDITIONAL | File-level obligations |
| LGPL | CONDITIONAL | Integration/distribution review |
| GPL | RESTRICTED | Legal review required |
| AGPL | RESTRICTED | Network/distribution implications |
| SSPL | RESTRICTED | Commercial/distribution review |
| Source Available | CONDITIONAL | Exact terms required |
| Proprietary | CONDITIONAL | Contract required |
| Commercial API | CONDITIONAL | Provider terms required |
| Non-commercial | NOT APPROVED FOR COMMERCIAL RELEASE | Research only unless terms change |
| No identifiable license | REJECTED | Cannot approve |
| Unknown model license | REJECTED | Cannot approve |
| Custom AI license | CONDITIONAL | Model-specific review |
| Dataset with unclear rights | REJECTED | Provenance required |

---

# 45. APPROVED SOFTWARE BASELINE

Current primary components include:

```text
FastAPI
React
Playwright
Qdrant
uv
pytest
OpenTelemetry
```

Their exact versions and exact licensing state will be captured in Version Lock.

For example, FastAPI is MIT, Qdrant is Apache-2.0, Playwright is Apache-2.0, and uv offers Apache-2.0 or MIT. citeturn0search3turn0search8turn0search15turn1search0

---

# 46. REDIS SPECIAL CASE

Redis requires special attention.

Older Redis releases used BSD-3-Clause licensing, while Redis 8.x uses a tri-license model involving:

```text
RSALv2
SSPLv1
AGPLv3
```

at the project's option structure. citeturn1search1turn1search10

Therefore the JARVIS Redis decision must be:

```text
Exact Redis Version
+
Exact License
+
Deployment Model
```

rather than simply:

```text
Redis = BSD
```

---

# 47. REDIS COMPLIANCE RULE

If the selected Redis version is subject to:

```text
RSALv2
SSPLv1
AGPLv3
```

the release must pass explicit compliance review before commercial distribution.

---

# 48. REDIS CLIENT VS REDIS SERVER

These are separate licensing objects.

For example:

```text
redis-py
```

is MIT licensed, while the Redis server has its own licensing structure. citeturn1search2turn1search1

Therefore:

```text
Client License
≠
Server License
```

---

# 49. DOCKER / CONTAINER LICENSES

Containerized deployment does not eliminate licensing obligations.

A container may contain:

```text
Base OS
System Libraries
Runtime
Application Dependencies
Tools
Certificates
Fonts
```

each with separate licenses.

---

# 50. CONTAINER IMAGE COMPLIANCE

Every production image should be considered a software distribution artifact.

Its dependencies should therefore be auditable.

---

# 51. DOCKER COMPONENT DISTINCTION

The Docker tooling itself and the software contained inside a Docker image are different compliance surfaces.

Docker's documentation repository is Apache-2.0 licensed, while container images may contain many separately licensed components. citeturn1search3

---

# 52. BASE IMAGE POLICY

Production base images must have:

```text
Known Publisher
Known Version
Known Digest
Known License State
Security Status
```

---

# 53. CONTAINER DIGEST

Where practical, production images should be pinned by immutable digest rather than only:

```text
latest
```

---

# 54. `latest` POLICY

Production compliance should prohibit uncontrolled:

```text
image: latest
```

references.

---

# 55. MODEL COMPLIANCE

Models require a dedicated compliance process.

---

# 56. MODEL COMPLIANCE OBJECT

For every approved model:

```text
Model Name
Provider
Version
Revision
Weights Source
License
Terms
Usage Restrictions
Commercial Restrictions
Distribution Rights
Derivative Rights
Output Terms
Training Restrictions
Attribution
Notice Requirements
Acceptable Use Policy
```

should be recorded.

---

# 57. MODEL LICENSE ≠ CODE LICENSE

A repository may contain:

```text
Code → Apache-2.0
Weights → Custom License
```

This is legally different from:

```text
Code → Apache-2.0
Weights → Apache-2.0
```

---

# 58. MODEL WEIGHTS

Model weights are treated as a separate compliance object.

---

# 59. MODEL DERIVATIVES

If a model license defines derivative models, JARVIS must comply with those conditions.

---

# 60. DISTILLATION

Distillation can create additional licensing questions.

If a model's terms define derivatives broadly, the use of that model for:

```text
Distillation
Synthetic Data Generation
Teacher-Student Training
Fine-tuning
```

must be evaluated.

---

# 61. FINE-TUNING

Fine-tuning does not automatically produce an unrestricted model.

The original model terms remain relevant.

---

# 62. MODEL MERGING

Model merging requires review of the terms governing each participating model.

---

# 63. MODEL QUANTIZATION

Quantized versions should be checked against:

```text
Original Model License
Distribution Terms
Derivative Terms
```

---

# 64. MODEL DISTRIBUTION

A model that can be legally used locally may not necessarily be legally redistributable.

---

# 65. MODEL HOSTING

Hosting a model as a service may trigger terms that differ from local use.

---

# 66. HOSTED SERVICE DEFINITION

JARVIS must distinguish:

```text
Local Model
Self-hosted Model
Private Cloud Model
Public API
Hosted JARVIS
```

for compliance purposes.

---

# 67. COMMERCIAL MODEL RESTRICTIONS

A model may impose:

```text
Revenue thresholds
Company-size thresholds
Usage restrictions
Field-of-use restrictions
Attribution
Acceptable-use restrictions
Commercial license requirements
```

---

# 68. MISTRAL EXAMPLE

Mistral states that most of its open models are released under Apache-2.0, while certain models use modified MIT terms with additional commercial conditions for companies above a specified monthly revenue threshold. citeturn0search0

Therefore:

```text
Mistral Model
```

cannot be treated as one universal license category.

The exact model must be checked.

---

# 69. GEMMA EXAMPLE

Google's Gemma models are governed by Gemma Terms of Use rather than simply being treated as generic Apache-2.0 software.

The current Gemma terms include distribution, notice, modification, use restrictions, and other conditions. citeturn0search1

Therefore:

```text
Gemma
→ Model-specific compliance
```

is mandatory.

---

# 70. CLOUD MODEL PROVIDERS

Cloud model APIs must be governed by:

```text
Provider Terms
API Terms
Commercial Agreement
Privacy Terms
Data Processing Terms
Usage Policy
```

where applicable.

---

# 71. API ≠ MODEL WEIGHTS

Using:

```text
Provider API
```

does not necessarily grant:

```text
Model Weights
```

or:

```text
Model Redistribution Rights
```

---

# 72. PROVIDER LOCK-IN

JARVIS must avoid making compliance dependent on a single provider.

The model abstraction layer should allow:

```text
Provider A
Provider B
Local Model
Provider C
```

where technically appropriate.

---

# 73. OUTPUT OWNERSHIP

Output rights must be determined from the specific provider's current terms.

For example, Anthropic has published commercial terms that address customer ownership of outputs and related legal protections, but the applicable current contractual terms must always be checked for the actual service being used. citeturn1search9

---

# 74. OUTPUT LIABILITY

Even where a provider assigns rights in outputs, JARVIS remains responsible for how outputs are used.

---

# 75. USER CONTENT

JARVIS must define who owns:

```text
User Input
User Files
User Prompts
User Memories
Generated Artifacts
```

according to the project's own terms and applicable law.

---

# 76. TRAINING ON USER DATA

JARVIS must not assume that user data may be used for model training.

The system should require an explicit policy decision.

---

# 77. DEFAULT USER-DATA PRINCIPLE

Unless explicitly authorized:

```text
User Data
→ Not used for model training
```

---

# 78. MEMORY COMPLIANCE

JARVIS memory is potentially sensitive user data.

Memory retention must therefore include:

```text
Purpose
Retention
Deletion
Access
Export
Correction
Security
Provenance
```

---

# 79. MEMORY DELETION

The user should be able to delete stored memory where the architecture and applicable law require it.

---

# 80. MEMORY PROVENANCE

Memory entries should ideally retain:

```text
Source
Timestamp
Origin
Confidence
Creation Mechanism
```

where appropriate.

---

# 81. DATA MINIMIZATION

JARVIS should not store data simply because it can.

The default principle is:

```text
Collect only what is necessary.
Retain only what is necessary.
```

---

# 82. PERSONAL DATA

The project may process personal data through:

```text
Voice
Camera
Browser
Filesystem
Email
Calendar
Contacts
Messages
Documents
```

Therefore privacy compliance is connected to this license/compliance document but should also be governed by the security architecture.

---

# 83. GDPR CONSIDERATION

If JARVIS processes personal data in the European Economic Area or serves users whose data is protected under applicable privacy law, GDPR and other applicable data-protection requirements may become relevant.

This document does not constitute a GDPR legal assessment.

---

# 84. DATA PROCESSING ROLES

Depending on deployment, JARVIS may involve:

```text
Controller
Processor
Subprocessor
Service Provider
User-controlled local processing
```

The exact role must be determined per deployment.

---

# 85. CLOUD DATA TRANSFER

Cloud AI services may cause user data to leave the local machine.

The architecture must make this boundary visible.

---

# 86. DATA FLOW

Conceptually:

```text
User
 ↓
JARVIS
 ↓
Policy
 ↓
Data Classification
 ↓
Local Model OR Cloud Provider
```

---

# 87. CLOUD PROVIDER APPROVAL

A provider receiving user data must be:

```text
Approved
Contractually acceptable
Privacy-reviewed
Security-reviewed
```

where applicable.

---

# 88. MCP COMPLIANCE

MCP servers are separate compliance objects.

---

# 89. MCP SERVER LICENSE

For every approved MCP server:

```text
Server License
Dependencies
Repository
Version
Source
Provider
Capabilities
Commercial Restrictions
```

must be recorded.

---

# 90. MCP SERVER ≠ MCP PROTOCOL

The protocol and the server implementation have separate legal identities.

---

# 91. MCP SERVER DISTRIBUTION

If JARVIS redistributes an MCP server:

```text
Server License
+
Dependencies
+
Notices
```

must be checked.

---

# 92. REMOTE MCP

Using a remote MCP service may create:

```text
API Terms
Privacy Terms
Commercial Terms
Data Transfer
Security
```

obligations.

---

# 93. PLUGIN COMPLIANCE

Plugins must have their own metadata:

```text
Plugin ID
Version
Author
License
Dependencies
Capabilities
Permissions
Data Access
Network Access
Distribution Rights
```

---

# 94. THIRD-PARTY PLUGINS

Third-party plugins are not trusted merely because they implement the JARVIS plugin interface.

They must pass:

```text
Security
License
Capability
Dependency
```

review.

---

# 95. PLUGIN LICENSE INHERITANCE

A plugin's license does not automatically become JARVIS's license.

The relationship must be evaluated.

---

# 96. PLUGIN DISTRIBUTION

If JARVIS distributes third-party plugins, each plugin's redistribution rights must be verified.

---

# 97. FRONTEND ASSET COMPLIANCE

Frontend assets include:

```text
Fonts
Icons
Images
SVGs
Animations
UI Components
Templates
Sounds
```

Each may have separate licensing.

---

# 98. FONT LICENSES

Fonts must be tracked separately from software dependencies.

---

# 99. ICON LICENSES

Icon libraries often have:

```text
MIT
Apache
CC
Custom
Commercial
```

terms.

The exact license must be recorded.

---

# 100. IMAGE LICENSES

Images must not be copied into the project merely because they are publicly visible online.

---

# 101. AUDIO ASSETS

Voice and audio assets may have:

```text
Copyright
Performance Rights
Database Rights
Commercial Restrictions
Model-specific rights
```

and require review.

---

# 102. VOICE MODELS

Voice models must be evaluated for:

```text
Model License
Voice License
Speaker Rights
Commercial Rights
Training Data Terms
Distribution Rights
```

---

# 103. SYNTHETIC VOICE

A generated voice may still raise:

```text
Personality Rights
Publicity Rights
Trademark Issues
Impersonation Risks
```

depending on jurisdiction and use.

---

# 104. COMPUTER VISION MODELS

Vision models follow the same compliance framework as language models.

---

# 105. OCR ENGINES

OCR components may have independent licenses.

---

# 106. BROWSER COMPONENTS

Browser automation libraries and browser binaries are separate compliance objects.

---

# 107. PLAYWRIGHT COMPLIANCE

Playwright itself is Apache-2.0 licensed. citeturn0search15

However, the browsers it installs and the underlying browser distributions may have separate licensing considerations.

Therefore:

```text
Playwright License
≠
Browser Distribution License
```

---

# 108. CHROMIUM

If Chromium-based components are distributed, their licensing and third-party notices must be reviewed separately.

---

# 109. FIREFOX

Firefox binaries and related components have their own licensing and trademark considerations.

---

# 110. WEBKIT

WebKit-related components likewise have separate upstream licensing.

---

# 111. BROWSER DISTRIBUTION RULE

JARVIS must not assume:

```text
Browser automation library license
```

covers:

```text
All browser binaries
```

---

# 112. SOURCE CODE DISTRIBUTION

If JARVIS distributes source code containing third-party components, applicable license notices must be included.

---

# 113. BINARY DISTRIBUTION

Binary distributions must include the required notices and license information.

---

# 114. CONTAINER DISTRIBUTION

Container images count as distribution artifacts for compliance purposes.

---

# 115. HOSTED SERVICE

A hosted JARVIS deployment may trigger obligations different from a downloadable application.

Each license must be evaluated under the actual deployment model.

---

# 116. NETWORK COPyleft

Licenses with network-use clauses require special attention.

AGPL is the principal example.

---

# 117. GPL / AGPL REVIEW RULE

Any direct GPL or AGPL production dependency requires explicit compliance review before inclusion.

---

# 118. SSPL REVIEW RULE

Any SSPL component requires explicit commercial/legal review.

---

# 119. SOURCE-AVAILABLE REVIEW RULE

Any source-available component requires exact-term review.

---

# 120. COMMERCIAL SOFTWARE REVIEW

Commercial dependencies require:

```text
License Key
Subscription
Seat Count
Deployment Count
Redistribution Rights
Cloud Rights
Enterprise Rights
```

to be recorded where applicable.

---

# 121. SUBSCRIPTION DEPENDENCIES

If a production component stops functioning when a subscription ends, that dependency becomes part of operational continuity planning.

---

# 122. API COST ≠ LICENSE

A paid API does not necessarily mean:

```text
Commercial license
```

and a free API does not necessarily mean:

```text
Unrestricted commercial rights
```

---

# 123. THIRD-PARTY SERVICES

Every external service should have:

```text
Provider
Service
Purpose
Data Sent
Data Retained
Terms
Pricing
License / Contract
Region
Fallback
```

recorded.

---

# 124. TELEMETRY SERVICES

Observability services may process:

```text
Logs
IPs
Identifiers
Errors
Prompts
Tool Names
URLs
Metadata
```

and therefore require privacy/security review.

---

# 125. ANALYTICS

Analytics components must be evaluated for:

```text
Data Collection
Tracking
Cookies
User Consent
Retention
Third-party Transfer
```

where applicable.

---

# 126. ERROR REPORTING

Error-reporting services must not receive secrets or unnecessary personal data.

---

# 127. LOGGING POLICY

Logs must avoid:

```text
API Keys
Passwords
Session Tokens
Private Keys
Sensitive User Data
Raw Authentication Headers
```

unless explicitly justified and protected.

---

# 128. COPYRIGHT NOTICE POLICY

JARVIS must preserve required copyright notices.

---

# 129. LICENSE NOTICE POLICY

JARVIS must include required license texts for redistributed components.

---

# 130. NOTICE FILE

Where applicable, a release should contain:

```text
THIRD_PARTY_NOTICES.md
```

or an equivalent generated artifact.

---

# 131. THIRD-PARTY NOTICES STRUCTURE

Conceptually:

```text
third_party/
├── licenses/
├── notices/
├── attributions/
└── sbom/
```

---

# 132. NOTICE GENERATION

Third-party notices should be generated from the locked dependency graph rather than maintained entirely by hand.

---

# 133. MANUAL OVERRIDES

Manual compliance overrides must be documented.

---

# 134. COMPLIANCE EXCEPTIONS

Exceptions require:

```text
Component
Version
Issue
Reason
Risk
Approval
Expiry
Mitigation
```

---

# 135. NO PERMANENT EXCEPTIONS

Exceptions should have an expiration or review date where practical.

---

# 136. LICENSE CHANGE MONITORING

The project should monitor upstream license changes.

---

# 137. LICENSE CHANGE EVENT

If an upstream project changes:

```text
License
Terms
Commercial Restrictions
Distribution Terms
```

the affected dependency must be re-evaluated.

---

# 138. VERSION CHANGE

A dependency upgrade should trigger license revalidation.

---

# 139. MODEL UPDATE

A model update should trigger model-license revalidation.

---

# 140. API TERMS CHANGE

A provider terms-of-service change should trigger provider compliance review.

---

# 141. COMPLIANCE FAILURE

A compliance failure should produce:

```text
COMPLIANCE FAILED
```

and block release where the issue is material.

---

# 142. COMPLIANCE WARNING

Non-critical issues may produce:

```text
COMPLIANCE WARNING
```

but must be tracked.

---

# 143. COMPLIANCE STATUS

Every release should have one of:

```text
COMPLIANT
COMPLIANT WITH EXCEPTIONS
WARNING
FAILED
UNKNOWN
```

---

# 144. RELEASE GATE

Production release requires:

```text
COMPLIANCE = COMPLIANT
```

or:

```text
COMPLIANT WITH EXCEPTIONS
```

with explicitly approved exceptions.

---

# 145. UNKNOWN IS NOT APPROVED

```text
UNKNOWN
```

must not silently become:

```text
APPROVED
```

---

# 146. COMPLIANCE CHECK PIPELINE

```text
Dependency Graph
      ↓
License Detection
      ↓
SPDX Normalization
      ↓
License Compatibility
      ↓
Model Terms Check
      ↓
MCP Check
      ↓
Container Check
      ↓
Notice Generation
      ↓
SBOM Generation
      ↓
Compliance Report
      ↓
Release Gate
```

---

# 147. SPDX

SPDX identifiers should be preferred where possible.

Examples:

```text
MIT
Apache-2.0
BSD-2-Clause
BSD-3-Clause
MPL-2.0
GPL-3.0-only
AGPL-3.0-only
```

---

# 148. LICENSE NORMALIZATION

Equivalent textual licenses should be normalized to recognized SPDX identifiers where possible.

---

# 149. UNKNOWN LICENSE

If normalization cannot establish the license:

```text
UNKNOWN
```

must be recorded.

---

# 150. CUSTOM LICENSE

Custom licenses must preserve the exact source terms.

---

# 151. MODEL LICENSE NORMALIZATION

Model licenses must not be forced into an SPDX category when their terms are materially different.

---

# 152. CUSTOM MODEL LICENSE

Use:

```text
CUSTOM-MODEL-LICENSE
```

or equivalent internal classification while preserving the exact upstream terms.

---

# 153. MODEL COMPLIANCE RECORD

Every approved model should have:

```text
MODEL_ID
MODEL_VERSION
MODEL_REVISION
PROVIDER
LICENSE
TERMS_URL
COMMERCIAL_STATUS
DISTRIBUTION_STATUS
DERIVATIVE_STATUS
NOTICE_REQUIREMENT
RESTRICTIONS
```

---

# 154. DATASET COMPLIANCE RECORD

Every project-owned or redistributed dataset should have:

```text
DATASET_ID
VERSION
SOURCE
LICENSE
PROVENANCE
COMMERCIAL_STATUS
REDISTRIBUTION_STATUS
PERSONAL_DATA_STATUS
```

---

# 155. TRAINING DATA

If JARVIS eventually trains or fine-tunes models, the training corpus must undergo independent data-rights review.

---

# 156. SCRAPED DATA

Data scraped from websites must not automatically be treated as freely reusable.

---

# 157. WEB CONTENT

Browser access does not imply redistribution rights.

---

# 158. WEB SCRAPING

The system must distinguish:

```text
Access
Storage
Transformation
Indexing
Redistribution
Training
```

as separate legal/compliance questions.

---

# 159. COPYRIGHTED DOCUMENTS

JARVIS may process user-provided documents where authorized.

That does not automatically grant JARVIS the right to redistribute those documents.

---

# 160. USER-PROVIDED DATA

User-provided data should be treated according to:

```text
User Authorization
Applicable Law
Service Terms
Retention Policy
```

---

# 161. OPEN-SOURCE CONTRIBUTIONS

Contributors must understand the contribution licensing terms.

---

# 162. CONTRIBUTOR LICENSE POLICY

Before accepting external contributions at scale, JARVIS should define whether contributions are governed by:

```text
DCO
CLA
Copyright Assignment
Project License
```

---

# 163. DCO / CLA

The project may choose:

```text
Developer Certificate of Origin
```

or:

```text
Contributor License Agreement
```

depending on governance requirements.

---

# 164. CONTRIBUTOR COPYRIGHT

The project must not assume that a contributor has authority to submit third-party copyrighted code.

---

# 165. THIRD-PARTY CODE CONTRIBUTION

Contributors must not copy code into JARVIS without verifying compatible licensing.

---

# 166. COPY-PASTE POLICY

Code copied from:

```text
Stack Overflow
GitHub
Blogs
Documentation
Forums
AI-generated output
```

must be treated according to its source and applicable rights.

---

# 167. AI-GENERATED CODE

AI-generated code does not automatically become:

```text
License-free
Copyright-free
Patent-free
```

The project must review significant generated code like other code.

---

# 168. AI-GENERATED CONTENT

Generated documentation, images, audio, and other artifacts may have separate terms depending on the generation system used.

---

# 169. TRADEMARK POLICY

JARVIS must not imply endorsement by:

```text
OpenAI
Anthropic
Google
Meta
Mistral
Microsoft
Docker
Qdrant
```

or any other third party unless explicitly authorized.

---

# 170. BRAND USAGE

Third-party logos and trademarks must be used only in ways permitted by the relevant trademark policies.

---

# 171. PROJECT NAME

The project name:

```text
JARVIS
```

may itself raise trademark considerations depending on the intended commercial use.

This should be legally reviewed before large-scale commercialization.

---

# 172. MODEL BRANDING

A model provider's name must not be presented as if the provider officially endorses JARVIS.

---

# 173. PLUGIN BRANDING

Third-party plugins must not be presented as official JARVIS components unless they are officially maintained by the project.

---

# 174. MCP BRANDING

MCP servers must not be presented as official integrations merely because they are technically compatible.

---

# 175. LICENSE COMPATIBILITY PRINCIPLE

The question is:

> Can the exact component, in the exact version, in the exact integration model, legally coexist with the intended JARVIS distribution model?

---

# 176. DISTRIBUTION MODELS

JARVIS must consider at least:

```text
Local Personal Use
Research
Internal Enterprise Use
Source Distribution
Binary Distribution
Container Distribution
Hosted SaaS
Commercial SaaS
Plugin Marketplace
Model Redistribution
```

---

# 177. PERSONAL USE

Personal use may have fewer commercial obligations but does not eliminate copyright or license obligations.

---

# 178. RESEARCH USE

Research status does not automatically grant rights unavailable under the applicable license.

---

# 179. INTERNAL ENTERPRISE

Internal use may differ from public distribution, but contractual and license terms still apply.

---

# 180. SOURCE DISTRIBUTION

Source distribution triggers the applicable redistribution obligations.

---

# 181. BINARY DISTRIBUTION

Binary distribution requires appropriate notices and license compliance.

---

# 182. CONTAINER DISTRIBUTION

Container distribution must account for all material components inside the image.

---

# 183. SAAS DISTRIBUTION

Hosted deployment requires analysis of:

```text
Network Copyleft
Provider Terms
User Data
Third-party Services
Model Terms
```

---

# 184. COMMERCIAL SAAS

Commercial SaaS adds:

```text
Commercial Terms
Privacy
Security
Customer Contracts
Data Processing
Subprocessors
```

requirements.

---

# 185. PLUGIN MARKETPLACE

If JARVIS eventually distributes plugins:

```text
Plugin License
Developer Terms
Malware Review
Copyright Review
Trademark Review
Privacy Review
```

must be implemented.

---

# 186. MODEL MARKETPLACE

If JARVIS distributes models:

```text
Model License
Weights
Tokenizer
Configuration
Adapters
Quantization
Model Card
Notice
```

must be included in compliance review.

---

# 187. MODEL ADAPTERS

LoRA/adapter weights may have separate licensing considerations.

---

# 188. EMBEDDING MODELS

Embedding models must follow the same model-license policy.

---

# 189. RERANKING MODELS

Reranking models require independent license verification.

---

# 190. SPEECH MODELS

STT/TTS models require independent license verification.

---

# 191. VISION MODELS

Vision models require independent license verification.

---

# 192. SAFETY MODELS

Safety and moderation models also require independent license verification.

---

# 193. OCR MODELS

OCR models and OCR data must be independently audited.

---

# 194. LICENSE MATRIX

The Approved Software Matrix should include:

```text
Component
Version
License
SPDX
Source
Commercial Status
Distribution Status
Notice Required
Compliance Status
```

---

# 195. REJECTED LICENSE CATEGORIES

The following are rejected by default until explicitly reviewed:

```text
Unknown
No License
Non-commercial
Research-only
Field-of-use restricted
Competitive-use restricted
Unclear source-available
Unclear model terms
```

---

# 196. COMMERCIAL RESTRICTION

A component with commercial restrictions cannot be placed into the commercial baseline without explicit approval.

---

# 197. REVENUE THRESHOLDS

If a model license contains revenue thresholds, the project must track them.

Example:

```text
Revenue Threshold
↓
Commercial License Required
```

---

# 198. ORGANIZATION SIZE

Some licenses or commercial agreements may depend on:

```text
Company Size
Revenue
Number of Users
Number of Developers
Deployment Scale
```

These conditions must be recorded.

---

# 199. USAGE LIMITS

API or software licenses may impose:

```text
Requests
Tokens
Users
Devices
Servers
Regions
```

limits.

---

# 200. LICENSE EXPIRATION

Some licenses or commercial agreements may expire or require renewal.

Such dependencies must be tracked.

---

# 201. CONTRACTUAL DEPENDENCIES

If JARVIS depends on a commercial contract, the contract must be recorded as part of the deployment profile.

---

# 202. JURISDICTION

The applicable law may depend on:

```text
Provider
Customer
Deployment Region
Contract
```

The project should not assume that one jurisdiction governs every component.

---

# 203. EXPORT CONTROL

Some software, models, cryptographic technology, or services may be subject to export-control requirements.

This requires separate legal review where applicable.

---

# 204. CRYPTOGRAPHY

Cryptographic libraries may have:

```text
Software License
Export Considerations
Patent Considerations
```

separately.

---

# 205. SECURITY SOFTWARE

Security tools and scanners may themselves have licenses that must be tracked.

---

# 206. DEVELOPMENT-ONLY DEPENDENCIES

Development dependencies can still create licensing obligations if distributed in the development environment or bundled into release artifacts.

---

# 207. TEST DEPENDENCIES

Test dependencies should be classified separately.

---

# 208. BUILD DEPENDENCIES

Build tools must be included in compliance analysis when redistributed or bundled.

---

# 209. RUNTIME DEPENDENCIES

Runtime dependencies have the highest distribution priority.

---

# 210. OPTIONAL DEPENDENCIES

Optional dependencies must still be compliant if an official JARVIS distribution enables them.

---

# 211. PLUGIN DEPENDENCIES

Plugin dependencies must be audited separately from core dependencies.

---

# 212. MCP DEPENDENCIES

MCP server dependencies must be audited separately.

---

# 213. CONTAINER DEPENDENCIES

Container base images and packages must be included in SBOM generation.

---

# 214. OS PACKAGES

Linux distribution packages can carry:

```text
GPL
LGPL
BSD
MIT
Apache
```

and many other licenses.

They must not be ignored.

---

# 215. PYTHON DEPENDENCIES

Python packages must be analyzed using package metadata and upstream license information.

---

# 216. NODE DEPENDENCIES

Node packages must be analyzed individually.

A package-lock file does not itself establish license compliance.

---

# 217. NPM LICENSE FIELD

The npm `license` field is useful metadata but should not be treated as an unquestionable legal determination.

---

# 218. PYPI LICENSE METADATA

PyPI metadata is useful but should be verified against the upstream project.

---

# 219. GITHUB LICENSE DETECTION

GitHub's detected license is useful but must not replace review of the actual license terms.

---

# 220. LICENSE PROVENANCE

For important dependencies, compliance records should retain:

```text
License Source URL
Repository
Version
Commit / Tag
License File Hash where appropriate
```

---

# 221. HASHING LICENSE ARTIFACTS

For high-assurance releases, the exact license/notice artifacts may be hashed.

---

# 222. COMPLIANCE AUDIT TRAIL

Every release should be capable of answering:

```text
Which dependencies were shipped?
Which versions?
Which licenses?
Which notices?
Which models?
Which terms?
Which exceptions?
```

---

# 223. RELEASE COMPLIANCE REPORT

A release should generate:

```text
COMPLIANCE_REPORT.md
SBOM
THIRD_PARTY_NOTICES.md
MODEL_NOTICES.md
LICENSE_SUMMARY.md
```

where applicable.

---

# 224. LICENSE SUMMARY

The summary should include:

```text
Approved
Conditional
Restricted
Unknown
```

components.

---

# 225. UNKNOWN COMPONENT

Unknown components block production release unless an explicit exception is approved.

---

# 226. COMPLIANCE AUTOMATION

The compliance system should automatically:

```text
Enumerate dependencies
Detect licenses
Normalize licenses
Detect conflicts
Generate SBOM
Generate notices
Check rejected packages
Check version changes
```

---

# 227. MANUAL REVIEW

Automation does not eliminate manual review for:

```text
Custom licenses
Model licenses
Commercial terms
Source-available licenses
AGPL/GPL
Provider contracts
Trademark issues
Dataset rights
```

---

# 228. LICENSE SCANNERS

Potential tools may include:

```text
ScanCode Toolkit
FOSSology
ORT
Syft
Grype
Trivy
CycloneDX tools
SPDX tools
```

The exact tools should be finalized in the testing/build/DevOps stack.

---

# 229. SCANNER OUTPUT

Scanner output must be treated as evidence, not absolute legal truth.

---

# 230. FALSE POSITIVES

License scanners can incorrectly classify dependencies.

A human review path must exist.

---

# 231. FALSE NEGATIVES

A scanner can also miss obligations.

Therefore:

```text
Scanner
+
Manual Review
```

is preferred for important releases.

---

# 232. COMPLIANCE SEVERITY

| Severity | Meaning |
|---|---|
| CRITICAL | Release must stop |
| HIGH | Release normally blocked |
| MEDIUM | Review required |
| LOW | Documentation issue |
| INFO | Informational |

---

# 233. CRITICAL LICENSE VIOLATIONS

Examples:

```text
Unknown license for redistributed dependency
Known incompatible license
Unauthorized model redistribution
Commercial restriction violation
Missing mandatory source distribution
```

---

# 234. HIGH VIOLATIONS

Examples:

```text
Missing required notice
Incorrect version license
Unreviewed model terms
Unapproved MCP redistribution
```

---

# 235. MEDIUM VIOLATIONS

Examples:

```text
Incomplete metadata
Missing provenance
Unclear optional dependency
```

---

# 236. LOW VIOLATIONS

Examples:

```text
Formatting
Non-critical metadata
Documentation inconsistency
```

---

# 237. COMPLIANCE EXCEPTION TEMPLATE

```text
Exception ID:
Component:
Version:
License:
Issue:
Risk:
Reason:
Mitigation:
Approver:
Created:
Expires:
Status:
```

---

# 238. EXCEPTION EXPIRATION

Expired exceptions must automatically return to:

```text
REVIEW REQUIRED
```

---

# 239. NO SILENT EXCEPTIONS

Exceptions must not exist only in:

```text
Slack
Discord
Chat
Email
Developer Memory
```

They must be recorded in the project compliance system.

---

# 240. LICENSE CHANGE RESPONSE

If a dependency changes license:

```text
Detect
 ↓
Notify
 ↓
Evaluate
 ↓
Freeze Upgrade
 ↓
Decide
```

---

# 241. LICENSE CHANGE OPTIONS

Possible decisions:

```text
Continue
Pin Older Version
Replace Dependency
Obtain Commercial License
Remove Dependency
```

---

# 242. PINNING

Pinning an older version is acceptable only if:

```text
Security
Support
Compatibility
License
```

remain acceptable.

---

# 243. ABANDONED SOFTWARE

An abandoned dependency is not automatically legally problematic.

However it creates:

```text
Security
Maintenance
Support
```

risks.

---

# 244. LICENSE VS MAINTENANCE

A permissive license does not compensate for unacceptable security or maintenance risk.

---

# 245. SECURITY VS LICENSE

Both are independent gates.

A dependency can be:

```text
License-compliant
```

but:

```text
Security-unacceptable
```

and therefore rejected.

---

# 246. LICENSE VS SECURITY

Likewise:

```text
Secure
```

does not mean:

```text
License-compatible
```

---

# 247. COMMERCIALIZATION GATE

Before JARVIS becomes a commercial product:

```text
Full Dependency Audit
+
Model Audit
+
MCP Audit
+
Plugin Audit
+
Trademark Review
+
Privacy Review
+
Contract Review
```

should be performed.

---

# 248. PRE-RELEASE CHECKLIST

```text
[ ] All direct dependencies approved
[ ] All versions locked
[ ] All licenses identified
[ ] All transitive dependencies scanned
[ ] SBOM generated
[ ] Third-party notices generated
[ ] Model licenses verified
[ ] Model terms verified
[ ] MCP licenses verified
[ ] Plugin licenses verified
[ ] Container licenses verified
[ ] Fonts verified
[ ] Images verified
[ ] Audio verified
[ ] Dataset provenance verified
[ ] Commercial restrictions checked
[ ] Network-copyleft checked
[ ] Unknown licenses resolved
[ ] Exceptions reviewed
[ ] Trademark review completed
[ ] Privacy review completed where required
```

---

# 249. RELEASE ARTIFACTS

Every releasable version should contain or provide access to:

```text
LICENSE
THIRD_PARTY_NOTICES.md
SBOM
MODEL_NOTICES.md
COMPLIANCE_REPORT.md
```

where applicable.

---

# 250. JARVIS LICENSE

The final JARVIS project license has not yet been permanently fixed by this document.

The project must determine whether the final distribution will be:

```text
Open Source
Source Available
Proprietary
Dual Licensed
Commercial
Hybrid
```

---

# 251. JARVIS LICENSE DECISION

This decision must occur before public distribution of a production release.

---

# 252. JARVIS CORE LICENSE

If the core is open source, its license must be compatible with:

```text
Third-party dependencies
Plugin model
MCP model
Commercialization goals
```

---

# 253. JARVIS PLUGIN LICENSE

The plugin architecture should define whether plugins may be:

```text
Open Source
Proprietary
Commercial
Third-party
```

---

# 254. PLUGIN ABI/API LICENSE

The plugin interface itself may be separately licensed from the plugin implementations.

---

# 255. MCP INTEGRATION LICENSE

The JARVIS MCP client/integration layer should be separated from individual MCP server licenses.

---

# 256. MODEL PROVIDER TERMS

JARVIS must not imply that using a model provider makes JARVIS a provider product.

---

# 257. CLOUD PROVIDER TERMS

Provider-specific terms should be isolated behind provider adapters.

---

# 258. PROVIDER ADAPTER

Conceptually:

```text
JARVIS
 ↓
Model Provider Interface
 ├── Provider A
 ├── Provider B
 ├── Provider C
 └── Local Runtime
```

This reduces both:

```text
Technical Lock-in
```

and:

```text
Compliance Coupling
```

---

# 259. MODEL FALLBACK

A fallback model should not be introduced without its own compliance review.

---

# 260. MODEL ROUTING

Model routing must account for:

```text
Capability
Cost
Latency
Privacy
License
Availability
```

---

# 261. PRIVACY-AWARE ROUTING

Sensitive data may require:

```text
Local Model
```

rather than:

```text
Cloud Model
```

depending on the deployment policy.

---

# 262. LICENSE-AWARE ROUTING

A model may be technically available but unavailable for a specific commercial deployment because of its terms.

---

# 263. COMMERCIAL MODEL MATRIX

The Approved Models document should classify models:

```text
PERSONAL
RESEARCH
COMMERCIAL
RESTRICTED
```

where applicable.

---

# 264. DISTRIBUTION MATRIX

Every model should additionally be classified:

```text
LOCAL USE
SELF-HOST
REDISTRIBUTION
HOSTED SERVICE
DERIVATIVE
```

---

# 265. MODEL COMPLIANCE EXAMPLE

```text
Model:
Example Model

License:
Custom

Local Use:
YES

Commercial Use:
CONDITIONAL

Redistribution:
NO

Hosted Service:
YES

Derivative:
CONDITIONAL

Status:
CONDITIONALLY APPROVED
```

---

# 266. NO MODEL GUESSING

If a model license cannot be confidently established:

```text
DO NOT APPROVE
```

---

# 267. DATASET GUESSING PROHIBITED

If training data provenance is materially unclear:

```text
DO NOT APPROVE FOR NEW TRAINING
```

until reviewed.

---

# 268. MODEL CARD REQUIREMENT

Approved models should have an accessible model card or equivalent documentation.

---

# 269. MODEL CARD CONTENT

Prefer:

```text
Intended Use
Limitations
License
Training Information
Evaluation
Safety
Known Restrictions
```

---

# 270. NOTICE PRESERVATION

Model notices must be preserved where required.

---

# 271. MODEL DOWNLOAD CACHE

Downloaded model artifacts should retain:

```text
Model ID
Revision
Source
License
Terms Snapshot
Checksum
```

---

# 272. MODEL CHECKSUM

Production model artifacts should be integrity-checked.

---

# 273. MODEL VERSION LOCK

The Version Lock should record:

```text
Model
Revision
Digest / Hash
Source
License Classification
```

where practical.

---

# 274. THIRD-PARTY DATA

Third-party datasets should never be copied into the repository without a documented legal basis.

---

# 275. USER DATA EXPORT

User data export should preserve user ownership/rights and applicable privacy obligations.

---

# 276. BACKUP COMPLIANCE

Backups may contain licensed or personal data.

Therefore backup storage is also a compliance surface.

---

# 277. LOG RETENTION

Logs may contain licensed/user data and must follow retention policy.

---

# 278. CACHE RETENTION

Caches can also contain user data.

---

# 279. VECTOR DATABASE DATA

Qdrant collections may contain:

```text
Embeddings
Documents
Metadata
User Data
```

and are therefore not exempt from privacy/compliance rules.

---

# 280. DATABASE EXPORT

Database exports should preserve access controls and applicable data rights.

---

# 281. DELETION

Deletion should propagate to relevant:

```text
Primary DB
Vector DB
Cache
Files
Backups where applicable
Logs where applicable
```

according to the retention architecture.

---

# 282. COMPLIANCE AND OBSERVABILITY

Observability systems should not accidentally create a second unauthorized copy of user data.

---

# 283. PROMPT LOGGING

Raw prompts should not automatically be logged indefinitely.

---

# 284. MODEL OUTPUT LOGGING

Raw model outputs should be logged only when necessary.

---

# 285. TOOL EXECUTION LOGGING

Tool executions should record enough metadata for auditing without unnecessarily storing sensitive content.

---

# 286. BROWSER LOGGING

Browser telemetry must avoid storing:

```text
Passwords
Session Cookies
Authentication Tokens
Private URLs
Sensitive Page Content
```

unless explicitly required and protected.

---

# 287. VOICE DATA

Audio recordings require explicit retention and privacy rules.

---

# 288. CAMERA DATA

Camera data requires explicit privacy rules.

---

# 289. SCREEN DATA

Desktop screenshots and screen recordings may contain sensitive information.

---

# 290. COMPLIANCE BOUNDARY

The following are all considered compliance-sensitive:

```text
Code
Dependencies
Models
Datasets
User Data
Generated Artifacts
Containers
Plugins
MCP
Cloud Services
Assets
```

---

# 291. LICENSE AUDIT FREQUENCY

At minimum:

```text
Every release
Every dependency upgrade
Every model upgrade
Every major architecture change
```

---

# 292. CONTINUOUS MONITORING

Where tooling permits, upstream license changes should be detected continuously.

---

# 293. DEPENDENCY UPDATE POLICY

Dependency updates must not bypass:

```text
Security
License
Compatibility
Testing
```

review.

---

# 294. AUTOMATED BLOCKING

The CI system should be able to block:

```text
Rejected dependency
Unknown license
Known incompatible license
Unapproved model
Unapproved MCP
Unapproved plugin
```

---

# 295. COMPLIANCE CI

Conceptually:

```text
Pull Request
     ↓
Dependency Change
     ↓
License Scan
     ↓
Security Scan
     ↓
SBOM Diff
     ↓
Policy Check
     ↓
PASS / FAIL
```

---

# 296. SBOM DIFF

Every release should compare its SBOM against the previous release where practical.

---

# 297. LICENSE DIFF

The system should detect:

```text
New license
Removed license
Changed license
Changed dependency
Changed model
```

---

# 298. COMPLIANCE REGRESSION

A previously compliant release can become non-compliant after:

```text
Dependency Upgrade
Model Upgrade
License Change
Distribution Model Change
```

---

# 299. DISTRIBUTION-MODEL REGRESSION

A component can be acceptable for:

```text
Personal Use
```

but unacceptable for:

```text
Commercial Redistribution
```

---

# 300. DEPLOYMENT-PROFILE COMPLIANCE

Compliance should therefore be evaluated against the deployment profile.

---

# 301. DEPLOYMENT PROFILES

Recommended profiles:

```text
PROFILE-LOCAL
PROFILE-RESEARCH
PROFILE-INTERNAL
PROFILE-COMMERCIAL
PROFILE-SAAS
PROFILE-DISTRIBUTION
```

---

# 302. PROFILE-SPECIFIC APPROVAL

A component may be:

```text
Approved for LOCAL
```

but:

```text
Rejected for COMMERCIAL
```

---

# 303. PROFILE EXAMPLE

```text
Custom Model

LOCAL:
APPROVED

RESEARCH:
APPROVED

COMMERCIAL:
CONDITIONAL

REDISTRIBUTION:
REJECTED
```

---

# 304. COMPLIANCE PROFILE MATRIX

| Component Type | Local | Research | Commercial | Redistribution |
|---|---|---|---|---|
| MIT code | APPROVED | APPROVED | APPROVED | APPROVED |
| Apache-2.0 code | APPROVED | APPROVED | APPROVED | APPROVED |
| BSD code | APPROVED | APPROVED | APPROVED | APPROVED |
| MPL-2.0 | CONDITIONAL | APPROVED | CONDITIONAL | CONDITIONAL |
| GPL | CONDITIONAL | APPROVED | RESTRICTED | RESTRICTED |
| AGPL | CONDITIONAL | APPROVED | RESTRICTED | RESTRICTED |
| SSPL | CONDITIONAL | CONDITIONAL | RESTRICTED | RESTRICTED |
| Non-commercial model | APPROVED | APPROVED | REJECTED | REJECTED |
| Unknown license | REJECTED | REJECTED | REJECTED | REJECTED |
| Custom commercial API | CONDITIONAL | CONDITIONAL | CONDITIONAL | N/A |

---

# 305. IMPORTANT

The table above is an engineering screening policy, not a legal determination of every possible license combination.

Exact terms control.

---

# 306. COMPLIANCE OWNERSHIP

The project should assign responsibility for:

```text
Dependency Compliance
Model Compliance
Data Compliance
Security Compliance
Release Compliance
```

---

# 307. ENGINEERING RESPONSIBILITY

Engineers are responsible for:

```text
Not introducing unapproved dependencies
Not copying unlicensed code
Not redistributing restricted models
Not bypassing compliance tooling
```

---

# 308. RELEASE RESPONSIBILITY

Release engineering is responsible for:

```text
SBOM
Notices
Version Lock
Compliance Report
```

---

# 309. SECURITY RESPONSIBILITY

Security engineering is responsible for:

```text
Supply Chain
Secrets
Third-party Risk
MCP Risk
Plugin Risk
```

---

# 310. LEGAL RESPONSIBILITY

Legal review is required when:

```text
License ambiguity
Commercial restrictions
Copyleft integration
Model distribution
Trademark
Patent
Contract
Privacy
```

cannot be resolved through standard engineering policy.

---

# 311. ESCALATION

When uncertain:

```text
Developer
 ↓
Engineering Review
 ↓
Compliance Review
 ↓
Legal Review if required
```

---

# 312. NO ASSUMPTION RULE

When a developer is uncertain:

```text
Do not assume.
Do not ship.
Escalate.
```

---

# 313. DOCUMENTATION REQUIREMENT

Every important license decision must be documented.

---

# 314. DECISION RECORD

A license decision should include:

```text
Decision ID
Component
Version
License
Source
Use Case
Distribution Model
Risk
Decision
Reviewer
Date
```

---

# 315. COMPLIANCE RECORD RETENTION

Compliance records should be retained with release history.

---

# 316. HISTORICAL RELEASE RECONSTRUCTION

The project should be able to reconstruct the compliance state of:

```text
JARVIS v1.0
JARVIS v1.1
JARVIS v2.0
```

independently.

---

# 317. LICENSE CHANGE HISTORY

Changes should be version-controlled.

---

# 318. COMPLIANCE BASELINE

Each JARVIS release receives a:

```text
Compliance Baseline
```

---

# 319. COMPLIANCE BASELINE CONTENT

```text
Dependency Graph
SBOM
License Matrix
Model Matrix
MCP Matrix
Plugin Matrix
Notices
Exceptions
Terms Snapshot
```

---

# 320. FINAL RELEASE GATE

```text
JAS Compliance
+
Security
+
Testing
+
Version Lock
+
Manifest
+
SBOM
```

must pass before production release.

---

# 321. ARCHITECTURE COMPLIANCE

A technology can fail compliance even when technically functional.

---

# 322. EXAMPLE

```text
Package works.
Tests pass.
Performance is excellent.
License is incompatible.
```

Result:

```text
RELEASE BLOCKED
```

---

# 323. OPPOSITE EXAMPLE

```text
License is compatible.
Security is unacceptable.
```

Result:

```text
RELEASE BLOCKED
```

---

# 324. THIRD EXAMPLE

```text
License compatible
Security acceptable
Architecture incompatible
```

Result:

```text
RELEASE BLOCKED
```

---

# 325. FOURTH EXAMPLE

```text
License compatible
Security acceptable
Architecture compatible
Tests pass
```

Result:

```text
APPROVED
```

---

# 326. COMPLIANCE HIERARCHY

```text
Legal Compatibility
        ↓
Security
        ↓
Architecture
        ↓
Technical Quality
        ↓
Operational Fit
```

A lower-level advantage does not override a higher-level blocking condition.

---

# 327. LICENSE COMPATIBILITY WITH JAS

JAS v1 prefers:

```text
MIT
BSD
Apache-2.0
ISC
```

for general-purpose infrastructure when technically appropriate.

---

# 328. WHY PERMISSIVE LICENSES ARE PREFERRED

They generally minimize:

```text
Redistribution Complexity
Source Disclosure Complexity
Commercialization Friction
```

while still requiring proper notices.

---

# 329. PERMISSIVE ≠ RISK-FREE

Even permissive software can contain:

```text
Patent Issues
Security Issues
Trademark Issues
Third-party Components
```

---

# 330. MODEL LICENSE PREFERENCE

For locally distributed models, JAS prefers models with:

```text
Clear License
Clear Commercial Rights
Clear Redistribution Rights
Clear Derivative Rights
Clear Model Card
```

---

# 331. MODEL LICENSE RISK

Custom model licenses receive greater scrutiny than standard permissive software licenses.

---

# 332. API PROVIDER PREFERENCE

Provider APIs should have:

```text
Clear Commercial Terms
Clear Data Handling
Clear Output Terms
Clear Privacy Terms
Stable API
```

---

# 333. MCP PREFERENCE

MCP servers should have:

```text
Known Source
Known Maintainer
Known License
Known Dependencies
Known Capabilities
Known Security Model
```

---

# 334. PLUGIN PREFERENCE

Plugins should have:

```text
Declared License
Declared Permissions
Declared Dependencies
```

---

# 335. SUPPLY-CHAIN PRINCIPLE

Every new dependency increases:

```text
Technical Risk
Security Risk
License Risk
Maintenance Risk
```

---

# 336. MINIMAL DEPENDENCY PRINCIPLE

JARVIS should not add a dependency when the capability can be implemented safely with existing approved infrastructure.

---

# 337. NO DEPENDENCY FOR CONVENIENCE

A dependency should provide meaningful value.

---

# 338. COMPLIANCE COST

Dependency selection must consider:

```text
License
Security
Maintenance
Operational Cost
```

not only developer convenience.

---

# 339. VENDOR LOCK-IN

Vendor lock-in is a compliance concern when:

```text
Terms
Pricing
Data Access
Distribution
```

can materially constrain the project.

---

# 340. COMMERCIAL EXIT STRATEGY

Critical third-party services should have a replacement or migration strategy where practical.

---

# 341. MODEL EXIT STRATEGY

Critical model providers should not be the only possible execution path if the architecture can reasonably support alternatives.

---

# 342. DATA EXIT STRATEGY

JARVIS-owned data should remain exportable in standard formats where practical.

---

# 343. MEMORY EXIT STRATEGY

Memory data should not be trapped in a proprietary provider format without an export strategy.

---

# 344. VECTOR DATABASE EXIT STRATEGY

Embeddings and metadata should be exportable where practical.

---

# 345. PROVIDER DATA PORTABILITY

Cloud provider dependencies should be evaluated for data portability.

---

# 346. LICENSE AND ARCHITECTURE

Compliance is therefore part of the architecture rather than a post-processing task.

---

# 347. FINAL COMPLIANCE PIPELINE

```text
Technology
    ↓
Research
    ↓
License Identification
    ↓
Security Review
    ↓
Architecture Review
    ↓
Commercial Review
    ↓
Approval
    ↓
Version Lock
    ↓
Manifest
    ↓
Bootstrap
    ↓
SBOM
    ↓
Release Compliance
```

---

# 348. FINAL DECISION STATES

```text
APPROVED
CONDITIONALLY APPROVED
RESTRICTED
DEFERRED
REJECTED
UNKNOWN
```

---

# 349. APPROVED

May be used under defined conditions.

---

# 350. CONDITIONALLY APPROVED

May be used only under explicitly defined conditions.

---

# 351. RESTRICTED

Requires additional review before use in specific deployment profiles.

---

# 352. DEFERRED

Not part of current baseline.

---

# 353. REJECTED

Must not be used in production baseline.

---

# 354. UNKNOWN

Insufficient information.

Unknown is not approval.

---

# 355. COMPLIANCE AUTOMATION TARGET

The long-term goal is:

```text
Developer adds dependency
        ↓
CI detects dependency
        ↓
License detected
        ↓
License normalized
        ↓
Compatibility evaluated
        ↓
SBOM updated
        ↓
Notice updated
        ↓
Compliance PASS / FAIL
```

---

# 356. BOOTSTRAP COMPLIANCE

Bootstrap should install only:

```text
Approved
Version-Locked
Compliance-Verified
```

components.

---

# 357. BOOTSTRAP BLOCK

If a package is classified:

```text
REJECTED
```

Bootstrap should block it.

---

# 358. BOOTSTRAP UNKNOWN

If a package is:

```text
UNKNOWN
```

Bootstrap should either:

```text
Fail
```

or require an explicit development/research override.

---

# 359. MANIFEST COMPLIANCE

Manifest entries should contain enough metadata to identify:

```text
Component
Version
License Class
Distribution Status
```

where appropriate.

---

# 360. VERSION LOCK COMPLIANCE

Version Lock must freeze:

```text
Exact Software
Exact Version
Exact Model
Exact Revision
Exact Container
```

to the extent practical.

---

# 361. COMPLIANCE AND REPRODUCIBILITY

A reproducible environment must also be a reproducibly auditable environment.

---

# 362. FINAL ARCHITECTURE

```text
                  JAS v1
                     │
                     ▼
             Approved Stack
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
    Software Matrix       License Policy
          │                     │
          └──────────┬──────────┘
                     ▼
               Version Lock
                     │
                     ▼
                 Manifest
                     │
                     ▼
                 Bootstrap
                     │
                     ▼
            Compliance Checker
                     │
                     ▼
              System Verification
                     │
                     ▼
                 JARVIS
```

---

# 363. FINAL PRINCIPLE

> **Every component used by JARVIS must have a known legal/compliance status appropriate to the way JARVIS uses and distributes that component.**

---

# 364. FINAL PRINCIPLE

> **"Open source" is a starting classification, not a compliance conclusion.**

---

# 365. FINAL PRINCIPLE

> **The exact version, exact artifact, exact license, and exact deployment model matter.**

---

# 366. FINAL PRINCIPLE

> **Software licenses, model licenses, dataset rights, API terms, and trademark rights are separate compliance surfaces.**

---

# 367. FINAL PRINCIPLE

> **Unknown licensing is not approval.**

---

# 368. FINAL PRINCIPLE

> **A component that is technically excellent but legally incompatible cannot enter the production baseline.**

---

# 369. FINAL PRINCIPLE

> **A component that is legally compatible but architecturally or technically unsafe cannot enter the production baseline.**

---

# 370. FINAL PRINCIPLE

> **Every production release must be auditable after the fact.**

---

# 371. FINAL PRINCIPLE

> **Compliance must be automated wherever possible and manually reviewed wherever automation is insufficient.**

---

# 372. FINAL PRINCIPLE

> **License decisions must be tied to the exact version and deployment model rather than remembered informally.**

---

# 373. FINAL PRIMARY COMPLIANCE RULE

```text
NO LICENSE
    → NO APPROVAL

UNKNOWN TERMS
    → NO APPROVAL

INCOMPATIBLE LICENSE
    → NO PRODUCTION

UNAPPROVED MODEL
    → NO PRODUCTION

UNAPPROVED MCP
    → NO PRODUCTION

UNAPPROVED PLUGIN
    → NO PRODUCTION
```

---

# 374. FINAL RELEASE RULE

```text
TECHNICALALLY WORKS
        ≠
COMPLIANT

COMPLIANT
        +
SECURE
        +
ARCHITECTURALLY VALID
        +
TESTED
        =
RELEASABLE
```

---

# 375. CURRENT PRIMARY LICENSE BASELINE

Conceptually:

```text
FastAPI
→ MIT

Playwright
→ Apache-2.0

Qdrant
→ Apache-2.0

uv
→ Apache-2.0 OR MIT

pytest
→ MIT

React
→ MIT
```

These classifications must still be tied to the exact version in Version Lock. FastAPI, Qdrant, Playwright, uv and pytest currently publish the cited license information in their respective project metadata/repositories. citeturn0search3turn0search8turn0search15turn1search0turn1search12

---

# 376. SPECIAL COMPLIANCE WATCH ITEMS

```text
Redis
Custom Model Licenses
Commercial AI APIs
Gemma Terms
Mistral Model-specific Terms
MCP Servers
Third-party Plugins
Browser Binaries
Container Base Images
Datasets
Fonts
Audio
Images
```

---

# 377. NEXT DOCUMENT RELATIONSHIP

The next document:

```text
24_VERSION_SUPPORT_POLICY.md
```

will define how approved technologies and their versions are:

```text
Supported
Current
Maintenance
Deprecated
Removed
```

over their lifecycle.

---

# 378. VERSION SUPPORT RELATIONSHIP

```text
23_LICENSE_AND_COMPLIANCE
            │
            ▼
24_VERSION_SUPPORT_POLICY
            │
            ▼
Version Lock
```

---

# 379. FINAL STATUS

```text
============================================================

JAS-AS-23
LICENSE AND COMPLIANCE

VERSION:
1.0

STATUS:
APPROVED

PRIMARY PURPOSE:
LICENSE + COMPLIANCE GOVERNANCE

CORE FUNCTION:
ENSURE THAT EVERY COMPONENT USED BY JARVIS
HAS A KNOWN AND ACCEPTABLE COMPLIANCE STATUS.

COVERS:
Software
Models
Datasets
MCP
Plugins
Containers
Cloud Services
Assets
Distribution
Commercialization
Privacy Interfaces
SBOM
Notices
Compliance Automation

NEXT DOCUMENT:
24_VERSION_SUPPORT_POLICY.md

============================================================
```

---

# 380. END OF DOCUMENT

```text
============================================================

JAS-AS-23
LICENSE AND COMPLIANCE v1.0

APPROVED

============================================================
```

**END OF `23_LICENSE_AND_COMPLIANCE.md`**