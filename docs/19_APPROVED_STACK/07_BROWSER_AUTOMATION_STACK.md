# 07 — BROWSER AUTOMATION STACK

**Document ID:** JAS-AS-07  
**Document:** `07_BROWSER_AUTOMATION_STACK.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Status:** APPROVED STACK SPECIFICATION  
**Version:** v1.0  
**Authority:** JAS v1  
**Depends On:** JAS v1, `00_APPROVED_STACK_OVERVIEW.md`, `01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md`  
**Feeds Into:** Version Lock, Manifest, Bootstrap, Compliance Checker, Browser Runtime, Agent Tooling, MCP Integration

---

# 1. PURPOSE

This document defines the browser automation technology strategy for the JARVIS system.

The objective is not merely to select a browser automation library.

The objective is to define a reliable, secure, observable, extensible and agent-compatible browser automation subsystem capable of supporting JARVIS as a long-lived personal AI platform.

The browser subsystem must allow JARVIS to:

- launch and control browsers,
- create isolated browser sessions,
- navigate websites,
- inspect pages,
- understand page structure,
- interact with web elements,
- enter and submit information,
- handle tabs and popups,
- manage authentication state,
- download files,
- upload files,
- capture screenshots,
- inspect accessibility information,
- observe browser state,
- recover from transient failures,
- execute deterministic workflows,
- expose browser capabilities to agents,
- integrate with MCP where appropriate,
- produce observability data,
- enforce security and permission policies.

Browser automation is therefore treated as a **first-class infrastructure capability**, not as a miscellaneous utility.

---

# 2. ARCHITECTURAL POSITION

Browser automation belongs to the JARVIS capability and execution infrastructure.

The conceptual architecture is:

```text
                         JARVIS
                           │
                           ▼
                    Agent Orchestrator
                           │
                           ▼
                      Tool Layer
                           │
                           ▼
                 Browser Capability API
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
       Policy / Security          Browser Runtime
             │                           │
             └─────────────┬─────────────┘
                           ▼
                    Browser Adapter
                           │
                           ▼
                      Playwright
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
         Chromium       Firefox        WebKit
```

The browser automation framework MUST NOT be exposed directly to the LLM.

The correct execution path is:

```text
LLM / Agent
     ↓
Intent
     ↓
Tool Request
     ↓
Policy Evaluation
     ↓
Permission Check
     ↓
Browser Capability
     ↓
Browser Runtime
     ↓
Automation Framework
     ↓
Browser
```

The LLM must never receive unrestricted browser-control privileges.

---

# 3. DESIGN PRINCIPLES

The browser subsystem SHALL follow these principles.

## 3.1 Browser Automation Is a Capability

Browser access is a capability granted to an agent or workflow.

It is not an inherent property of the LLM.

---

## 3.2 Least Privilege

A browser session should receive only the permissions required for the current task.

Examples:

```text
READ_ONLY
READ_AND_NAVIGATE
INTERACT
DOWNLOAD
UPLOAD
AUTHENTICATED_INTERACTION
HIGH_RISK_ACTION
```

These capability levels must be enforced above the automation framework.

---

## 3.3 Isolation by Default

Browser sessions should be isolated unless persistent state is explicitly required.

The preferred model is:

```text
Task
 ↓
Browser Context
 ↓
Pages
```

rather than sharing one uncontrolled global browser session.

Playwright BrowserContexts are designed as independent browser sessions and can provide isolated non-persistent contexts. citeturn0search4

---

## 3.4 Deterministic Execution

Whenever possible, browser actions should be deterministic.

The system should prefer:

```text
semantic locator
↓
stable element
↓
explicit action
↓
explicit verification
```

over:

```text
random coordinate
↓
blind click
↓
hope
```

---

## 3.5 Observation Before Action

Agent-driven browser interaction should generally follow:

```text
Observe
 ↓
Understand
 ↓
Plan
 ↓
Act
 ↓
Verify
```

rather than:

```text
Guess
 ↓
Act
```

---

## 3.6 Verification After Side Effects

Actions with meaningful consequences should have post-action verification.

Example:

```text
Click "Submit"
       ↓
Observe
       ↓
Check resulting page/state
       ↓
Confirm success
```

---

## 3.7 Explicit Human Approval for High-Risk Actions

The browser subsystem must support an approval boundary for actions such as:

- financial transactions,
- irreversible account changes,
- sending sensitive communications,
- deleting data,
- purchasing goods,
- accepting legal agreements,
- changing security settings,
- submitting government or legal forms,
- revealing sensitive information.

The automation engine must not independently decide that an irreversible action is safe merely because an LLM requested it.

---

# 4. PRIMARY TECHNOLOGY DECISION

## 4.1 Primary Browser Automation Framework

**Selected Technology: Playwright**

Status:

```text
APPROVED
```

Playwright is selected as the primary browser automation framework for JARVIS.

The selection is based on its combination of:

- Chromium support,
- Firefox support,
- WebKit support,
- multi-page browser contexts,
- isolated browser contexts,
- authentication-state handling,
- downloads,
- uploads,
- screenshots,
- browser events,
- network capabilities,
- tracing,
- cross-platform support,
- TypeScript/JavaScript support,
- Python support,
- agent-oriented capabilities,
- MCP ecosystem integration,
- mature documentation,
- active development.

Playwright explicitly positions itself for web automation, scripting and AI-agent workflows. citeturn0search15

---

# 5. PLAYWRIGHT ROLE

Playwright SHALL act as the low-level browser automation engine.

It is responsible for:

```text
Browser Launch
Browser Lifecycle
Browser Contexts
Pages
Navigation
Locators
DOM Interaction
Keyboard
Mouse
Input
Screenshots
Downloads
Uploads
Dialogs
Popups
Network Events
Browser Events
Tracing
Browser Configuration
```

Playwright SHALL NOT be responsible for:

```text
User authorization
Agent policy
LLM reasoning
Business logic
Long-term memory
Credential governance
Task planning
Risk classification
High-level permissions
JARVIS identity
```

Those responsibilities belong to higher architectural layers.

---

# 6. ABSTRACTION REQUIREMENT

JARVIS MUST NOT make the entire application directly dependent on Playwright APIs.

Instead:

```text
JARVIS
   ↓
