# 10 — FRONTEND STACK

**Document ID:** JAS-AS-10  
**Document:** `10_FRONTEND_STACK.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Status:** APPROVED STACK SPECIFICATION  
**Version:** v1.0  
**Authority:** JAS v1  
**Depends On:** JAS v1, `00_APPROVED_STACK_OVERVIEW.md`, `01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md`, `02_CORE_RUNTIME_AND_PROGRAMMING_LANGUAGES.md`, `03_AI_AND_LLM_FRAMEWORKS.md`, `11_BACKEND_STACK.md`, `14_SECURITY_STACK.md`  
**Related Documents:** `07_BROWSER_AUTOMATION_STACK.md`, `08_VOICE_AND_AUDIO_STACK.md`, `09_COMPUTER_VISION_STACK.md`, `12_PLUGIN_AND_EXTENSION_STACK.md`, `13_MCP_AND_EXTERNAL_INTEGRATION_STACK.md`, `16_MONITORING_AND_OBSERVABILITY_STACK.md`, `17_TESTING_AND_QUALITY_ASSURANCE_STACK.md`, `18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md`  
**Feeds Into:** Version Lock, Manifest, Bootstrap, Compliance Checker, JARVIS Frontend, Desktop Client, Web Client

---

# 1. PURPOSE

This document defines the frontend architecture and approved technology direction for JARVIS.

The frontend is not considered merely a visual interface.

It is the primary human interaction layer through which the user interacts with:

```text
JARVIS
Agents
Tasks
Memory
Voice
Vision
Browser
Tools
Plugins
MCP
System State
Permissions
Notifications
Observability
Settings
```

The frontend must therefore function as:

> **JARVIS Human–AI Interaction Platform**

rather than simply:

> **Chat UI**

---

# 2. ARCHITECTURAL OBJECTIVE

The frontend architecture must support:

```text
Text Interaction
Voice Interaction
Visual Interaction
Agent Activity
Task Management
Tool Execution
Memory Interaction
System Monitoring
Permission Requests
Notifications
Configuration
Debugging
Administration
```

The intended architecture is:

```text
                         USER
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
        Text             Voice            Vision
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                    FRONTEND CLIENT
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
       ▼                   ▼                   ▼
    UI State          Server State        Event Stream
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                    Frontend Services
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
           REST          WebSocket      SSE*
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                       BACKEND
                           │
                           ▼
                     JARVIS CORE
```

`*` SSE may be used where appropriate; WebSocket is preferred for bidirectional real-time interaction.

---

# 3. CORE DESIGN PRINCIPLES

## 3.1 Frontend Is Not JARVIS Core

The frontend must never contain the actual intelligence of JARVIS.

Correct:

```text
Frontend
   ↓
API / Event Interface
   ↓
Backend
   ↓
JARVIS Core
```

Not:

```text
Frontend
   ↓
LLM
   ↓
Tools
   ↓
Operating System
```

The frontend is an interaction layer.

---

# 4. FRONTEND RESPONSIBILITIES

The frontend is responsible for:

```text
Rendering
User Interaction
Input Collection
Output Presentation
Local UI State
Server State Consumption
Streaming Display
Permission Prompts
Task Visualization
Agent Visualization
Error Presentation
Notifications
Settings
Accessibility
Responsive Layout
Desktop Integration
```

The frontend is not responsible for:

```text
Agent Planning
Tool Authorization
Security Policy
Memory Governance
Model Selection
Secrets Management
OS-Level Authorization
Business-Critical State
```

---

# 5. PRIMARY FRONTEND LANGUAGE

**Selected Language: TypeScript**

Status:

```text
APPROVED
```

TypeScript will be the primary language for the JARVIS frontend.

The frontend should use strict TypeScript configuration.

Preferred:

```text
Type Safety
Strict Null Checks
Explicit Interfaces
Typed API Contracts
Typed Events
Typed State
```

---

# 6. WHY TYPESCRIPT

JARVIS frontend communication will involve complex structures such as:

```text
Agent Events
Tool Calls
Tool Results
Memory Records
Permission Requests
Streaming Tokens
Task States
System Health
Vision Observations
Voice Events
Plugin Metadata
MCP Events
```

These structures benefit significantly from compile-time typing.

The objective is to prevent situations such as:

```text
Backend:
tool_status = "awaiting_approval"

Frontend:
tool_status === "waiting"
```

from reaching runtime.

---

# 7. FRONTEND FRAMEWORK

**Selected Framework: React**

Status:

```text
APPROVED
```

React is selected as the primary frontend UI framework.

React 19 is currently stable according to the official React documentation. citeturn0search16

---

# 8. WHY REACT

React provides:

```text
Component Model
State Integration
Large Ecosystem
TypeScript Support
Server Communication Integration
Streaming UI Compatibility
Desktop Shell Compatibility
Testing Ecosystem
Long-Term Ecosystem Depth
```

React is also well suited to JARVIS because the interface will contain many independently updating surfaces:

```text
Chat
Agent Status
Task Status
Voice State
System Health
Tool Activity
Notifications
Memory
Settings
```

---

# 9. REACT ARCHITECTURE

The frontend should be component-oriented.

Conceptually:

```text
Application
│
├── Shell
│
├── Navigation
│
├── Chat
│
├── Voice
│
├── Agents
│
├── Tasks
│
├── Tools
│
├── Memory
│
├── Browser
│
├── Vision
│
├── Permissions
│
├── Notifications
│
├── System
│
└── Settings
```

---

# 10. COMPONENT DESIGN

Components should preferably follow:

```text
Small
Composable
Typed
Testable
Accessible
Predictable
```

Large monolithic components should be avoided.

---

# 11. FRONTEND BOUNDARIES

The frontend should maintain explicit boundaries:

```text
UI
 ↓
View Model / Hooks
 ↓
Frontend Services
 ↓
API / Event Client
 ↓
Backend
```

UI components should not directly contain arbitrary `fetch()` calls.

---

# 12. API CLIENT

The frontend should have a centralized API client.

Conceptually:

```text
frontend/
└── services/
    └── api/
        ├── client
        ├── auth
        ├── agents
        ├── tasks
        ├── memory
        ├── tools
        ├── system
        └── settings
```

The exact folder structure belongs to implementation.

---

# 13. SERVER STATE VS CLIENT STATE

One of the most important architectural decisions is separating:

```text
Server State
```

from:

```text
Client State
```

They must not be treated as the same thing.

---

# 14. SERVER STATE

Server state includes:

```text
Tasks
Agents
Conversations
Memory
System Status
Tool Results
Configuration
Backend Resources
Persistent Data
```

This state originates outside the browser process.

---

# 15. CLIENT STATE

Client state includes:

```text
Sidebar Open
Selected Conversation
Current Tab
Modal Open
Theme
Temporary Input
UI Preferences
Active Panel
Local Interaction State
```

This state primarily belongs to the frontend.

---

# 16. SERVER STATE MANAGEMENT

**Selected Technology: TanStack Query**

Status:

```text
APPROVED
```

TanStack Query is designed around asynchronous server data, caching, refetching, mutations and query state. The current documentation identifies `@tanstack/react-query` as the React integration. citeturn0search4turn0search5

---

# 17. WHY TANSTACK QUERY

JARVIS will frequently need:

```text
Fetch
Cache
Invalidate
Refetch
Retry
Mutation
Background Update
Loading State
Error State
```

TanStack Query provides an established abstraction for this class of problem.

---

# 18. TANSTACK QUERY RESPONSIBILITIES

It should manage:

```text
API Queries
Server Resource Cache
Mutations
Invalidation
Refetching
Retry
Loading States
Error States
```

It should not be used as the universal application state container.

---

# 19. CLIENT STATE MANAGEMENT

**Selected Technology: Zustand**

Status:

```text
APPROVED
```

Zustand is a lightweight state-management library designed around small stores and hooks, with support for TypeScript and vanilla stores. citeturn1search1turn1search4

---

# 20. WHY ZUSTAND

JARVIS does not need a giant global Redux-style state tree for every UI interaction.

Examples of suitable Zustand state:

```text
UI Preferences
Navigation
Active Workspace
Voice UI State
Temporary UI State
Desktop Window State
Local Interaction State
```

---

# 21. ZUSTAND POLICY

Zustand must not become a dumping ground for all application state.

Incorrect:

```text
Everything
 ↓
