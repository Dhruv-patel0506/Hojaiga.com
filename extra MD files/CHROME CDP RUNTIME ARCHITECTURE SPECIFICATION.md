# **CHROME CDP RUNTIME ARCHITECTURE SPECIFICATION**

## **1\. PURPOSE**

The Chrome CDP Runtime (`Chrome_CDP_Runtime.md`) is the exclusive, authoritative browser communication, execution, and instrumentation layer for the Hojaiga Automation Operating System (AOS).

It abstracts Chromium-based browser instances into deterministically controllable, event-driven interfaces by communicating directly over the Chrome DevTools Protocol (CDP) via WebSocket interfaces. It owns browser connection lifecycles, execution contexts, DOM/Accessibility tree syntheses, virtual input emulation, network flow interceptions, media stream capture, and native OS file picker bridge integrations.

Restoration of execution pipelines, failover routing, and state restoration during process terminations are handled via the embedded Session Recovery and Crash Engine in direct coordination with the system Recovery Manager.

## **2\. CDP ARCHITECTURE**

The Chrome CDP Runtime operates as an asynchronous, non-blocking I/O multiplexer constructed around a bi-directional WebSocket transport layer. It parses and generates JSON-RPC 2.0 messages conforming to the Chromium DevTools Protocol specification.

\+-----------------------------------------------------------------------------------+  
|                                CHROME CDP RUNTIME                                 |  
|                                                                                   |  
|  \+--------------------+     \+---------------------+     \+----------------------+  |  
|  |  Connection Mgr    |     |  Target Router      |     | Frame/Context Tracker|  |  
|  |  (WS Multiplexer)  |-----\>  (Session Dispatch) |-----\>  (ExecutionContext)   |  |  
|  \+--------------------+     \+---------------------+     \+----------------------+  |  
|            |                           |                           |              |  
|            v                           v                           v              |  
|  \+--------------------+     \+---------------------+     \+----------------------+  |  
|  |  Command Queue     |     |  Event Bus          |     | Out-of-Band Stream   |  |  
|  |  (RPC Request/Res) |     |  (CDP Event PubSub) |     | (Screencast/Tracing) |  |  
|  \+--------------------+     \+---------------------+     \+----------------------+  |  
\+-----------------------------------------------------------------------------------+  
                                         ^  
                                         | JSON-RPC 2.0 over WebSocket  
                                         v  
\+-----------------------------------------------------------------------------------+  
|                        CHROMIUM BROWSER PROCESS (TARGET)                          |  
|                                                                                   |  
|  \[ Browser Target \] \----\> \[ Page Target \] \----\> \[ Worker / Frame / App Targets \]  |  
\+-----------------------------------------------------------------------------------+

### **Core Architecture Components**

1. **Connection Manager (WebSocket Multiplexer):** Manages raw TCP/WebSocket connections to Chromium debugging endpoints (`ws://<host>:<port>/devtools/browser/<guid>`). Handles connection heartbeats, frame framing, backpressure mitigation, and TLS termination for remote instances.  
2. **Target Router (Session Dispatcher):** Routes CDP commands and events using CDP Flat Protocol Sessions (`Target.attachToTarget` with `flatten: true`). Maps unique CDP `sessionId` strings to internal AOS Session Handles.  
3. **Command Queue:** Guarantees command order, handles timeout policies, and matches JSON-RPC `id` requests with returning responses. Supports request priority queues for real-time human-in-the-loop overrides.  
4. **Event Bus:** Asynchronous event distribution system using lock-free ring buffers to publish CDP domain events (`Page.*`, `Network.*`, `DOM.*`, `Console.*`) to subscribing system modules.  
5. **Frame & Execution Context Tracker:** Maintains real-time mapping of `FrameId`, `LoaderId`, and JavaScript `ExecutionContextId` across frame navigations, reloads, and cross-origin iframe lifecycle changes.  
6. **Out-of-Band Stream Engine:** Efficiently processes heavy binary payloads (screencast frames, tracing buffers, continuous canvas video feeds) without blocking standard RPC command lanes.

## **3\. BROWSER DISCOVERY AND ATTACHMENT**

The discovery subsystem scans, verifies, and attaches to Chromium instances across local and remote environments.

                    \+---------------------------+  
                     | Browser Discovery Engine  |  
                     \+---------------------------+  
                                   |  
         \+-------------------------+-------------------------+  
         |                                                   |  
         v                                                   v  
\+------------------+                               \+-------------------+  
| Local Process    |                               | Remote Endpoints  |  
| Auto-Discovery   |                               | Endpoint Resolver |  
\+------------------+                               \+-------------------+  
         |                                                   |  
         |---\> Unix Domain Sockets                           |---\> IPv4 / IPv6 HTTP Scans  
         |---\> Named Pipes (Windows)                         |---\> /json/version Queries  
         |---\> CLI Arguments Parsing                         |---\> Cloud Grid Endpoints  
         \+-------------------------+-------------------------+  
                                   |  
                                   v  
                     \+---------------------------+  
                     | Version & Handshake Verify|  
                     \+---------------------------+  
                                   |  
                                   v  
                     \+---------------------------+  
                     | WebSocket Attachment      |  
                     \+---------------------------+

### **3.1 Local Process Auto-Discovery**

* **Process Table Inspection:** Scans active OS process tables for binaries matching `chrome`, `chromium`, `msedge`, `brave`, `electron`, and `thorium`.  
* **Port Discovery:** Reads parameters `--remote-debugging-port=<port>` or `--remote-debugging-pipe`.  
* **DevTools Active Port File:** Parses file targets in user data profiles (`DevToolsActivePort` file inside target profiles) to obtain dynamic port bindings and base WebSocket paths.

### **3.2 Remote Endpoint Discovery**