Browser Capability Interface
   ↓
Browser Adapter
   ↓
Playwright
```

The browser adapter provides an internal abstraction boundary.

Conceptually:

```text
BrowserCapability
├── launch()
├── close()
├── create_session()
├── navigate()
├── inspect()
├── click()
├── fill()
├── select()
├── upload()
├── download()
├── screenshot()
├── extract()
├── wait()
├── observe()
└── recover()
```

The exact API is an implementation concern and SHALL be defined during core architecture implementation.

---

# 7. SUPPORTED BROWSERS

The browser subsystem shall support the following browser families through the primary automation framework:

| Browser | Status | Primary Role |
|---|---|---|
| Chromium | APPROVED | Primary automation target |
| Firefox | APPROVED | Cross-browser compatibility |
| WebKit | APPROVED | Cross-browser compatibility |
| Google Chrome | SUPPORTED | Branded Chromium execution |
| Microsoft Edge | SUPPORTED | Branded Chromium execution |

Playwright supports Chromium, Firefox and WebKit and can also operate against installed Google Chrome and Microsoft Edge channels. citeturn0search1

---

# 8. PRIMARY BROWSER POLICY

Although multiple browsers are supported, JARVIS SHALL NOT automatically execute every task against every browser.

The default policy is:

```text
Task
 ↓
Browser Compatibility Requirement
 ↓
Selected Browser
 ↓
Execution
```

The default browser should be selected based on:

- site compatibility,
- task requirements,
- authentication state,
- required browser features,
- debugging requirements,
- performance,
- security policy,
- user preference.

Chromium should be the default candidate for general-purpose automation unless another browser is specifically required.

---

# 9. BROWSER CONTEXT MODEL

BrowserContexts are a core architectural primitive.

The preferred session model is:

```text
Browser Process
      │
      ├── Context A
      │     ├── Page
      │     └── Page
      │
      ├── Context B
      │     └── Page
      │
      └── Context C
            └── Page
```

Contexts SHOULD be used to isolate:

- tasks,
- identities,
- sessions,
- authentication state,
- cookies,
- local storage,
- permissions,
- temporary browsing state.

Playwright supports multiple independent browser contexts and multiple pages within each context. citeturn0search4turn0search14

---

# 10. SESSION TYPES

JARVIS shall conceptually support at least the following session classes.

## 10.1 Ephemeral Session

Used for:

- public websites,
- research,
- temporary browsing,
- one-off tasks.

Characteristics:

```text
No persistent authentication
No long-term cookies
Disposable
Isolated
```

---

## 10.2 Persistent User Session

Used when the user explicitly authorizes persistent login state.

Examples:

```text
Google
GitHub
Booking
Amazon
University Portal
Government Portal
```

Persistent sessions require additional security controls.

---

## 10.3 Restricted Session

A session with explicitly limited permissions.

Example:

```text
Can navigate
Can read
Cannot upload
Cannot download
Cannot submit
```

---

## 10.4 High-Trust Session

A session may be used for sensitive workflows only after explicit user authorization.

It must have:

- stronger credential isolation,
- audit logging,
- explicit permission scope,
- action confirmation,
- stricter timeout policies.

---

# 11. AUTHENTICATION AND CREDENTIALS

Authentication state is security-sensitive.

JARVIS SHALL NOT store raw credentials inside browser automation code.

The browser layer should receive credentials or authenticated state through the approved security subsystem.

Possible state:

```text
Credential Store
       ↓
Security Layer
       ↓
Browser Session
```

Authentication state may contain cookies, headers or other information capable of impersonating a user. Such state must therefore never be committed to source control. Playwright specifically warns that stored authentication state can contain sensitive cookies and headers. citeturn0search0

Authentication state SHALL be:

- encrypted or protected where appropriate,
- access-controlled,
- scoped,
- auditable,
- revocable,
- excluded from Git,
- excluded from normal application logs.

---

# 12. PROFILE MANAGEMENT

Browser profiles SHALL be treated as managed resources.

The architecture should distinguish:

```text
Browser Binary
Browser Context
Browser Profile
Authentication State
User Identity
```

These concepts must not be conflated.

A profile may contain:

- cookies,
- local storage,
- browser preferences,
- cached state,
- authentication state,
- site-specific configuration.

Profiles must therefore be protected as sensitive assets.

---

# 13. NAVIGATION

Navigation capabilities include:

```text
goto(URL)
back()
forward()
reload()
open_new_page()
open_popup()
```

Navigation should enforce:

- URL policy,
- network policy,
- timeout policy,
- redirect handling,
- protocol restrictions,
- domain restrictions where configured.

The system should support policy rules such as:

```text
ALLOW
DENY
CONFIRM
```

for destinations.

---

# 14. URL SECURITY

The browser security layer SHALL be capable of detecting:

- suspicious domains,
- unexpected redirects,
- protocol changes,
- dangerous downloads,
- credential phishing indicators,
- untrusted destinations,
- unexpected cross-origin navigation.

The LLM must not be allowed to override security policy merely by generating a different URL.

---

# 15. PAGE AND TAB MANAGEMENT

Each BrowserContext may contain multiple Pages.

The browser subsystem SHALL support:

```text
Create Page
Close Page
Switch Page
Observe Page
Detect Popup
Track URL
Track Title
Track Navigation
```

Page identity must be maintained explicitly.

Agents must never rely solely on:

```text
"the active tab"
```

as an implicit reference.

Instead, tasks should maintain explicit page handles or IDs.

---

# 16. DOM INTERACTION

The preferred interaction hierarchy is:

```text
Accessibility / Semantic Locator
        ↓
Stable Locator
        ↓
CSS / XPath where necessary
        ↓