Global Store
```

Correct:

```text
Server Data
 ↓
TanStack Query

Local UI State
 ↓
Zustand

Component-only State
 ↓
React State
```

---

# 22. REACT LOCAL STATE

Simple component-local state should remain in React where practical.

Example:

```text
Dropdown Open
Input Value
Hover State
Temporary Animation State
```

No external store is required unless the state crosses component boundaries.

---

# 23. FRONTEND BUILD TOOL

**Selected Technology: Vite**

Status:

```text
APPROVED
```

Vite will serve as the primary frontend development and build tool.

The Vite documentation provides built-in production build functionality and dependency license reporting through its build tooling. citeturn0search20

---

# 24. WHY VITE

JARVIS frontend development benefits from:

```text
Fast Development Server
Fast HMR
Modern ESM
TypeScript Integration
Simple Configuration
Production Bundling
Plugin Ecosystem
Desktop Shell Compatibility
```

Vite also works naturally with React and is suitable for both browser deployment and desktop shells.

---

# 25. VITE ROLE

Vite is responsible for:

```text
Development Server
Module Bundling
Asset Processing
Production Build
Environment Configuration
Frontend Build Pipeline
```

It is not responsible for:

```text
Backend
Agent Execution
Security
Authentication
Persistent State
```

---

# 26. NEXT.JS EVALUATION

Next.js is a React framework for building full-stack web applications. Its official documentation describes automatic configuration of lower-level build/compiler tooling and support for interactive React applications. citeturn0search15

Status:

```text
CONDITIONALLY APPROVED
```

Next.js is not selected as the default JARVIS frontend runtime.

---

# 27. WHY NEXT.JS IS NOT DEFAULT

JARVIS has a different primary requirement from a conventional content-heavy web application.

The frontend is primarily:

```text
Interactive
Realtime
Local
Stateful
Desktop-oriented
Agent-oriented
Streaming
```

rather than:

```text
SEO-heavy
Content-heavy
Server-rendered
Public website
```

Therefore the additional Next.js server architecture is not automatically justified.

---

# 28. WHEN NEXT.JS MAY BE USED

Next.js may be appropriate for separate products such as:

```text
Public JARVIS Website
Documentation
Marketing Site
Account Portal
Public Dashboard
Cloud Management Portal
```

These may be separate applications.

---

# 29. JARVIS CORE UI VS PUBLIC WEB

The architecture should allow:

```text
JARVIS Desktop UI
        +
JARVIS Web UI
        +
Public Web
```

to share:

```text
Design System
Type Definitions
API Client
UI Components
```

where practical.

---

# 30. STYLING SYSTEM

**Selected Technology: Tailwind CSS**

Status:

```text
APPROVED
```

Tailwind CSS v4 introduced a redesigned engine and modern CSS-based configuration approach. Its current compatibility documentation targets modern browsers, with core v4 support beginning at Chrome 111, Safari 16.4 and Firefox 128. citeturn0search14turn0search17

---

# 31. WHY TAILWIND

Tailwind provides:

```text
Consistent Styling
Design Tokens
Responsive Utilities
Rapid UI Development
Theme Support
Dark Mode
Component Composition
```

It also reduces the need for a large custom CSS architecture.

---

# 32. TAILWIND POLICY

Tailwind must not be used to create arbitrary visual inconsistency.

The project should define:

```text
Spacing
Typography
Colors
Radius
Shadows
Motion
Breakpoints
Z-Index
```

as design tokens.

---

# 33. DESIGN SYSTEM

JARVIS should have an internal design system.

Conceptually:

```text
JARVIS Design System
│
├── Typography
├── Colors
├── Spacing
├── Buttons
├── Inputs
├── Dialogs
├── Menus
├── Cards
├── Panels
├── Notifications
├── Command Palette
├── Chat Components
└── Status Components
```

---

# 34. COMPONENT LIBRARY POLICY

The project should prefer accessible primitives over large opinionated UI frameworks when possible.

Potential candidates may include:

```text
Radix UI
Headless UI
Custom Accessible Components
```

Exact component-library selection should be finalized after dedicated evaluation.

---

# 35. UI LIBRARY STATUS

No large monolithic UI component framework is mandatory for v1.

Status:

```text
DEFERRED / EVALUATION REQUIRED
```

Reason:

```text
JARVIS requires a highly custom interface.
```

---

# 36. ACCESSIBILITY

Accessibility is a core requirement.

The frontend should target:

```text
Keyboard Navigation
Screen Readers
Focus Management
ARIA
Reduced Motion
Readable Contrast
Semantic HTML
Accessible Dialogs
Accessible Forms
```

Accessibility must be tested rather than assumed.

---

# 37. RESPONSIVE DESIGN

The UI should support:

```text
Desktop
Laptop
Tablet
Mobile Web
```

However, the primary JARVIS experience is desktop.

The interface should not sacrifice desktop functionality merely to optimize mobile.

---

# 38. DESKTOP-FIRST DESIGN

The primary interaction surface is expected to be:

```text
Windows Desktop
```

with future support for:

```text
Linux
macOS
```

The UI should therefore support:

```text
Large Workspace
Multi-panel Layout
Sidebars
Command Palette
Task Panels
System Panels
Persistent Chat
Voice Controls
```

---

# 39. DESKTOP SHELL

**Selected Technology: Tauri 2**

Status:

```text
APPROVED CANDIDATE / PREFERRED DESKTOP SHELL
```

Tauri is designed to build desktop applications using web frontends and native system integration, and its project is distributed under MIT/Apache-2.0 licensing where applicable. citeturn1search0

---

# 40. WHY TAURI

JARVIS needs desktop capabilities such as:

```text
System Tray
Global Shortcuts
Notifications
Window Management
Native File Access
Microphone
Camera
Screen Capture
Auto Start
System Integration
```

Tauri provides a bridge between:

```text
Web UI
```

and:

```text
Native Desktop
```

without requiring the entire application to embed a full Chromium runtime.

---

# 41. TAURI ARCHITECTURE

The preferred architecture is:

```text
                 JARVIS Desktop
                       │
               ┌───────┴───────┐
               │               │
               ▼               ▼
          React Frontend     Tauri
               │               │
               │               ▼
               │          Native Layer
               │               │
               └───────┬───────┘
                       ▼
                  JARVIS Backend
```

---

# 42. TAURI SECURITY

The frontend must not receive unrestricted native permissions.

Tauri capabilities should be configured according to least privilege.

Conceptually:

```text
Frontend
 ↓
Allowed Capability
 ↓
Native API
```

not:

```text
Frontend
 ↓
Unrestricted OS
```

---

# 43. TAURI COMMAND POLICY

Native operations should use explicit command interfaces.

Examples:

```text
Open File
Save File
Show Notification
Get System Info
Manage Window
```

Each command should have:

```text
Input Validation
Authorization
Error Handling
Auditability
```

where relevant.

---

# 44. ELECTRON EVALUATION

Electron is a mature framework for building cross-platform desktop applications with JavaScript, HTML and CSS by embedding Chromium and Node.js. citeturn0search12

Status:

```text
CONDITIONALLY APPROVED
```

---

# 45. WHY ELECTRON IS NOT DEFAULT

Electron is technically strong and mature.

However, for JARVIS:

```text
Chromium Runtime
+
Node.js Runtime
+
Desktop Application
```

creates a larger runtime footprint than the preferred Tauri architecture.

Tauri therefore becomes the default desktop-shell direction.

---

# 46. ELECTRON FALLBACK

Electron may be reconsidered if future requirements demonstrate that:

```text
Browser Compatibility
Electron Ecosystem
Node Integration
Web API Requirements
```

provide a meaningful advantage over Tauri.

---

# 47. DESKTOP DECISION

```text
Tauri 2
    ↓
Preferred

Electron
    ↓
Conditional Alternative
```

The frontend itself remains:

```text
React + TypeScript
```

regardless of desktop shell.

---

# 48. WEB APP ARCHITECTURE

The frontend should remain usable as a normal web application.

Conceptually:

```text
Browser
  ↓
React
  ↓
Vite
  ↓
JARVIS API
  ↓