* **HTTP JSON Query:** Queries `http://<host>:<port>/json/version` and `http://<host>:<port>/json/list` endpoints to fetch `webSocketDebuggerUrl` strings and protocol target maps.  
* **Health Check Probe:** Validates HTTP 200 response and confirms protocol version parity (`Protocol-Version >= 1.3`).

### **3.3 Attachment Execution Protocol**

1. Issue initial HTTP GET request to `/json/version` on the target port to verify CDP capability.  
2. Extract root `webSocketDebuggerUrl`.  
3. Open non-blocking WebSocket connection to the root endpoint.  
4. Enable global domains: `Target.setDiscoverTargets`, `Target.setAutoAttach`.  
5. Retain local process handles for orphan cleanup and process tree tracking.

## **4\. MULTI-BROWSER, MULTI-WINDOW, AND MULTI-TAB SUPPORT**

The runtime uses a hierarchical topology for nested management across multiple browser instances down to individual target frames.

                           \[ CDP Runtime Engine \]  
                                      |  
         \+----------------------------+----------------------------+  
         |                                                         |  
\[ Browser Instance 1 \]                                   \[ Browser Instance 2 \]  
  (Process ID: 4102\)                                       (Process ID: 8812\)  
         |                                                         |  
         \+--------------------------+                              \+-------------------+  
         |                          |                                                  |  
 \[ Window ID: W-101 \]       \[ Window ID: W-102 \]                              \[ Window ID: W-201 \]  
         |                          |                                                  |  
   \+-----+-----+              \+-----+-----+                                      \+-----+-----+  
   |           |              |           |                                      |           |  
\[Tab T-01\]  \[Tab T-02\]     \[Tab T-03\]  \[Tab T-04\]                             \[Tab T-05\]  \[Tab T-06\]  
   |           |              |           |                                      |           |  
 (Target)    (Target)       (Target)    (Target)                               (Target)    (Target)

### **Hierarchy & Structural Isolation**

| Level | CDP Domain Anchor | Identification | Scope / Responsibility |
| ----- | ----- | ----- | ----- |
| **Browser Instance** | `Browser.*` | `BrowserID` (UUIDv4) | Process boundary, global permissions, process isolation, profile data directories. |
| **Browser Context** | `Target.createBrowserContext` | `BrowserContextID` | Incognito state, isolated storage (cookies, IndexedDB, localStorage), proxy settings. |
| **Window** | `Browser.getWindowForTarget` | `WindowID` (Integer) | Visual bounds, OS-level window placement, state (maximized, minimized, fullscreen). |
| **Tab / Page Target** | `Target.createTarget` | `TargetID` / `SessionID` | Top-level frame rendering, execution context, page navigation, event pipelines. |
| **Sub-Frame** | `Page.getFrameTree` | `FrameId` | Cross-origin sandbox, inner DOM tree execution, iframe target attachment. |

### **Flattened CDP Attachment Strategy**

To prevent connection exhaustion and reduce socket overhead, the system utilizes target flattening (`Target.attachToTarget(targetId, flatten=true)`). All communications stream over a **single root WebSocket connection per Browser Instance**, routing page/tab interactions via assigned `sessionId` headers.

## **5\. BROWSER SESSION LIFECYCLE**

 \+------------------+  
  |    UNINITIALIZED |  
  \+------------------+  
           |  
           | Launch / Attach Request  
           v  
  \+------------------+  
  |     CONNECTING   |  
  \+------------------+  
           |  
           | Handshake Validated & Target.setAutoAttach Enabled  
           v  
  \+------------------+  
  |      ACTIVE      | \<=======================================+  
  \+------------------+                                         |  
           |                                                   |  
           | Target Crash / Disconnect                         | Session Restored  
           v                                                   |  
  \+------------------+       Recovery Engine Initiated         |  
  |     RECOVERING   | \----------------------------------------+  
  \+------------------+  
           |  
           | Recovery Threshold Exceeded / Fatal Process Loss  
           v  
  \+------------------+  
  |    TERMINATED    |  
  \+------------------+

### **Lifecycle States and Transitions**

1. **UNINITIALIZED:** Session object allocated; configuration and target metrics loaded.  
2. **CONNECTING:** WebSocket opening handshakes initiated; `/json/version` validated; root target attached.  
3. **ACTIVE:** Target context created (`Target.createBrowserContext`); domains enabled (`Page`, `DOM`, `Network`, `Runtime`, `Accessibility`); event pipelines active.  
4. **RECOVERING:** Unscheduled WebSocket drops or target process crashes detected. Command execution paused; incoming events queued; recovery state machine engaged.  
5. **TERMINATED:** Contexts closed (`Target.disposeBrowserContext`); target process cleanly reaped or detached; resources freed.

## **6\. DOM TREE AND ACCESSIBILITY TREE SYNTHESIS**

To allow agents to inspect, query, and interact with the browser, the runtime builds a combined structural map by stitching together the raw DOM tree and the Accessibility (AX) tree.

      DOM Tree Extraction                         AX Tree Extraction  
   (DOM.getDocument / DOM.getFlattenedDocument)   (Accessibility.getFullAXTree)  
              |                                            |  
              \+---------------------+----------------------+  
                                    |  
                                    v  
                     \+----------------------------+  
                     |  Hybrid Structural Engine  |  
                     \+----------------------------+  
                                    |  
            \+-----------------------+-----------------------+  
            |                                               |  
            v                                               v  
\+-----------------------+                       \+-----------------------+  
| Spatial Coordinate    |                       | Visual Selector Map   |  
| Normalizer            |                       | (Aria \+ Visual IDs)   |  
| (DOM.getBoxModel)     |                       |                       |  
\+-----------------------+                       \+-----------------------+  
            |                                               |  
            \+-----------------------+-----------------------+  
                                    |  
                                    v  
                     \+----------------------------+  
                     | Unified Shadow DOM & Frame |  
                     | Composite Representation   |  
                     \+----------------------------+

