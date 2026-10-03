# **Desktop Automation Protocol (DAP) / GUI\_CDP\_Runtime Architecture Specification**

Document Version : 1.0.0-PROD  
Specification ID : Hojaiga-SPEC-GUI-CDP-001  
Filename         : GUI\_CDP\_Runtime.md  
Target Platform  : Windows 10/11 x64, Windows Server 2019/2022  
Status           : Production Ready

## **1\. Executive Summary & Core Paradigm**

The **GUI CDP Runtime** (internally designated as the **Desktop Automation Protocol** or **DAP**) is Hojaiga’s native execution sub-system for cross-process, OS-wide GUI introspection, control, capture, and event routing.

Where the Chrome DevTools Protocol (CDP) provides an asynchronous, event-driven wire protocol over WebSocket/JSON-RPC to control browser DOM elements and V8 isolates, **DAP** provides the equivalent primitive abstractions over **Windows OS Desktop Handles, Process Spaces, UI Automation (UIA) Provider Trees, Native Messaging Pipelines, and Computer Vision Models**.

\[ Traditional Web Automation \]  
Chrome Browser  \<---\>  CDP JSON-RPC Wire  \<---\>  DevTools / Playwright Agent

\[ Hojaiga Desktop Automation (DAP) \]  
Windows Desktop \<---\>  DAP Native Engine   \<---\>  DAP JSON-RPC Pipe/Socket \<---\> Hojaiga Orchestrator  
                       ├─ UIA / Win32 / WinUI  
                       ├─ Electron / Qt / GTK / Java  
                       ├─ Background Engine  
                       └─ OCR & Computer Vision

### **Key Capabilities**

* **Universal Framework Abstraction**: Unified tree representation across Win32, WinUI 2/3, WPF, Qt5/6, GTK 3/4, Electron/Chromium Embedded Framework (CEF), and Java (AWT/Swing/JavaFX via Access Bridge).  
* **Deterministic & Visual Query Engine**: Query nodes using unified selector syntax (window:query, control:query, a11y:query, ocr:query, vision:query).  
* **Non-Invasive Background Automation**: Interacts with minimized, covered, or unfocused windows via direct Win32 message injection (WM\_COMMAND, WM\_SETTEXT, BM\_CLICK), UIA Patterns, and specialized off-screen rendering contexts (PrintWindow / BitBlt bitmasks). Automatic foreground orchestration handles applications requiring true physical inputs.  
* **Resilient Execution Pipeline**: Fully state-machine-driven execution pipeline featuring auto-healing, visual verification, automatic dynamic scale adaptation (High DPI / Multi-Monitor), and fault isolation via out-of-process target proxies.

## **2\. Master System Architecture**

\+----------------------------------------------------------------------------------------------------------------+  
|                                           HOJAIGA CORE ORCHESTRATOR                                            |  
\+----------------------------------------------------------------------------------------------------------------+  
                                                         ^  
                                                         | (JSON-RPC 2.0 over Named Pipes / Encrypted WebSockets)  
                                                         v  