Backend
```

This provides:

```text
Remote Access
Development
Administration
Mobile Web
Browser-based UI
```

where security policy permits.

---

# 49. DESKTOP APP ARCHITECTURE

Desktop:

```text
Tauri
  ↓
React
  ↓
Frontend Services
  ↓
Backend / Local JARVIS
```

The frontend should not assume that it always runs inside Tauri.

---

# 50. RUNTIME DETECTION

The frontend may detect:

```text
Web
Desktop
Development
Production
```

but feature availability must be capability-driven rather than hard-coded.

Example:

```text
supports:
  camera: true
  system_tray: true
  filesystem: false
```

---

# 51. CAPABILITY MODEL

The frontend should consume a capability description from the backend/native layer.

Conceptually:

```yaml
capabilities:
  voice: true
  vision: true
  browser: true
  filesystem: false
  notifications: true
  global_hotkeys: true
```

The UI can then adapt.

---

# 52. CHAT INTERFACE

Chat is one frontend surface, not the entire architecture.

The chat UI should support:

```text
Messages
Streaming
Tool Calls
Tool Results
Attachments
Images
Audio
Citations
Errors
Agent State
Approval Requests
```

---

# 53. STREAMING

JARVIS responses may be streamed.

Example:

```text
User
 ↓
Request
 ↓
Backend
 ↓
LLM
 ↓
Token/Event Stream
 ↓
Frontend
```

The frontend must render incremental responses without blocking the UI.

---

# 54. STREAM TYPES

The event stream should support more than tokens.

Possible events:

```text
message.started
message.delta
message.completed

agent.started
agent.progress
agent.completed

tool.started
tool.awaiting_approval
tool.completed
tool.failed

voice.started
voice.partial
voice.completed

vision.started
vision.observation

task.started
task.progress
task.completed
```

Exact event schemas belong to backend/API contracts.

---

# 55. EVENT-DRIVEN UI

The frontend should be event-driven for real-time JARVIS activity.

Instead of polling continuously:

```text
GET /status
GET /status
GET /status
```

prefer:

```text
Backend
 ↓
Event Stream
 ↓
Frontend
```

when real-time state is required.

---

# 56. WEBSOCKET

WebSocket is the preferred transport for:

```text
Bidirectional Realtime Communication
Voice Sessions
Agent Activity
Interactive Tasks
Streaming Events
```

---

# 57. SERVER-SENT EVENTS

SSE may be used for:

```text
Server → Client Streaming
```

when bidirectional communication is unnecessary.

However, the frontend architecture must not depend on one transport implementation.

---

# 58. EVENT ABSTRACTION

The UI should consume:

```text
EventClient
```

rather than raw WebSocket APIs throughout the component tree.

Conceptually:

```text
WebSocket / SSE
       ↓
Event Client
       ↓
Typed Events
       ↓
Application State
       ↓
UI
```

---

# 59. EVENT RECONNECTION

Realtime connections must support:

```text
Disconnect
Reconnect
Backoff
Session Recovery
Event Ordering
Duplicate Detection
```

---

# 60. OFFLINE / DEGRADED STATE

The frontend should detect:

```text
Backend Offline
Network Unavailable
Connection Lost
Authentication Expired
Service Degraded
```

and present clear state to the user.

---

# 61. CHAT MESSAGE MODEL

Messages should not be plain strings only.

Conceptually:

```yaml
message:
  id: ...
  role: user
  timestamp: ...
  content:
    - type: text
      value: ...
  attachments: []
  metadata: {}
```

This allows future multimodal interaction.

---

# 62. MULTIMODAL INPUT

Frontend should support:

```text
Text
Image
Audio
File
Screenshot
Camera
```

as distinct input types.

---

# 63. ATTACHMENTS

Attachments must include:

```text
File ID
Name
Type
Size
Hash
Upload Status
Security Status
```

where applicable.

---

# 64. FILE UPLOAD SECURITY

The frontend should not assume uploaded files are safe.

The backend must perform:

```text
Validation
Scanning
Type Detection
Size Limits
Policy Enforcement
```

Frontend validation is only a UX layer.

---

# 65. VOICE UI

The frontend must integrate with the Voice & Audio Stack.

Conceptual state:

```text
IDLE
 ↓
LISTENING
 ↓
PROCESSING
 ↓
THINKING
 ↓
SPEAKING
 ↓
INTERRUPTED
 ↓
IDLE
```

---

# 66. VOICE VISUALIZATION

The UI may expose:

```text
Microphone Status
Listening Indicator
Waveform
Transcription
Response Streaming
Speaking Indicator
Interrupt Control
```

---

# 67. VOICE PERMISSIONS

The frontend must clearly indicate:

```text
Microphone Available
Microphone Permission
Microphone Active
Microphone Muted
```

No hidden microphone activation.

---

# 68. VISION UI

The frontend must integrate with the Computer Vision Stack.

Potential surfaces:

```text
Camera Preview
Screen Preview
Vision Observation
OCR Results
Detected Objects
Visual Context
```

---

# 69. VISION PRIVACY UI

When camera or screen capture is active, the UI should provide a clear indication.

Examples:

```text
CAMERA ACTIVE
SCREEN SHARING ACTIVE
```

The user should be able to revoke access where supported.

---

# 70. AGENT ACTIVITY UI

JARVIS should expose what the system is doing without overwhelming the user.

Example:

```text
JARVIS
  └─ Planning
      └─ Research Agent
          └─ Browser
              └─ Reading page
```

---

# 71. AGENT TRACE

The frontend may display:

```text
Agent
Task
Tool
Status
Duration
Result
```

but sensitive internal reasoning should not be exposed automatically.

---

# 72. CHAIN-OF-THOUGHT POLICY

The frontend must not expose hidden chain-of-thought.

Instead, it may expose safe structured summaries such as:

```text
Planning
Searching
Comparing sources
Running tool
Waiting for approval
```

---

# 73. TOOL EXECUTION UI

When a tool runs:

```text
Tool
 ↓
Frontend Event
 ↓
Tool Activity Card
```

Example:

```text
Browser Tool
Status: Running
Target: example.com
Duration: 2.3s
```

---

# 74. TOOL APPROVAL UI

High-risk tools should produce an explicit approval surface.

Example:

```text
JARVIS wants to:
Delete 3 files

[Cancel]
[Approve]
```

---

# 75. PERMISSION UX

Permissions should be understandable.

Avoid:

```text
Allow capability #42?
```

Prefer:

```text
JARVIS wants permission to access:
Your Downloads folder
```

---

# 76. PERMISSION SCOPE

Permission UI should communicate:

```text
What
Why
Duration
Scope
Risk
```

where practical.

---

# 77. MEMORY UI

The frontend may expose memory management:

```text
Remembered Information
Preferences
Projects
Events
Procedures
Memory Sources
Delete
Forget
Edit
```

---

# 78. MEMORY PRIVACY

The user should be able to:

```text
Inspect
Delete
Correct
Disable
```

memory where supported by backend policy.

---

# 79. TASK MANAGEMENT

Long-running tasks need a dedicated UI.

Example:

```text
Task
├── Status
├── Started
├── Progress
├── Agent
├── Tools
├── Result
└── Errors
```

---

# 80. BACKGROUND TASKS

The frontend must distinguish:

```text
Interactive Request
```

from:

```text
Background Task
```

Examples:

```text
Research report
Long-running coding task
Scheduled automation
File processing
Video analysis
```

---

# 81. NOTIFICATIONS

Frontend notification system should support:

```text
Success
Info
Warning
Error
Approval
Task Complete
System Alert
```

---

# 82. SYSTEM STATUS

The UI should expose system health at an appropriate level.

Example:

```text
JARVIS
● Online

LLM
● Available

Voice
● Available

Vision
● Available

Browser
● Available
```

---

# 83. DETAILED HEALTH

Advanced users may inspect:

```text
CPU
RAM
GPU
VRAM
Services
Models
Database
Queue
Latency
Errors
```

This belongs in an optional diagnostics interface.

---

# 84. OBSERVABILITY UI

The frontend may consume observability data from the backend.

It should never directly connect to internal monitoring infrastructure unless explicitly designed and secured.

---

# 85. LOG VIEWER

An administrative log viewer may support:

```text
Timestamp
Level
Service
Trace ID
Task ID
Message
Metadata
```

---

# 86. TRACE VISUALIZATION

JARVIS activity may be represented as:

```text
Request
 ↓
