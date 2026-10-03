# **Organ 06 — Automation Specification Document**

## **1\. Overview**

The Automation Organ is the primary execution runtime for browser, window, desktop GUI, system application, and hardware media interaction within the Hojaiga Automation Operating System. It integrates Playwright, Chrome DevTools Protocol (CDP), Windows UI Automation (UIA), OBS Studio media recording, and an isolated security sandbox to execute complex interactive workflows deterministically. Operating CPU-first with memory-efficient headless/headed browser sessions, the Automation Organ controls user-level interfaces without exposing private organ internals or compromising operating system stability.

MD+ 4

## **2\. Purpose**

The purpose of the Automation Organ is to provide robust, reliable, and secure interaction capabilities across desktop applications and web applications. It translates high-level domain directives from the Controllers Organ into precise browser actions, window management operations, file dialog interactions, clipboard manipulation, and audio/video recording workflows while maintaining strict plugin validation and session recovery controls.

MD+ 3

## **3\. Philosophy**

In strict alignment with Chapter 7 of the Master Architecture Blueprint, Universal Law 8 (Failure Transparency and Recovery), and Policy Manual Chapter 1, all automation interactions must be verifiable, sandboxed, recoverable, and transparent. The Automation Organ treats external GUIs and web pages as untrusted target environments. Direct access to system interfaces is routed exclusively through validated plugins and secure sandbox wrappers, ensuring that dynamic browser elements, file downloads, or parent-child window hierarchy shifts do not stall or corrupt the system runtime state.

MD+ 4

## **4\. Primary Responsibilities**

* **Browser Automation & CDP Management:** Drive Playwright and raw Chrome DevTools Protocol (CDP) sessions for web scraping, form filling, and web-app interaction.  
   MD+ 1  
* **Browser Session & State Management:** Maintain isolated browser contexts, manage cookies, localStorage, proxies, file downloads, and upload streams.  
   MD+ 1  
* **Desktop GUI & Window Automation:** Enforce parent-child window tracking, focus management, and element manipulation via Windows UI Automation (UIA).  
   MD+ 1  
* **Application Lifecycle Control:** Launch, monitor, attach to, and gracefully terminate desktop applications via Application Manager.  
   MD+ 1  
* **Tool & Plugin Sandbox Execution:** Validate and run automation extensions within a strictly restricted security sandbox.  
   MD+ 1  
* **OBS Studio Integration:** Orchestrate OBS recording sessions for task auditing, screen capture, and visual validation.  
   MD+ 1  
* **System OS Interactions:** Safely handle OS file dialogs, clipboard operations, and system notifications.  
   MD+ 1  
* **Self-Healing & Retry Logic:** Automatically handle element wait timeouts, stale element references, and browser crashes through configurable retry loops.  
   MD+ 1

## **5\. Internal Modules**

* `automation_core`: Central IPC communication socket listener and orchestration runtime.  
* `browser_manager`: Controls Playwright browser instances (Chromium/Firefox/WebKit) and raw CDP connections.  
   MD+ 1  
* `window_manager`: Manages desktop window handles (HWND), top-level/child window hierarchy, and UI focus tracking.  
   MD+ 1  
* `uia_controller`: Native Windows UI Automation (UIA) wrapper for desktop app element trees and control patterns.  
   MD+ 1  
* `app_manager`: Governs process spawning, binary path verification, and execution monitoring.  
   MD+ 1  
* `tool_manager`: Manages executable tools, CLI wrappers, and local automation scripts.  
   MD+ 1  
* `obs_integration`: Websocket-based controller interface for OBS Studio recording and streaming pipelines.  
   MD+ 1  
* `security_sandbox`: Isolated execution container restricting plugin rights and file system access.  
   MD+ 1  
* `plugin_validator`: Verifies extension signatures, code safety, and schema manifest compliance.  
   MD+ 1  
* `session_manager`: Persists and restores web session storage, cookies, downloads, and upload states.  
   MD+ 1  
* `system_interact`: Low-level wrapper for clipboard, native file dialogs, mouse, and keyboard events.  
   MD+ 1  
* `recovery_engine`: Handles crash detection, element re-locating strategies, and automated retry loops.  
   MD+ 1