\+----------------------------------------------------------------------------------------------------------------+  
|                                                DAP RUNTIME CORE                                                |  
|                                                                                                                |  
|  \+-----------------------------------+  \+------------------------------------+  \+----------------------------+  |  
|  |    Session & Multiplexer Manager  |  |      Tree Orchestration Engine     |  |   Security & ACL Enforcer  |  |  
|  \+-----------------------------------+  \+------------------------------------+  \+----------------------------+  |  
|                                                                                                                |  
|  \+----------------------------------------------------------------------------------------------------------+  |  
|  |                                          QUERY ENGINE & SELECTORS                                        |  |  
|  |     \[ Native Selector \]    \[ Visual/OCR Selector \]    \[ A11y Selector \]    \[ Semantic AI Selector \]      |  |  
|  \+----------------------------------------------------------------------------------------------------------+  |  
|                                                                                                                |  
|  \+----------------------------------------------------------------------------------------------------------+  |  
|  |                                         INTERACTION PIPELINE ENGINE                                      |  |  
|  |     \[ Input Injector \]     \[ Pattern Executor \]    \[ Background Driver \]   \[ Focus Manager & Restorer \]  |  |  
|  \+----------------------------------------------------------------------------------------------------------+  |  
|                                                                                                                |  
|  \+----------------------------------------------------------------------------------------------------------+  |  
|  |                                      PERCEPTION & ANALYTICS PIPELINE                                     |  |  
|  |     \[ Window Capture (DXGI) \]   \[ Tesseract/Paddle OCR \]   \[ YOLOv8 Element Vision \]  \[ Diff Engine \]  |  |  
|  \+----------------------------------------------------------------------------------------------------------+  |  
\+----------------------------------------------------------------------------------------------------------------+  
                                                         |  
                   \+-------------------------------------+-------------------------------------+  
                   |                                     |                                     |  
                   v                                     v                                     v  
\+-------------------------------------+ \+-------------------------------------+ \+-------------------------------------+  
|        PROVIDER DRIVER: UIA         | |       PROVIDER DRIVER: WIN32        | |      PROVIDER DRIVER: JAVA AB      |  
|  WinUI, WPF, Chromium, Qt, GTK      | |  Legacy Win32, Controls, Menus    | |  Java Swing, AWT, JavaFX          |  
\+-------------------------------------+ \+-------------------------------------+ \+-------------------------------------+  
                   |                                     |                                     |  
                   \+-------------------------------------+-------------------------------------+  
                                                         |  
                                                         v  
\+----------------------------------------------------------------------------------------------------------------+  
|                                          TARGET APPLICATION PROCESS SPACE                                      |  
|   \[ Application Windows \]     \[ Sub-Windows \]     \[ Context Menus \]     \[ Dialogs \]     \[ UI Elements \]      |  
\+----------------------------------------------------------------------------------------------------------------+

## **3\. Directory & Folder Structure**

dap-runtime/  
├── bin/  
│   ├── release-x64/  
│   │   ├── DapRuntime.exe  
│   │   ├── DapHostProxy.exe  
│   │   ├── DapJavaBridge.dll  
│   │   └── DapHook64.dll  
│   └── release-arm64/  
├── docs/  
│   └── GUI\_CDP\_Runtime.md  
├── include/  
│   └── dap/  
│       ├── dap\_client\_protocol.h  
│       ├── dap\_engine\_exports.h  
│       └── dap\_types.h  
├── config/  
│   ├── dap\_runtime.json  
│   ├── ocr\_models.json  
│   └── vision\_weights.onnx  
├── src/  
│   ├── main.cpp  
│   ├── core/  
│   │   ├── session\_manager.cpp  
│   │   ├── session\_manager.h  
│   │   ├── security\_enforcer.cpp  
│   │   ├── security\_enforcer.h  
│   │   ├── configuration.cpp  
│   │   └── configuration.h  
│   ├── protocol/  
│   │   ├── jsonrpc\_parser.cpp  
│   │   ├── jsonrpc\_parser.h  
│   │   ├── websocket\_server.cpp  
│   │   ├── websocket\_server.h  
│   │   ├── pipe\_server.cpp  
│   │   └── pipe\_server.h  
│   ├── trees/  
│   │   ├── desktop\_tree.cpp  
│   │   ├── desktop\_tree.h  
│   │   ├── window\_tree.cpp  
│   │   ├── window\_tree.h  
│   │   ├── accessibility\_tree.cpp  
│   │   ├── accessibility\_tree.h  
│   │   ├── element\_tree.cpp  
│   │   ├── element\_tree.h  
│   │   ├── interaction\_tree.cpp  
│   │   ├── interaction\_tree.h  
│   │   └── event\_tree.cpp  
│   │   └── event\_tree.h  
│   ├── providers/  
│   │   ├── provider\_interface.h  
│   │   ├── uia\_provider/  
│   │   │   ├── uia\_driver.cpp  
│   │   │   └── uia\_cache\_builder.cpp  
│   │   ├── win32\_provider/  
│   │   │   ├── win32\_driver.cpp  
│   │   │   └── win32\_message\_injector.cpp  
│   │   ├── java\_provider/  
│   │   │   ├── java\_bridge\_driver.cpp  
│   │   │   └── jab\_wrapper.cpp  
│   │   ├── qt\_gtk\_provider/  
│   │   │   └── native\_accessibility\_driver.cpp  
│   │   └── chromium\_provider/  
│   │       └── cdp\_bridge.cpp  
│   ├── interaction/  
│   │   ├── input\_injector.cpp  
│   │   ├── input\_injector.h  
│   │   ├── background\_executor.cpp  
│   │   ├── background\_executor.h  
│   │   ├── focus\_orchestrator.cpp  
│   │   ├── focus\_orchestrator.h  
│   │   └── clipboard\_manager.cpp  
│   ├── perception/  
│   │   ├── capture\_engine\_dxgi.cpp  
│   │   ├── capture\_engine\_gdi.cpp  
│   │   ├── ocr\_engine\_tesseract.cpp  
│   │   ├── vision\_engine\_onnx.cpp  
│   │   └── dpi\_manager.cpp  
│   └── telemetry/  
│       ├── logger.cpp  
│       ├── metrics\_collector.cpp  
│       └── crash\_reporter.cpp  
└── tests/  
    ├── unit/  
    ├── integration/  
    └── e2e\_apps/