Coordinate Interaction as last resort
```

The system should avoid brittle selectors whenever possible.

Preferred examples conceptually include:

```text
Role
Label
Text
Test ID
Stable Attribute
```

rather than:

```text
nth-child(...)
generated-class-12345
absolute coordinates
```

---

# 17. ACCESSIBILITY TREE

Accessibility information is an important source of structured page understanding.

The browser layer SHOULD expose accessibility-oriented information to agent tooling when available.

This is particularly important for:

- agent reasoning,
- form understanding,
- semantic element identification,
- robust interaction,
- reduced token consumption.

The browser subsystem should prefer structured accessibility information over transmitting entire raw DOM trees to the LLM whenever possible.

---

# 18. SCREENSHOT SUPPORT

The system SHALL support screenshots at:

```text
Page level
Element level
Failure level
Debug level
Audit level
```

Screenshots may be used for:

- visual reasoning,
- debugging,
- failure recovery,
- evidence,
- observability,
- vision-agent integration.

Screenshots containing sensitive information must follow the same security policy as other browser artifacts.

---

# 19. DOWNLOADS

Downloads SHALL be treated as explicit browser artifacts.

The browser layer must support:

```text
Detect Download
Wait for Completion
Validate Filename
Validate File Type
Validate Size
Store Artifact
Associate Artifact with Task
```

Playwright exposes download events and supports saving completed downloads to a specified location. Browser-context downloads are removed when the context is closed unless explicitly saved elsewhere. citeturn0search3

Downloaded files must not automatically become trusted.

The artifact pipeline should support:

```text
Download
 ↓
Validation
 ↓
Optional Malware/Security Scan
 ↓
Artifact Storage
 ↓
Agent Access
```

---

# 20. UPLOADS

Uploads SHALL be explicit capabilities.

The system should support:

```text
Select File
Validate File
Check Permission
Upload
Verify Upload
```

The agent must not upload arbitrary local files without authorization.

A future permission model should allow rules such as:

```text
Allow upload from:
    workspace/
    
Deny upload from:
    credentials/
    secrets/
    private keys/
```

---

# 21. FORMS

Form automation is a major JARVIS capability.

The system should support:

```text
Identify Form
Identify Fields
Understand Field Semantics
Fill Fields
Validate Fields
Submit
Observe Result
```

Sensitive forms should trigger elevated policies.

Examples:

```text
Banking
Government
Immigration
Legal
Healthcare
Employment
University
Financial
```

The browser layer must not infer permission merely because the user previously authorized browser access.

---

# 22. HUMAN-IN-THE-LOOP

The architecture SHALL support human approval checkpoints.

Example:

```text
Agent
 ↓
Prepare Form
 ↓
Show User
 ↓
User Approval
 ↓
Submit
 ↓
Verify
```

This is especially important for:

- purchases,
- financial transfers,
- legal submissions,
- account deletion,
- security changes,
- irreversible actions,
- messages sent to external parties.

---

# 23. WAITING STRATEGY

Browser automation SHALL avoid unnecessary fixed sleeps.

Bad pattern:

```text
sleep(5000)
click()
```

Preferred model:

```text
Wait for Condition
 ↓
Verify Condition
 ↓
Perform Action
```

Possible conditions include:

```text
Element Visible
Element Enabled
Navigation Complete
Network Idle where appropriate
Expected Text Present
Expected URL
Download Started
Popup Created
```

Timeouts must be explicit and configurable.

---

# 24. TIMEOUT POLICY

Timeouts should exist at multiple levels:

```text
Action Timeout
Navigation Timeout
Page Timeout
Task Timeout
Browser Startup Timeout
Download Timeout
Authentication Timeout
```

A timeout should generate structured failure information.

Example:

```text
TIMEOUT
task_id
session_id
page_id
operation
elapsed_ms
url
last_known_state
```

---

# 25. RETRY POLICY

Retries SHALL NOT be unconditional.

The system should distinguish:

```text
Transient Failure
Recoverable Failure
Deterministic Failure
Security Failure
Permission Failure
Unknown Failure
```

Example:

```text
Network Timeout
→ Retry possible

Element Missing
→ Re-observe and reconsider

Permission Denied
→ Do not retry automatically

Security Policy Violation
→ Stop

Invalid Form
→ Re-evaluate input
```

---

# 26. RECOVERY MODEL

Browser recovery should follow:

```text
Failure
 ↓
Capture State
 ↓
Classify Failure
 ↓
Re-observe
 ↓
Determine Recovery Strategy
 ↓
Retry / Replan / Abort
```

Recovery should never blindly repeat a side-effecting action.

For example:

```text
Click "Buy"
```

must not automatically be repeated if the system cannot determine whether the first click succeeded.

---

# 27. ANTI-FRAGILE AUTOMATION

JARVIS should be designed to tolerate normal web variability.

The browser subsystem should account for:

- dynamic DOMs,
- delayed loading,
- changing element positions,
- popup windows,
- redirects,
- cookie banners,
- localization,
- responsive layouts,
- transient network failures,
- stale elements,
- session expiration,
- changed page structures.

The correct response is not to make the automation "blindly persistent."

Instead:

```text
Observe
 ↓
Detect Change
 ↓
Re-understand
 ↓
Adapt
 ↓
Verify
```

---

# 28. HEADLESS VS HEADED

Both modes shall be supported.

## Headless

Preferred for:

- background tasks,
- automation services,
- CI,
- server execution,
- high-volume deterministic workflows.

## Headed

Preferred for:

- debugging,
- human supervision,
- interactive authentication,
- visual inspection,
- troubleshooting,
- user-assisted workflows.

Playwright supports both browser execution approaches and provides browser configuration for these modes. citeturn0search1

---

# 29. BROWSER LIFECYCLE

The browser runtime SHALL manage:

```text
Acquire Browser
 ↓
Create Context
 ↓
Create Page
 ↓
Execute Task
 ↓
Collect Artifacts
 ↓
Close Pages
 ↓
Close Context
 ↓
