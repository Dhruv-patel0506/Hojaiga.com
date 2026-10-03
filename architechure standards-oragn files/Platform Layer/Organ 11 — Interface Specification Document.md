# **Organ 11 — Interface Specification Document**

## **1\. Overview**

The Interface Organ is the primary human-system interaction layer, user context manager, status visualizer, and command ingestion kernel of the Hojaiga Automation Operating System. It provides non-blocking local GUI components, terminal CLI interfaces, system tray indicators, and direct web-view rendering modules that allow human operators to issue requests, inspect system state, authorize governance approvals, and view live automation progress. Operating CPU-first, the Interface Organ isolates rendering processes from core OS execution, communicating strictly through Central Nervous System (CNS) IPC sockets.

## **2\. Purpose**

The purpose of the Interface Organ is to present a clean, transparent, controllable, and responsive interface between human operators and the Hojaiga system. In accordance with Constitutional Principle 4 (Stewardship and Controlled Governance), Universal Law 12 (Human Approval Boundaries), and Policy Manual Chapter 1, the Interface Organ ensures that human operators retain full visibility and final governing approval authority over high-impact operations without stalling background system pipelines.

## **3\. Philosophy**

In strict compliance with Master Architecture Blueprint Chapter 1 and Universal Law 3 (Separation of Responsibility), the Interface Organ owns zero automation logic, model inference runtimes, or private state databases. It acts purely as an event producer and renderer. It translates user inputs into standardized task payloads emitted to the CNS, and renders real-time telemetry, logs, and state updates received from system events. The interface must remain responsive under all conditions, rendering system statuses efficiently on the host CPU without allocating GPU VRAM.

## **4\. Primary Responsibilities**

* **Command Ingestion & Parsing:** Ingest natural language goals, CLI commands, and visual UI interactions from human operators.  
* **Real-Time Telemetry & Status Visualization:** Render live system state trees, active organ health metrics, task progress DAGs, and resource consumption counters.  
* **Human-in-the-Loop Governance Prompts:** Display mandatory approval dialogs for protected operations, security privilege requests, or ambiguous planning choices.  
* **System Tray & Notification Management:** Maintain light background presence via Windows desktop system tray icons and native OS desktop notifications.  
* **Session Room Display:** Render active conversation rooms, execution step histories, and visual screenshots captured during browser or desktop automation runs.  
* **CLI & Shell Terminal Wrapper:** Provide lightweight interactive terminal interfaces for advanced system operators.

## **5\. Internal Modules**

* interface\_core: Master IPC socket handler, event router, and UI state synchronizer.  
* gui\_renderer: Native desktop application GUI window renderer (built on PySide6 / Qt6 CPU-rasterized engine).  
* cli\_terminal: Interactive command-line shell parser and terminal status formatter.  
* tray\_manager: Windows system tray icon controller managing background service menus and quick controls.  
* governance\_dialogs: High-priority modal dialog manager forcing human approval loops for security and policy events.  
* telemetry\_widget: Real-time performance chart and tree renderer displaying active tasks and organ states.  
* notification\_engine: Native OS desktop toast notification wrapper.

## **6\. Internal Folder Structure**

/organ\_11\_interface  
├── bin/  
│   └── interface\_app         \# Primary GUI executable process  
├── config/  
│   └── ui\_theme.json         \# Dark/Light theme constants and layout settings  
├── src/  
│   ├── core/  
│   │   ├── interface\_kernel.py  
│   │   └── state\_bridge.py  
│   ├── gui/  
│   │   ├── main\_window.py  
│   │   ├── telemetry\_view.py  
│   │   └── room\_view.py  
│   ├── cli/  
│   │   └── terminal\_shell.py  
│   ├── dialogs/  
│   │   ├── approval\_modal.py  
│   │   └── policy\_prompt.py  
│   ├── system/  
│   │   ├── tray\_icon.py  
│   │   └── notifications.py  
│   └── sockets/  
│       └── ipc\_client.py  
├── tests/  
└── manifest.json

## **7\. Public Interfaces**

* IPC Socket Interface: \\\\.\\pipe\\hojaiga\_interface (Windows) / /tmp/hojaiga\_interface.sock (Linux/Unix).  
  * rpc DisplayApprovalPrompt(PromptRequestPayload) \-\> HumanApprovalVerdict  
  * rpc UpdateTelemetryDisplay(TelemetryUpdatePayload) \-\> Ack  
  * rpc SendNotification(NotificationPayload) \-\> NotificationAck  
  * rpc RenderTaskProgress(ProgressUpdatePayload) \-\> Ack  
  * rpc GetActiveUserInputs(QueryPayload) \-\> UserInputPayload