## **4\. Tree Metamodel Specifications**

DAP unifies six explicit, synchronized tree projections representing the state of the Windows Desktop environment.

                 \+--------------------------+  
                  |       DESKTOP TREE       | (Physical Display Topology & Monitors)  
                  \+--------------------------+  
                               |  
                               v  
                  \+--------------------------+  
                  |       WINDOW TREE        | (HWnd Hierarchy, Z-Order, Process Bounds)  
                  \+--------------------------+  
                               |  
                               v  
                  \+--------------------------+  
                  |    ACCESSIBILITY TREE    | (UIAutomation / JAB / MSAA Provider Hierarchy)  
                  \+--------------------------+  
                               |  
                               v  
                  \+--------------------------+  
                  |       ELEMENT TREE       | (Normalized Semantic Controls & Layout Nodes)  
                  \+--------------------------+  
                               |  
            \+------------------+------------------+  
            |                                     |  
            v                                     v  
\+--------------------------+         \+--------------------------+  
|     INTERACTION TREE     |         |        EVENT TREE        |  
| (Actionable Bounds,      |         | (Active Listeners,       |  
|  Click Points, Patterns) |         |  Hook Targets, Queues)   |  
\+--------------------------+         \+--------------------------+

### **Node Structural Definition (Unified C++ Data Model)**

C++  
struct DAPNode {  
    std::string node\_id;          // Unique GUID within DAP Runtime  
    std::string parent\_node\_id;   // Parent GUID  
    std::vector\<std::string\> child\_node\_ids;

    // Window / OS Primitives  
    uint64\_t hwnd;                // OS Window Handle (HWND)  
    uint32\_t process\_id;          // Target Process ID (PID)  
    uint32\_t thread\_id;           // Target Thread ID  
    std::string framework\_type;   // "Win32" | "WPF" | "WinUI" | "Qt" | "Electron" | "Java"

    // Geometry & Layout  
    struct Rect {  
        int32\_t left, top, right, bottom;  
        double scale\_factor;  
    } bounds;

    // Accessibility & Semantic Metadata  
    std::string control\_type;     // "Button", "Edit", "Window", "List", etc.  
    std::string name;             // Accessible Name / Title  
    std::string class\_name;        // Native Window Class / Framework Class  
    std::string automation\_id;    // Native AutomationID  
    std::string value;            // Current Control Text/Value  
      