Agent
 ↓
LLM
 ↓
Tool
 ↓
Browser
 ↓
Result
```

with timing.

This is valuable for debugging.

---

# 87. THEME

The frontend should support:

```text
Dark
Light
System
```

with dark mode as a first-class JARVIS experience.

---

# 88. DESIGN LANGUAGE

The JARVIS design language should prioritize:

```text
Clarity
Low Visual Noise
Information Density
Strong Hierarchy
Fast Interaction
Technical Aesthetic
Accessibility
```

The UI should avoid becoming a decorative dashboard with little operational value.

---

# 89. COMMAND PALETTE

A global command palette is strongly recommended.

Example:

```text
Ctrl + K

Search JARVIS
Run task
Open memory
Open settings
Start voice
Open browser
Show agents
```

---

# 90. GLOBAL SHORTCUTS

Desktop shell may provide:

```text
Wake JARVIS
Open Window
Start Voice
Stop Voice
Command Palette
```

through approved native integrations.

---

# 91. SYSTEM TRAY

Desktop application should eventually support:

```text
JARVIS Running
Open
Pause
Voice
Settings
Quit
```

from the system tray.

---

# 92. WINDOW MANAGEMENT

The desktop UI may support:

```text
Main Window
Compact Window
Always-on-top Mode
Mini Assistant
Picture-in-picture-like surfaces
```

where technically justified.

---

# 93. MULTI-WINDOW POLICY

Multiple windows must share controlled application state.

The system should avoid independent conflicting stores.

---

# 94. FRONTEND SECURITY MODEL

The frontend is an untrusted presentation surface from the backend's perspective.

The backend must never rely on:

```text
Frontend says:
"I am authorized."
```

Authorization must happen server-side.

---

# 95. AUTHENTICATION

The frontend may manage:

```text
Login
Session
Refresh
Logout
```

but authentication authority belongs to backend/security infrastructure.

---

# 96. SECRET MANAGEMENT

Secrets must never be embedded in:

```text
React
JavaScript bundle
Vite environment variables exposed to client
HTML
Local Storage
```

unless the value is explicitly public.

---

# 97. API KEYS

API keys belong in:

```text
Backend
Secret Store
OS Credential Store
```

depending on deployment.

The frontend should receive capability results, not raw provider credentials.

---

# 98. XSS PROTECTION

The frontend must avoid unsafe HTML rendering.

User-generated:

```text
Markdown
HTML
Tool Output
Browser Content
OCR
MCP Content
```

must be treated as untrusted.

---

# 99. PROMPT INJECTION UI

The frontend must visually distinguish trusted system information from external content.

Example:

```text
Browser content
OCR output
MCP result
Uploaded document
```

must not visually appear as if it were a system instruction.

---

# 100. CONTENT SANITIZATION

Any HTML or rich content rendering must use approved sanitization mechanisms.

Raw:

```text
dangerouslySetInnerHTML
```

should be prohibited unless explicitly justified and reviewed.

---

# 101. CSP

The production web frontend should use an appropriate Content Security Policy.

The exact policy belongs to deployment/security configuration.

---

# 102. LOCAL STORAGE POLICY

Local storage may contain:

```text
Non-sensitive UI Preferences
Theme
Layout
```

but should not contain:

```text
API Keys
Access Tokens where avoidable
Passwords
Secrets
Sensitive Memory
```

---

# 103. AUTH TOKEN POLICY

Authentication token storage must be determined with the security architecture.

The frontend must not independently invent token-storage rules.

---

# 104. DESKTOP SECURITY

Tauri capabilities should be explicitly scoped.

Desktop native commands must use:

```text
Allowlist / Capability Model
Validation
Least Privilege
```

---

# 105. PLUGIN UI

Plugins may provide frontend capabilities.

However, plugins must not receive unrestricted access to the entire React application.

Preferred:

```text
Plugin
 ↓
Extension Contract
 ↓
Sandbox / Capability Boundary
 ↓
UI Surface
```

---

# 106. PLUGIN COMPONENTS

Potential plugin UI capabilities:

```text
Panel
Card
Command
Settings Page
Status Widget
Chat Tool
```

---

# 107. MCP UI

MCP tools should be represented through standardized frontend components where possible.

Example:

```text
MCP Tool
 ↓
Tool Metadata
 ↓
Generic Tool UI
```

rather than custom UI for every server.

---

# 108. DESIGN SYSTEM + PLUGINS

Plugins should consume JARVIS design tokens rather than introducing completely unrelated visual systems.

---

# 109. FRONTEND PACKAGE STRUCTURE

Conceptually:

```text
frontend/
│
├── app/
├── components/
├── features/
├── hooks/
├── services/
├── state/
├── api/
├── events/
├── types/
├── styles/
├── assets/
├── tests/
└── desktop/
```

The exact repository structure belongs to implementation.

---

# 110. FEATURE-BASED ORGANIZATION

Where the project becomes large, feature-oriented organization is preferred.

Example:

```text
features/
├── chat/
├── voice/
├── vision/
├── agents/
├── tasks/
├── memory/
├── browser/
├── permissions/
├── system/
└── settings/
```

This is preferred over a massive:

```text
components/
```

directory containing the entire application.

---

# 111. SHARED COMPONENTS

Reusable components belong in:

```text
components/ui/
```

or an equivalent shared design-system boundary.

---

# 112. BUSINESS LOGIC

Business/application logic should not be deeply embedded in visual components.

Prefer:

```text
Component
 ↓
Hook / Service
 ↓
Application Logic
```

---

# 113. API CONTRACTS

Frontend and backend should share typed contracts where practical.

Potential approaches:

```text
OpenAPI
Generated Types
Shared TypeScript Schema
JSON Schema
```

The final backend contract strategy belongs to `11_BACKEND_STACK.md`.

---

# 114. TYPE GENERATION

Where an authoritative API schema exists:

```text
Backend Schema
 ↓
Code Generation
 ↓
Frontend Types
```

is preferred over manually duplicating interfaces.

---

# 115. ERROR HANDLING

Frontend errors should be categorized:

```text
Validation Error
Authentication Error
Authorization Error
Network Error
Backend Error
Tool Error
Agent Error
System Error
Unknown Error
```

---

# 116. ERROR UX

Errors should provide:

```text
What happened
What can be done
Retry
Details
Reference ID
```

where appropriate.

---

# 117. RETRY POLICY

The frontend should not blindly retry every failure.

For example:

```text
GET transient failure
→ Retry possible

Unauthorized
→ Re-authenticate

Permission denied
→ Do not retry automatically

User action failed
→ Offer retry
```

---

# 118. LOADING STATES

Every asynchronous UI surface should have an intentional state model.

Avoid:

```text
Nothing displayed for 5 seconds
```

Prefer:

```text
Loading
Processing
Waiting
Streaming
Completed
Failed
```

---

# 119. SKELETONS

Skeleton UI may be used for data-loading surfaces where useful.

However, streaming agent interactions should show meaningful activity rather than generic skeletons.

---

# 120. ANIMATION

Animations should communicate:

```text
State Change
Activity
Transition
Attention
```

not merely decoration.

---

# 121. REDUCED MOTION

The frontend must respect the user's reduced-motion preference.

---

# 122. PERFORMANCE

The frontend must remain responsive during:

```text
Streaming
Agent Activity
Large Chat History
Vision Results
Logs
Task Lists
```

---

# 123. RENDER OPTIMIZATION

Use:

```text
Memoization
Selectors
Virtualization
Lazy Loading
Code Splitting
Event Throttling
Debouncing
```

where justified.

---

# 124. CHAT VIRTUALIZATION

Long conversations should eventually use virtualization or equivalent optimization.

---

# 125. LOG VIRTUALIZATION

Large log and trace panels should use virtualization.

---

# 126. LARGE ARTIFACTS

The frontend should not load large files entirely into memory unnecessarily.

Use:

```text
Streaming
Pagination
Chunking
Lazy Loading
Preview Generation
```

---

# 127. IMAGE OPTIMIZATION

Vision artifacts should support:

```text
Thumbnail
Preview
Original
```

rather than always transmitting full-resolution originals.

---

# 128. AUDIO UI PERFORMANCE

Audio visualization must not block the main UI thread.

---

# 129. WEB WORKERS

Web Workers may be used for CPU-heavy frontend operations such as:

```text
Large Parsing
Local Processing
Data Transformation
```

but should not be introduced unnecessarily.

---

# 130. DESKTOP NATIVE WORK

CPU-heavy native work should generally be delegated to:

```text
Backend
Native Layer
Worker
```

rather than blocking the frontend renderer.

---

# 131. TESTING STRATEGY

Frontend testing must include:

```text
Unit
Component
Integration
End-to-End
Accessibility
Visual Regression
Performance
Security
```

---

# 132. UNIT TESTING

Test:

```text
Utilities
Hooks
State Logic
Event Parsers
API Mappers
Validation
Formatting
```

---

# 133. COMPONENT TESTING

Test:

```text
Buttons
Forms
Dialogs
Chat
Tool Cards
Agent Cards
Permission Dialogs
Settings
```

---

# 134. INTEGRATION TESTING

Test:

```text
Frontend
 ↓