## **8\. Internal Interfaces**

* IGUIRenderer:  
  * launch\_window(): Initializes Qt application loop and binds main control dashboard.  
  * update\_organ\_health\_tree(health\_data): Re-draws organ status indicators in real time.  
* IGovernanceDialog:  
  * prompt\_user\_modal(policy\_violation\_details): Freezes UI context until explicit human "Approve" or "Reject" click occurs.

## **9\. Socket Definitions**

* Named Pipe Socket: hojaiga\_interface.  
* Wire Protocol: Length-Prefixed Binary Frame \[ 4-byte payload length | 2-byte op\_code | JSON Payload \].  
* Max Payload Size: 16 MB per request frame.

## **10\. Pipeline Definitions**

* HumanApprovalPipeline:  
  1. CNS Detects Restricted Operation \-\> 2\. Security/Governance Organ Requests Approval \-\> 3\. Interface Organ Triggers governance\_dialogs Modal \-\> 4\. Human Operator Inspects Details \-\> 5\. Operator Grants/Denies Approval \-\> 6\. Interface Emits EVENT\_HUMAN\_APPROVAL\_VERDICT \-\> 7\. CNS Resumes Execution.

## **11\. Incoming Connections**

* **CNS Organ (02):** Transmits telemetry metrics, task execution updates, log frames, and human approval requests.

## **12\. Outgoing Connections**

* **CNS Organ (02):** Emits human user goals, CLI command inputs, governance approval verdicts, and interface status signals (EVENT\_USER\_GOAL\_SUBMITTED, EVENT\_HUMAN\_APPROVAL\_VERDICT, EVENT\_UI\_CLOSED).

## **13\. State Management**

The Interface Organ operates UI render states:

* HEADLESS\_TRAY: GUI window minimized or closed; active strictly in system tray with low memory footprint.  
* DASHBOARD\_ACTIVE: Primary Qt main window visible; rendering live telemetry and room contexts.  
* MODAL\_AWAITING\_HUMAN: High-priority approval modal open; rendering restricted operation request.  
* CLI\_MODE: Running strictly in terminal shell mode without Qt GUI dependencies loaded.

## **14\. Event Definitions**

* EVENT\_USER\_GOAL\_SUBMITTED: Emitted when human operator submits a new task via GUI or CLI.  
* EVENT\_HUMAN\_APPROVAL\_VERDICT: Fired when operator clicks "Approve" or "Deny" on governance prompt.  
* EVENT\_UI\_MODE\_CHANGED: Fired when switching between Headless Tray, Dashboard Active, and CLI Mode.

## **15\. Data Contracts**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "ApprovalPromptRequest",  
  "type": "object",  
  "properties": {  
    "prompt\_id": { "type": "string", "format": "uuid" },  
    "task\_id": { "type": "string", "format": "uuid" },  
    "requesting\_organ": { "type": "string" },  
    "action\_summary": { "type": "string" },  
    "risk\_level": { "type": "string", "enum": \["LOW", "MEDIUM", "HIGH", "CRITICAL"\] },  
    "policy\_violated": { "type": "string" },  
    "timeout\_ms": { "type": "integer", "default": 300000 }  
  },  
  "required": \["prompt\_id", "task\_id", "requesting\_organ", "action\_summary", "risk\_level"\]  
}

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "HumanApprovalResponse",  
  "type": "object",  
  "properties": {  
    "prompt\_id": { "type": "string", "format": "uuid" },  
    "verdict": { "type": "string", "enum": \["APPROVED", "DENIED", "TIMED\_OUT"\] },  
    "operator\_notes": { "type": "string" },  
    "timestamp": { "type": "integer" }  
  },  
  "required": \["prompt\_id", "verdict", "timestamp"\]  
}

## **16\. Internal Database Structures**

The Interface Organ maintains an in-memory SQLite view state store (:memory:):

* Table ui\_session\_state (key TEXT PRIMARY KEY, value TEXT, updated\_at TIMESTAMP).  
* Table active\_prompts (prompt\_id TEXT PRIMARY KEY, task\_id TEXT, risk\_level TEXT, status TEXT, created\_at TIMESTAMP).

## **17\. Cache Strategy**

* UI Component Cache: Static UI widgets, icon resources, and layout templates pre-loaded in RAM to ensure immediate window rendering on tray click.

## **18\. Memory Strategy**

* Total resident RAM footprint maintained under 256 MB in DASHBOARD\_ACTIVE mode and under 64 MB in HEADLESS\_TRAY mode.  
* Software rasterization avoids GPU VRAM allocation.