## **6\. Internal Folder Structure**

/organ\_06\_automation  
├── bin/  
│   ├── automation\_daemon      \# Primary runtime process executable  
│   └── sandbox\_runner         \# Isolated plugin container process  
├── config/  
│   ├── browser\_profiles.json  \# Browser launch flags and viewport defaults  
│   └── sandbox\_policy.json    \# File system and network isolation rules  
├── src/  
│   ├── core/  
│   │   ├── automation\_kernel.py  
│   │   └── dispatcher.py  
│   ├── browser/  
│   │   ├── browser\_manager.py  
│   │   ├── cdp\_client.py  
│   │   └── session\_store.py  
│   ├── desktop/  
│   │   ├── window\_manager.py  
│   │   ├── uia\_controller.py  
│   │   └── app\_manager.py  
│   ├── media/  
│   │   └── obs\_client.py  
│   ├── sandbox/  
│   │   ├── security\_sandbox.py  
│   │   └── plugin\_validator.py  
│   ├── system/  
│   │   ├── clipboard.py  
│   │   └── file\_dialogs.py  
│   ├── resilience/  
│   │   └── retry\_engine.py  
│   └── sockets/  
│       └── ipc\_server.py  
├── tests/  
└── manifest.json

## **7\. Public Interfaces**

* `IPC Socket Interface`: `\\.\pipe\hojaiga_automation` (Windows) / `/tmp/hojaiga_automation.sock` (Linux/Unix).  
   MD  
  * `rpc LaunchBrowserSession(BrowserConfigPayload)` \-\> `SessionHandle`  
  * `rpc ExecuteBrowserAction(BrowserActionPayload)` \-\> `BrowserActionResult`  
  * `rpc CaptureWindowTree(WindowQueryPayload)` \-\> `WindowTreeStructure`  
  * `rpc ClickUIElement(UIAElementQuery)` \-\> `UIAActionResult`  
  * `rpc StartOBSCapture(CaptureConfigPayload)` \-\> `StreamStatus`  
  * `rpc StopOBSCapture(StopConfigPayload)` \-\> `MediaFilePath`  
  * `rpc ExecuteSandboxedPlugin(PluginExecutionPayload)` \-\> `PluginResult`  
  * `rpc AccessClipboard(ClipboardOperationPayload)` \-\> `ClipboardContent`  
  * `rpc HandleFileDialog(FileDialogActionPayload)` \-\> `FileActionResult`

## **8\. Internal Interfaces**

* `IBrowserManager`:  
  * `spawn_context(profile_id)`: Allocates an isolated Playwright browser context with specific proxy/cookie profiles.  
     MD+ 1  
  * `get_cdp_session(page_id)`: Returns a direct Chrome DevTools Protocol WebSocket channel for low-level protocol commands.  
     MD+ 1  
* `IWindowManager`:  
  * `enumerate_child_windows(parent_hwnd)`: Scans OS window tree to construct parent-child window tracking maps.  
     MD+ 1  
  * `force_focus_window(hwnd)`: Sets target application window to active foreground state safely.  
     MD+ 1  
* `ISandboxRunner`:  
  * `execute_isolated(plugin_binary, strict_policy)`: Spawns sandboxed sub-process under restricted Job Object security policies.  
     MD+ 1

## **9\. Socket Definitions**

* Named Pipe Socket: `hojaiga_automation`.  
   MD  
* Wire Protocol: Length-Prefixed Binary Frame \[ 4-byte payload length | 2-byte op\_code | JSON Payload \].  
   MD  
* Max Payload Size: 32 MB per frame (supports binary screenshot and buffer streams).

## **10\. Pipeline Definitions**

* `WebAutomationPipeline`:  
  1. CNS Route Directive \-\> 2\. Schema Check \-\> 3\. Acquire/Verify Browser Context \-\> 4\. Execute Playwright Action \-\> 5\. Catch Dynamic DOM Timeouts \-\> 6\. Trigger Retry Engine if Stale \-\> 7\. Return Execution Output.  
      MD+ 2  