    // Status Flags  
    bool is\_enabled;  
    bool is\_visible;  
    bool is\_focused;  
    bool is\_offscreen;  
    bool supports\_background;     // True if background input/patterns work without foregrounding

    // Visual Detection Attributes (populated if visual pipeline is active)  
    float vision\_confidence;      // 0.0 to 1.0 confidence score  
    std::string ocr\_text;         // OCR extracted text inside node bounds  
};

## **5\. Sequence & Flow Diagrams**

### **5.1 System Lifecycle Sequence**

Code snippet  
sequenceDiagram  
    autonumber  
    participant Host as Hojaiga Orchestrator  
    participant DAP as DAP Runtime Core  
    participant Security as Security Enforcer  
    participant Tree as Tree Orchestrator  
    participant OS as Windows OS / Target Apps

    Host-\>\>DAP: Launch DapRuntime.exe \--pipe=hojaiga\_dap\_01  
    DAP-\>\>Security: Validate Host Process Token & Permissions  
    Security--\>\>DAP: Session Authorized (Level: Elevated Admin)  
    DAP-\>\>DAP: Initialize Win32 Hook Engine & DXGI Capture  
    DAP-\>\>Tree: Initialize Desktop & Window Trees  
    Tree-\>\>OS: EnumWindows() & Register WinEvent Hooks  
    OS--\>\>Tree: Returns Desktop Topographies & HWNDs  
    DAP--\>\>Host: JSON-RPC Ready Signal {status: "RUNNING", pipe: "hojaiga\_dap\_01"}

### **5.2 Packet Flow Sequence (JSON-RPC 2.0 Command Execution)**

Code snippet  
sequenceDiagram  
    autonumber  
    participant Host as Hojaiga Orchestrator  
    participant Protocol as Protocol Parser  
    participant Query as Query Engine  
    participant Interactor as Interaction Engine  
    participant Target as Target Application

    Host-\>\>Protocol: JSON-RPC Req: "Control.invoke" {nodeId: "node\_98A3"}  
    Protocol-\>\>Query: Resolve Node "node\_98A3"  
    Query--\>\>Protocol: Node Resolved (HWND: 0x001F0422, Type: "Button", Framework: "UIA")  
    Protocol-\>\>Interactor: Execute Invoke Pattern (HWND: 0x001F0422)  
      
    alt Target Supports Background Direct Execution  
        Interactor-\>\>Target: UIA InvokePattern::Invoke() / Win32 BM\_CLICK  
        Target--\>\>Interactor: Action Acknowledged  
    else Target Requires Foreground Dispatch  
        Interactor-\>\>Target: Request Focus & Bring to Foreground  
        Interactor-\>\>Target: Physical Input Injection (SendInput Click)  
        Interactor-\>\>Target: Restore Previous Window Focus  
    end

    Interactor--\>\>Protocol: Execution Result Success  
    Protocol--\>\>Host: JSON-RPC Res: {id: 104, result: {success: true, duration\_ms: 12}}

### **5.3 Auto-Recovery Pipeline Sequence**

Code snippet  
sequenceDiagram  
    autonumber  
    participant Host as Hojaiga Orchestrator  
    participant Runtime as DAP Runtime Engine  
    participant Target as Target Process (e.g., Photoshop.exe)  
    participant Vision as Vision Engine

    Host-\>\>Runtime: Command: "Control.invoke" {selector: "btn\_save"}  
    Runtime-\>\>Target: Execute Action  
    Target--xRuntime: CRASH / Handle Invalidated / Freeze Timeout  
      
    Note over Runtime: Health Monitor Detects State Degradation  
    Runtime-\>\>Runtime: Mark Current Tree Node Stale  
    Runtime-\>\>Target: Attempt Process Re-attach / Window Refetch  
      
    alt Standard Re-Attach Succeeded  
        Runtime-\>\>Target: Query Fresh Window Handles  
        Runtime--\>\>Host: Action Retried & Succeeded  
    else Native Tree Lost / Broken Provider  
        Runtime-\>\>Vision: Fallback: Trigger DXGI Capture & OCR/YOLO Analysis  
        Vision--\>\>Runtime: Visual Bounding Box Found for "Save" Button  
        Runtime-\>\>Target: Inject Physical Mouse Click via Coordinates  
        Runtime--\>\>Host: Action Succeeded via Vision Recovery Fallback  
    end