### **6.1 Unified Node Model**

The runtime constructs a lightweight representation for each interactive element:

JSON  
{  
  "nodeId": 1042,  
  "backendNodeId": 89201,  
  "frameId": "F-01-A",  
  "tagName": "BUTTON",  
  "attributes": {"id": "submit-btn", "class": "btn primary", "type": "submit"},  
  "axNode": {  
    "role": "button",  
    "name": "Confirm Order",  
    "disabled": false,  
    "focused": false  
  },  
  "boundingBox": {  
    "x": 450.5,  
    "y": 820.0,  
    "width": 120.0,  
    "height": 40.0  
  },  
  "isClickable": true,  
  "isVisible": true,  
  "shadowRootType": null  
}

### **6.2 Structural Processing Pipeline**

1. **Tree Extraction:** Calls `DOM.getFlattenedDocument(depth=-1, pierce=true)` to extract pierceable shadow roots and cross-origin frame pointers.  
2. **AX Mapping:** Calls `Accessibility.getFullAXTree()` to fetch the Accessibility tree, correlating nodes via `backendNodeId`.  
3. **Box Model Alignment:** Maps visual layout coordinates using `DOM.getBoxModel` for bounding boxes, scroll offsets, and viewport visibility validation.  
4. **Mutations Tracking:** Subscribes to `DOM.documentUpdated`, `DOM.childNodeInserted`, `DOM.childNodeRemoved`, and `DOM.attributeModified` to selectively mutate the in-memory tree without full DOM polling.

## **7\. EVENT LISTENER & BROWSER EVENT CATALOG**

The runtime uses an event routing system to parse raw CDP events into internal AOS events.

Raw CDP JSON Stream  
        |  
        v  
\+-------------------------+  
| Event Parser & Router   |  
\+-------------------------+  
        |  
        \+-----------------------------------+-----------------------------------+  
        |                                   |                                   |  
        v                                   v                                   v  
\+-------------------------+     \+-------------------------+     \+-------------------------+  
| Target Domain Events    |     | Network Domain Events   |     | Console / Log Events    |  
| (Page, DOM, Target)     |     | (Network.\*)             |     | (Console, Runtime)      |  
\+-------------------------+     \+-------------------------+     \+-------------------------+  
        |                                   |                                   |  
        \+-----------------------------------+-----------------------------------+  
                                            |  
                                            v  
                                \+-------------------------+  
                                | Lock-Free Ring Buffer   |  
                                | Event Bus               |  
                                \+-------------------------+  
                                            |  
                                            v  
                                \[ AOS System Subscribers \]

### **Core Event Subscriptions Catalog**

| Domain | CDP Native Event | Unified AOS Event Type | Payload Attributes |
| ----- | ----- | ----- | ----- |
| **Page Lifecycle** | `Page.loadEventFired` | `EVENT_PAGE_LOADED` | `timestamp`, `frameId` |
|  | `Page.domContentEventFired` | `EVENT_DOM_READY` | `timestamp` |
|  | `Page.frameNavigated` | `EVENT_FRAME_NAVIGATED` | `frameId`, `url`, `unreachableUrl` |
| **Target** | `Target.targetCreated` | `EVENT_TARGET_CREATED` | `targetInfo` (`targetId`, `type`, `url`) |
|  | `Target.targetCrashed` | `EVENT_TARGET_CRASHED` | `targetId`, `status`, `errorCode` |
| **DOM Engine** | `DOM.documentUpdated` | `EVENT_DOM_MUTATED` | `invalidatedNodeIds` |
| **Network** | `Network.requestWillBeSent` | `EVENT_NETWORK_REQUEST` | `requestId`, `request` (`url`, `method`, `headers`) |
|  | `Network.responseReceived` | `EVENT_NETWORK_RESPONSE` | `requestId`, `response` (`status`, `headers`, `mimeType`) |
|  | `Network.loadingFailed` | `EVENT_NETWORK_FAILED` | `requestId`, `errorText`, `canceled` |
| **Runtime/Console** | `Runtime.consoleAPICalled` | `EVENT_CONSOLE_MESSAGE` | `type`, `args`, `executionContextId`, `stackTrace` |
|  | `Runtime.exceptionThrown` | `EVENT_RUNTIME_EXCEPTION` | `timestamp`, `exceptionDetails` |
| **Dialogs** | `Page.javascriptDialogOpening` | `EVENT_DIALOG_OPENED` | `url`, `message`, `type`, `defaultPrompt` |
| **Security** | `Security.securityStateChanged` | `EVENT_SECURITY_CHANGED` | `securityState`, `explanations` |

## **8\. NETWORK MONITORING, REQUEST INTERCEPTION, & STORAGE**

### **8.1 Network Interception Pipeline**

Network requests can be monitored, logged, modified, or blocked using `Fetch` and `Network` CDP domains.

      Browser Page Outgoing Request  
                     |  
                     v  
\+------------------------------------------+  
| Fetch.requestPaused Event Triggered      |  
\+------------------------------------------+  
                     |  
                     v  
\+------------------------------------------+  
| Evaluated by AOS Network Interceptor     |  
\+------------------------------------------+  
                     |  
    \+----------------+----------------+  
    |                                 |  
    v                                 v  
\[ Rule: BLOCK / MATCH \]         \[ Rule: MODIFY / PASS \]  
    |                                 |  
    |---\> Fetch.failRequest           |---\> Fetch.continueRequest  
    |    (ErrorReason: BlockedByClient)|    (Header Mutated / Auth Injected)  
    |                                 |  
    v                                 v  
Request Cancelled               Request Stream Sent

### **8.2 Network Domain Capability**