API
 ↓
Backend
```

including:

```text
Authentication
Streaming
Errors
Reconnect
Tool Approval
```

---

# 135. END-TO-END TESTING

A realistic E2E scenario:

```text
Open JARVIS
 ↓
Send message
 ↓
Backend processes request
 ↓
Agent runs tool
 ↓
Frontend receives events
 ↓
Tool result appears
 ↓
Final response appears
```

---

# 136. VOICE E2E

Example:

```text
Start Voice
 ↓
Microphone Permission
 ↓
Listening
 ↓
STT
 ↓
Agent
 ↓
TTS
 ↓
Speaking
```

---

# 137. VISION E2E

Example:

```text
Capture Screen
 ↓
Vision
 ↓
Observation
 ↓
Agent
 ↓
UI Result
```

---

# 138. ACCESSIBILITY TESTING

Automated accessibility checks should be combined with manual keyboard/screen-reader validation.

---

# 139. VISUAL REGRESSION

Critical screens should have visual regression tests:

```text
Login
Chat
Agent Activity
Settings
Permission
Task Detail
System Dashboard
```

where applicable.

---

# 140. FRONTEND BUILD

Production build should produce:

```text
Static Assets
JavaScript Bundles
CSS
Source Maps
License Report
```

where source maps are appropriate for deployment policy.

---

# 141. LICENSE COMPLIANCE

The frontend dependency graph must be auditable.

The build process should be able to produce a dependency license inventory.

Vite itself provides a build-license reporting capability that can generate a license file for bundled dependencies. citeturn0search20

---

# 142. NODE DEPENDENCY POLICY

Every frontend dependency must be evaluated for:

```text
License
Maintenance
Security
Bundle Size
API Stability
JAS Compatibility
```

---

# 143. DEPENDENCY MINIMIZATION

The frontend should not install a library merely because it is convenient.

Prefer:

```text
Native Browser API
```

when it is sufficient and stable.

---

# 144. FRONTEND SUPPLY-CHAIN SECURITY

The project must account for:

```text
NPM Packages
Transitive Dependencies
Build Plugins
Vite Plugins
Tauri Plugins
```

---

# 145. LOCKFILES

Frontend dependencies must be locked.

The exact package-manager strategy belongs to:

```text
18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md
```

---

# 146. VERSION LOCK

Version Lock must capture at minimum:

```text
Node.js
TypeScript
React
React DOM
Vite
TanStack Query
Zustand
Tailwind CSS
Tauri
Tauri Plugins
Frontend Testing Stack
Build Plugins
```

Exact versions are intentionally deferred.

---

# 147. MANIFEST

The future Manifest should conceptually define:

```yaml
frontend:
  framework: react
  language: typescript
  build: vite

  state:
    server: tanstack-query
    client: zustand

  styling:
    framework: tailwind

  desktop:
    shell: tauri

  realtime:
    transport: websocket

  features:
    voice: true
    vision: true
    browser: true
    agents: true
    memory: true
```

This is conceptual only.

---

# 148. BOOTSTRAP

Bootstrap should eventually:

```text
Install Node
Install Frontend Dependencies
Validate Node Version
Validate Lockfile
Build Frontend
Run Frontend Tests
Build Tauri
Validate Native Dependencies
Generate Development Configuration
```

---

# 149. COMPLIANCE CHECKER

The Compliance Checker should validate:

```text
React Version
TypeScript Configuration
Vite Configuration
Approved Dependencies
Forbidden Dependencies
Lockfile
Tauri Capabilities
API Contracts
Security Headers
No Embedded Secrets
Build Output
License Inventory
```

---

# 150. DEVELOPMENT ENVIRONMENT

Development mode should support:

```text
Hot Reload
Frontend Debugging
Backend Connection
Mock API
Mock Event Stream
Development Logs
React DevTools
```

where approved.

---

# 151. MOCKING

Frontend development should be possible without the complete JARVIS backend.

Use:

```text
Mock API
Mock Events
Fixture Data
Fake Agent Events
Fake Tool Results
```

This allows frontend development independently.

---

# 152. MOCK POLICY

Mocks must not become an alternative production architecture.

They must follow the real API contracts.

---

# 153. FEATURE FLAGS

Feature flags may be used for:

```text
Experimental UI
New Voice UI
New Vision UI
Beta Features
```

but feature flags must not replace proper architecture.

---

# 154. EXPERIMENTAL UI

Experimental frontend functionality must be isolated.

Example:

```text
Experimental
 ↓
Feature Flag
 ↓
User-visible only if enabled
```

---

# 155. FRONTEND TELEMETRY

The frontend may emit:

```text
Performance Metrics
Errors
UI Events
Connection Metrics
```

but telemetry must respect privacy policy.

---

# 156. NO UNNECESSARY USER TRACKING

JARVIS is a personal AI.

Therefore external analytics should not automatically be included.

Default:

```text
No Third-Party Tracking
```

unless explicitly approved.

---

# 157. LOCAL-FIRST PRINCIPLE

Where practical:

```text
Local UI
Local Configuration
Local Interaction
```

should remain functional without unnecessary external services.

---

# 158. REMOTE ACCESS

Remote access may be supported later.

However:

```text
Remote Web UI
```

must pass through the security/authentication architecture.

---

# 159. MOBILE

A responsive web frontend should remain possible.

Native mobile applications are not a v1 requirement.

Future:

```text
React Native
Tauri Mobile
PWA
```

may be evaluated separately.

---

# 160. PWA

Progressive Web App capabilities may be evaluated for:

```text
Mobile Access
Installability
Offline UI
Notifications
```

but are not required for core JARVIS.

---

# 161. FRONTEND INTERNATIONALIZATION

The architecture should remain i18n-compatible.

Potential languages:

```text
English
German
Turkish
```

The exact initial language set is a product decision.

---

# 162. DATE / TIME

The frontend should not hard-code locale-specific date formats.

Use:

```text
Locale
Timezone
User Preferences
```

where appropriate.

---

# 163. NUMBER / CURRENCY

Formatting should respect user locale and backend-provided semantics.

---

# 164. TEXT DIRECTION

The UI should remain structurally compatible with RTL languages even if they are not initially supported.

---

# 165. DOCUMENTATION

Frontend components should document:

```text
Purpose
Props
Events
State
Accessibility
Dependencies
```

---

# 166. STORYBOOK

Storybook or an equivalent component-development tool may be evaluated.

Status:

```text
OPTIONAL
```

It should only be adopted if component complexity justifies it.

---

# 167. FRONTEND DEVTOOLS

Development tooling may include:

```text
React DevTools
TanStack Query Devtools
Browser DevTools
Tauri DevTools
```

These are development dependencies and must not automatically ship in production.

---

# 168. PRODUCTION DEBUGGING

Production builds should expose controlled diagnostics without exposing:

```text
Secrets
Internal Tokens
Sensitive Data
Hidden Reasoning
```

---

# 169. CRASH HANDLING

Frontend crashes should be isolated where possible.

The application should provide:

```text
Error Boundary
Recovery
Reload
Diagnostic ID
```

---

# 170. ERROR BOUNDARIES

React error boundaries should protect major UI regions.

Example:

```text
Application
├── Chat Boundary
├── Agent Boundary
├── Memory Boundary
├── Settings Boundary
└── System Boundary
```

A failure in one panel should not necessarily destroy the entire application.

---

# 171. REALTIME STATE CONSISTENCY

If:

```text
WebSocket Event
```

updates a resource already managed by TanStack Query, the event layer should update/invalidate the relevant query rather than maintaining a second conflicting source of truth.

---

# 172. SINGLE SOURCE OF TRUTH

For each piece of state there should be one authoritative owner.

Example:

```text
Task status
→ Backend

