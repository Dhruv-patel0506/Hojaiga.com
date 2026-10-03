## **Popup\_Handler.md (Desktop Interaction Manager)**

# **ROLE**

You are the Principal Desktop Interaction Systems Architect for the Hojaiga Automation Operating System (AOS).

Authority Order:

1. Constitution.md  
2. Hojaiga\_LawBook.md  
3. Diagrams(inner+upper)  
4. Legacy\_Code\_Migration\_Guide.md  
5. Policy\_Manual.md  
6. Master\_Architecture\_Blueprint.md  
7. Organ\_Specification.md

Never contradict these documents. Expand them only. Do NOT redesign the architecture.

# **OBJECTIVE**

Create a production-ready, highly deterministic architecture specification for `Popup_Handler.md` (internally and operationally designated as the **Desktop Interaction Manager** or **DIM**).

The Desktop Interaction Manager is the primary Desktop Interaction Organ of Hojaiga. It is responsible for discovering, classifying, tracking, reading, controlling, and resolving every GUI window, child control, native file dialog, floating menu, and system notification that appears outside or alongside the browser automation pipeline.

The Desktop Interaction Manager guarantees that Hojaiga automation workflows are never blocked, deadlocked, or desynchronized by native operating system dialogs, installer wizards, nested child windows, modal popups, file pickers, or unexpected system prompts. The Desktop Interaction Manager owns 100% of non-browser window and native OS interactions.

# **PURPOSE**

The Desktop Interaction Manager is strictly responsible for:

* **Desktop Window Discovery**: Scanning, enumeration, and real-time tracking of top-level OS windows.  
* **Popup & Child Window Detection**: Real-time detection of popups, dialogs, and nested child control windows.  
* **Unlimited Hierarchy Tracking**: Maintaining recursive, arbitrary-depth Parent-Child-Owner window trees without recursion limits.  
* **Modal Window Management**: Tracking, isolating, and resolving modal dialog stacks that block parent window input.  
* **Installer Wizard Automation**: End-to-end execution of multi-step installation and setup wizards (MSI, Inno, NSIS, etc.).  
* **Native OS & File Dialogs**: Complete drive navigation, filter matching, multi-file selection, and execution of file/folder pickers via the Native File Picker Engine (NFPE).  
* **System Security & Prompts**: Identification and policy-bound escalation of UAC, credential, certificate, and administrator prompts.  
* **Notifications & Floating Elements**: Capture and handling of toasts, balloon notifications, tooltips, context menus, and splash screens.  
* **Multi-Layer Automation Engines**: Multi-tier control via UI Automation, Win32, MSAA, IAccessible2, WPF, Qt, GTK, Electron, Java Accessibility, OCR, and Computer Vision.  
* **Focus & Stack State Management**: Dynamic tracking, locking, auto-switching, and deterministic focus restoration upon dialog resolution.  
* **Display Environment Awareness**: Full multi-monitor awareness, high-DPI scaling coordinate translation, and virtual desktop mapping.  
* **Workflow Orchestration**: Intercepting popups, issuing immediate workflow pause signals to the scheduler, resolving the UI barrier, verifying closure, and issuing workflow resume signals.

# **HIGH-LEVEL ARCHITECTURE**

\+---------------------------------------------------------------------------------------------------+  
|                                          DESKTOP DISPLAY                                          |  
|                     (Multi-Monitor, High-DPI Virtual Screen Space, Win32/X11/Wayland)             |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                DESKTOP INTERACTION MANAGER (DIM)                                  |  
|                                                                                                   |  
|  \+---------------------------------------------------------------------------------------------+  |  
|  |                               WINDOW MANAGEMENT SUBSYSTEM                                   |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  |  | Window Discovery Engine  |  |   Window Classifier      |  |  Installer Wizard Engine      |  |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  |  | Window Tree & Stack Mgr  |  | Notifications Handler    |  | Focus & Z-Order Controller    |  |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  \+---------------------------------------------------------------------------------------------+  |  
|                                                 |                                                 |  
|  \+---------------------------------------------------------------------------------------------+  |  
|  |                             NATIVE FILE PICKER ENGINE (NFPE)                                |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  |  | Dialog Detector          |  | Directory Navigator      |  | File Matcher & Filter         |  |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  |  | Multi-Selection Engine   |  | Playwright Fallback Proxy |  | Directory Memory Store        |  |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  \+---------------------------------------------------------------------------------------------+  |  
|                                                 |                                                 |  
|  \+---------------------------------------------------------------------------------------------+  |  
|  |                            DESKTOP INTERACTION ENGINE (DIE)                                 |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  |  | Native Accessibility API |  | OCR Engine (Tesseract/Win)|  | Vision Engine (OpenCV Match)  |  |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  |  | Coordinate Mapper (DPI)  |  | Input Injector (Kbd/Mouse)|  | Security & Policy Guard       |  |  |  
|  |  \+--------------------------+  \+--------------------------+  \+-------------------------------+  |  |  
|  \+---------------------------------------------------------------------------------------------+  |  
\+---------------------------------------------------------------------------------------------------+  
                                                  |  
                                                  v  
\+---------------------------------------------------------------------------------------------------+  
|                                  WORKFLOW SCHEDULER & PIPELINE                                    |  
|              (Pause Signal  \--\>  Popup Interception  \--\>  Resolution  \--\>  Resume Signal)          |  
\+---------------------------------------------------------------------------------------------------+

# **SUBSYSTEM ARCHITECTURE**

The Desktop Interaction Manager (DIM) splits operational load into three strictly decoupled, highly specialized internal subsystems:

                 DESKTOP INTERACTION MANAGER (DIM)  
                                  │  
    ┌─────────────────────────────┼─────────────────────────────┐  
    │                             │                             │  
    ▼                             ▼                             ▼  
\+-----------------------+ \+-----------------------+ \+-----------------------+  
|    WINDOW MANAGER     | | NATIVE FILE PICKER    | | DESKTOP INTERACTION   |  
|      SUBSYSTEM        | |     ENGINE (NFPE)     | |     ENGINE (DIE)      |  
|                       | |                       | |                       |  
| • Main Windows        | | • Open File Dialog    | | • Accessibility APIs  |  
| • Child Windows       | | • Save File Dialog    | | • OCR Processing      |  
| • Modal Stacks        | | • Folder Picker       | | • Computer Vision     |  
| • Installer Wizards   | | • Directory Navigation| | • Focus Management    |  
| • Notifications       | | • File Filtering      | | • Window Tree Tracking|  
| • Z-Order Control     | | • Multi-Selection     | | • Coordinate Translation|  
| • System Dialogs      | | • Playwright Proxy    | | • Input Injection     |  
\+-----------------------+ \+-----------------------+ \+-----------------------+

# **RESPONSIBILITIES**

The Desktop Interaction Manager must:

1. **Discover Every Window**: Continuously enumerate top-level, child, tool, system, and hidden windows across all screens.  
2. **Track Every Child Window**: Build and update an internal tree representation of child windows to an arbitrary depth.  
3. **Track Unlimited Nesting**: Maintain zero structural array bounds or fixed recursion depth limits when indexing nested controls (N-level depth).  
4. **Read Every Popup**: Extract textual, structural, control, and visual data from every detected pop-up element via native APIs, accessibility hooks, or OCR.  
5. **Maintain Window Hierarchy**: Store and query exact parent-child-owner links across the complete desktop tree.  
6. **Maintain Window Stack**: Keep an active Z-order desktop stack to identify obscured, overlapping, or topmost elements.  
7. **Track Focused Window**: Continuously track active OS input focus down to the exact control handle.  
8. **Automate Focus Switching**: Programmatically grant input focus to target controls or dialogs prior to sending keystrokes or mouse events.  
9. **Automatically Restore Focus**: Record pre-interception window focus state and seamlessly restore input focus to the target application after resolving a popup.  
10. **Pause Workflows**: Immediately signal the Workflow Scheduler to freeze execution states upon detecting an blocking or unhandled popup.  
11. **Resume Workflows**: Re-verify system readiness and dispatch execution resume signals post-resolution.  
12. **Prevent Deadlocks**: Implement hard timeouts, loop-detection mechanics, and auto-dismissal rules to prevent infinite waiting loops.  
13. **Support Multi-Engine Fallbacks**: Gracefully fall back from Native Accessibility down to OCR, Vision, or Human Escalation.  
14. **Support Duplicate Windows**: Disambiguate multiple instances of identical titles or class names using Process IDs (PID), thread handles, bounding rects, and parent window IDs.  
15. **Support Multi-Monitor & DPI Scaling**: Correct physical-to-logical pixel mappings across monitors with differing DPI scaling factors (e.g., 100%, 125%, 150%, 200%).  
16. **Enforce Security Policies**: Isolate administrative prompts (UAC, Passwords, Certificates) and forbid unauthorized auto-approval.

# **WINDOW TYPES**

The Desktop Interaction Manager natively classifies and interacts with:

* **Main Window**: Top-level application frame containing the primary user interface.  
* **Child Window**: Sub-window tied directly to a parent container, bounded or unbounded by parent client area.  
* **Modal Window**: Dialog box blocking all user input to its parent window or entire application stack until dismissed.  
* **Floating Window**: Tool palette or status window staying on top of client areas without grabbing exclusive input focus.  
* **Detached Window**: Previously embedded pane or tab un-docked into an independent top-level desktop window.  
* **Tool Window**: Small-frame auxiliary window excluded from taskbar enumeration.  
* **Wizard Window**: Sequential multi-step installer or configuration flow interface.  
* **Installer**: Setup executable window modifying system binaries or persistent application state.  
* **Message Box**: Native standard system dialog displaying alerts, warnings, or simple prompts.  
* **Confirmation**: Binary or ternary choice dialog (e.g., Yes/No/Cancel, Allow/Deny).  
* **Authentication**: Input form requesting username, password, token, or MFA keys.  
* **UAC (User Account Control)**: Secure Desktop administrative elevation prompt.  
* **Security Prompt**: Firewall, network access, or untrusted execution warning window.  
* **Crash Reporter**: System error, core dump notification, or application crash dialog.  
* **Progress Window**: Non-modal or modal status indicator showing percentage completion or transfer bars.  
* **Splash Screen**: Frameless image/logo window displayed during application boot sequence.  
* **Properties Window**: Attribute configuration window for files, objects, or system settings.  
* **Settings Window**: Deep preference management window for application behavior.  
* **Notification**: OS-native or custom balloon/toast alert element.  
* **Toast**: Ephemeral slide-in alert popping up at screen extremities.  
* **Balloon**: Speech-bubble style notification tied to system tray icons.  
* **Context Menu**: Ephemeral popup menu spawned via right-click or shortcut key actions.  
* **Tooltip**: Ephemeral hover box explaining control functionality.  
* **File Picker**: Native or custom GUI dialog for selecting input files.  
* **Folder Picker**: Native or custom GUI dialog for selecting target directories.  
* **Save Dialog**: File system destination and file naming dialog.  
* **Open Dialog**: File system source selection dialog.  
* **License Agreement**: EULA text container requiring acceptance before proceeding.  
* **Unknown Window**: Unclassified GUI window falling back to OCR and Vision pipelines.

# **INSTALLER WIZARD ENGINE**

The Installer Wizard Engine within the Window Manager Subsystem automates software installation, repair, modification, and uninstallation workflows across all common installer frameworks:

### **Supported Installer Technologies**

* **MSI**: Windows Installer Native Packages.  
* **Inno Setup**: Open-source scriptable installer framework.  
* **NSIS**: Nullsoft Scriptable Install System.  
* **InstallShield**: Commercial enterprise setup packager.  
* **WiX Toolset**: Windows Installer XML toolset applications.  
* **Visual Studio Installer**: Microsoft developer toolset installer.  
* **Python Installer**: Standard Python distribution setup routines.  
* **Java Installer**: Oracle / OpenJDK installer setup applications.  
* **Chrome / Chromium Installer**: Google silent and GUI setup wrappers.  
* **OBS Studio Installer**: Media software deployment wizard.  
* **Generic / Future Installer**: Heuristic-based installer automation via control text and button layout matching.

### **Automated Button Action Engine**

The engine maps and automatically interacts with standard installer action paths: `Next` | `Back` | `Install` | `Repair` | `Modify` | `Remove` | `Browse` | `Cancel` | `Accept` | `Decline` | `Finish` | `Restart Later` | `Restart Now`

 \+-----------------------------------------------------------------+  
  |                    INSTALLER WIZARD ENGINE                      |  
  \+-----------------------------------------------------------------+  
                                   |  
                                   v  