* **Global Interception:** Enabled via `Fetch.enable` with urlPatterns `[{urlPattern: "*"}]`.  
* **Header Injections:** Dynamically injects authentication tokens, custom user-agents, and trace headers into `Fetch.continueRequest`.  
* **Response Mocking:** Injects custom payloads and HTTP status codes directly using `Fetch.fulfillRequest`.  
* **Traffic Recording:** Logs raw bytes for HTTP request/response bodies via `Network.getResponseBody`.

### **8.3 Storage, Cookies, & Storage Buckets Management**

Storage Operation Request  
        |  
        \+-----------------------+-----------------------+  
        |                       |                       |  
        v                       v                       v  
\[ Cookie Subsystem \]    \[ Local/Session Storage \]   \[ IndexedDB Subsystem \]  
  Storage.getCookies      Storage.getUsageAndQuota    Storage.clearDataForOrigin  
  Storage.setCookies      Runtime.evaluate (KV Store) Storage.clearDataForStorageKey  
  Storage.clearCookies

* **Cookie Management:** Provides programmatic read, write, filter, and purge operations using `Storage.getCookies`, `Storage.setCookies`, and `Storage.clearCookies`. Supports SameSite and Secure flags.  
* **Storage Isolation:** Maps storage contexts to isolated `BrowserContextID` targets, preventing storage leaks across workflow tasks.  
* **Quota Management:** Monitors storage limits using `Storage.getUsageAndQuota` to clear IndexedDB, Cache Storage, Service Workers, or WebSQL when storage thresholds are reached.

## **9\. DOWNLOADS, UPLOADS, & NATIVE FILE PICKER INTEGRATION**

File transfers (uploads and downloads) are managed by combining CDP events with native OS file dialog bridges.

                                 Native OS File Picker Triggered  
                                                |  
                      \+-------------------------+-------------------------+  
                      |                                                   |  
                      v                                                   v  
          \[ CDP Interception Flow \]                            \[ Native OS Bridge Flow \]  
          (DOM Input File Elements)                           (System File Dialog Windows)  
                      |                                                   |  
                      v                                                   v  
          Page.setInterceptFileChooser                      Windows UI Automation / WIN32 API  
                      |                                                   |  
                      v                                                   v  
         FileChooserOpened Event Intercepted                 Native Dialog Handle Identified  
                      |                                                   |  
                      v                                                   v  
         DOM.setFileInputFiles Executed                     WM\_SETTEXT / Edit Controls Populated  
                      |                                                   |  
                      \+-------------------------+-------------------------+  
                                                |  
                                                v  
                                  File Path Successfully Injected

### **9.1 Download Management Architecture**

1. Configure global download behavior per session: `Browser.setDownloadBehavior` with `behavior: "allow"`, `downloadPath: "/var/aos/downloads/<sessionId>"`, `eventsEnabled: true`.  
2. Intercept `Browser.downloadWillBegin` to track target file names, total bytes, and initial URLs.  
3. Monitor progress via `Browser.downloadProgress` (`state: "inProgress" | "completed" | "canceled"`).  
4. Verify downloaded file hashes (SHA-256) upon write completion before releasing to requesting workflows.

### **9.2 File Upload Handling**

#### **Standard DOM File Input Interception**

1. Enable file chooser interception: `Page.setInterceptFileChooser(enabled: true)`.  
2. Intercept `Page.fileChooserOpened` events, extracting `backendNodeId` and selection mode (`selectSingle` vs `selectMultiple`).  
3. Inject absolute file paths using `DOM.setFileInputFiles(files: [...], backendNodeId: ID)`.

#### **Native OS File Picker Integration**

When web applications invoke non-standard native OS dialog windows directly (e.g., via Win32 Shell API, custom Native Messaging hosts, or OS shell extensions):

1. **Fallback Bridge Listener:** Spawns an OS-level window hook monitoring target process ID window trees for system dialog classes (`#32770` on Windows, `GtkFileChooserDialog` on Linux).  
2. **Dialog Control Binding:** Matches edit controls (`Edit1`) and button elements (`Button1`).  
3. **Programmatic Injection:** Sends target paths via `WM_SETTEXT` API and issues `BM_CLICK` events to proceed, bypassing blocking native UI dialogs.

## **10\. JAVASCRIPT RUNTIME, CONSOLE MONITORING, & PERMISSIONS**

### **10.1 Execution Context Lifecycle & JS Evaluation**

* **Context Tracking:** Captures `Runtime.executionContextCreated`, `Runtime.executionContextDestroyed`, and `Runtime.executionContextsCleared` to track frame-level JavaScript execution environments.  
* **Isolated World Creation:** Creates isolated execution sandboxes using `Page.createIsolatedWorld` to evaluate automation logic safely without exposing script objects to page-level JS contexts.  
* **Expression Evaluation:** Runs scripts via `Runtime.evaluate` (for global code) or `Runtime.callFunctionOn` (for specific DOM element functions), passing parameters safely as `CallArgument` JSON objects.

### **10.2 Console Monitoring & Error Tracking**

* Enables `Console.enable` and `Runtime.enable`.  
* Captures standard console output (`log`, `debug`, `info`, `warn`, `error`, `trace`) via `Runtime.consoleAPICalled`.  
* Intercepts unhandled script exceptions and promise rejections via `Runtime.exceptionThrown`. Extracts parsed stack traces, script URLs, line/column offsets, and error objects.

### **10.3 Permissions Management**

Modifies permissions dynamically without requiring browser restarts using `Browser.grantPermissions`:

JSON  
{  
  "method": "Browser.grantPermissions",  
  "params": {  
    "permissions": \[  
      "geolocation",  
      "notifications",  
      "audioCapture",  
      "videoCapture",  
      "clipboardReadWrite"  
    \],  
    "origin": "https://automation.target.internal"  
  }  
}