Cached task status
→ TanStack Query

Selected task
→ Zustand

Temporary button state
→ React
```

---

# 173. FRONTEND / BACKEND CONTRACT

The frontend must not infer backend behavior from UI assumptions.

The API contract should define:

```text
Request
Response
Errors
Events
Permissions
Capabilities
Version
```

---

# 174. API VERSIONING

Frontend and backend should support controlled API evolution.

Potential approach:

```text
API v1
 ↓
Compatible Changes
 ↓
Deprecation
 ↓
API v2
```

The exact policy belongs to backend architecture.

---

# 175. FRONTEND VERSION

The frontend should expose its version to backend observability.

Example:

```text
frontend_version
build_id
commit
environment
```

---

# 176. BUILD IDENTIFICATION

Every production frontend build should be identifiable.

Conceptually:

```yaml
build:
  version: ...
  commit: ...
  timestamp: ...
```

---

# 177. DESKTOP UPDATE

Tauri desktop releases should eventually support:

```text
Update Check
Download
Verify
Install
Rollback / Recovery
```

This belongs partly to deployment architecture.

---

# 178. WEB DEPLOYMENT

Web frontend may be deployed as:

```text
Static Assets
```

behind an approved web server/CDN.

The frontend should remain separable from backend deployment.

---

# 179. DESKTOP DEPLOYMENT

Desktop application packaging should produce platform-specific artifacts:

```text
Windows
Linux
macOS
```

as supported.

---

# 180. WINDOWS PRIORITY

Windows is the primary desktop target.

Therefore:

```text
Tauri
React
Vite
Camera
Microphone
System Tray
Global Shortcuts
Notifications
Filesystem
```

must be validated on Windows.

---

# 181. LINUX

Linux should remain a supported development/deployment target where native dependencies allow.

---

# 182. MACOS

macOS compatibility should remain possible.

Full support may be validated later.

---

# 183. CONTAINERIZED FRONTEND

The web frontend can be containerized.

Desktop frontend should not be treated as a containerized workload.

---

# 184. FRONTEND + BACKEND DEPLOYMENT

Preferred separation:

```text
Frontend
   │
   │ HTTPS / WebSocket
   ▼
Backend
   │
   ▼
JARVIS Core
```

This allows frontend and backend to evolve independently within contract boundaries.

---

# 185. FRONTEND + LOCAL BACKEND

Desktop mode may use:

```text
Tauri
 ↓
React
 ↓
Local Backend
```

or:

```text
Tauri
 ↓
React
 ↓
Remote Backend
```

depending on deployment.

---

# 186. CONNECTION MODES

The frontend should support a conceptual connection state:

```text
LOCAL
REMOTE
DISCONNECTED
CONNECTING
DEGRADED
```

---

# 187. FRONTEND ARCHITECTURE TARGET

The resulting architecture is:

```text
                    JARVIS FRONTEND
                           │
                ┌──────────┴──────────┐
                │                     │
             Browser                Tauri
                │                     │
                └──────────┬──────────┘
                           ▼
                     React + TS
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
         UI State      Server State    Events
             │             │             │
          Zustand     TanStack Query  WebSocket
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                    Frontend Services
                           │
                           ▼
                      API Client
                           │
                           ▼
                        Backend
                           │
                           ▼
                      JARVIS Core
```

---

# 188. PRIMARY V1 STACK

The recommended initial frontend stack is:

```text
TypeScript
+
React
+
Vite
+
TanStack Query
+
Zustand
+
Tailwind CSS
+
Tauri 2
```

with:

```text
WebSocket
```

for real-time bidirectional events.

---

# 189. TECHNOLOGY STATUS MATRIX

| Component | Technology | Status | Role |
|---|---|---|---|
| Language | TypeScript | APPROVED | Primary frontend language |
| UI Framework | React | APPROVED | Component/UI platform |
| Build | Vite | APPROVED | Development/build |
| Server State | TanStack Query | APPROVED | Remote/server state |
| Client State | Zustand | APPROVED | Local application state |
| Styling | Tailwind CSS | APPROVED | Styling foundation |
| Desktop Shell | Tauri 2 | APPROVED CANDIDATE / PREFERRED | Native desktop |
| Realtime | WebSocket | APPROVED ARCHITECTURAL CHOICE | Bidirectional events |
| Streaming | SSE | APPROVED OPTIONAL | Server-to-client streaming |
| Full-stack React | Next.js | CONDITIONAL | Separate web products |
| Desktop Alternative | Electron | CONDITIONAL | Alternative shell |
| Component Primitives | Radix/Headless/Custom | DEFERRED | Accessibility/UI |
| Storybook | Optional | DEFERRED | Component development |
| Mobile | React Native/Tauri Mobile | FUTURE | Future client |

---

# 190. WHY THIS STACK

The stack deliberately separates:

```text
UI
+
Build
+
Server State
+
Client State
+
Styling
+
Desktop
+
Realtime
```

rather than choosing a single framework to solve everything.

This creates:

```text
Replaceable Layers
+
Clear Responsibilities
+
Lower Coupling
+
Better Testing
+
Desktop/Web Reuse
+
Long-Term Maintainability
```

---

# 191. WHAT IS NOT BEING DONE

The following are explicitly avoided:

```text
One giant React component
Frontend directly calling OS
Frontend directly calling LLM
Frontend storing API secrets
Frontend deciding authorization
Frontend implementing agent planning
Frontend containing memory governance
Frontend directly connecting to databases
Frontend directly controlling MCP servers
```

---

# 192. FRONTEND AS A TRUST BOUNDARY

The frontend is considered:

```text
Presentation Layer
```

not:

```text
Security Authority
```

This distinction is mandatory.

---

# 193. FRONTEND + SECURITY

The architecture is:

```text
User
 ↓
Frontend
 ↓
Backend Authentication
 ↓
Authorization
 ↓
Policy
 ↓
Capability
 ↓
Tool
```

not:

```text
User
 ↓
Frontend
 ↓
Tool
```

---

# 194. FRONTEND + AGENTS

The frontend displays agent state.

It does not own agent execution.

```text
Backend
 ↓
Agent
 ↓
Events
 ↓
Frontend
```

---

# 195. FRONTEND + MEMORY

The frontend displays/manages memory through APIs.

It does not directly query the memory database.

```text
Frontend
 ↓
Memory API
 ↓
Memory Service
 ↓
Database
```

---

# 196. FRONTEND + VOICE

Voice processing belongs to the Voice & Audio Stack.

Frontend responsibilities:

```text
Permission
Controls
State
Visualization
Transcript
Playback
Interrupt
```

---

# 197. FRONTEND + VISION

Vision processing belongs to the Computer Vision Stack.

Frontend responsibilities:

```text
Preview
Capture Controls
Observation Display
Permission
Artifacts
```

---

# 198. FRONTEND + BROWSER

Browser automation belongs to the Browser Automation Stack.

Frontend may display:

```text
Browser Session
Current URL
Activity
Screenshot
Tool State
Approval
```

but does not own browser automation.

---

# 199. FRONTEND + PLUGINS

Plugin architecture must provide controlled extension points.

Potential UI extension points:

```text
Command
Panel
Widget
Tool
Settings
Notification
```

---

# 200. FRONTEND + MCP

MCP results must enter through backend/integration architecture.

Frontend must not arbitrarily connect to external MCP servers.

---

# 201. FUTURE: SPATIAL UI

Long-term JARVIS may evolve toward:

```text
3D UI
AR
VR
Spatial Computing
```

The frontend architecture should not make such evolution impossible.

---

# 202. FUTURE: HOLOGRAPHIC INTERFACE

A future interface may provide:

```text
Voice
Vision
3D Visualization
Agent State
Spatial Controls
```

This remains a future client rather than a v1 requirement.

---

# 203. FUTURE: MULTI-DEVICE

The same JARVIS backend may eventually serve:

```text
Desktop
Laptop
Phone
Tablet
Web
AR
VR
Automotive
```

The frontend stack should therefore remain client-oriented.

---

# 204. FUTURE: REMOTE JARVIS

A future remote deployment may use:

```text
JARVIS Cloud / Server
        │
        ├── Desktop Client
        ├── Web Client
        ├── Mobile Client
        └── Spatial Client