\+-----------------------------------------------------------------------+  
| STEP 1: DETECT INSTALLER FRAMEWORK                                    |  
| Inspect Window Class, Executable Metadata, UI Automation Structure    |  
| (e.g., InnoClass, \#32770, WiX\_UI\_Bootstrapper, InstallShield\_Class)    |  
\+-----------------------------------------------------------------------+  
                                   |  
                                   v  
\+-----------------------------------------------------------------------+  
| STEP 2: PARSE CURRENT WIZARD PAGE                                     |  
| Extract Page Title, License Agreement Text, Checkbox States, Inputs   |  
\+-----------------------------------------------------------------------+  
                                   |  
                                   v  
\+-----------------------------------------------------------------------+  
| STEP 3: MATCH POLICY & INTENT                                         |  
| • License Page   \-\> Find "I Accept", Check Radio/Box, Click Next       |  
| • Directory Page \-\> Validate Path via NFPE or Keep Default, Click Next|  
| • Option Page    \-\> Uncheck Telemetry/Adware Checkboxes, Click Next   |  
| • Install Page   \-\> Wait for Progress Bar, Intercept Sub-Dialogs      |  
| • Completion     \-\> Uncheck "Launch Now" if requested, Click Finish    |  
\+-----------------------------------------------------------------------+  
                                   |  
                                   v  
\+-----------------------------------------------------------------------+  
| STEP 4: VERIFY INSTALLER EXIT                                         |  
| Confirm Process Termination, Handle "Restart Required" Prompts        |  
\+-----------------------------------------------------------------------+

# **CHILD WINDOW MANAGEMENT & UNLIMITED HIERARCHY**

The Desktop Interaction Manager tracks every window without structural depth limits.

\+-----------------------------------------------------------------------+  
|                           DESKTOP ROOT (0)                            |  
\+-----------------------------------------------------------------------+  
                                   |  
                   \+---------------+---------------+  
                   |                               |  
                   v                               v  
         \+-------------------+           \+-------------------+  
         |  OBS Studio Main  |           | VS Code Main Window|  
         \+-------------------+           \+-------------------+  
                   |  
                   v  
         \+-------------------+  
         | Source Dialog     |  
         \+-------------------+  
                   |  
                   v  
         \+-------------------+  
         | Properties Frame  |  
         \+-------------------+  
                   |  
                   v  
         \+-------------------+  
         | Color Picker Pop  |  
         \+-------------------+  
                   |  
                   v  
         \+-------------------+  
         | Advanced Hue Drop |  
         \+-------------------+  
                   |  
                   v  
         \+-------------------+  
         | Custom RGB Input  |  \<-- Depth Level N (Unlimited Recursion)  
         \+-------------------+

Every child node object explicitly stores:

* `Handle`: Unique OS window handle (`HWND` / `XID`).  
* `ParentHandle`: Direct parent window handle.  
* `OwnerHandle`: Owner window handle (for modal/owned popups).  
* `Children`: Array of direct child node descriptors.  
* `ProcessID`: Operating system process identifier (PID).  
* `ThreadID`: Creating thread identifier.  
* `BoundingRect`: DPI-adjusted absolute coordinates `(X1, Y1, X2, Y2)`.  
* `FocusState`: Boolean indicating active keyboard focus.  
* `VisibilityState`: Boolean indicating physical visibility on desktop screen space.  
* `ZOrderIndex`: Position in global and local window stack.  
* `Priority`: Execution/Handling priority metric.

# **WINDOW TREE SPECIFICATION**

The Desktop Interaction Manager maintains an in-memory representation of the active desktop layout:

Desktop  
│  
├── Chrome (HWND: 0x000102A4, PID: 4120\)  
│     │  
│     └── Save As Dialog (HWND: 0x00020120, Modal: True)  
│           │  
│           ├── DUIViewWndClassName (HWND: 0x00020124)  
│           │     │  
│           │     └── Explorer Pane (HWND: 0x00020128)  
│           │           │  
│           │           └── Folder View (HWND: 0x0002012C)  
│           │  
│           ├── File Name Combo Box (HWND: 0x00020130)  
│           └── Save Button (HWND: 0x00020134)  
│  
├── OBS Studio (HWND: 0x000305B0, PID: 8812\)  
│     │  
│     ├── Source Dialog (HWND: 0x000305C2, Modal: True)  
│     │     │  
│     │     └── Properties (HWND: 0x000305C8)  
│     │  
│     └── Settings (HWND: 0x00030610, Modal: False)  
│  
├── VS Code (HWND: 0x000408F2, PID: 10432\)  
└── Explorer (HWND: 0x00010058, PID: 1840\)

# **NATIVE FILE PICKER ENGINE (NFPE)**

The Native File Picker Engine (NFPE) is a dedicated subsystem inside the Desktop Interaction Manager built to discover, navigate, populate, and resolve operating system file and folder selection dialogs across any application.

                         NFPE MODULE ARCHITECTURE  
                                     │  
    ┌────────────────────────────────┼────────────────────────────────┐  
    │                                │                                │  
    ▼                                ▼                                ▼  
\+-----------------------+  \+-----------------------+  \+-----------------------+  
|   DIALOG INTERCEPT    |  |  DIRECTORY NAVIGATOR  |  |  FILE SELECTION ENGINE|  
|                       |  |                       |  |                       |  
| • Open File Dialog    |  | • Quick Access Paths  |  | • Single File Select  |  
| • Save File Dialog    |  | • Local & Network Drive| | • Multi-File Select   |  
| • Save As Dialog      |  | • UNC & Cloud Drives  |  | • Wildcard / Regex    |  
| • Folder Picker       |  | • Path Injection      |  | • Attribute Matching  |  
| • Import/Export       |  | • Directory Memory    |  | • Playwright Fallback |  
\+-----------------------+  \+-----------------------+  \+-----------------------+

### **File Selection Modes**

1. **Single File Selection**: Locating and choosing exactly one target file path.  
2. **Multiple File Selection**: Selecting N discrete files within a folder using programmatic array selection or key-modifier input injection (`Ctrl+Click`, `Shift+Click`).  
3. **Folder Selection**: Navigating into directory hierarchies and executing folder authorization/selection buttons.  
4. **Mixed File Selection**: Selecting files and directories simultaneously where supported by custom dialogs.  
5. **Directory Tree Selection**: Deep navigation through tree view controls (e.g., `SysTreeView32`).  
6. **Wildcard Selection**: Injecting wildcard query strings (e.g., `*.log`, `data_2026_*.csv`) into file input controls.  
7. **Recursive Folder Selection**: Crawling sub-directories automatically to find files matching workflow constraints.  
8. **Filtered Selection**: Selecting active file filter dropdown indices before selecting targets.

### **File Matching Strategies**

When locating target files, NFPE executes configured matching logic:

* `Exact Match`: String equals `target_filename.ext`.  
* `Contains`: String contains substring target.  
* `Starts With`: Filename matches prefix.  
* `Ends With`: Filename matches suffix/extension.  
* `Regex`: Complex regular expression execution against folder listing arrays.  
* `Wildcard`: Standard shell wildcard pattern parsing (`?`, `*`).  
* `Fuzzy Match`: Levenshtein distance scoring threshold check (similarity score \>0.85).  
* `Attribute Filter`: Matching creation date, modification date, file size, or extension.

### **Directory Navigation & Memory**

NFPE maintains an in-memory path store (`Directory Memory`) tracking:

* `Recent Directories`: Chronological queue of last 50 accessed directories.  
* `Pinned Directories`: Fixed system locations (Desktop, Documents, Downloads).  
* `Workflow Directories`: Active execution paths injected by current workflow context.  
* `Temporary Directories`: Ephemeral staging paths.  
* `Project Directories`: Repository or workspace roots.  
* `Last Successful Selection`: Path cache for quick recovery if a dialog re-opens.

### **Playwright Integration Strategy**

For browser-based automation workflows, NFPE continuously coordinates with Playwright context handles:

                   Browser Upload Triggered  
                               │  
                               v  
               Is Playwright API Available & Unblocked?  
                               │  
                ┌──────────────┴──────────────┐  
                │                             │  
             \[ YES \]                       \[ NO \]  
                │                             │  
                v                             v  
  Use Playwright Direct API         Trigger Native File Picker Engine  
  (fileChooser.setFiles)            (NFPE OS Interception Pipeline)

If Playwright file chooser registration times out, is blocked by browser cross-origin policy, or involves a non-browser native file dialog, execution seamlessly routes to NFPE without interrupting workflow state.

# **DETECTION EVENTS**

The Desktop Interaction Manager registers low-level OS hooks (e.g., `SetWinEventHook` on Windows, `XCB` event listeners on Linux) to continuously track desktop state changes:

* `EVENT_WINDOW_CREATED`: New top-level or child window handle generated by OS.  
* `EVENT_WINDOW_CLOSED`: Window handle destroyed.  
* `EVENT_WINDOW_HIDDEN`: Window visibility state set to false.  
* `EVENT_WINDOW_RESTORED`: Window un-minimized or restored from tray.  
* `EVENT_WINDOW_ACTIVATED`: Window granted foreground input state.  
* `EVENT_WINDOW_MINIMIZED`: Window minimized.  
* `EVENT_WINDOW_MAXIMIZED`: Window expanded to screen bounds.  
* `EVENT_TITLE_CHANGED`: Text title string mutated.  
* `EVENT_FOCUS_CHANGED`: Input focus shifted between specific control handles.  
* `EVENT_OWNER_CHANGED`: Ownership relationship modified.  
* `EVENT_POPUP_CREATED`: Ephemeral popup control spawned.  
* `EVENT_DIALOG_CREATED`: Native dialog frame generated.  
* `EVENT_WIZARD_CREATED`: Multi-step installer page loaded.  
* `EVENT_TOOLTIP_CREATED`: Ephemeral hover window spawned.  
* `EVENT_CONTEXT_MENU_OPENED`: Context menu opened.

# **AUTOMATION ENGINE FALLBACK PIPELINE**

When interacting with any target GUI window or control, DIM executes a multi-layered fallback strategy:

             AUTOMATION ENGINE FALLBACK PIPELINE  
                               │  
                               v  
\+--------------------------------------------------------------+  
| LAYER 1: UI Automation / Native Accessibility                |  
| (Windows UIA, MSAA, IAccessible2, AT-SPI2, Apple AX)         |  
\+--------------------------------------------------------------+  
                               │  
                    \[ FAILED / UNRESPONSIVE \]  
                               │  
                               v  
\+--------------------------------------------------------------+  
| LAYER 2: Framework Native API Drivers                        |  
| (Win32 API, WPF, Qt Accessibility, Java Access Bridge, GTK)  |  
\+--------------------------------------------------------------+  
                               │  
                    \[ FAILED / UNRESPONSIVE \]  
                               │  
                               v  
\+--------------------------------------------------------------+  
| LAYER 3: Optical Character Recognition (OCR Engine)          |  
| (Tesseract OCR, Windows Media OCR)                           |  
\+--------------------------------------------------------------+  
                               │  
                    \[ FAILED / UNRESPONSIVE \]  
                               │  
                               v  
\+--------------------------------------------------------------+  
| LAYER 4: Computer Vision & Template Matching                 |  
| (OpenCV Feature Matching, Multi-Scale Template Match)        |  
\+--------------------------------------------------------------+  
                               │  
                    \[ FAILED / UNRESPONSIVE \]  
                               │  
                               v  
\+--------------------------------------------------------------+  
| LAYER 5: Pixel-Level Geometry Fallback                       |  
| (Relative bounding box click, DPI-scaled coordinate offset)  |  
\+--------------------------------------------------------------+  
                               │  
                    \[ FAILED / UNRESPONSIVE \]  
                               │  
                               v  
\+--------------------------------------------------------------+  
| LAYER 6: Human Approval / Policy Escalation                  |  
| (Emit Workflow Pause, Alert Human Operator, Await Input)     |  
\+--------------------------------------------------------------+

# **WORKFLOW INTEGRATION & PAUSE/RESUME**

\+---------------------------------------------------------------------------------------------------+  
| WORKFLOW SCHEDULER                                                                                |  
| (Executing Automation Steps)                                                                      |  
\+---------------------------------------------------------------------------------------------------+  
       |                                                                                    ^  
       | \[Workflow Running\]                                                                 | \[Resume Signal\]  
       v                                                                                    |  
\+---------------------------------------------------------------------------------------------------+  
| DESKTOP INTERACTION MANAGER (DIM)                                                                 |  
|                                                                                                   |  
|  1\. DETECT POPUP         \-\> Intercept OS Event, match target window handle.                       |  
|  2\. PAUSE SCHEDULER      \-\> Issue synchronous Workflow Pause Signal to halt steps.                |  
|  3\. CAPTURE & READ       \-\> Snapshot UI Automation tree, execute OCR/Vision if needed.          |  
|  4\. DECIDE ACTION        \-\> Query policy rulebook, match installer/dialog templates.              |  
|  5\. EXECUTE ACTION       \-\> Inject mouse/keyboard inputs or invoke native UIA control patterns.  |  
|  6\. VERIFY CLOSURE       \-\> Confirm window destruction via OS event hooks.                        |  
|  7\. RESTORE FOCUS        \-\> Programmatically reactivate pre-interception focused window handle.  |  
|  8\. RESUME SCHEDULER     \-\> Emit Workflow Resume Signal.                                         |  
\+---------------------------------------------------------------------------------------------------+

# **FOCUS MANAGER**

The Focus Manager maintains operational control over input state to prevent input leakage (e.g., typing keystrokes meant for a dialog into a background text editor):

\+-----------------------------------------------------------------------+  
|                         FOCUS MANAGER STACK                           |  
\+-----------------------------------------------------------------------+  
| Active Focused Control  : HWND 0x00020130 (File Name Input)           |  
| Active Focused Window   : HWND 0x00020120 (Save As Dialog)            |  
| Previous Focused Window : HWND 0x000102A4 (Chrome Main Window)        |  
| Modal Lock Stack        : \[0x00020120 \-\> 0x000102A4\]                  |  
| Desktop Z-Order Stack   : Topmost \-\> Foreground \-\> Normal \-\> Desktop   |  
\+-----------------------------------------------------------------------+

### **Focus Operations**

* `CaptureFocusState()`: Stores active window handle, control handle, caret position, and selection bounds.  
* `SetFocusExplicit(HWND, ControlID)`: Forces window foreground state via OS attachment (`AttachThreadInput`) and sets focus to target control.  
* `RestoreFocusState()`: Restores input focus to the exact window and control recorded prior to popup interception.

# **SECURITY & POLICY GUARD**

The Security & Policy Guard within the Desktop Interaction Engine isolates security-critical system dialogs.

\+-----------------------------------------------------------------------+  
|                       SECURITY PROMPT DETECTED                        |  
|   (UAC Prompt, Administrator Elevation, Password Input, Certificate)   |  
\+-----------------------------------------------------------------------+  
                                   |  
                                   v  
\+-----------------------------------------------------------------------+  
| IS AUTOMATED APPROVAL PERMITTED BY POLICY\_MANUAL.MD?                  |  
\+-----------------------------------------------------------------------+  
                                   |  
           \+-----------------------+-----------------------+  
           |                                               |  
        \[ NO \]                                          \[ YES \]  
           |                                               |  
           v                                               v  
\+-----------------------------------+   \+-----------------------------------+  
| • BLOCK AUTOMATED CLICKING        |   | • Verify Signed Cryptographic     |  
| • Freeze Execution & Signal Pause |   |   Approval Payload Token          |  
| • Prompt Human Admin for Approval |   | • Inject Credentials / Approve    |  
\+-----------------------------------+   \+-----------------------------------+

Automated auto-approval is **strictly prohibited** without a signed approval policy for:

* User Account Control (UAC) administrative elevation windows.  
* OS credential manager / password prompts.  
* PIN / Smartcard authentication dialogs.  
* SSL/TLS client certificate selection dialogs.  
* Windows Defender Firewall network access authorization.  
* System security warning prompts for unsigned binary execution.

# **OCR ENGINE SPECIFICATION**

The OCR Engine provides optical text recognition when native accessibility trees are unpopulated or obfuscated:

* **Supported OCR Drivers**: Tesseract OCR v5+, Windows.Media.Ocr (Native Win10/11 API), EasyOCR engine (optional Python runtime binding).  
* **Target Detection Capabilities**: Buttons, Labels, Textboxes, Checkboxes, Radio Buttons, Tab Headers, Status Indicators, Progress Percentages, Data Tables, Menu Items, Control Icons.  
* **Pre-Processing Pipeline**: Image Binarization, Contrast Adjustment, Adaptive Thresholding, DPI Rescaling to 300 DPI, Noise Reduction.

\+-------------------+     \+-------------------+     \+-------------------+     \+-------------------+  
|  Raw Window Image | \--\> | Binarization &    | \--\> | OCR Text & Bounding| \--\> | Dynamic UI Control|  
|  Capture (Bitmap) |     | Thresholding      |     | Box Detection     |     | Map (JSON Tree)   |  
\+-------------------+     \+-------------------+     \+-------------------+     \+-------------------+

# **COMPUTER VISION ENGINE SPECIFICATION**

The Computer Vision Engine provides pixel-level visual recognition when accessibility and OCR engines fail to locate controls:

* **Supported Drivers**: OpenCV C++ Native Core, Deep Feature Matching.  
* **Algorithms**: Multi-Scale Template Matching, SIFT/ORB Feature Matching, Canny Edge Detection, Color/Pixel Histogram Matching.  
* **Threshold Metrics**: Minimum template match confidence score threshold set to ≥0.90.

\+-----------------------+     \+-----------------------+     \+-----------------------+  
| Target Template Image | \--\> | OpenCV Template Match | \--\> | Match Confidence      |  
| (Control Asset)       |     | (Multi-Scale Search)  |     | Assessment (\>= 0.90)  |  
\+-----------------------+     \+-----------------------+     \+-----------------------+  
                                                                        |  
                                                                        v  
\+-----------------------+                                   \+-----------------------+  
| Fail \-\> Fallback to   | \<-------------------------------- | Compute Centroid      |  
| Pixel Relative Bounds |               \[ Fail \]            | Target Coordinates    |  
\+-----------------------+                                   \+-----------------------+

# **WINDOW CLASSIFICATION ENGINE**

The Window Classifier processes raw window metadata and classifies windows into one of the following operational types:

`Installer` | `Wizard` | `Dialog` | `Popup` | `Notification` | `Error` | `Warning` | `Information` | `Success` | `Progress` | `Authentication` | `Security` | `Tool` | `Floating` | `File Picker` | `Folder Picker` | `Menu` | `Tooltip` | `Unknown`

                                 RAW WINDOW HANDLE DETECTED  
                                              │  
                                              v  
                            \+-----------------------------------+  
                            |   Check Window Class & Style      |  
                            |   (e.g., \#32770, WS\_EX\_TOPMOST)   |  
                            \+-----------------------------------+  
                                              │  
                                              v  
                            \+-----------------------------------+  
                            |   Parse Control Text & Structural |  
                            |   Child Tree Patterns             |  
                            \+-----------------------------------+  
                                              │  
                                              v  
                            \+-----------------------------------+  
                            |   Query Installer & Dialog Rules  |  
                            \+-----------------------------------+  
                                              │  
                                              v  
                            \+-----------------------------------+  
                            |   ASSIGN DETERMINISTIC CLASS TYPE |  
                            \+-----------------------------------+

# **SOCKET SPECIFICATIONS**

All inter-process communication between DIM and the Hojaiga AOS Core takes place over dedicated, non-blocking IPC domain sockets:

| Socket Name | Path / Endpoint | Direction | Auth | Timeout | Retry | Version |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| **Window Discovery Socket** | `ipc:///var/run/hojaiga/dim_win_discovery.sock` | Outbound | System Token | 500ms | 3 | v1.0 |
| **Popup Socket** | `ipc:///var/run/hojaiga/dim_popup.sock` | Bi-directional | System Token | 1000ms | 3 | v1.0 |
| **Dialog Socket** | `ipc:///var/run/hojaiga/dim_dialog.sock` | Bi-directional | System Token | 1000ms | 3 | v1.0 |
| **Child Window Socket** | `ipc:///var/run/hojaiga/dim_child_win.sock` | Bi-directional | System Token | 500ms | 2 | v1.0 |
| **Modal Window Socket** | `ipc:///var/run/hojaiga/dim_modal_win.sock` | Bi-directional | System Token | 1000ms | 3 | v1.0 |
| **Installer Socket** | `ipc:///var/run/hojaiga/dim_installer.sock` | Bi-directional | System Token | 5000ms | 5 | v1.0 |
| **OCR Socket** | `ipc:///var/run/hojaiga/dim_ocr.sock` | Bi-directional | System Token | 2000ms | 2 | v1.0 |
| **Vision Socket** | `ipc:///var/run/hojaiga/dim_vision.sock` | Bi-directional | System Token | 2000ms | 2 | v1.0 |
| **Accessibility Socket** | `ipc:///var/run/hojaiga/dim_accessibility.sock` | Bi-directional | System Token | 500ms | 3 | v1.0 |
| **Focus Socket** | `ipc:///var/run/hojaiga/dim_focus.sock` | Bi-directional | System Token | 200ms | 3 | v1.0 |
| **Window Tree Socket** | `ipc:///var/run/hojaiga/dim_wintree.sock` | Request-Reply | System Token | 1000ms | 2 | v1.0 |
| **Window Event Socket** | `ipc:///var/run/hojaiga/dim_winevent.sock` | Push-only | System Token | 100ms | 5 | v1.0 |
| **Desktop Interaction Socket** | `ipc:///var/run/hojaiga/dim_desktop_interact.sock` | Bi-directional | System Token | 1000ms | 3 | v1.0 |
| **Workflow Pause Socket** | `ipc:///var/run/hojaiga/dim_wf_pause.sock` | Bi-directional | System Token | 200ms | 5 | v1.0 |
| **Workflow Resume Socket** | `ipc:///var/run/hojaiga/dim_wf_resume.sock` | Bi-directional | System Token | 200ms | 5 | v1.0 |
| **Security Prompt Socket** | `ipc:///var/run/hojaiga/dim_security_prompt.sock` | Bi-directional | Admin Token | 5000ms | 1 | v1.0 |
| **File Picker Socket** | `ipc:///var/run/hojaiga/dim_file_picker.sock` | Bi-directional | System Token | 2000ms | 3 | v1.0 |
| **Directory Navigation Socket** | `ipc:///var/run/hojaiga/dim_dir_nav.sock` | Bi-directional | System Token | 1000ms | 3 | v1.0 |
| **File Search Socket** | `ipc:///var/run/hojaiga/dim_file_search.sock` | Bi-directional | System Token | 3000ms | 2 | v1.0 |
| **File Validation Socket** | `ipc:///var/run/hojaiga/dim_file_val.sock` | Request-Reply | System Token | 500ms | 2 | v1.0 |
| **File Selection Socket** | `ipc:///var/run/hojaiga/dim_file_select.sock` | Bi-directional | System Token | 1000ms | 3 | v1.0 |
| **Multi-Selection Socket** | `ipc:///var/run/hojaiga/dim_multi_select.sock` | Bi-directional | System Token | 2000ms | 3 | v1.0 |
| **Folder Selection Socket** | `ipc:///var/run/hojaiga/dim_folder_select.sock` | Bi-directional | System Token | 1000ms | 3 | v1.0 |
| **Explorer Socket** | `ipc:///var/run/hojaiga/dim_explorer.sock` | Bi-directional | System Token | 1000ms | 3 | v1.0 |
| **Upload Socket** | `ipc:///var/run/hojaiga/dim_upload.sock` | Bi-directional | System Token | 5000ms | 3 | v1.0 |
| **Download Socket** | `ipc:///var/run/hojaiga/dim_download.sock` | Bi-directional | System Token | 5000ms | 3 | v1.0 |

# **PIPELINE SPECIFICATIONS**

\+--------------------------+-----------------------+-----------------------+-----------------------+-----------------------+  
| Pipeline                 | Source                | Destination           | Payload               | Recovery Mode         |  
\+--------------------------+-----------------------+-----------------------+-----------------------+-----------------------+  
| Window Discovery Pipe    | OS Event Hook         | Window Manager        | HWND Metadata Struct  | Rescan Desktop Tree   |  
| Popup Pipeline           | Window Discovery Pipe | Classifier Subsystem  | Raw Window Capture    | Fallback to OCR       |  
| Window Classification    | Popup Pipeline        | Action Decision Rules | Class Taxonomy Token  | Mark as Unknown Window|  
| OCR Pipeline             | Window Capture Bitmap | Text Parser Engine    | OCR Bounding Box List | Vision Match Fallback |  
| Vision Pipeline          | Window Capture Bitmap | Computer Vision Core  | Feature Match Vector  | Relative Bound Click  |  
| Focus Pipeline           | Focus Manager         | OS Input State        | HWND Focus Token      | Force Re-Attach Input |  
| Interaction Pipeline     | Action Decision Rules | OS Control Injector   | Input Event Struct    | Re-Try via Win32 API  |  
| Verification Pipeline    | Interaction Pipeline  | Verification Engine   | Window State Query    | Re-Execute Action     |  
| Workflow Pause Pipeline  | DIM Interceptor       | Workflow Scheduler    | Pause Request Token   | Hard Lock Scheduler   |  
| Workflow Resume Pipeline | Verification Pipeline | Workflow Scheduler    | Resume Request Token  | Force Focus Reset     |  
| File Discovery Pipeline  | NFPE Detector         | File Search Engine    | File Query Struct     | Broaden Search Filter |  
| Directory Navigation Pipe| NFPE Path Injector    | File Dialog Controls  | Absolute Target Path  | Fallback Quick Access |  
| File Validation Pipeline | File Matcher          | Security Validator    | File Attribute Struct | Reject File Selection |  
| Selection Pipeline       | NFPE Multi-Select Engine| File Dialog Controls| HWND Selection Array  | Inject Key Modifiers  |  
| Upload Pipeline          | Playwright / NFPE     | Application Input     | Upload Stream / Path  | Re-Open File Dialog   |  
| Download Pipeline        | Application Event     | Target System Storage | File Destination Path | Override Collision    |  
| Recovery Pipeline        | System Error Handler  | Safe Mode / Supervisor| Diagnostic Error Dump | Force Dismiss Window  |  
\+--------------------------+-----------------------+-----------------------+-----------------------+-----------------------+

# **ERROR HANDLING & RECOVERY**

The Desktop Interaction Manager handles desktop automation edge cases deterministically:

1. **Hidden Window**: Query window state using `IsWindowVisible`. If hidden, bypass physical input injection and manipulate the UI frame directly via UI Automation pattern invocation (`IUIAutomationInvokeProvider`).  
2. **Off-Screen Window**: Check bounding rectangle against total desktop screen virtual bounds. If outside screen bounds, execute `SetWindowPos` or `MoveWindow` to bring the target window into active monitor coordinate bounds.  
3. **Disabled Controls**: Detect disabled control state (`WS_DISABLED`). Issue a waiting loop (up to a configured timeout) for the control state to toggle to enabled. If timeout expires, log error and pause workflow.  
4. **Missing Accessibility**: Fall back through the Automation Engine Fallback Pipeline (UIA \-\> Win32 \-\> OCR \-\> Vision).  
5. **Unknown Window**: Execute OCR text recognition and Computer Vision layout extraction; attempt standard dismissal buttons (e.g., Close `X`, Cancel, OK) or escalate to Human Approval.  
6. **Duplicate Windows**: Disambiguate identical windows using Process ID (PID), thread ID, window creation timestamp, parent handle link, or visual content checksums.  
7. **Lost Focus**: Periodically verify that the target window remains in the foreground. If focus is lost during injection, execute `SetForegroundWindow` and re-inject inputs.  
8. **Timeout**: Trigger timeout counter per window operation (default: 10 seconds). Upon expiration, execute the Recovery Pipeline.  
9. **Popup Storm**: Detect high-frequency popup creation (\>5 popups per second). Immediately freeze workflow execution, engage the Popup Storm Guard, log offending process handles, and halt automatic processing to prevent infinite loops.  
10. **Installer Loop**: Track wizard page transitions using a visited-state hash array. If the same page state appears \>3 times, detect an installer loop, abort setup execution, and alert the Workflow Scheduler.  
11. **Security Prompt**: Intercept administrative security prompts, enforce security policies, and suspend automated actions unless pre-approved.  
12. **Window Freeze**: Issue `SendMessageTimeout` with a 2-second threshold to detect unresponsive UI message loops (`IsHungAppWindow`). If hung, log the unresponsive process and alert the supervisor.  
13. **Deadlock**: Maintain global transaction locks with a 15-second hard timeout to break potential resource contention loops between the Focus Manager, File Picker Engine, and Workflow Scheduler.

# **ARCHITECTURAL DIAGRAMS**

## **Overall Popup Handler Architecture (Mermaid)**

Code snippet  
graph TD  
    Desktop\[Desktop Environment\] \--\>|OS Hooks / Events| DIM\[Desktop Interaction Manager\]  
      
    subgraph DIM \[Desktop Interaction Manager\]  
        WMS\[Window Manager Subsystem\]  
        NFPE\[Native File Picker Engine\]  
        DIE\[Desktop Interaction Engine\]  
    end  
      
    WMS \--\>|Window Discovery| WCE\[Window Classifier Engine\]  
    WCE \--\>|Classified Type| FOC\[Focus & Stack Manager\]  
      
    NFPE \--\>|File Dialog Detected| NAV\[Directory Navigator\]  
    NAV \--\>|Locate Target| FSE\[File Selection Engine\]  
      
    DIE \--\>|UIA / Win32| INJ\[Input Injector\]  
    DIE \--\>|Fallback| OCR\[OCR Engine\]  
    OCR \--\>|Fallback| VIS\[Computer Vision Engine\]  
      
    FOC \--\>|Pause Exec| WFS\[Workflow Scheduler\]  
    INJ \--\>|Action Applied| VER\[Verification Engine\]  
    VER \--\>|Pass| WFS  
    VER \--\>|Fail| REC\[Recovery Engine\]

## **Window Discovery Flow (Mermaid)**

Code snippet  
sequenceDiagram  
    participant OS as Operating System  
    participant WDE as Window Discovery Engine  
    participant WCE as Window Classifier  
    participant WTM as Window Tree Manager  
    participant WFS as Workflow Scheduler

    OS-\>\>WDE: EVENT\_WINDOW\_CREATED (HWND)  
    WDE-\>\>WTM: Insert HWND into Desktop Tree  
    WDE-\>\>WCE: Classify Window (Metadata \+ Controls)  
    WCE--\>\>WDE: Window Class (Modal Dialog)  
    WDE-\>\>WFS: Issue Workflow Pause Signal  
    WDE-\>\>WTM: Lock Z-Order Stack

## **Window Tree (Mermaid)**

Code snippet  
graph TD  
    Root\[Desktop Root\] \--\> Chrome\[Chrome Browser HWND:0x102A4\]  
    Root \--\> OBS\[OBS Studio HWND:0x305B0\]  
    Root \--\> VSCode\[VS Code HWND:0x408F2\]  
      
    Chrome \--\> SaveAs\[Save As Dialog HWND:0x20120 \- Modal\]  
    SaveAs \--\> FileInput\[File Name Combo HWND:0x20130\]  
    SaveAs \--\> SaveBtn\[Save Button HWND:0x20134\]  
      
    OBS \--\> SourceDlg\[Source Dialog HWND:0x305C2\]  
    SourceDlg \--\> PropFrame\[Properties Frame HWND:0x305C8\]

## **Popup Lifecycle (Mermaid)**

Code snippet  
stateDiagram-v2  
    \[\*\] \--\> Unidentified: OS Event Hook Fired  
    Unidentified \--\> Classified: Window Classifier Run  
    Classified \--\> WorkflowPaused: Intercept & Pause Scheduler  
    WorkflowPaused \--\> ReadingContent: UIA / OCR / Vision Scan  
    ReadingContent \--\> ActionExecuted: Button Click / Text Input  
    ActionExecuted \--\> VerifyingClosure: Verification Engine Check  
    VerifyingClosure \--\> FocusRestored: Window Closed Successfully  
    FocusRestored \--\> WorkflowResumed: Resume Scheduler  
    WorkflowResumed \--\> \[\*\]  
      
    VerifyingClosure \--\> RecoveryTriggered: Timeout / Window Hung  
    RecoveryTriggered \--\> \[\*\]: Force Dismiss / Human Escalation

## **Focus Management (Mermaid)**

Code snippet  
graph LR  
    A\[Intercept Window\] \--\> B\[Capture Current Focus State\]  
    B \--\> C\[Push Current HWND to Focus Stack\]  
    C \--\> D\[Attach Thread Input to Target Window\]  
    D \--\> E\[Inject Inputs into Target Window\]  
    E \--\> F\[Pop HWND from Focus Stack\]  
    F \--\> G\[Restore Focus to Original HWND\]

## **OCR Pipeline (Mermaid)**

Code snippet  
graph TD  
    A\[Capture Target Window Bitmap\] \--\> B\[Grayscale Transformation\]  
    B \--\> C\[Adaptive Thresholding & Binarization\]  
    C \--\> D\[300 DPI Rescaling\]  
    D \--\> E\[Tesseract / Win OCR Parsing\]  
    E \--\> F\[Extract Text & Bounding Rects\]  
    F \--\> G\[Map Coordinates to Control Centroids\]

## **Vision Pipeline (Mermaid)**

Code snippet  
graph TD  
    A\[Capture Window Screen Region\] \--\> B\[Load Template Asset\]  
    B \--\> C\[OpenCV Multi-Scale Match\]  
    C \--\> D{Confidence \>= 0.90?}  
    D \-- Yes \--\> E\[Compute Centroid Coordinates\]  
    D \-- No \--\> F\[Feature Match / Fallback to Relative Bounds\]  
    E \--\> G\[Inject Click Event\]

## **Installer Wizard Flow (Mermaid)**

Code snippet  
graph TD  
    A\[Detect Installer HWND\] \--\> B\[Parse Page UI Layout\]  
    B \--\> C{Page Type?}  
    C \-- Welcome \--\> D\[Click Next\]  
    C \-- EULA \--\> E\[Check Accept & Click Next\]  
    C \-- Directory \--\> F\[Validate / Inject Path & Click Next\]  
    C \-- Progress \--\> G\[Wait for Progress Completion\]  
    C \-- Finish \--\> H\[Uncheck Launch Options & Click Finish\]  
    D \--\> B  
    E \--\> B  
    F \--\> B  
    G \--\> B  
    H \--\> I\[Installer Complete\]

## **Workflow Pause/Resume (Mermaid)**

Code snippet  
sequenceDiagram  
    participant WF as Workflow Engine  
    participant DIM as Desktop Interaction Manager  
    participant OS as Native Operating System

    WF-\>\>OS: Execute Automation Action  
    OS-\>\>DIM: Spawn Native Modal Dialog Event  
    DIM-\>\>WF: SEND PAUSE SIGNAL  
    Note over WF: Workflow Execution Frozen  
    DIM-\>\>OS: Resolve Dialog (Click OK / Input File)  
    OS--\>\>DIM: Dialog Destroyed Event  
    DIM-\>\>WF: SEND RESUME SIGNAL  
    Note over WF: Workflow Execution Resumed

## **Desktop Interaction Architecture (Mermaid)**

Code snippet  
graph TD  
    subgraph DIM Core  
        WM\[Window Manager\]  
        FP\[Native File Picker Engine\]  
        DIE\[Desktop Interaction Engine\]  
    end

    WM \--\>|Tracks| WTree\[Window Hierarchy Tree\]  
    FP \--\>|Navigates| TargetFile\[Target File / Folder\]  
    DIE \--\>|Executes| Inputs\[Kbd / Mouse Injection\]

    WTree \--\>|Focus Control| Inputs  
    TargetFile \--\>|File Path Injection| Inputs

# **ASCII DIAGRAMS**

### **Desktop Window Tree**

\+-----------------------------------------------------------------------+  
| DESKTOP ROOT (0x00000000)                                             |  
\+-----------------------------------------------------------------------+  
    |  
    \+---\> Chrome (HWND: 0x000102A4, PID: 4120\)  
    |       |  
    |       \+---\> Save As Dialog (HWND: 0x00020120, Modal: True)  
    |               |  
    |               \+---\> DUIViewWndClassName (HWND: 0x00020124)  
    |               |       |  
    |               |       \+---\> Explorer Pane (HWND: 0x00020128)  
    |               |  
    |               \+---\> File Name Combo Box (HWND: 0x00020130)  
    |               \+---\> Save Button (HWND: 0x00020134)  
    |  
    \+---\> OBS Studio (HWND: 0x000305B0, PID: 8812\)  
    |       |  
    |       \+---\> Source Dialog (HWND: 0x000305C2, Modal: True)  
    |               |  
    |               \+---\> Properties Frame (HWND: 0x000305C8)  
    |  
    \+---\> VS Code (HWND: 0x000408F2, PID: 10432\)

### **Nested Child Windows**

\[Level 0: Main Window HWND: 0x0010\]  
   |  
   \+---\> \[Level 1: Tab Container HWND: 0x0012\]  
            |  
            \+---\> \[Level 2: Panel Container HWND: 0x0014\]  
                     |  
                     \+---\> \[Level 3: Custom Group Box HWND: 0x0016\]  
                              |  
                              \+---\> \[Level 4: Input Frame HWND: 0x0018\]  
                                       |  
                                       \+---\> \[Level N: Target Control HWND: 0x001A\]

### **Popup Detection**

\+-----------------------------------------------------------------------+  
| DETECT OS EVENT HOOK (EVENT\_WINDOW\_CREATED)                           |  
\+-----------------------------------------------------------------------+  
                                   |  
                                   v  
\+-----------------------------------------------------------------------+  
| QUERY HWND METADATA (Class Name, Window Style, Process ID)            |  
\+-----------------------------------------------------------------------+  
                                   |  
                                   v  
\+-----------------------------------------------------------------------+  
| MATCH POPUP TAXONOMY (Modal Dialog / System Message / File Picker)    |  
\+-----------------------------------------------------------------------+  
                                   |  
                                   v  
\+-----------------------------------------------------------------------+  
| EMIT WORKFLOW PAUSE SIGNAL & LOCK FOCUS STACK                         |  
\+-----------------------------------------------------------------------+

### **Installer Wizard**

\+-------------------+     \+-------------------+     \+-------------------+  
|   WELCOME PAGE    | \--\> |    EULA PAGE      | \--\> |  DIRECTORY PAGE   |  
| Click "Next"      |     | Click "Accept"    |     | Inject Path       |  
\+-------------------+     \+-------------------+     \+-------------------+  
                                                              |  
                                                              v  
\+-------------------+     \+-------------------+     \+-------------------+  
|  FINISH PAGE      | \<-- |   PROGRESS PAGE   | \<-- |   INSTALL PAGE    |  
| Click "Finish"    |     | Wait Completion   |     | Click "Install"   |  
\+-------------------+     \+-------------------+     \+-------------------+

### **Focus Stack**

\+-----------------------------------------------------------------------+  
| \[TOP\]    HWND 0x00020130 (Active Target Control: File Name Input)     |  
| \[MID\]    HWND 0x00020120 (Active Intercepted Dialog: Save As)         |  
| \[BASE\]   HWND 0x000102A4 (Pre-Interception Focused Window: Chrome)    |  
\+-----------------------------------------------------------------------+

### **Modal Stack**

\+-----------------------------------------------------------------------+  
| \[MODAL 2\] HWND 0x000305C8 (Child Properties Dialog \- Locked)          |  
| \[MODAL 1\] HWND 0x000305C2 (Source Dialog \- Locked)                     |  
| \[ROOT\]    HWND 0x000305B0 (OBS Main Window \- Input Blocked)            |  
\+-----------------------------------------------------------------------+

### **OCR Flow**

Raw Image Bitmap \-\> Grayscale \-\> Thresholding \-\> 300 DPI \-\> OCR Parse \-\> Control Map

### **Vision Flow**

Screen Capture \-\> Template Load \-\> OpenCV Match \-\> Confidence Check \-\> Click Centroid

### **Window Discovery**

OS Event \-\> Handle Filter \-\> Tree Registry \-\> Window Classifier \-\> Focus Lock

### **Desktop Architecture**

\+-----------------------------------------------------------------------+  
|                  DESKTOP INTERACTION MANAGER (DIM)                    |  
|                                                                       |  
|  \+--------------------+  \+--------------------+  \+-----------------+  |  
|  |   WINDOW MANAGER   |  | NATIVE FILE PICKER |  | DESKTOP ENGINE  |  |  
|  |     SUBSYSTEM      |  |   ENGINE (NFPE)    |  |     (DIE)       |  |  
|  \+--------------------+  \+--------------------+  \+-----------------+  |  
\+-----------------------------------------------------------------------+  
                                   |  
                                   v  
\+-----------------------------------------------------------------------+  
|                 SYSTEM WORKFLOW SCHEDULER & PIPELINE                  |  
\+-----------------------------------------------------------------------+

# **FOLDER STRUCTURE**

/opt/hojaiga/src/desktop\_interaction\_manager/  
├── bin/  
│   └── dim\_daemon                  \# Main Desktop Interaction Manager Daemon  
├── config/  
│   ├── dim\_config.yaml             \# Main operational settings  
│   ├── installer\_rules.json        \# Wizard detection rule definitions  
│   └── security\_policies.json      \# Elevated prompt handling rules  
├── docs/  
│   └── Popup\_Handler.md            \# System specification  
├── inc/  
│   ├── accessibility\_driver.hpp  
│   ├── desktop\_interaction\_engine.hpp  
│   ├── file\_picker\_engine.hpp  
│   ├── focus\_manager.hpp  
│   ├── installer\_wizard\_engine.hpp  
│   ├── ocr\_engine.hpp  
│   ├── vision\_engine.hpp  
│   ├── window\_classifier.hpp  
│   ├── window\_discovery\_engine.hpp  
│   ├── window\_manager\_subsystem.hpp  
│   └── window\_tree\_manager.hpp  
├── src/  
│   ├── accessibility\_driver.cpp  
│   ├── desktop\_interaction\_engine.cpp  
│   ├── file\_picker\_engine.cpp  
│   ├── focus\_manager.cpp  
│   ├── installer\_wizard\_engine.cpp  
│   ├── ocr\_engine.cpp  
│   ├── vision\_engine.cpp  
│   ├── window\_classifier.cpp  
│   ├── window\_discovery\_engine.cpp  
│   ├── window\_manager\_subsystem.cpp  
│   └── window\_tree\_manager.cpp  
└── tests/  
    ├── integration/  
    │   ├── test\_file\_picker\_flow.cpp  
    │   ├── test\_installer\_wizard.cpp  
    │   └── test\_workflow\_pause\_resume.cpp  
    └── unit/  
        ├── test\_ocr\_parsing.cpp  
        ├── test\_vision\_matching.cpp  
        └── test\_window\_tree.cpp

# **IMPLEMENTATION GUIDE**

## **C++ Header Definition: `desktop_interaction_engine.hpp`**

C++  
\#ifndef HOJAIGA\_DESKTOP\_INTERACTION\_ENGINE\_HPP  
\#define HOJAIGA\_DESKTOP\_INTERACTION\_ENGINE\_HPP

\#include \<string\>  
\#include \<memory\>  
\#include \<vector\>  
\#include \<cstdint\>

namespace Hojaiga::AOS::DIM {

using WindowHandle \= uint64\_t;

enum class WindowType {  
    MAIN\_WINDOW,  
    CHILD\_WINDOW,  
    MODAL\_WINDOW,  
    INSTALLER\_WIZARD,  
    MESSAGE\_BOX,  
    FILE\_PICKER,  
    FOLDER\_PICKER,  
    UAC\_PROMPT,  
    UNKNOWN  
};

struct WindowRect {  
    int32\_t left;  
    int32\_t top;  
    int32\_t right;  
    int32\_t bottom;  
};

struct WindowNode {  
    WindowHandle handle;  
    WindowHandle parent\_handle;  
    WindowHandle owner\_handle;  
    uint32\_t process\_id;  
    std::string title;  
    std::string class\_name;  
    WindowType type;  
    WindowRect bounds;  
    bool is\_visible;  
    bool has\_focus;  
    std::vector\<std::shared\_ptr\<WindowNode\>\> children;  
};

class DesktopInteractionEngine {  
public:  
    DesktopInteractionEngine();  
    \~DesktopInteractionEngine();

    bool Initialize(const std::string& config\_path);  
    bool StartEventMonitoring();  
    bool StopEventMonitoring();

    std::shared\_ptr\<WindowNode\> BuildDesktopWindowTree();  
    bool SetFocusToWindow(WindowHandle handle);  
    bool RestorePreviousFocus();

    bool ExecuteOCROnWindow(WindowHandle handle, std::string& extracted\_text);  
    bool ExecuteVisionMatch(WindowHandle handle, const std::string& template\_path, int32\_t& out\_x, int32\_t& out\_y);

    bool InterceptAndResolveFilePicker(const std::string& target\_path, bool is\_save\_dialog);

private:  
    class Impl;  
    std::unique\_ptr\<Impl\> pimpl\_;  
};

} // namespace Hojaiga::AOS::DIM

\#endif // HOJAIGA\_DESKTOP\_INTERACTION\_ENGINE\_HPP

## **Performance & System Limits**

* **Window Event Interception Latency**: \<10 milliseconds from OS hook event generation to DIM registration.  
* **Window Classification Speed**: \<15 milliseconds per newly detected window handle.  
* **OCR Text Extraction Latency**: \<250 milliseconds for full standard dialog frame capture.  
* **Computer Vision Match Speed**: \<100 milliseconds across 1920×1080 screen area.  
* **Focus Restoration Latency**: \<20 milliseconds post-dialog closure.  
* **Maximum RAM Allocation**: Hard memory ceiling set to 512 MB.  
* **Maximum CPU Utilization**: Maximum sustained CPU limit of 5% of a single core during active desktop event polling.

## **Thread Model & Event Loop**

The DIM daemon operates a multi-threaded architecture:

* **Thread 1 (Main OS Hook Thread)**: Executes the native platform event pump (`GetMessage`/`DispatchMessage` on Windows, `XCB` event loop on Linux).  
* **Thread 2 (Window Tree & Focus Manager Thread)**: Processes window tree updates, Z-order tracking, and focus stack locking.  
* **Thread 3 (OCR & Vision Worker Thread Pool)**: Asynchronous thread pool (4 worker threads) executing image pre-processing, Tesseract parsing, and OpenCV matching.  
* **Thread 4 (IPC Socket Communication Thread)**: Non-blocking socket listener dispatching event payloads to the Workflow Scheduler.

# **FUTURE COMPATIBILITY**

The Desktop Interaction Manager is architected for seamless future OS expansion:

1. **Cross-Platform OS Abstraction Layer**: Pluggable driver architecture allowing runtime swapping from Win32/UIA drivers to Wayland/X11 (`AT-SPI2`) on Linux and Accessibility API (`AXUIElement`) on macOS.  
2. **Virtual Desktop & Remote Desktop Support**: Direct compatibility with Citrix virtualized channels, Remote Desktop Protocol (RDP) screen buffers, and VMware/VirtualBox client windows.  
3. **High-DPI Dynamic Monitor Migration**: Real-time recalculation of absolute bounding coordinates as windows cross between 100% scaling and 200% high-DPI displays using `PerMonitorV2` awareness.  
4. **AI-Assisted Vision Models**: Future integration with lightweight local neural vision models (e.g., YOLO-UI, OmniParser) for semantic control classification on custom non-standard GUI frameworks.  
5. **Multi-Touch & Spatial Input**: Support for touch gesture injection, digital stylus inputs, and virtual canvas manipulation.