Release Browser
```

Browser processes should not remain alive indefinitely without an explicit reason.

Long-lived browser processes must have:

- health checks,
- resource monitoring,
- idle timeout,
- crash recovery,
- cleanup.

---

# 30. CONCURRENCY

The browser layer must support controlled concurrency.

Conceptually:

```text
Browser Pool
    │
    ├── Session A
    ├── Session B
    ├── Session C
    └── Session D
```

Concurrency limits should depend on:

- CPU,
- RAM,
- browser memory,
- task type,
- site restrictions,
- network capacity,
- user-defined policy.

The system must avoid uncontrolled browser spawning.

---

# 31. RESOURCE MANAGEMENT

Each browser task should have resource accounting.

Possible metrics:

```text
Browser Startup Time
Context Creation Time
Task Duration
CPU Usage
Memory Usage
Network Traffic
Number of Pages
Number of Contexts
Download Size
Screenshot Count
Failure Count
Retry Count
```

These metrics belong to the observability subsystem.

---

# 32. NETWORK INTERACTION

Browser automation may need network-level visibility for:

- debugging,
- request tracking,
- performance analysis,
- authentication troubleshooting,
- failure diagnosis.

However, network interception is a privileged capability.

Agents should not automatically receive arbitrary request interception or modification capabilities.

---

# 33. JAVASCRIPT EXECUTION

Direct JavaScript execution in pages is powerful but potentially dangerous.

Therefore:

```text
page.evaluate(...)
```

or equivalent low-level script execution must not automatically be exposed as a general-purpose LLM tool.

If exposed, it should be:

```text
Privileged Capability
+
Policy Check
+
Explicit Tool Definition
```

---

# 34. BROWSER TOOL API

The future JARVIS tool layer should expose semantic browser operations rather than raw automation-library primitives.

Preferred:

```text
browser.navigate
browser.observe
browser.find
browser.click
browser.fill
browser.select
browser.upload
browser.download
browser.screenshot
browser.open_tab
browser.close_tab
browser.back
browser.forward
```

Avoid exposing unrestricted low-level primitives such as:

```text
execute_arbitrary_browser_code
execute_arbitrary_javascript
modify_network_without_policy
```

unless explicitly privileged.

---

# 35. AGENT INTEGRATION

The browser system must be compatible with:

```text
Research Agent
Browser Agent
Coding Agent
Planning Agent
System Agent
Vision Agent
```

The browser itself should remain an infrastructure capability.

The agent decides:

```text
What to accomplish
```

The browser subsystem decides:

```text
How to safely execute the authorized browser operation
```

---

# 36. AGENT OBSERVATION MODEL

The browser agent should receive compact structured observations.

Conceptually:

```text
BrowserObservation
├── session_id
├── page_id
├── url
├── title
├── visible_text
├── accessibility_tree
├── interactive_elements
├── dialogs
├── downloads
├── navigation_state
├── authentication_state
└── screenshots
```

The exact schema shall be defined during core implementation.

---

# 37. TOKEN EFFICIENCY

Browser information can become extremely large.

The system must therefore avoid sending entire pages to an LLM unnecessarily.

Preferred hierarchy:

```text
Task-Relevant Observation
        ↓
Relevant DOM / Accessibility
        ↓
Relevant Text
        ↓
Screenshot
        ↓
Full Page Data
```

The observation layer should support:

- element filtering,
- text truncation,
- semantic extraction,
- viewport-based observation,
- incremental observation,
- caching.

---

# 38. VISION INTEGRATION

Browser automation and computer vision are related but distinct capabilities.

The architecture should permit:

```text
Browser
 ↓
Screenshot
 ↓
Vision System
 ↓
Visual Understanding
 ↓
Agent
```

Vision should be used when DOM/accessibility information is insufficient.

Examples:

- canvas applications,
- visual editors,
- image-heavy interfaces,
- graphical dashboards,
- unusual UI widgets.

The system should not use vision when a deterministic DOM interaction is available unless there is a specific reason.

---

# 39. MCP INTEGRATION

MCP is an integration mechanism, not the browser runtime itself.

The architecture may support:

```text
JARVIS
 ↓
MCP Client
 ↓
Browser MCP Server
 ↓
Browser Runtime
```

The browser capability may therefore be exposed through MCP when useful.

A current example is Microsoft's Playwright MCP project, which integrates Playwright browser control with MCP and structured accessibility snapshots. citeturn0search13turn0search15

However:

> JARVIS MUST NOT become architecturally dependent on a single MCP browser server.

The native browser capability abstraction remains the authoritative internal interface.

---

# 40. MCP VS NATIVE BROWSER CAPABILITY

The distinction is:

```text
Native Browser Capability
=
JARVIS internal execution interface