## **11\. SCREENSHOT, RECORDING, & BROWSER VISION**

                         \[ Screenshot / Vision Request \]  
                                         |  
         \+-------------------------------+-------------------------------+  
         |                               |                               |  
         v                               v                               v  
\[ Viewport Screenshot \]       \[ Element Screenshot \]          \[ Full-Page Screenshot \]  
  Page.captureScreenshot        DOM.getBoxModel                 Emulation.setDeviceMetrics  
  (Format: PNG / JPEG / WEBP)   Compute Clip Bounds             Capture Target Scroll Heights  
                                Page.captureScreenshot(clip)    Page.captureScreenshot  
                                                                Reset Device Metrics  
         |                               |                               |  
         \+-------------------------------+-------------------------------+  
                                         |  
                                         v  
                         \+-------------------------------+  
                         | Optical Vision Processor      |  
                         | (Frame Normalizer & OCR Base) |  
                         \+-------------------------------+

### **11.1 Screenshot Engine**

* **Viewport Capture:** Executes `Page.captureScreenshot` with target encoding (`image/png`, `image/jpeg`, `image/webp`) and customizable compression ratios.  
* **Element-Level Capture:** Queries `DOM.getBoxModel` for target element coordinates, constructing precise clip parameters (`{x, y, width, height, scale: 1}`).  
* **Full-Page Stitching:** Evaluates scroll layout parameters (`metrics.contentSize`), dynamically updates emulation dimensions via `Emulation.setDeviceMetricsOverride`, takes screen captures, and restores original device metrics.

### **11.2 Continuous Recording Subsystem**

* Employs `Page.startScreencast` with specified format, quality, and frame constraints (`maxWidth`, `maxHeight`, `everyNthFrame`).  
* Listens for `Page.screencastFrame` events, returning base64 encoded frame buffers and metadata.  
* Sends immediate frame acknowledgments via `Page.screencastFrameAck` to prevent browser frame-dropping.  
* Streams binary frames directly to an h.264 / VP8 hardware encoder pipeline.

### **11.3 Browser Vision Processing Layer**

* Normalizes incoming frame buffers for computer vision (CV) processing engines.  
* Uses spatial coordinate transformation matrices to translate vision model output bounding boxes back into actionable CSS/Viewport coordinates for virtual input targeting.

## **12\. VIRTUAL INPUT EMULATION (MOUSE, KEYBOARD, TOUCH)**

Input actions mimic real user interaction by sending low-level input events directly to Chromium's compositor layer using `Input.dispatchMouseEvent`, `Input.dispatchKeyEvent`, and `Input.dispatchTouchEvent`.

     High-Level Input Request (e.g. Type Text / Click Element)  
                                 |  
                                 v  
               \+-----------------------------------+  
               | Input Synthesizer & Bezier Curve  |  
               | Path Generator                    |  
               \+-----------------------------------+  
                                 |  
         \+-----------------------+-----------------------+  
         |                                               |  
         v                                               v  
\[ Virtual Mouse Stream \]                        \[ Virtual Keyboard Stream \]  
  Input.dispatchMouseEvent                        Input.dispatchKeyEvent  
  \- mouseMoved (Bezier trajectory steps)          \- keyDown (WindowsVirtualKeyCode)  
  \- mousePressed (Button, ClickCount)             \- char (Text Buffer translation)  
  \- mouseReleased                                 \- keyUp

### **12.1 Virtual Mouse Engine**

* **Humanized Trajectory Planning:** Generates natural mouse movement paths using Cubic Bézier curves with randomized jitter and velocity profiling, preventing immediate bot detection.  
* **Precision Dispatching:** Sends `mouseMoved`, `mousePressed`, `mouseReleased`, and `mouseWheel` events containing target viewport coordinates, modifier keys (`Shift`, `Control`, `Alt`, `Meta`), and click counts.

### **12.2 Virtual Keyboard Engine**

* **Key Event Sequences:** Generates key press sequences (`keyDown` \-\> `char` \-\> `keyUp`) with configurable key-hold durations and randomized inter-key typing delays.  
* **Key Code Translation:** Converts input text into corresponding standard `WindowsVirtualKeyCode`, key string representations, and native scan codes.

## **13\. BROWSER RECOVERY, CRASH ENGINE, & RESTART**

                         Target Process Crash / Socket Loss  
                                          |  
                                          v  
                        \+------------------------------------+  
                        | Crash Engine Event Interception    |  
                        \+------------------------------------+  
                                          |  
                        \+-----------------+-----------------+  
                        |                                   |  
                        v                                   v  
             \[ Transient Socket Loss \]           \[ Fatal Renderer / Process Crash \]  
                        |                                   |  
                        v                                   v  
             Socket Re-connection Loop            Extract Last Session Snapshot  
             Exponential Backoff                  Kill Orphan Process Handles  
                        |                                   |  
                        v                                   v  
             Target.attachToTarget                Respawn Browser Process (--restore)  
                        |                                   |  
                        \+-----------------+-----------------+  
                                          |  
                                          v  
                        \+------------------------------------+  
                        | Session State Restoration          |  
                        | (Tabs, URLs, Storage, Contexts)    |  
                        \+------------------------------------+  
                                          |  
                                          v  
                        \+------------------------------------+  
                        | Notify AOS Recovery Manager        |  
                        | Resume Execution Pipelines         |  
                        \+------------------------------------+

### **13.1 Crash Detection Vectors**

1. **Target Crash:** Intercepts `Target.targetCrashed` events containing crash reason codes (`crashed`, `killed`, `oom`).  
2. **WebSocket Disconnection:** Intercepts unexpected socket closure events or TCP socket resets.  
3. **Heartbeat Timeout:** Periodically issues `Browser.getVersion` requests; triggers recovery if response times exceed defined thresholds.