```

---

# 205. FUTURE: OFFLINE JARVIS

The desktop client should remain compatible with a local-first architecture:

```text
Desktop
 ↓
Local Backend
 ↓
Local Models
```

when hardware permits.

---

# 206. FUTURE: MODEL STREAMING

The frontend should remain compatible with future:

```text
Token Streaming
Audio Streaming
Video Streaming
Vision Streaming
Agent Streaming
```

without changing the fundamental UI architecture.

---

# 207. FUTURE: REAL-TIME AVATAR

A future JARVIS avatar may combine:

```text
Voice
Face
Animation
Vision
Emotion-like UI State
```

but must remain a presentation layer.

---

# 208. FRONTEND MODEL POLICY

The frontend should not depend on a specific LLM.

The UI should consume abstract events:

```text
Message
Tool
Agent
Task
Status
```

rather than model-specific responses.

---

# 209. MODEL INDEPENDENCE

Example:

```text
OpenAI
Anthropic
Google
Local Model
Other Provider
```

should all be able to produce compatible frontend event structures.

---

# 210. PROVIDER ABSTRACTION

The frontend should never contain:

```text
if provider == "OpenAI"
```

for normal UI rendering.

Provider differences belong below the API contract.

---

# 211. FRONTEND EVENT SCHEMA

The eventual event system should have:

```text
Event ID
Event Type
Timestamp
Task ID
Conversation ID
Agent ID
Payload
Version
```

where relevant.

---

# 212. EVENT VERSIONING

Event schemas should be versioned.

Example:

```text
agent.started.v1
tool.started.v1
message.delta.v1
```

This allows controlled evolution.

---

# 213. FRONTEND LOGGING

Frontend logs should be structured.

Example:

```yaml
event:
  level: error
  component: chat
  trace_id: ...
  message: ...
```

---

# 214. FRONTEND PRIVACY

Logs must not accidentally capture:

```text
Passwords
API Keys
Sensitive User Content
Private Memory
Audio
Camera Frames
```

unless explicitly required and authorized.

---

# 215. CONTENT REDACTION

Frontend diagnostic logging should support redaction.

---

# 216. FRONTEND CACHE

Browser caches should not become a second persistent database.

Cache only what is necessary.

---

# 217. CACHE POLICY

Potential cache categories:

```text
UI Preferences
Static Assets
Server Query Cache
Temporary Artifacts
```

Persistent user memory belongs to backend memory architecture.

---

# 218. FRONTEND DATA RETENTION

Temporary frontend data should have explicit retention behavior.

Examples:

```text
Temporary Upload
Temporary Preview
Temporary Transcript
```

should not remain indefinitely without reason.

---

# 219. SECURITY EVENTS

Frontend should surface critical security events:

```text
Permission Denied
Session Expired
Suspicious Tool Request
Unauthorized Access
Capability Disabled
```

---

# 220. USER CONTROL

The frontend must make it easy to:

```text
Stop
Cancel
Pause
Approve
Deny
Revoke
Forget
Logout
```

---

# 221. KILL / STOP CONTROL

Long-running JARVIS tasks should have a visible cancellation mechanism.

Example:

```text
Task Running

[Stop Task]
```

The backend remains responsible for actually stopping execution.

---

# 222. INTERRUPTIBILITY

Voice and agent interfaces should support interruption.

Example:

```text
JARVIS speaking
 ↓
User interrupts
 ↓
Frontend sends interrupt event
 ↓
Backend cancels generation / TTS
```

---

# 223. CANCELLATION

Frontend cancellation is a request.

Backend must enforce actual cancellation.

---

# 224. FRONTEND RELIABILITY

Frontend failures should not automatically terminate backend tasks.

For example:

```text
Browser window closes
```

should not necessarily mean:

```text
Agent task destroyed
```

Long-running task state belongs to backend.

---

# 225. SESSION RECOVERY

After reconnect:

```text
Frontend
 ↓
Backend
 ↓
Recover Active Tasks
 ↓
Synchronize State
```

---

# 226. REHYDRATION

The frontend should rehydrate:

```text
Current Session
Active Tasks
Relevant Conversations
UI Preferences
```

without duplicating backend state.

---

# 227. DESKTOP RESTART

After application restart:

```text
Frontend
 ↓
Connect
 ↓
Authenticate
 ↓
Retrieve State
 ↓
Render
```

---

# 228. FRONTEND HEALTH CHECK

The frontend should verify:

```text
Backend Reachability
API Availability
Realtime Connection
Authentication
Capability State
```

---

# 229. READINESS

Frontend readiness should be distinct from backend readiness.

Example:

```text
Frontend Ready
Backend Connecting
```

is a valid state.

---

# 230. SYSTEM READINESS

Full JARVIS readiness requires:

```text
Frontend
+
Backend
+
Core
+
Models
+
Required Services
```

The frontend should present this clearly.

---

# 231. BOOT SEQUENCE

Desktop startup may eventually be:

```text
Tauri
 ↓
React
 ↓
Connect Backend
 ↓
Authenticate
 ↓
Retrieve Capabilities
 ↓
Retrieve System Status
 ↓
Initialize Realtime
 ↓
Ready
```

---

# 232. FRONTEND STARTUP FAILURE

If backend is unavailable:

```text
Frontend
 ↓
Offline / Reconnect Screen
```

rather than blank failure.

---

# 233. DEVELOPMENT STARTUP

Development mode should support independent startup:

```text
Frontend
Backend
```

with clear configuration.

---

# 234. TEST ENVIRONMENT

CI should be capable of:

```text
Install Dependencies
Type Check
Lint
Unit Test
Component Test
Build
E2E
Accessibility
```

where infrastructure permits.

---

# 235. TYPE CHECK

Production build should fail on TypeScript errors.

---

# 236. LINTING

Linting should enforce:

```text
TypeScript
React Rules
Hooks Rules
Security Rules
Import Boundaries
```

---

# 237. ARCHITECTURAL LINTING

Where possible, automated checks should prevent:

```text
UI → Database
UI → Secret Store
UI → OS unrestricted
UI → Agent Runtime
```

dependencies.

---

# 238. DEPENDENCY BOUNDARIES

Example:

```text
components
  ↓
features
  ↓
services
  ↓
api
```

but:

```text
components
  X→ database
```

---

# 239. CIRCULAR DEPENDENCIES

Circular frontend module dependencies should be prohibited.

---

# 240. CODE SPLITTING

Feature-heavy surfaces may be lazy-loaded:

```text
Memory
Vision
System Diagnostics
Settings
```

when appropriate.

---

# 241. INITIAL LOAD

The initial JARVIS interface should prioritize:

```text
Chat
Voice
Core Navigation
Connection State
```

rather than loading every advanced feature.

---

# 242. PERFORMANCE BUDGET

The frontend should define budgets for:

```text
Initial Load
Time to Interactive
Memory
Bundle Size
Realtime Latency
Render Latency
```

Exact values should be defined during implementation benchmarking.

---

# 243. OBSERVABILITY

Frontend observability should correlate with backend traces.

Shared identifiers:

```text
trace_id
request_id
task_id
conversation_id
agent_id
```

---

# 244. FRONTEND TRACE

Example:

```text
User Click
 ↓
request_id
 ↓
Backend Request
 ↓
Agent
 ↓
Tool
 ↓
Response
 ↓
Frontend Render
```

This enables end-to-end debugging.

---

# 245. FINAL V1 ARCHITECTURE

```text
========================================================
JARVIS FRONTEND v1
========================================================

LANGUAGE:
    TypeScript
    APPROVED

UI:
    React
    APPROVED

BUILD:
    Vite
    APPROVED

SERVER STATE:
    TanStack Query
    APPROVED

CLIENT STATE:
    Zustand
    APPROVED

STYLING:
    Tailwind CSS
    APPROVED