MCP Browser Server
=
external / standardized integration interface
```

This prevents MCP implementation details from leaking into the JARVIS core.

---

# 41. ALTERNATIVE TECHNOLOGY EVALUATION

The principal alternatives considered are:

```text
Playwright
Selenium
Puppeteer
```

---

# 42. SELENIUM

Status:

```text
CONDITIONALLY APPROVED / ALTERNATIVE
```

Selenium remains an important browser automation ecosystem with W3C WebDriver support, broad browser compatibility and remote execution capabilities. citeturn0search5

Advantages:

- mature ecosystem,
- broad industry adoption,
- WebDriver standard,
- large language-binding ecosystem,
- remote browser infrastructure,
- strong enterprise history.

Disadvantages for JARVIS primary use:

- more fragmented architecture,
- more traditional WebDriver-oriented model,
- additional infrastructure complexity for some workflows,
- less attractive as the primary agent-native automation layer.

Selenium should therefore remain a viable fallback or integration candidate rather than the primary browser runtime.

---

# 43. PUPPETEER

Status:

```text
ALTERNATIVE / NOT PRIMARY
```

Puppeteer is a strong browser automation framework with particularly strong Chrome/Chromium integration.

Modern Puppeteer also supports Firefox and WebDriver BiDi, while retaining CDP-based Chrome automation. citeturn0search16turn0search10

Advantages:

- excellent Chrome ecosystem integration,
- strong JavaScript/TypeScript experience,
- CDP access,
- mature project,
- WebDriver BiDi support.

Disadvantages for JARVIS:

- less attractive cross-browser strategy than Playwright for the intended architecture,
- stronger historical coupling to Chromium/Chrome workflows,
- Playwright provides a more direct fit for JARVIS's multi-browser and agent-oriented requirements.

Puppeteer should remain monitored but is not selected as the primary framework.

---

# 44. COMPARISON

| Criterion | Playwright | Selenium | Puppeteer |
|---|---:|---:|---:|
| Chromium | Excellent | Excellent | Excellent |
| Firefox | Excellent | Excellent | Supported |
| WebKit | Excellent | Via ecosystem/browser support model | No equivalent primary focus |
| Browser Context Isolation | Excellent | Good | Good |
| Modern Web Apps | Excellent | Good | Excellent |
| Agent Suitability | Excellent | Good | Good |
| MCP Ecosystem | Excellent | Limited | Limited |
| Tracing / Debugging | Excellent | Good | Good |
| Downloads | Excellent | Good | Excellent |
| Authentication State | Excellent | Good | Good |
| Cross-Browser Strategy | Excellent | Excellent | Good |
| Python Support | Yes | Yes | No native Python API |
| TypeScript Support | Excellent | Yes | Excellent |
| Remote Grid Ecosystem | Good | Excellent | Good |
| JARVIS Fit | **Excellent** | Good | Good |

---

# 45. FINAL TECHNOLOGY DECISION

The decision is:

```text
PRIMARY
Playwright
```

```text
SECONDARY / FALLBACK
Selenium
```

```text
ALTERNATIVE / WATCH
Puppeteer
```

The primary implementation should be Playwright.

The architecture must nevertheless preserve an adapter boundary so that replacing or supplementing the underlying browser engine remains technically possible.

---

# 46. LICENSING

Playwright is distributed under the Apache License 2.0. The official Playwright repository identifies Apache-2.0 as its license. citeturn0search2turn0search8

For JARVIS, licensing evaluation must include:

```text
Playwright License
Browser Binary Licenses
Browser Distribution Terms
Transitive Dependencies
MCP Server Licenses
Model Licenses
Container Images
OS Dependencies
```

Approval of Playwright does not automatically approve every browser binary or external component connected to it.

Final compliance shall be consolidated in:

```text
23_LICENSE_AND_COMPLIANCE.md
```

---

# 47. VERSION POLICY

This document intentionally does not permanently lock a specific Playwright version.

The distinction is:

```text
Approved Stack
=
Technology Decision

Version Lock
=
Exact Version Decision
```

Therefore:

```text
Playwright
APPROVED
```

belongs here.

The exact package version belongs in Version Lock.

Browser binary revisions must also be locked or otherwise reproducibly controlled during Version Lock.

This is particularly important because Playwright versions are associated with specific browser binaries, and updating Playwright can require updating installed browser binaries. citeturn0search1

---

# 48. BROWSER BINARY REPRODUCIBILITY

The browser binary is part of the runtime.

Therefore the following cannot be treated as independent:

```text
Playwright Package
+
Browser Binary
```

Version Lock must define a reproducible relationship between them.

The Bootstrap system must verify that the expected browser binaries exist.

Conceptually:

```text
Playwright Version
        ↓
Expected Browser Revision
        ↓
Installed Browser
        ↓
Verification
```

---

# 49. BOOTSTRAP REQUIREMENTS

Bootstrap SHALL support browser provisioning.

The browser bootstrap process should include:

```text
Detect OS
 ↓
Detect Runtime
 ↓
Install Browser Automation Dependency
 ↓
Install Required Browser Binaries
 ↓
Verify Browser Launch
 ↓
Verify Browser Version
 ↓
Verify Permissions
 ↓
Run Smoke Test
 ↓
Report
```

Playwright provides CLI mechanisms for installing its supported browsers and, where applicable, system dependencies. citeturn0search1

---

# 50. WINDOWS SUPPORT

Windows is a first-class development environment requirement for JARVIS.

The browser subsystem must therefore be tested on Windows.

Minimum requirements include:

```text
Browser Launch
Headless
Headed
Downloads
Uploads
Authentication
Screenshots
Multiple Contexts
Multiple Pages
Process Cleanup
Browser Crash Recovery
```

---

# 51. LINUX SUPPORT

Linux is required for:

- server deployment,
- container execution,
- CI,
- staging,
- production infrastructure.

The browser subsystem must therefore be validated on supported Linux environments.

---

# 52. MACOS

macOS may be supported where useful but is not a primary JARVIS deployment requirement unless later architecture decisions change this.

The abstraction should nevertheless avoid unnecessary OS-specific assumptions.

---

# 53. CONTAINERIZATION

Browser execution must be compatible with containerized deployment where practical.

Potential architecture:

```text
JARVIS Service
      │
      ▼
Browser Worker
      │
      ▼
Browser Process
```

Containerized browser execution must address:

- sandboxing,
- shared memory,
- resource limits,
- filesystem isolation,
- user permissions,
- browser dependencies,
- artifact storage.

---

# 54. SECURITY BOUNDARIES

The browser subsystem is considered a high-risk capability.

Security boundaries must exist between:

```text
LLM
Agent
Tool
Browser Capability
Browser Process
Host OS
```

The browser must not automatically receive:

```text
unrestricted filesystem access
unrestricted shell access
unrestricted credential access
unrestricted network access
```

---

# 55. SECRET MANAGEMENT

Secrets must be handled outside browser automation source code.

Examples:

```text
Passwords
API Tokens
Session Cookies
OAuth Tokens
Private Keys
Authentication State
```

must be managed by the approved security infrastructure.

The browser layer should receive only the minimum information required for execution.

---

# 56. DOWNLOAD SECURITY

Downloaded files should be treated as untrusted input.

Pipeline:

```text
Download
 ↓
Hash
 ↓
Metadata
 ↓
Security Scan
 ↓
Artifact Store
 ↓