### **13.2 Automated Recovery Sequence**

1. **Freeze Execution:** Instantly pauses high-level workflow tasks bound to the affected `BrowserID`.  
2. **Process Cleanup:** Forcefully terminates orphaned child processes, releasing lock files in target user data directories.  
3. **Instance Respawn:** Spawns a new browser process using saved launch flags, proxy configurations, and profile contexts.  
4. **Session State Reconstruction:**  
   * Restores browser context boundaries (`Target.createBrowserContext`).  
   * Replaces saved cookies and local storage state entries.  
   * Re-opens tabs to their last verified URLs using `Target.createTarget`.  
   * Re-injects init scripts (`Page.addScriptToEvaluateOnNewDocument`).  
5. **Pipeline Unfreeze:** Verifies browser health, hands control back to workflow execution engines, and notifies the central AOS Recovery Manager.

## **14\. PLAYWRIGHT INTEGRATION & WORKFLOW INTERACTION**

The Chrome CDP Runtime acts as an execution target for higher-level automation frameworks like Playwright, while maintaining direct control through AOS native commands.

      \[ AOS Workflow / Agent Framework \]  
                       |  
        \+--------------+--------------+  
        |                             |  
        v                             v  
\[ Native AOS CDP Adapter \]    \[ Playwright Bridge API \]  
        |                             |  
        | Direct Internal Bus         | Uses Custom CDP Router Endpoint  
        v                             v  
\+-----------------------------------------------------+  
|             Chrome CDP Runtime Engine               |  
\+-----------------------------------------------------+

### **Integration Layer Features**

* **CDP Multiplexing Server:** Exposes a loopback WebSocket endpoint that translates external Playwright/Puppeteer connection streams into internal AOS CDP Session handles.  
* **Bi-Directional Command Pipeline:** Allows native AOS workflows and Playwright script execution tasks to operate concurrently within the same browser contexts.  
* **Shared Context Store:** Ensures cookies, storage states, network interception rules, and frame mappings remain unified across execution layers.

## **15\. PIPELINES AND SOCKETS SPECIFICATION**

Every subsystem within the runtime exposes explicit pipeline definitions and socket communication protocols.

### **15.1 Sockets Matrix**

| Socket Name | Direction | Auth Model | Validation Schema | Timeout | Retry Rules | Transport |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| **CDP Transport Socket** | IN/OUT | Token Handshake | JSON-RPC 2.0 | 30s | Exponential Backoff (Max 5\) | WebSocket |
| **Event Bus Socket** | OUT | Internal Sub | Binary Protobuf / MessagePack | None | Lock-Free Ring Drop | IPC In-Memory |
| **Frame Stream Socket** | OUT | Internal Sub | Raw Screencast Frame Packets | 2s | Frame Drop / Skip | Unix Socket / Shared Mem |
| **Native Picker Socket** | IN/OUT | System Elevation | Native C-Struct Pass-through | 15s | 3 Retries | Win32 / IPC Pipe |
| **External Adapter Socket** | IN | JWT / TLS | Playwright / Puppeteer Protocol | 60s | 2 Retries | TCP Loopback |

### **15.2 Pipelines Matrix**

| Pipeline Name | Source | Destination | Primary Payload | Failover Strategy |
| ----- | ----- | ----- | ----- | ----- |
| **Command Dispatch Pipeline** | System Engine | Connection Manager | Serialized CDP JSON Request | Queue and retry on reconnect |
| **Event Broadcast Pipeline** | Connection Manager | Event Bus Subscribers | Parsed CDP Event Object | Drop non-critical events |
| **Network Interception Pipeline** | Network Interceptor | Chromium Network Stack | Intercepted Request/Response Payload | Default to pass-through |
| **Frame Capture Pipeline** | Screencast Engine | Video Encoder / CV Bus | Frame Buffers \+ Coordinate Metrics | Skip frame on buffer saturation |
| **Crash Recovery Pipeline** | Crash Engine | Recovery Manager | Session Snapshot JSON | Escalate to system panic log |

## **16\. SECURITY, AUTHENTICATION, LOGGING, & METRICS**

### **16.1 Security & Access Control**

* **Sandboxing:** Browser processes run under isolated user accounts with strict OS sandbox options (`--no-sandbox` strictly prohibited unless running in isolated container environments).  
* **Remote Debugging Authentication:** Remote WebSocket connections require TLS 1.3 encryption and JWT bearer tokens passed during socket handshakes.  
* **Data Sanitization:** Strips authorization headers, auth tokens, and sensitive cookie fields from system logs during execution tracing.

### **16.2 Logging & Tracing**

Generates structured JSON logs categorized by subsystem:

* `CDP_TRACE`: Raw JSON-RPC request and response payloads.  
* `BROWSER_LIFECYCLE`: Process spawn, detachment, termination, and crash events.  
* `NETWORK_LOG`: Intercepted request headers, error responses, and traffic metrics.  
* `SECURITY_LOG`: Certificate mismatches, permission requests, and policy violations.

### **16.3 Real-Time Metrics & Telemetry**

                                 Telemetry Exporter  
                                          |  
        \+---------------------------------+---------------------------------+  
        |                                 |                                 |  
        v                                 v                                 v  
\[ CDP RPC Latency \]              \[ Browser Memory Usage \]         \[ Event Bus Throughput \]  
  Distribution Histograms          JS Heap Size (Runtime)           Messages Processed / Sec  
  Round-trip Duration (ms)         DOM Nodes Counter                Dropped Event Counters

* **RPC Latency:** Tracks round-trip times for command execution per CDP domain.  
* **Memory & Resource Usage:** Monitors JS heap usage, DOM node counts, and layouts using `Performance.getMetrics`.  
* **Throughput Metrics:** Tracks incoming event throughput, buffer fill levels, and dropped frame counts.