* `DesktopGUIAutomationPipeline`:  
  1. CNS Route Directive \-\> 2\. Verify Target App HWND via `app_manager` \-\> 3\. Focus Window via `window_manager` \-\> 4\. Traverse UIA Tree \-\> 5\. Execute Physical/Virtual Click/Input \-\> 6\. Capture Visual Verification \-\> 7\. Return Result.  
      MD+ 2

## **11\. Incoming Connections**

* **CNS Organ (02):** Routes all automation commands, web requests, and desktop GUI interaction requests.  
   MD+ 1  
* **Controllers Organ (05):** Direct controller task dispatches (`app_controller`, `tool_controller`) routed via CNS.  
   MD+ 2

## **12\. Outgoing Connections**

* **CNS Organ (02):** Transmits step completion statuses, visual frames, desktop tree events, and recovery triggers (`EVENT_AUTOMATION_STEP_PASSED`, `EVENT_BROWSER_CRASHED`, `EVENT_ELEMENT_NOT_FOUND`).  
   MD+ 2  
* **OBS Studio Process:** External WebSocket connection (`ws://127.0.0.1:4455`) for recording control.  
   MD+ 1

## **13\. State Management**

The Automation Organ operates a multi-tiered state model across browser and desktop layers:

* `UNINITIALIZED`: Daemon active, no browser instances or active UIA sessions allocated.  
   MD  
* `READY`: Browsers warm-pooled; window listeners active.  
   MD  
* `EXECUTING`: Playwright script or UIA execution active.  
   MD  
* `RECOVERING`: Attempting element re-location or browser restart following a DOM/process crash.  
   MD+ 1  
* `TERMINATING`: Closing browser contexts, flushing download buffers, releasing HWND locks.  
   MD+ 1

## **14\. Event Definitions**

* `EVENT_AUTOMATION_CONTEXT_CREATED`: Fired when a new isolated browser session is created.  
   MD+ 1  
* `EVENT_BROWSER_CRASHED`: Triggered if the Chromium/Firefox child process exits unexpectedly.  
   MD+ 1  
* `EVENT_WINDOW_HIERARCHY_CHANGED`: Fired when parent-child window focus shifts during desktop automation.  
   MD+ 1  
* `EVENT_SANDBOX_VIOLATION_BLOCKED`: Emitted if a plugin attempts unauthorized disk/network operations.  
   MD+ 1

## **15\. Data Contracts**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "BrowserActionRequest",  
  "type": "object",  
  "properties": {  
    "action\_id": { "type": "string", "format": "uuid" },  
    "session\_id": { "type": "string" },  
    "action\_type": {   
      "type": "string",   
      "enum": \["navigate", "click", "type", "select\_option", "upload\_file", "download\_file", "evaluate\_cdp"\]   
    },  
    "selector": { "type": "string" },  
    "input\_data": { "type": "string" },  
    "timeout\_ms": { "type": "integer", "default": 10000 }  
  },  
  "required": \["action\_id", "session\_id", "action\_type"\]  
}

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "UIAActionRequest",  
  "type": "object",  
  "properties": {  
    "action\_id": { "type": "string", "format": "uuid" },  
    "process\_name": { "type": "string" },  
    "hwnd": { "type": "integer" },  
    "element\_path": { "type": "array", "items": { "type": "string" } },  
    "control\_type": { "type": "string" },  
    "interaction": { "type": "string", "enum": \["click", "set\_value", "focus", "close"\] }  
  },  
  "required": \["action\_id", "process\_name", "interaction"\]  
}

## **16\. Internal Database Structures**

The Automation Organ maintains an in-memory runtime tracking database using SQLite (`:memory:`):

* Table `browser_sessions` (`session_id` TEXT PRIMARY KEY, `browser_type` TEXT, `profile_path` TEXT, `created_at` TIMESTAMP, `status` TEXT).  
   MD+ 1  
* Table `window_handles` (`hwnd` INTEGER PRIMARY KEY, `parent_hwnd` INTEGER, `process_id` INTEGER, `window_title` TEXT, `is_active` INTEGER).  
   MD+ 1  
* Table `sandboxed_plugins` (`plugin_id` TEXT PRIMARY KEY, `manifest_hash` TEXT, `permission_mask` INTEGER, `is_validated` INTEGER).  
   MD+ 1

## **17\. Cache Strategy**