DESKTOP:
    Tauri 2
    PREFERRED / APPROVED CANDIDATE

REALTIME:
    WebSocket
    APPROVED

SERVER STREAMING:
    SSE
    OPTIONAL

WEB FRAMEWORK:
    Next.js
    CONDITIONAL

DESKTOP ALTERNATIVE:
    Electron
    CONDITIONAL

========================================================
```

---

# 246. DEFINITION OF DONE

The frontend stack is operationally complete when:

```text
[ ] TypeScript configured
[ ] React integrated
[ ] Vite integrated
[ ] TanStack Query integrated
[ ] Zustand integrated
[ ] Tailwind integrated
[ ] Design tokens defined
[ ] Design system established
[ ] API client implemented
[ ] Event client implemented
[ ] WebSocket implemented
[ ] Reconnect logic implemented
[ ] Authentication integrated
[ ] Authorization boundaries respected
[ ] Chat UI implemented
[ ] Streaming implemented
[ ] Agent activity implemented
[ ] Tool activity implemented
[ ] Permission UI implemented
[ ] Voice UI implemented
[ ] Vision UI implemented
[ ] Task UI implemented
[ ] Memory UI implemented
[ ] Settings implemented
[ ] System status implemented
[ ] Error boundaries implemented
[ ] Accessibility tested
[ ] E2E tests implemented
[ ] Visual regression strategy implemented
[ ] Tauri desktop shell implemented
[ ] Windows validated
[ ] Linux validated
[ ] API contract validated
[ ] Lockfile integrated
[ ] License inventory generated
[ ] Security review completed
[ ] Version Lock integrated
[ ] Manifest integrated
[ ] Bootstrap integrated
[ ] Compliance Checker integrated
```

---

# 247. FINAL ARCHITECTURAL RULES

### Rule 1

**TypeScript is the primary frontend language.**

### Rule 2

**React is the primary UI framework.**

### Rule 3

**Vite is the default frontend build system.**

### Rule 4

**TanStack Query owns server-state management.**

### Rule 5

**Zustand owns appropriate client/application state.**

### Rule 6

**React local state remains preferred for component-local state.**

### Rule 7

**The frontend is not JARVIS Core.**

### Rule 8

**The frontend is not a security authority.**

### Rule 9

**The frontend must never contain production secrets.**

### Rule 10

**The frontend must not directly access databases.**

### Rule 11

**The frontend must not directly execute privileged OS operations.**

### Rule 12

**Native capabilities must pass through explicit desktop capability boundaries.**

### Rule 13

**Tauri 2 is the preferred desktop shell.**

### Rule 14

**Electron remains a conditional alternative.**

### Rule 15

**Next.js is not the default JARVIS application runtime.**

### Rule 16

**Web and desktop clients should share the same core frontend architecture where practical.**

### Rule 17

**Server state and client state must remain conceptually separate.**

### Rule 18

**Realtime communication must use a typed event abstraction.**

### Rule 19

**The frontend must support reconnect and degraded states.**

### Rule 20

**Long-running backend tasks must survive frontend disconnects where architecture permits.**

### Rule 21

**High-risk operations require explicit user approval through the security architecture.**

### Rule 22

**External content is untrusted.**

### Rule 23

**Browser, OCR, MCP and uploaded content must not automatically become trusted instructions.**

### Rule 24

**Accessibility is a core requirement.**

### Rule 25

**The UI must remain responsive during streaming and agent execution.**

### Rule 26

**Large data surfaces should use pagination, virtualization or streaming where appropriate.**

### Rule 27

**No third-party analytics/tracking is included by default.**

### Rule 28

**Frontend dependencies require license and security review.**

### Rule 29

**Exact dependency versions belong to Version Lock.**

### Rule 30

**The Manifest defines the frontend operational configuration.**

### Rule 31

**Bootstrap must be able to provision and validate the frontend environment.**

### Rule 32

**Compliance Checker must enforce frontend architectural rules.**

### Rule 33

**The frontend must remain model-provider agnostic.**

### Rule 34

**The frontend must remain compatible with local and remote JARVIS deployments.**

### Rule 35

**UI architecture must not prevent future voice, vision, spatial or multimodal interfaces.**

---

# 248. SOURCE BASIS

Primary technology decisions in this document are based on official documentation and repositories.

Major references include:

- React official documentation — React 19 stable release. citeturn0search16
- Next.js official documentation — React framework and application architecture. citeturn0search15
- Vite official documentation — build system and dependency license reporting. citeturn0search20
- TanStack Query official documentation — server-state/query architecture. citeturn0search4turn0search5
- Zustand official repository/documentation — client-side state architecture. citeturn1search1turn1search4
- Tailwind CSS official documentation — v4 architecture and browser compatibility. citeturn0search14turn0search17
- Tauri official repository — desktop/mobile application architecture and licensing. citeturn1search0
- Electron official documentation — desktop application architecture. citeturn0search12

Exact versions are deliberately not frozen here.

They belong to:

```text
VERSION LOCK v1
```

and:

```text
21_APPROVED_SOFTWARE_MATRIX.md
```

and, where applicable:

```text
19_APPROVED_MODELS.md
```

---

# 249. HANDOFF TO NEXT ARCHITECTURAL PHASE

The frontend dependency chain is:

```text
10_FRONTEND_STACK.md
          │
          ▼
21_APPROVED_SOFTWARE_MATRIX.md
          │
          ▼
VERSION LOCK v1
          │
          ▼
MANIFEST v1
          │
          ▼
BOOTSTRAP v1
          │
          ▼
ARCHITECTURE COMPLIANCE CHECKER
          │
          ▼
FRONTEND IMPLEMENTATION
          │
          ▼
JARVIS USER INTERFACE
```

---

# 250. FINAL DECISION

```text
========================================================
JARVIS FRONTEND STACK — FINAL v1 DECISION
========================================================

PRIMARY LANGUAGE:
    TypeScript
    APPROVED

PRIMARY UI FRAMEWORK:
    React
    APPROVED

PRIMARY BUILD SYSTEM:
    Vite
    APPROVED

SERVER STATE:
    TanStack Query
    APPROVED

CLIENT STATE:
    Zustand
    APPROVED

STYLING:
    Tailwind CSS
    APPROVED

DESIGN SYSTEM:
    JARVIS CUSTOM DESIGN SYSTEM
    REQUIRED

REALTIME:
    WebSocket
    APPROVED

SERVER STREAMING:
    SSE
    OPTIONAL

DESKTOP:
    Tauri 2
    PREFERRED

ELECTRON:
    CONDITIONAL ALTERNATIVE

NEXT.JS:
    CONDITIONAL
    NOT DEFAULT JARVIS RUNTIME

MOBILE:
    FUTURE

SPATIAL:
    FUTURE

THIRD-PARTY ANALYTICS:
    NOT INCLUDED BY DEFAULT

SECRETS IN FRONTEND:
    PROHIBITED

DIRECT DATABASE ACCESS:
    PROHIBITED

DIRECT UNAUTHORIZED OS ACCESS:
    PROHIBITED

FRONTEND AS SECURITY AUTHORITY:
    PROHIBITED

MODEL PROVIDER COUPLING:
    PROHIBITED

========================================================

PRIMARY V1 ARCHITECTURE:

                 USER
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
        TEXT     VOICE    VISION
          │        │        │
          └────────┼────────┘
                   ▼
             React + TS
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
   Zustand    TanStack Query  Events
       │           │           │
       └───────────┼───────────┘
                   ▼
             API / Event Client
                   │
             ┌─────┴─────┐
             ▼           ▼
           Web          Tauri
             │           │
             └─────┬─────┘
                   ▼
                Backend
                   │
                   ▼
              JARVIS Core

========================================================
```

**Final architectural decision:** JARVIS v1 will use **TypeScript + React + Vite** as its core frontend foundation, with **TanStack Query** for server state, **Zustand** for client/application state, **Tailwind CSS** for styling, and **Tauri 2** as the preferred desktop shell. The frontend remains a strictly bounded interaction layer: it does not own agent reasoning, authorization, secrets, databases, or privileged OS execution.

This keeps the frontend consistent with the same principle we established for Browser, Voice and Vision: **capabilities remain replaceable, boundaries remain stable, and the UI never becomes the system itself.**