## **17\. MERMAID DIAGRAMS**

### **17.1 Overall CDP Runtime Architecture**

Code snippet  
graph TD  
    A\[AOS System Orchestrator\] \--\>|Command Stream| B(Chrome CDP Runtime)  
    B \--\> C{Target Router}  
      
    C \--\>|Session 1| D\[Browser Instance 1\]  
    C \--\>|Session 2| E\[Browser Instance 2\]  
      
    D \--\> F\[Connection Manager\]  
    F \--\>|WebSocket / DevTools| G\[Chromium Process ID: 1042\]  
      
    G \--\>|Page / Network Events| H\[Event Bus Parser\]  
    H \--\>|Unified Events| I\[Lock-Free Event Bus\]  
    I \--\>|Subscribed Events| A  
      
    subgraph "Internal Subsystems"  
        J\[Network Interceptor\]  
        K\[DOM & AX Synthesizer\]  
        L\[Crash & Recovery Engine\]  
        M\[Native File Picker Bridge\]  
    end  
      
    B \--- J  
    B \--- K  
    B \--- L  
    B \--- M

### **17.2 Complete CDP Packet Flow**

Code snippet  
sequenceDiagram  
    participant AOS as AOS Orchestrator  
    participant TR as Target Router  
    participant CM as Connection Manager  
    participant CH as Chromium Browser  
      
    AOS-\>\>TR: Execute Action (Page.navigate, URL)  
    TR-\>\>CM: Format JSON-RPC Packet (ID: 104, SessionID: S-12)  
    CM-\>\>CH: Send WS Frame {"id":104,"method":"Page.navigate","params":{...}}  
    CH--\>\>CM: WS Frame Event {"method":"Page.frameStartedLoading","params":{...}}  
    CM--\>\>AOS: Emit Unified Event (EVENT\_FRAME\_LOADING)  
    CH--\>\>CM: WS Frame Response {"id":104,"result":{"frameId":"F1"}}  
    CM--\>\>TR: Match Request ID 104  
    TR--\>\>AOS: Action Execution Result Success

### **17.3 Browser Lifecycle and Session Restore**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Uninitialized  
    Uninitialized \--\> Launching: Command Launch  
    Launching \--\> Connecting: Process Spawned  
    Connecting \--\> Active: WS Handshake OK  
      
    state Active {  
        \[\*\] \--\> Idle  
        Idle \--\> ProcessingCommand: RPC Input  
        ProcessingCommand \--\> Idle: Execution Success  
        Idle \--\> InterceptingNetwork: Request Triggered  
        InterceptingNetwork \--\> Idle: Request Handled  
    }  
      
    Active \--\> Recovering: Target Crash / Socket Drop  
    Recovering \--\> Reconnecting: Respawn Process  
    Reconnecting \--\> StateRestoration: Apply Cookies / Storage / URLs  
    StateRestoration \--\> Active: Session Restored  
    Recovering \--\> Terminated: Retries Exceeded  
    Active \--\> Terminated: Explicit Shutdown  
    Terminated \--\> \[\*\]

## **18\. ASCII DIAGRAMS**

### **18.1 Component Hierarchy Architecture**

Plaintext  
\+-----------------------------------------------------------------------------------+  
|                              CHROME\_CDP\_RUNTIME.MD                                |  
|                                                                                   |  
|  \+-----------------------------------------------------------------------------+  |  
|  |                           CORE RUNTIME CONTROLLER                           |  |  
|  \+-----------------------------------------------------------------------------+  |  
|         |                                 |                                |      |  
|         v                                 v                                v      |  
|  \+--------------+                 \+---------------+                \+-----------+  |  
|  | DISCOVERY    |                 | SESSION       |                | RECOVERY  |  |  
|  | & ATTACH     |                 | MANAGER       |                | ENGINE    |  |  
|  \+--------------+                 \+---------------+                \+-----------+  |  
|         |                                 |                                |      |  
|         \+---------------------------------+--------------------------------+      |  
|                                           |                                       |  
|                                           v                                       |  
|  \+-----------------------------------------------------------------------------+  |  
|  |                         SUBSYSTEM EXECUTION MATRIX                          |  |  
|  |                                                                             |  |  
|  |  \[ DOM & AX Synthesizer \]        \[ Virtual Input Engine \]                   |  |  
|  |  \[ Network Interceptor  \]        \[ Screencast & Vision \]                    |  |  
|  |  \[ Storage & Cookies    \]        \[ File Picker Bridge  \]                    |  |  
|  \+-----------------------------------------------------------------------------+  |  
|                                           |                                       |  
|                                           v                                       |  
|  \+-----------------------------------------------------------------------------+  |  
|  |                        WEBSOCKET TRANSPORT LAYER                            |  |  
|  |             (JSON-RPC 2.0 Multiplexer over Flat CDP Sessions)               |  |  
|  \+-----------------------------------------------------------------------------+  |  
\+-----------------------------------------------------------------------------------+

### **18.2 File Upload & Native Bridge Fallback Processing Flow**