* UIA Tree Cache: Desktop UI Automation element trees cached for 500ms to eliminate continuous OS thread-traversal overhead during multi-input workflows.  
   MD+ 1  
* Browser Page Pool: Up to 2 pre-warmed headless page contexts retained in RAM for instant action dispatch.  
   MD+ 1

## **18\. Memory Strategy**

* Core daemon RAM capped at 1.5 GB max (including active Playwright Chromium subprocesses).  
   MD  
* Browser memory limits enforced via Chromium CLI flags (`--js-flags="--max-old-space-size=512"`) to prevent VRAM or host RAM exhaustion.  
   MD+ 1

## **19\. Thread Safety**

* Native Windows UI Automation calls dispatched through a single-threaded apartment (STA) thread queue to prevent Win32 thread safety violations.  
   MD  
* Async Playwright control loops managed via dedicated Python `asyncio` event loops protected by thread locks.  
   MD

## **20\. Concurrency**

* Up to 4 parallel headless browser pages per Chromium instance.  
   MD+ 1  
* Desktop UIA and window management operations execute sequentially to ensure deterministic mouse/keyboard and window focus behavior.  
   MD+ 2

## **21\. Hardware Optimization**

* CPU-First Architecture: Web rendering layout calculations and UIA element matching execute on Intel Core i7 physical cores.  
   MD  
* GPU Hardware Acceleration explicitly disabled in Chromium flags (`--disable-gpu`) to preserve all 4 GB GPU VRAM for Brain Organ LLM inference.  
   MD+ 1

## **22\. GPU Usage**

* Zero VRAM allocation. All browser rendering operates via software rasterization (`--disable-software-rasterizer`, `--disable-gpu`).  
   MD+ 1

## **23\. CPU Usage**

* Idle CPU consumption: \<1.0%.  
   MD  
* Peak CPU usage during complex web DOM rendering or UIA tree traversal capped at 20% across host CPU cores.  
   MD+ 1

## **24\. SSD Usage**

* Runtime download staging, browser session cookies, temporary screenshots, and session profiles stored on 100 GB SSD Runtime.  
   MD+ 1

## **25\. HDD Usage**

* Recorded OBS task execution video files, bulk web scrapes, and historical session logs archived to external HDD storage.  
   MD+ 1

## **26\. Security Model**

* Sandbox Containment: Plugin execution takes place within restricted Win32 Job Objects restricting process spawning, network sockets, and non-whitelisted path writes.  
   MD+ 1  
* Extension Validation: Mandatory SHA-256 signature and manifest validation before dynamic extension loading.  
   MD+ 1

## **27\. Permissions**

* Desktop window actions restricted strictly to windows owned by the current user session.  
   MD+ 1  
* Administrative privilege escalation prohibited during application launching or UI automation passes.  
   MD+ 2

## **28\. Logging**

* Structured JSON logging compliant with Policy Manual Chapter 8\.  
   MD  
* Records `action_id`, `session_id`, `target_selector`, `hwnd`, `duration_ms`, `retry_attempts`, and `status_code`.  
   MD+ 1

## **29\. History Recording**

* Complete DOM action logs, selector match history, and OBS media references are appended sequentially to external HDD history archives.  
   MD+ 2

## **30\. Recovery Strategy**

* Dynamic DOM Re-Locating: If a target element selector fails due to page updates, `retry_engine` attempts fuzzy text matching and relative visual layout positioning before raising an exception.  
   MD+ 1  
* Browser Context Recovery: Automated recovery spawns a new Chromium page context and restores stored cookies/localStorage in under 2 seconds if a browser process crashes.  
   MD+ 1

## **31\. Failure Handling**

* Window Freeze: If an application window stops responding (`IsHungAppWindow` check returns true), `window_manager` logs the event, notifies CNS, and executes controlled app restart sequences.  
   MD+ 2

## **32\. Validation Rules**

* Plugins must pass manifest verification (whitelisted capabilities, declared paths).  
   MD+ 1  
* Browser actions must complete within specified timeout windows (default 10000ms).  
   MD+ 1

## **33\. Testing Strategy**

* End-to-end browser tests against local offline HTML fixture pages verifying Playwright, CDP, and download operations.  
   MD+ 1  