Optional Parsing
```

The browser agent should not automatically execute downloaded files.

---

# 57. UPLOAD SECURITY

Uploads must enforce:

```text
Source Path Policy
File Type Policy
File Size Policy
User Permission
Destination Domain Policy
Audit
```

Sensitive files must be blocked by policy unless explicitly authorized.

---

# 58. AUDIT LOGGING

Security-relevant browser operations should be auditable.

Examples:

```text
Session Created
Authentication Used
Domain Accessed
File Downloaded
File Uploaded
Form Submitted
Permission Granted
Permission Denied
Sensitive Action Approved
Sensitive Action Rejected
Browser Error
Recovery Performed
```

Audit logs should contain identifiers and metadata rather than raw secrets.

---

# 59. OBSERVABILITY

Browser execution must integrate with the global JARVIS observability system.

Required signals include:

### Metrics

```text
browser_tasks_total
browser_task_duration
browser_failures_total
browser_retries_total
browser_sessions_active
browser_pages_active
browser_downloads_total
browser_uploads_total
browser_memory_usage
```

### Logs

Structured events should include:

```text
task_id
agent_id
session_id
page_id
operation
domain
duration
result
error
```

Sensitive information must be redacted.

---

# 60. TRACING

Browser traces should be available for debugging and failure analysis.

Playwright provides browser tracing functionality capable of capturing browser operations and network activity for later inspection. citeturn0search6

Tracing should be configurable by environment:

```text
Development:
    detailed

Testing:
    detailed

Staging:
    configurable

Production:
    sampled / policy-controlled
```

Sensitive trace artifacts must be protected.

---

# 61. TESTING REQUIREMENTS

The browser subsystem requires multiple testing layers.

## Unit Tests

Test:

```text
Browser adapters
Policy checks
URL validation
Session management
Artifact handling
Timeout logic
Retry classification
```

## Integration Tests

Test:

```text
Playwright
Browser
Browser Context
Downloads
Uploads
Authentication
MCP
Tool Layer
```

## End-to-End Tests

Test complete workflows:

```text
User
 ↓
Agent
 ↓
Browser Tool
 ↓
Policy
 ↓
Browser
 ↓
Result
```

## Failure Tests

Test:

```text
Browser Crash
Network Failure
Timeout
Invalid Selector
Expired Session
Download Failure
Upload Failure
Popup
Redirect
Permission Denial
```

---

# 62. BROWSER SMOKE TEST

Bootstrap and CI should have a minimal browser smoke test.

Conceptually:

```text
Launch Browser
 ↓
Create Context
 ↓
Open Page
 ↓
Navigate to Test Target
 ↓
Read Expected Content
 ↓
Take Screenshot
 ↓
Close Context
 ↓
Close Browser
```

A failed smoke test should prevent the environment from being considered browser-ready.

---

# 63. REGRESSION TESTING

Browser automation is particularly vulnerable to website changes.

Therefore the project should maintain regression workflows for important integrations.

Examples:

```text
GitHub
Google
Calendar
Selected Research Sites
Selected University Portals
Selected User Services
```

Only systems explicitly approved for automated testing should be included.

---

# 64. WEBSITE COMPATIBILITY

JARVIS must not assume that every website is equally automatable.

Websites may differ in:

```text
DOM quality
Accessibility
Authentication
CAPTCHA
Rate limits
Dynamic rendering
Anti-automation mechanisms
WebSockets
Canvas
iframes
Shadow DOM
```

The browser agent must be able to report:

```text
AUTOMATABLE
PARTIALLY AUTOMATABLE
REQUIRES HUMAN ASSISTANCE
NOT SUPPORTED
```

---

# 65. CAPTCHA POLICY

JARVIS must not be designed around bypassing CAPTCHA or other anti-abuse mechanisms.

If a legitimate task encounters a CAPTCHA:

```text
Pause
 ↓
Notify / Request Human Action
 ↓
Resume if permitted
```

The system should treat CAPTCHA as a human-in-the-loop boundary rather than as an automation challenge to defeat.

---

# 66. RATE LIMITING

Browser automation must respect:

- website rate limits,
- robots and service policies where applicable,
- user-defined limits,
- task-specific limits.

JARVIS must avoid uncontrolled crawling or request amplification.

---

# 67. ANTI-BOT SYSTEMS

The architecture must not assume that browser automation can or should defeat anti-bot protections.

If a service prohibits automated interaction, the task should be stopped or routed through an approved API/integration if one exists.

---

# 68. BROWSER API VS BROWSER AUTOMATION

Where a stable official API exists and is appropriate, JARVIS should prefer the API over browser automation.

Decision hierarchy:

```text
Official API
     ↓
Approved MCP / Integration
     ↓
Browser Automation
     ↓
Vision / Human-Assisted Interaction
```

Browser automation should not be used simply because it is technically possible.

---

# 69. RESEARCH WORKFLOWS

Browser automation is especially useful for:

```text
Web Research
Information Retrieval
Interactive Websites
Sources without APIs
Form Navigation
Document Retrieval
Dynamic Web Applications
```

Research agents should combine:

```text
Browser
+
Search
+
Source Extraction
+
Citation / Provenance
```

rather than blindly treating browser output as verified truth.

---

# 70. DATA PROVENANCE

Browser-derived information should retain provenance where practical.

Possible metadata:

```text
URL
Domain
Timestamp
Page Title
Extraction Method
Screenshot Reference
Task ID
Agent ID
```

This is important for reproducible research.

---

# 71. ARTIFACT MANAGEMENT

Browser-generated artifacts may include:

```text
Downloads
Screenshots
PDFs
HTML
Trace Files
HAR-like Network Artifacts
Extracted Text
Page Snapshots
```

Artifacts should be stored through the JARVIS artifact/storage subsystem rather than arbitrary temporary locations.

---

# 72. FAILURE CLASSIFICATION

Browser errors should map to standardized categories.

Example:

```text
BROWSER_STARTUP_FAILURE
BROWSER_CRASH
CONTEXT_CREATION_FAILURE
NAVIGATION_FAILURE
TIMEOUT
ELEMENT_NOT_FOUND
ELEMENT_NOT_INTERACTABLE
AUTHENTICATION_FAILURE
SESSION_EXPIRED
DOWNLOAD_FAILURE
UPLOAD_FAILURE
NETWORK_FAILURE
POLICY_DENIED
PERMISSION_DENIED
SECURITY_VIOLATION
UNKNOWN_FAILURE
```

This enables agents and observability systems to reason about failures consistently.

---

# 73. POLICY ENGINE INTEGRATION

The browser capability must query the security/policy engine before sensitive operations.

Conceptually:

```text
Browser Request
      ↓