## **19\. Thread Safety**

* Native Qt UI updates execute strictly on the main application GUI thread.  
* Incoming IPC socket threads route updates to the main Qt event loop using thread-safe signal/slot queues (QMetaObject::invokeMethod).

## **20\. Concurrency**

* Single-threaded Qt main render loop handling visual display.  
* Background worker thread handling non-blocking IPC socket communication with CNS.

## **21\. Hardware Optimization**

* CPU-First Architecture: Qt rendering forced to software rasterization mode (QT\_QUICK\_BACKEND=software or AA\_UseSoftwareOpenGL) on host Intel Core i7 CPU.  
* Absolutely zero GPU VRAM consumption, leaving 100% of NVIDIA RTX 3050 VRAM available for the Brain Organ.

## **22\. GPU Usage**

* Zero GPU usage. GPU rendering explicitly disabled to preserve VRAM for LLM inference.

## **23\. CPU Usage**

* Idle state CPU footprint (Headless Tray): \<0.1%.  
* Peak CPU consumption during dashboard rendering and telemetry chart updates capped at 5%.

## **24\. SSD Usage**

* Themes, layout configurations, and temporary session screenshot caches reside on 100 GB SSD Runtime.

## **25\. HDD Usage**

* Historical user query exports and full UI session snapshots archived to External HDD storage.

## **26\. Security Model**

* Governance Authority Protection: Approval dialogs display cryptographically signed request hashes to prevent UI spoofing.  
* Restricted Input Channels: User inputs are sanitized and schema-validated before being emitted to CNS.

## **27\. Permissions**

* Interface application executes under standard user account permissions.  
* No administrative privilege escalation permitted within interface processes.

## **28\. Logging**

* Structured JSON audit logging conforming to Policy Manual Chapter 8\.  
* Records user interaction events, goal submissions, modal prompt results, and UI error states.

## **29\. History Recording**

* All human operator interactions, commands, and approval verdicts are recorded in external HDD history archives.

## **30\. Recovery Strategy**

* UI Process Restart: If the Qt GUI application crashes, the system tray watchdog auto-restarts the interface in HEADLESS\_TRAY mode within 1 second without affecting running background tasks.

## **31\. Failure Handling**

* Modal Timeout: If a human approval prompt is not acted upon within timeout\_ms (default 300,000ms), governance\_dialogs automatically issues a DENIED verdict to preserve system safety.

## **32\. Validation Rules**

* Goal submissions must not be empty, must stay under 4096 characters, and must pass input sanitization checks.

## **33\. Testing Strategy**

* Unit tests for command parsing, input sanitization, and PySide6 UI event handlers.  
* Integration tests simulating approval prompts and verifying IPC signal dispatching to CNS.

## **34\. Extension Points**

* Custom Dashboard Widgets: Plug-in interface in gui/ allowing custom organ telemetry widgets to be added.

## **35\. Future Compatibility**

* Dynamic UI theme and schema migration handling via versioned theme manifests.

## **36\. Versioning**

* Semantic Versioning: v1.0.0 Interface Organ Specification.

## **37\. Dependencies**

* PySide6 (Qt6 for Python) with software rendering backend.  
* Python 3.11+.

## **38\. Interaction with Other Organs**

* **CNS (Organ 02):** Routes all user goal submissions and receives system telemetry events.  
* **Security (Organ 07):** Sends mandatory human approval prompts via CNS.  
* **Brain (Organ 01):** Interface renders plan DAGs compiled by Brain Organ.

## **39\. Mermaid Component Diagram**

Code snippet  
graph TD  
    CNS\[CNS Organ 02\] \--\>|IPC Sockets| Core\[Interface Kernel\]  
    Core \--\> GUI\[PySide6 GUI Renderer\]  
    Core \--\> CLI\[CLI Terminal Shell\]  
    Core \--\> Tray\[Tray Manager\]  
    Core \--\> Modal\[Governance Dialogs\]  
    Core \--\> Telem\[Telemetry Widget\]  
    GUI \--\> Desktop\[Windows Desktop Screen\]  
    Modal \--\>|Human Click| Verdict\[Approval / Denial Verdict\]  
    Verdict \--\> CNS

## **40\. Mermaid Sequence Diagram**