## **6\. Communication Protocol & Wire Specification**

Communication takes place over Windows Named Pipes (\\\\.\\pipe\\hojaiga\_dap\_\<id\>) or Encrypted Local WebSockets (ws://127.0.0.1:\<port\>).

The transport protocol complies strictly with **JSON-RPC 2.0**.

### **6.1 Packet Frames**

#### **Command Request Frame (Host \-\> DAP)**

JSON  
{  
  "jsonrpc": "2.0",  
  "id": 1042,  
  "method": "Control.invoke",  
  "params": {  
    "sessionId": "sess\_8f93a1c0",  
    "target": {  
      "queryType": "a11y",  
      "selector": "Window\[name='Photoshop'\] \-\> Button\[automationId='SaveBtn'\]"  
    },  
    "options": {  
      "timeoutMs": 5000,  
      "forceForeground": false,  
      "verifyVisualState": true  
    }  
  }  
}

#### **Command Response Frame (DAP \-\> Host)**

JSON  
{  
  "jsonrpc": "2.0",  
  "id": 1042,  
  "result": {  
    "status": "SUCCESS",  
    "executionTimeMs": 14,  
    "backgroundExecuted": true,  
    "nodeState": {  
      "nodeId": "node\_00f81a2c",  
      "enabled": true,  
      "visible": true  
    }  
  }  
}

#### **Asynchronous Event Frame (DAP \-\> Host)**

JSON  
{  
  "jsonrpc": "2.0",  
  "method": "Window.eventOccurred",  
  "params": {  
    "eventType": "WINDOW\_FOCUS\_CHANGED",  
    "timestampUs": 1724001234567890,  
    "hwnd": 131284,  
    "processId": 4092,  
    "title": "Adobe Photoshop 2026",  
    "bounds": { "left": 0, "top": 0, "right": 1920, "bottom": 1080 }  
  }  
}

## **7\. Complete API Method Specifications**

### **7.1 Window Management Domain (Window.\*)**

 ┌────────────────────────────────────────────────────────────────────────┐  
  │                           Window Domain API                            │  
  ├──────────────────────────────────┬─────────────────────────────────────┤  
  │ Method                           │ Purpose                             │  
  ├──────────────────────────────────┼─────────────────────────────────────┤  
  │ Window.enumerate                 │ Returns global Window Hierarchy Tree│  
  │ Window.focus                     │ Brings target HWND to foreground    │  
  │ Window.activate                  │ Sends WM\_ACTIVATE / UIA SetFocus    │  
  │ Window.restore                   │ Restores minimized/maximized window │  
  │ Window.maximize                  │ Maximize target window              │  
  │ Window.minimize                  │ Minimize target window              │  
  │ Window.capture                   │ Takes DXGI/PrintWindow Frame Capture│  
  │ Window.query                     │ Query window tree using native rules│  
  └──────────────────────────────────┴─────────────────────────────────────┘

#### **Method Specifications**

* **Window.enumerate(options?: EnumerateOptions): WindowTree**  
  * options.includeChildWindows: boolean (Default: true)  
  * options.processFilter: Array\<number\> (PIDs to isolate)  
  * *Returns*: Complete hierarchy array of all top-level and nested HWND instances.  
* **Window.focus(target: NodeTarget): WindowState**  
  * Activates input thread attach (AttachThreadInput), restores window if minimized, calls SetForegroundWindow and verifies focus lock.  
* **Window.capture(target: NodeTarget, options?: CaptureOptions): CaptureResult**  
  * options.format: "png" | "bmp" | "raw\_rgba"  
  * options.method: "DXGI\_DESKTOP\_DUP" | "PRINT\_WINDOW" | "BITBLT"  
  * *Returns*: Base64 image payload or shared memory handle along with precise scale metadata.

### **7.2 Control & Element Domain (Control.\*)**

 ┌────────────────────────────────────────────────────────────────────────┐  
  │                           Control Domain API                           │  
  ├──────────────────────────────────┬─────────────────────────────────────┤  
  │ Method                           │ Purpose                             │  
  ├──────────────────────────────────┼─────────────────────────────────────┤  
  │ Control.query                    │ Resolve element by UIA/Win32 path   │  
  │ Control.invoke                   │ Primary action trigger (Click/Press)│  
  │ Control.expand                   │ Expand tree nodes / combo boxes     │  
  │ Control.collapse                 │ Collapse expandables                │  
  │ Control.select                   │ Select item in List/Grid/Tab        │  
  │ Control.read                     │ Read full property bag of target    │  
  │ Control.value                    │ Read or set text/value pattern      │  
  └──────────────────────────────────┴─────────────────────────────────────┘

#### **Method Specifications**

* **Control.query(selector: SelectorQuery): Array\<ElementNode\>**  
  * Accepts UIA, Win32, or hybrid selectors (e.g., Control\[type='Edit' && name='Username'\]).  
* **Control.invoke(target: NodeTarget): DirectExecutionResult**  
  * Attempts direct pattern invocation (IUIAutomationInvokeProvider::Invoke, WM\_COMMAND, BM\_CLICK). Falls back to physical injection if background flags fail.  
* **Control.value(target: NodeTarget, textValue?: string): ValueResult**  
  * If textValue is provided: Sets the value directly via IUIAutomationValueProvider::SetValue or WM\_SETTEXT.  
  * If omitted: Returns current value string.

### **7.3 Mouse Automation Domain (Mouse.\*)**

* **Mouse.move(x: number, y: number, options?: MovementOptions)**  
  * Smooth curved or instantaneous mouse movements. Supports physical driver level (SendInput) or synthetic window message post (WM\_MOUSEMOVE).  
* **Mouse.drag(startX: number, startY: number, endX: number, endY: number, buttons?: string)**  
  * Handles standard Drag and Drop orchestration, supporting Ole32 OLE Drag-Drop events and raw input sequences.  
* **Mouse.doubleClick(x?: number, y?: number, target?: NodeTarget)**  
* **Mouse.rightClick(x?: number, y?: number, target?: NodeTarget)**  
* **Mouse.scroll(deltaX: number, deltaY: number, target?: NodeTarget)**  
* **Mouse.multiSelect(targets: Array\<NodeTarget\>)**  
  * Synthesizes CTRL \+ Click sequences or bounding box rubber-band selections.

### **7.4 Keyboard Automation Domain (Keyboard.\*)**

* **Keyboard.type(text: string, options?: TypeOptions)**  
  * Sends text via Unicode input events (KEYEVENTF\_UNICODE), bypassing active layout changes, or injects directly into focused UIA text controls.  
* **Keyboard.shortcut(shortcutSequence: string)**  
  * Parses standard shortcut patterns (e.g., "Ctrl+Shift+S", "Alt+F4") and executes correct virtual key down/up sequences with strict timing delays.

### **7.5 Perception Domain (OCR.\* & Vision.\*)**

 ┌────────────────────────────────────────────────────────────────────────┐  
  │                        Perception Domain API                           │  
  ├──────────────────────────────────┬─────────────────────────────────────┤  
  │ Method                           │ Purpose                             │  
  ├──────────────────────────────────┼─────────────────────────────────────┤  
  │ OCR.capture                      │ Run OCR on region/window            │  
  │ OCR.query                        │ Find elements by text string & bounds│  
  │ Vision.capture                   │ Run ML object detection models      │  
  │ Vision.query                     │ Query controls via visual ML tags   │  
  └──────────────────────────────────┴─────────────────────────────────────┘

#### **Method Specifications**

* **OCR.query(target: NodeTarget, textPattern: string): Array\<VisualNode\>**  
  * Executes GPU/CPU accelerated OCR (PaddleOCR / Tesseract runtime) on specified window bounds and returns bounding boxes of text hits.  
* **Vision.query(target: NodeTarget, className: string): Array\<VisualNode\>**  
  * Runs YOLOv8 ONNX object detection model to locate non-standard UI controls (e.g., custom rendered game buttons, Canvas elements, video editor tracks) by visually categorizing UI components.

## **8\. Background Execution & Foreground Orchestration Engine**

The core requirement of DAP is non-disruptive execution. It determines whether an interaction can occur silently in the background or requires foreground access.

                       \+---------------------------------------+  
                        |      INTERACTION ACTION REQUESTED     |  
                        \+---------------------------------------+  
                                            |  
                                            v  
                        \+---------------------------------------+  
                        | Does target node support Direct       |  
                        | Background Invocation?                |  
                        | (Win32 Message / UIA Native Pattern)  |  
                        \+---------------------------------------+  
                                   |                 |  
                         YES       |                 | NO  
            \+----------------------+                 \+----------------------+  
            v                                                               v  
\+---------------------------------------+       \+---------------------------------------+  
|  EXECUTE IN BACKGROUND                |       |  FOREGROUND ORCHESTRATION PIPELINE    |  
|  1\. Send WM\_COMMAND / UIA Invoke      |       |  1\. Capture current Foreground HWND   |  
|  2\. Target remains covered/minimized  |       |  2\. Lock Input Subsystem              |  
|  3\. Zero mouse cursor displacement    |       |  3\. Restore & Focus Target HWND       |  
\+---------------------------------------+       |  4\. Execute Physical Input (SendInput)|  
                                                |  5\. Restore Original Foreground HWND  |  
                                                |  6\. Unlock Input Subsystem            |  
                                                \+---------------------------------------+

### **Background Capabilities Matrix by Framework**

| UI Framework | Background Text Input | Background Click / Invoke | Background Capture | Background Tree Introspection |
| :---- | :---- | :---- | :---- | :---- |
| **Win32** | WM\_SETTEXT / EM\_REPLACESEL | WM\_COMMAND / BM\_CLICK | PrintWindow (PW\_RENDERFULLCONTENT) | Native (EnumChildWindows) |
| **UIA (WPF/WinUI)** | IUIAutomationValueProvider | IUIAutomationInvokeProvider | DXGI Desktop Duplication / BitBlt | Native (IUIAutomationTreeWalker) |
| **Electron / Chromium** | CDP Bridge / UIA Patterns | UIA Invoke Pattern | DXGI / BitBlt | Chromium Accessibility Engine |
| **Qt / GTK** | Native MSAA/UIA Direct Calls | MSAA accDoDefaultAction | BitBlt / DXGI | Native Accessibility Providers |
| **Java (Swing/AWT)** | Java Access Bridge (setTextContents) | JAB doAccessibleAction | BitBlt / JAB Offscreen Buffer | Java Access Bridge Context Context |

## **9\. Error, State & Event Catalogs**

### **9.1 Error Catalog**

| Error Code | Error Constant | Category | Description |
| :---- | :---- | :---- | :---- |
| 0x1001 | ERR\_NODE\_NOT\_FOUND | Query | Target query selector returned zero matching nodes. |
| 0x1002 | ERR\_NODE\_AMBIGUOUS | Query | Query matched multiple nodes when single node expected. |
| 0x2001 | ERR\_WINDOW\_STALE | Runtime | Window handle (HWND) became invalid during action. |
| 0x2002 | ERR\_FOREGROUND\_LOCK\_FAILED | OS System | Unable to acquire foreground context (SetForegroundWindow rejected). |
| 0x3001 | ERR\_BACKGROUND\_UNSUPPORTED | Execution | Operation cannot complete in background; foreground focus required. |
| 0x4001 | ERR\_OCR\_ENGINE\_FAILURE | Perception | Optical Character Recognition backend crashed or timed out. |
| 0x4002 | ERR\_VISION\_MODEL\_NOT\_LOADED | Perception | ONNX model context uninitialized or missing weights. |
| 0x5001 | ERR\_ACCESS\_DENIED\_ELEVATION | Security | Target process runs at higher Integrity Level (UAC / Admin required). |

### **9.2 State Catalog**

             \+-------------------------------------------------+  
              |                    UNINITIALIZED                |  
              \+-------------------------------------------------+  
                                       |  
                                       v  
              \+-------------------------------------------------+  
              |                     READY                       |  
              \+-------------------------------------------------+  
                 |                     |                     |  
                 v                     v                     v  
  \+--------------------+  \+--------------------+  \+--------------------+  
  |     EXECUTING      |  |     SCANNING       |  |     RECOVERING     |  
  \+--------------------+  \+--------------------+  \+--------------------+  
                 |                     |                     |  
                 \+---------------------+---------------------+  
                                       |  
                                       v  
              \+-------------------------------------------------+  
              |                     FAULTED                     |  
              \+-------------------------------------------------+

### **9.3 Event Catalog**

* **Window.created**: Fired when a new top-level or child HWND is created.  
* **Window.destroyed**: Fired when an HWND is destroyed.  
* **Window.focusChanged**: Fired when active OS window focus shifts.  
* **Element.propertyChanged**: Fired on UIA or Win32 property changes (value, visibility, text).  
* **System.dpiChanged**: Fired when target window changes monitor scale context.  
* **System.securityPromptDetected**: Fired when an OS UAC dialog or credential prompt appears.

## **10\. Non-Functional Requirements & Performance Metrics**

 ┌────────────────────────────────────────────────────────────────────────┐  
  │                   Performance & SLA Metrics                           │  
  ├──────────────────────────────────┬─────────────────────────────────────┤  
  │ Metric                           │ Target SLA Specification            │  
  ├──────────────────────────────────┼─────────────────────────────────────┤  
  │ Cold Startup Time                │ ≤ 180 ms                            │  
  │ Command Execution Latency        │ ≤ 8 ms (Direct Win32/UIA Patterns)  │  
  │ Tree Resolution Latency          │ ≤ 25 ms (Full Desktop scan \<5k nodes│  
  │ Visual Screen Capture Latency    │ ≤ 4 ms (DXGI Frame Grabbing @ 4K)   │  
  │ OCR Target Query Latency         │ ≤ 120 ms (GPU Accelerated)          │  
  │ Memory Baseline Idle             │ ≤ 35 MB                             │  
  │ Memory Peak Active               │ ≤ 180 MB (with Vision models loaded)│  
  │ Maximum Managed Handles          │ 10,000 Concurrent Window Nodes      │  
  └──────────────────────────────────┴─────────────────────────────────────┘

### **Security & Integrity Enforcement**

1. **UAC / Integrity Boundary**: The runtime automatically elevates to High Integrity Level or launches an out-of-process elevated worker (DapHostProxy.exe) to automate elevated installer wizards and secure system prompts.  
2. **Process Sandboxing**: Third-party framework hooks (such as DapJavaBridge.dll) execute within target spaces with strict exception-handling wrappers to avoid crashing host user applications under any scenario.  
3. **Encrypted IPC**: Pipe transport uses local process security descriptors (SDDL), ensuring only authorized Hojaiga Core Orchestrator PIDs can bind and communicate with the DAP runtime instance.