Risk Classification
      ↓
Policy Engine
      ↓
ALLOW / DENY / CONFIRM
      ↓
Execution
```

Examples:

```text
Open public webpage
→ ALLOW

Download PDF
→ ALLOW

Upload private document
→ CONFIRM

Submit bank transfer
→ CONFIRM / HIGH RISK

Delete account
→ CONFIRM / HIGH RISK
```

---

# 74. USER PERMISSION MODEL

Permissions should be granular.

Possible permission scopes:

```text
browser.read
browser.navigate
browser.interact
browser.download
browser.upload
browser.authentication
browser.submit
browser.external_message
browser.purchase
browser.high_risk
```

The exact permission taxonomy belongs to the security architecture, but browser capabilities must be designed to support it.

---

# 75. DATA PRIVACY

Browser sessions can expose:

```text
Personal Data
Cookies
Messages
Emails
Financial Data
Documents
Passwords
Browsing History
```

Therefore browser automation must be treated as a privacy-sensitive subsystem.

Logs, screenshots, traces and browser profiles must be governed accordingly.

---

# 76. DEVELOPMENT ENVIRONMENT

Developers should be able to run:

```text
Browser Automation
Headless
Headed
Debug
Trace
Screenshot
```

without requiring production infrastructure.

The local developer workflow should remain simple while preserving the same architectural interfaces used in production.

---

# 77. CI/CD

CI should execute:

```text
Browser Installation
Browser Smoke Tests
Unit Tests
Integration Tests
Selected E2E Tests
```

Browser binaries should be reproducibly provisioned.

CI failures must distinguish:

```text
Application Failure
Browser Failure
Infrastructure Failure
Website Regression
External Service Failure
```

---

# 78. VERSION LOCK REQUIREMENTS

The future Version Lock MUST capture at minimum:

```text
Browser Automation Framework
Framework Version
Browser Family
Browser Revision / Build
Runtime Version
Relevant Node/Python Dependency Versions
MCP Browser Server Version
Container Image / Digest where applicable
```

The exact structure will be defined by the Version Lock architecture.

---

# 79. MANIFEST REQUIREMENTS

Manifest should be capable of describing:

```yaml
browser:
  provider: playwright
  enabled: true
  browsers:
    - chromium
    - firefox
    - webkit
  headless_default: true
  persistent_profiles: controlled
  downloads: enabled
  uploads: policy_controlled
  tracing: configurable
  mcp: optional
```

This is conceptual only.

The final Manifest schema must be defined in the Manifest specification.

---

# 80. COMPLIANCE CHECKER REQUIREMENTS

The Architecture Compliance Checker should eventually validate:

```text
Approved Browser Framework
Browser Adapter Exists
Direct Playwright Access Restricted
Browser Tool Boundary Exists
Security Policy Integration Exists
Session Isolation Enabled
Credential Isolation Enabled
Artifact Storage Compliant
Logging Redaction Enabled
Version Lock Compliance
Manifest Compliance
```

Potential violation:

```text
Agent
 ↓
Direct Playwright API
```

should be considered an architectural violation.

Correct:

```text
Agent
 ↓
Browser Tool
 ↓
Policy
 ↓
Browser Capability
 ↓
Adapter
 ↓
Playwright
```

---

# 81. DEFINITION OF DONE

The browser automation stack is considered operationally complete only when:

```text
[ ] Playwright approved
[ ] Browser adapter defined
[ ] Browser capability interface defined
[ ] Session model defined
[ ] Permission model integrated
[ ] Authentication model integrated
[ ] Artifact handling integrated
[ ] Download handling implemented
[ ] Upload handling implemented
[ ] Screenshot support implemented
[ ] Observability integrated
[ ] Tracing available
[ ] Retry/recovery implemented
[ ] Browser smoke test implemented
[ ] Windows validated
[ ] Linux validated
[ ] CI browser tests implemented
[ ] Version Lock integrated
[ ] Manifest integrated
[ ] Compliance checks implemented
```

---

# 82. APPROVAL STATUS

Final status:

```text
┌─────────────────────────────────────────────┐
│ BROWSER AUTOMATION STACK                    │
├─────────────────────────────────────────────┤
│ Primary Framework: Playwright               │
│ Status: APPROVED                            │
│                                             │
│ Selenium: Secondary / Alternative           │
│ Status: CONDITIONALLY APPROVED              │
│                                             │
│ Puppeteer: Alternative / Watch              │
│ Status: NOT PRIMARY                         │
└─────────────────────────────────────────────┘
```

Playwright is therefore the approved primary browser automation technology for JARVIS v1 architecture.

---

# 83. WHY PLAYWRIGHT WAS SELECTED

The decision is based on architectural fit rather than popularity.

The strongest reasons are:

1. Multi-browser support.
2. Strong browser-context isolation.
3. Modern web application support.
4. Strong automation API.
5. Authentication-state support.
6. Download/upload capabilities.
7. Screenshots and tracing.
8. Strong TypeScript and Python support.
9. Agent-oriented positioning.
10. MCP integration ecosystem.
11. Good fit with JARVIS's browser-agent architecture.
12. Ability to preserve a future adapter boundary.

The decision is therefore:

```text
Playwright
    ↓
Best Current Fit
    ↓
APPROVED
```

rather than:

```text
Playwright
    ↓