* Integration tests targeting native Windows applications (e.g., Notepad) to verify UIA element manipulation and parent-child HWND tracking.  
   MD+ 1

## **34\. Extension Points**

* Custom Automation Plugins: Interface definitions in `sandbox/` permit adding custom web/desktop automation drivers.  
   MD+ 1

## **35\. Future Compatibility**

* Dynamic CDP protocol version alignment supporting Chromium runtime version upgrades.  
   MD+ 1

## **36\. Versioning**

* Semantic Versioning: `v1.0.0` Automation Organ Specification.  
   MD+ 1

## **37\. Dependencies**

* Playwright Core / Chromium headless binaries.  
   MD+ 1  
* Windows UI Automation API bindings (PyWinAuto / `UIAutomationCore.dll`).  
   MD+ 1  
* `obs-websocket-py` / OBS Studio 30+.  
   MD+ 1

## **38\. Interaction with Other Organs**

* **CNS (Organ 02):** Routes incoming execution demands and outgoing status frames.  
   MD+ 1  
* **Controllers (Organ 05):** Translates high-level app plans into Automation Organ calls.  
   MD+ 2  
* **Security (Organ 07):** Audits sandbox policy files and validates plugin execution rights.  
   MD+ 2  
* **Infrastructure (Organ 09):** Provides SSD/HDD storage targets for media recordings and session state dumps.  
   MD+ 1

## **39\. Mermaid Component Diagram**

Code snippet  
graph TD  
    CNS\[CNS Organ 02\] \--\>|IPC Sockets| Core\[Automation Kernel\]  
    Core \--\> BM\[Browser Manager\]  
    Core \--\> WM\[Window Manager\]  
    Core \--\> UIA\[Windows UIA Controller\]  
    Core \--\> OBS\[OBS Integration\]  
    Core \--\> SB\[Security Sandbox\]  
    BM \--\>|CDP / WebSocket| Playwright\[Playwright Chromium\]  
    WM \--\>|Win32 API| HWND\[Desktop HWND Handles\]  
    UIA \--\>|UIAutomationCore| WinApp\[Desktop Applications\]  
    SB \--\>|Job Objects| Extension\[Sandboxed Plugins\]

## **40\. Mermaid Sequence Diagram**

Code snippet  
sequenceDiagram  
    participant CNS as Organ 02 (CNS)  
    participant Core as Automation Kernel  
    participant BM as Browser Manager  
    participant Play as Playwright Core  
    participant SB as Sandbox Runner

    CNS-\>\>Core: Execute Browser Action (Click Selector)  
    Core-\>\>BM: Acquire Active Page Context  
    BM-\>\>Play: Execute Click (CSS Selector)  
    alt Element Stale or Timeout  
        Play--\>\>BM: Timeout Exception  
        BM-\>\>BM: Trigger Retry Engine (Fuzzy Re-Locate)  
        BM-\>\>Play: Retry Click Action  
    end  
    Play--\>\>BM: Click Execution Success  
    BM--\>\>Core: Action Complete Payload  
    Core--\>\>CNS: Execution Result

## **41\. Mermaid Flow Diagram**

Code snippet  
flowchart TD  
    A\[Incoming Task Directives\] \--\> B{Task Scope}  
    B \-- Web Automation \--\> C\[Route to Browser Manager\]  
    B \-- Desktop GUI \--\> D\[Route to Window Manager / UIA\]  
    B \-- Media Recording \--\> E\[Route to OBS Client\]  
    B \-- Plugin Task \--\> F\[Validate Manifest & Load Sandbox\]  
    C \--\> G\[Execute Playwright / CDP Pass\]  
    D \--\> H\[Enumerate HWND & Focus Target\]  
    H \--\> I\[Execute UIA Element Control\]  
    G \--\> J{Execution Success?}  
    J \-- No \--\> K\[Invoke Recovery Engine & Retry Loop\]  
    J \-- Yes \--\> L\[Package Results & Return to CNS\]  
    K \--\> J