Code snippet  
sequenceDiagram  
    participant CNS as Organ 02 (CNS)  
    participant Core as Interface Kernel  
    participant Modal as Governance Dialogs  
    participant Human as Human Operator

    CNS-\>\>Core: DisplayApprovalPrompt(Request, Risk: HIGH)  
    Core-\>\>Modal: Popup Modal Dialog (Software Rendered)  
    Modal-\>\>Human: Display Action Details & Policy Warning  
    Human--\>\>Modal: Click "Approve Task"  
    Modal--\>\>Core: Capture Approval Signal  
    Core--\>\>CNS: Emit HumanApprovalResponse (APPROVED)  
    CNS-\>\>CNS: Resume Pipeline Execution

## **41\. Mermaid Flow Diagram**

Code snippet  
flowchart TD  
    A\[User Input Received via GUI or CLI\] \--\> B\[Sanitize Input String\]  
    B \--\> C{Input Valid?}  
    C \-- No \--\> D\[Display Input Error Alert\]  
    C \-- Yes \--\> E\[Package Task Payload Frame\]  
    E \--\> F\[Emit EVENT\_USER\_GOAL\_SUBMITTED to CNS\]  
    F \--\> G\[Update UI Progress State to "Planning"\]

## **42\. Mermaid State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> HeadlessTray  
    HeadlessTray \--\> DashboardActive : User Opens Window  
    DashboardActive \--\> HeadlessTray : User Minimizes / Closes Window  
    DashboardActive \--\> ModalAwaitingHuman : Restricted Approval Needed  
    ModalAwaitingHuman \--\> DashboardActive : Human Decision Received / Timeout  
    HeadlessTray \--\> CLIMode : Launched via Shell  
    CLIMode \--\> \[\*\]

## **43\. Mermaid Folder Diagram**

Code snippet  
graph TD  
    Root\[organ\_11\_interface\] \--\> Bin\[bin/interface\_app\]  
    Root \--\> Config\[config/ui\_theme.json\]  
    Root \--\> Src\[src/\]  
    Src \--\> Core\[core/interface\_kernel.py\]  
    Src \--\> GUI\[gui/main\_window.py\]  
    Src \--\> CLI\[cli/terminal\_shell.py\]  
    Src \--\> Dialogs\[dialogs/approval\_modal.py\]  
    Src \--\> System\[system/tray\_icon.py\]

## **44\. Mermaid Socket Diagram**

Code snippet  
graph LR  
    CNS\[CNS Master\] \-- Named Pipe \--\> Pipe\[\\\\.\\pipe\\hojaiga\_interface\]  
    Pipe \--\> IPC\[Interface IPC Listener Thread\]  
    IPC \--\> Core\[Interface Kernel Engine\]

## **45\. Mermaid Pipeline Diagram**

Code snippet  
graph LR  
    P1\[1. Input Ingestion\] \--\> P2\[2. Schema & Security Sanitization\]  
    P2 \--\> P3\[3. Task Payload Packaging\]  
    P3 \--\> P4\[4. CNS Dispatch\]  
    P4 \--\> P5\[5. Event Telemetry Reception\]  
    P5 \--\> P6\[6. Software UI Render Update\]

## **46\. Engineering Recommendations**

* Force PySide6 software OpenGL rasterization (os.environ\["QT\_QUICK\_BACKEND"\] \= "software") prior to QApplication instantiation to ensure zero VRAM allocation.  
* Implement non-blocking IPC message queuing between the socket listener thread and Qt event loop using PySide6.QtCore.Signal.

## **47\. Tradeoffs**

* **Software CPU Rasterization vs. Hardware Accelerated GPU Rendering:** Software rendering increases CPU utilization by \~2% during complex UI updates, but completely preserves 4 GB VRAM for LLM inference.  
* **Headless Tray Focus vs. Always-On Main Window:** Keeping the primary UI in system tray mode reduces baseline RAM usage to \<64 MB, but introduces a 200ms window render delay when restored by user.

## **48\. Alternatives Considered**

* **Web-Based Electron App Interface:** Rejected due to excessive memory footprint (\>500 MB RAM baseline) and Chromium background rendering overhead.  
* **Raw Win32 Native C++ UI:** Rejected due to development velocity constraints and lack of modular cross-widget layout styling compared to PySide6.

## **49\. Future Improvements**

* Dynamic layout adaptability based on host display DPI scaling and dark/light system mode changes.  
* Lightweight voice command input integration via CPU-based audio processing libraries.

## **50\. Claude Implementation Instructions**

1. Build directory structure as outlined in Section 6\.  
2. Set environment variables forcing Qt PySide6 software rendering.  
3. Implement dialogs/approval\_modal.py generating modal prompts with auto-timeout logic.  
4. Build gui/main\_window.py displaying organ state trees and live progress.  
5. Establish Named Pipe IPC client connecting to \\\\.\\pipe\\hojaiga\_interface.