Permanent Irreplaceable Dependency
```

The adapter boundary remains mandatory.

---

# 84. REJECTED / NON-PRIMARY TECHNOLOGIES

## Selenium

Not rejected as a technology.

Status:

```text
CONDITIONALLY APPROVED
```

Reason for not selecting as primary:

```text
JARVIS's agent-oriented browser architecture
+
modern context/session requirements
+
desired developer experience
+
Playwright's overall fit
```

---

## Puppeteer

Not rejected.

Status:

```text
ALTERNATIVE / WATCH
```

Reason for not selecting as primary:

```text
Playwright provides a better overall fit for
JARVIS's multi-browser architecture.
```

Puppeteer remains relevant and should be periodically reevaluated.

---

# 85. FUTURE TECHNOLOGY WATCH

The browser subsystem should monitor:

```text
WebDriver BiDi
Browser-native AI interfaces
Browser agent protocols
Computer-use APIs
Browser MCP implementations
Remote browser infrastructure
Browser sandboxing
Cloud browser execution
Local browser isolation
AI-native browser runtimes
```

WebDriver BiDi is particularly important because it is designed as a bidirectional browser automation protocol and is being adopted across browser automation ecosystems. Selenium and Puppeteer both expose ongoing BiDi support. citeturn0search7turn0search10

However:

```text
Emerging
≠
Approved
```

Future technologies must go through the normal Approved Stack governance process.

---

# 86. FUTURE ARCHITECTURE

The intended long-term browser architecture is:

```text
                       JARVIS
                          │
                          ▼
                  Agent Orchestrator
                          │
                          ▼
                    Browser Tool
                          │
                          ▼
                   Policy Engine
                          │
                 ┌────────┴────────┐
                 ▼                 ▼
          Browser Capability    Audit/Trace
                 │
                 ▼
            Browser Adapter
                 │
                 ▼
             Playwright
                 │
       ┌─────────┼─────────┐
       ▼         ▼         ▼
   Chromium   Firefox   WebKit
       │
       ▼
    Websites
```

MCP may connect at the integration boundary:

```text
External Agent / MCP Client
          │
          ▼
    Playwright MCP
          │
          ▼
      Playwright
```

but MCP must remain optional from the perspective of the JARVIS internal browser architecture.

---

# 87. FINAL ARCHITECTURAL RULES

The following rules are mandatory.

### Rule 1

**Playwright is the approved primary browser automation framework.**

### Rule 2

**Agents must not directly depend on Playwright.**

### Rule 3

**Browser access must pass through a JARVIS browser capability/tool boundary.**

### Rule 4

**Security and policy checks must occur before sensitive browser operations.**

### Rule 5

**Browser sessions must be isolated by default.**

### Rule 6

**Credentials and authentication state must be handled through the security subsystem.**

### Rule 7

**Downloads are untrusted artifacts until validated.**

### Rule 8

**Uploads require explicit policy authorization.**

### Rule 9

**High-risk browser actions require human approval unless explicitly governed otherwise by a future security policy.**

### Rule 10

**Browser failures must be observable and classifiable.**

### Rule 11

**Retry logic must distinguish transient failures from side-effect uncertainty.**

### Rule 12

**The browser runtime must be reproducible through Version Lock and Bootstrap.**

### Rule 13

**Browser versions and binaries must be treated as part of the runtime dependency graph.**

### Rule 14

**MCP is an integration mechanism, not the browser runtime itself.**

### Rule 15

**The browser adapter boundary must remain replaceable.**

### Rule 16

**Official APIs should be preferred over browser automation when an approved API provides the required capability.**

### Rule 17

**CAPTCHA and anti-abuse systems must not be treated as mechanisms to bypass.**

### Rule 18

**No browser automation capability may silently expand into unrestricted host-system access.**

---

# 88. SOURCE BASIS

This document's technology evaluation is based primarily on the official documentation and repositories of the evaluated projects.

Primary references include:

- Playwright official documentation — browser support, installation and browser lifecycle.
- Playwright official documentation — BrowserContext, pages, authentication, downloads and tracing.
- Playwright official repository — licensing and project metadata.
- Selenium official documentation — WebDriver and WebDriver BiDi.
- Puppeteer official documentation — browser and WebDriver BiDi support.

The exact technology versions SHALL NOT be frozen by this document.

They belong to:

```text
VERSION LOCK v1
```

---

# 89. HANDOFF TO NEXT ARCHITECTURAL PHASE

After this document is approved, the browser-related decisions flow into:

```text
07_BROWSER_AUTOMATION_STACK.md
            │
            ▼
      Version Lock v1
            │
            ▼
        Manifest v1
            │
            ▼
       Bootstrap v1
            │
            ▼
 Architecture Compliance Checker
            │
            ▼
     Browser Runtime
            │
            ▼
       Browser Agent
```

No exact package version should be invented or frozen during this phase.

The next phase will determine the exact reproducible browser dependency set.

---

# 90. FINAL DECISION

```text
====================================================
JARVIS BROWSER AUTOMATION STACK — FINAL v1 DECISION
====================================================

PRIMARY:
    Playwright

STATUS:
    APPROVED

BROWSER TARGETS:
    Chromium
    Firefox
    WebKit

SECONDARY:
    Selenium

STATUS:
    CONDITIONALLY APPROVED / FALLBACK

ALTERNATIVE:
    Puppeteer

STATUS:
    NOT PRIMARY / WATCH

ARCHITECTURAL REQUIREMENT:
    Browser Adapter

SECURITY REQUIREMENT:
    Policy + Permission + Audit

SESSION DEFAULT:
    Isolated

AUTHENTICATION:
    Security-subsystem controlled

HIGH-RISK ACTIONS:
    Human approval required

MCP:
    Optional integration layer

VERSION:
    Deferred to Version Lock

BOOTSTRAP:
    Mandatory browser provisioning + verification

COMPLIANCE:
    Direct agent-to-Playwright access prohibited
====================================================
```

**Decision:** Playwright is the approved primary browser automation technology for JARVIS v1.