## **42\. Mermaid State Diagram**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Uninitialized  
    Uninitialized \--\> Ready : Browsers Warm-Pooled & Listener Up  
    Ready \--\> Executing : Action Received  
    Executing \--\> Recovering : Timeout / Process Stale  
    Recovering \--\> Executing : Target Re-Located / Process Restarted  
    Executing \--\> Ready : Task Finished  
    Executing \--\> Terminating : Hard Shutdown Call  
    Terminating \--\> \[\*\]

## **43\. Mermaid Folder Diagram**

Code snippet  
graph TD  
    Root\[organ\_06\_automation\] \--\> Bin\[bin/automation\_daemon\]  
    Root \--\> Config\[config/browser\_profiles.json\]  
    Root \--\> Src\[src/\]  
    Src \--\> Core\[core/automation\_kernel.py\]  
    Src \--\> Browser\[browser/browser\_manager.py\]  
    Src \--\> Desktop\[desktop/window\_manager.py\]  
    Src \--\> Media\[media/obs\_client.py\]  
    Src \--\> Sandbox\[sandbox/security\_sandbox.py\]  
    Src \--\> Resilience\[resilience/retry\_engine.py\]

## **44\. Mermaid Socket Diagram**

Code snippet  
graph LR  
    CNS\[CNS Master Socket\] \-- Named Pipe \--\> Pipe\[\\\\.\\pipe\\hojaiga\_automation\]  
    Pipe \--\> IPC\[IPC Server Listener Thread\]  
    IPC \--\> Core\[Automation Kernel Router\]

## **45\. Mermaid Pipeline Diagram**

Code snippet  
graph LR  
    P1\[1. IPC Ingestion\] \--\> P2\[2. Action Classification\]  
    P2 \--\> P3\[3. Target Focus & Context Binding\]  
    P3 \--\> P4\[4. Sandboxed Execution\]  
    P4 \--\> P5\[5. Retry & Fallback Check\]  
    P5 \--\> P6\[6. State & Media Persistence\]

## **46\. Engineering Recommendations**

* Force Chromium software rendering explicitly (`--disable-gpu`) on the Windows 11 host to eliminate any possibility of dynamic VRAM allocation interfering with the 4 GB GPU VRAM pool reserved for `llama.cpp`.  
   MD+ 1  
* Initialize Windows UI Automation (UIA) threads explicitly in Single-Threaded Apartment (STA) mode to avoid `CO_E_NOTINITIALIZED` COM concurrency crashes during desktop window manipulation.  
   MD

## **47\. Tradeoffs**

* **Headless Software Rendering vs. Hardware-Accelerated Browser Operations:** Software rendering increases host CPU utilization by \~5% during complex web page layouts, but guarantees zero VRAM footprint and absolute stability for the primary LLM Brain.  
   MD+ 1  
* **Strict Win32 Job Object Sandboxing vs. Direct Extension Loading:** Sandboxing introduces a \~10ms overhead during extension startup, but prevents malicious or buggy plugins from modifying core operating system configurations.  
   MD+ 1

## **48\. Alternatives Considered**

* **Selenium WebDriver Local Server:** Rejected due to excessive Java runtime overhead, slower execution speeds, and poor modern shadow-DOM handling compared to native Playwright/CDP integration.  
   MD+ 1  
* **AutoIt / Raw Windows Mouse-Click Automation:** Rejected due to high fragility against screen resolution changes, lack of element tree inspection, and inability to handle hidden background windows reliably.  
   MD+ 1

## **49\. Future Improvements**

* AI-assisted visual element locating using CPU-based template matching algorithms when UIA accessibility trees are omitted in custom desktop applications.  
   MD+ 1  
* Direct CDP network interception pipelines for ultra-fast API response mocking during automated web tests.  
   MD+ 1

## **50\. Claude Implementation Instructions**

1. Create file and folder structure as outlined in Section 6\.  
    MD  
2. Implement `browser/browser_manager.py` using Playwright Python async bindings with explicit Chromium GPU-disable flags.  
    MD+ 1  
3. Build `desktop/window_manager.py` and `uia_controller.py` using PyWin32 / `UIAutomationCore` libraries.  
    MD+ 1  
4. Implement `sandbox/security_sandbox.py` deploying Win32 `JobObjects` for plugin process restriction.  
    MD+ 1  
5. Set up Named Pipe IPC server listening at `\\.\pipe\hojaiga_automation`.  
    MD