Plaintext  
\[ File Upload Triggered \]  
           |  
           v  
 Is Page.setInterceptFileChooser Active?  
           |  
           \+---\> YES \---\> Intercept Page.fileChooserOpened Event  
           |                     |  
           |                     v  
           |              Execute DOM.setFileInputFiles (Via CDP)  
           |                     |  
           |                     v  
           |              Upload Complete (CDP Native)  
           |  
           \+---\> NO / NATIVE DIALOG POPPED  
                                 |  
                                 v  
                  Trigger OS Bridge Monitor  
                                 |  
                                 v  
                  Locate Native OS Dialog Class (\#32770 / GtkDialog)  
                                 |  
                                 v  
                  Inject File Path via OS Native API (WM\_SETTEXT)  
                                 |  
                                 v  
                  Send Click Action to OK Button (BM\_CLICK)  
                                 |  
                                 v  
                  Upload Complete (OS Bridge Fallback)

## **19\. FOLDER STRUCTURE**

Plaintext  
/hojaiga/aos/src/chrome\_cdp\_runtime/  
├── core/                           \# Primary runtime orchestration modules  
│   ├── runtime\_controller.rs      \# Core engine lifecycle & entrypoints  
│   ├── target\_router.rs           \# Session router & flat protocol dispatcher  
│   └── connection\_manager.rs      \# WebSocket connection pool & frame handlers  
├── discovery/                      \# Discovery & attachment modules  
│   ├── process\_scanner.rs         \# Local process table inspector  
│   ├── port\_finder.rs             \# DevToolsActivePort parser  
│   └── endpoint\_resolver.rs       \# Remote HTTP /json endpoint validator  
├── dom/                            \# DOM and Accessibility synthesis  
│   ├── dom\_tree\_builder.rs        \# Pierceable shadow DOM parser  
│   ├── ax\_tree\_synthesizer.rs     \# Accessibility tree mapper  
│   └── coordinate\_normalizer.rs   \# Layout box model & spatial matrix parser  
├── input/                          \# Emulated input modules  
│   ├── virtual\_mouse.rs           \# Bézier curve trajectory generator & click emulator  
│   ├── virtual\_keyboard.rs        \# Scan code, virtual key code, & typing emulator  
│   └── touch\_emulator.rs          \# Touch gesture & multi-point event emulator  
├── network/                        \# Interception & storage subsystems  
│   ├── network\_interceptor.rs     \# Fetch domain request/response modification  
│   ├── cookie\_manager.rs          \# Storage & cookie isolation manager  
│   └── download\_manager.rs        \# Download tracking & hash verification  
├── media/                          \# Visual inspection & stream modules  
│   ├── screenshot\_engine.rs       \# Viewport, element, & full-page capture  
│   ├── screencast\_recorder.rs     \# Frame streaming acknowledge loop  
│   └── vision\_bridge.rs           \# CV coordinate normalizer & OCR alignment  
├── bridge/                         \# Native OS interaction bridges  
│   ├── file\_chooser\_interceptor.rs\# CDP file input interception  
│   └── native\_picker\_win32.rs     \# Windows Shell API / Win32 OS dialog fallback  
├── recovery/                       \# Resilience and crash systems  
│   ├── crash\_detector.rs          \# Target crash & heartbeat monitor  
│   ├── state\_snapshotter.rs       \# Session state persistent memory  
│   └── restart\_orchestrator.rs    \# Auto-respawn & re-attach engine  
├── adapters/                       \# Framework compatibility layers  
│   ├── playwright\_bridge.rs       \# Playwright multiplexer adapter  
│   └── puppet\_bridge.rs           \# Puppeteer CDP router adapter  
├── sockets/                        \# Socket interfaces definitions  
│   ├── cdp\_transport\_socket.rs  
│   └── event\_bus\_socket.rs  
├── pipelines/                      \# Async processing pipeline definitions  
│   ├── command\_pipeline.rs  
│   └── event\_pipeline.rs  
├── config/                         \# Configuration definitions  
│   ├── runtime\_config.yaml        \# Settings schema  
│   └── cdp\_capabilities.json      \# Chromium launch options schema  
└── tests/                          \# Integration & Unit test suits  
    ├── unit/                      \# Mocked CDP unit tests  
    └── integration/               \# Headless Chromium live system integration tests

## **20\. CONFIGURATION SCHEMA (`runtime_config.yaml`)**

YAML  
chrome\_cdp\_runtime:  
  version: "2.0.0"  
  connection:  
    max\_concurrent\_browsers: 8  
    websocket\_timeout\_ms: 30000  
    heartbeat\_interval\_ms: 5000  
    max\_payload\_size\_mb: 64  
    enable\_tls: true

  discovery:  
    auto\_discover\_local: true  
    scan\_ports: \[9222, 9223, 9224\]  
    process\_names:  
      \- "chrome"  
      \- "chromium"  
      \- "msedge"  
      \- "brave"

  subsystems:  
    dom:  
      max\_tree\_depth: \-1  
      pierce\_shadow\_dom: true  
      include\_accessibility: true

    input:  
      humanize\_mouse\_movement: true  
      typing\_delay\_variance\_ms: \[20, 120\]

    network:  
      enable\_global\_interception: true  
      max\_captured\_body\_size\_kb: 10240

    media:  
      screencast\_format: "jpeg"  
      screencast\_quality: 80  
      screencast\_max\_fps: 30

    file\_picker:  
      enable\_native\_fallback: true  
      native\_dialog\_timeout\_ms: 10000

  recovery:  
    auto\_recovery\_enabled: true  
    max\_crash\_retries: 3  
    retry\_backoff\_ms: 1000  
    restore\_session\_state: true

  logging:  
    level: "INFO"  
    log\_cdp\_traffic: false  
    sanitizers:  
      \- "Authorization"  
      \- "Set-Cookie"

## **21\. FUTURE EXPANSION**

1. **WebDriver BiDi Unified Engine:** Seamlessly fallback from CDP to W3C WebDriver BiDi protocol for Firefox and Safari automation capabilities.  
2. **GPU Hardware Accelerated Vision Pipeline:** Pass screencast binary buffers directly to GPU memory via WebGPU / DirectX Shared Surfaces, reducing latency for real-time computer vision agent workflows.  
3. **Headless Anti-Detection Engine:** Native C++ patches applied to Chromium network stacks dynamically modifying TLS fingerprinting, WebGL context signatures, and CDP detection vectors.

