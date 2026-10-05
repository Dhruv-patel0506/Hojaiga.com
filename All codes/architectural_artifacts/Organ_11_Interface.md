# Organ 11 — Interface Specification Document

**Version:** 1.0.0
**Authority Order:** Constitution → Law Book → Upper/Inner Surface Diagrams → Legacy Code Migration Guide (reference only) → Policy Manual → Master Architecture Blueprint → Organ Specification

**Governing Law References:** Universal Law 3 (Separation of Responsibility), Universal Law 12 (Human Approval Boundaries), Constitutional Principle 4 (Stewardship and Controlled Governance), Policy Manual Chapter 1, 8.

---

## 1. Overview

The Interface Organ is the primary human-system interaction layer of Hojaiga. It ingests commands (GUI, CLI), renders live telemetry, enforces human-in-the-loop governance approval, and manages tray/notification presence. It owns **zero automation logic, model inference, or private state databases** — it is strictly an event producer/renderer communicating with the rest of the system exclusively through the `hojaiga_interface` socket.

## 2. Implementation Summary

A single importable module, `organ_11_interface.py`, implements every module defined in Section 5 of the specification, consolidated for single-file distribution per delivery instructions:

| Spec Module | Implementation |
|---|---|
| `interface_core` / `interface_kernel.py` | `InterfaceKernel` |
| `state_bridge.py` | `StateBridge` (in-memory SQLite) |
| `gui_renderer` / `main_window.py` | `GUIBridge` (PySide6, soft-imported) |
| `cli_terminal` / `terminal_shell.py` | `CLITerminalShell` |
| `tray_manager` / `tray_icon.py` | `TrayManager` (pystray, soft-imported) |
| `governance_dialogs` / `approval_modal.py` | `GovernanceDialogManager` |
| `telemetry_widget` / `telemetry_view.py` | `TelemetryUpdatePayload` + `GUIBridge.update_organ_health_tree` |
| `notification_engine` / `notifications.py` | `NotificationEngine` (plyer, soft-imported) |
| `sockets/ipc_client.py` | `IPCClient`, `IPCServer`, frame codec |

Optional dependencies (`PySide6`, `pystray`, `Pillow`, `plyer`, `pywin32`) are all soft-imported. Their absence degrades the organ gracefully (e.g. GUI unavailable → CLI mode; tray unavailable → headless log-only) rather than crashing, honoring Universal Law 8 (Failure Transparency and Recovery).

## 3. Public Interface (Section 7 realized)

All RPCs are implemented as `OpCode`-tagged frames over the `hojaiga_interface` socket using the exact wire format mandated in Section 9: `[4-byte length | 2-byte op_code | JSON payload]`, capped at 16 MB.

| RPC | OpCode | Direction |
|---|---|---|
| `DisplayApprovalPrompt` | `DISPLAY_APPROVAL_PROMPT` → `APPROVAL_VERDICT` | CNS → Interface → CNS |
| `UpdateTelemetryDisplay` | `UPDATE_TELEMETRY_DISPLAY` → `TELEMETRY_ACK` | CNS → Interface |
| `SendNotification` | `SEND_NOTIFICATION` → `NOTIFICATION_ACK` | CNS → Interface |
| `RenderTaskProgress` | `RENDER_TASK_PROGRESS` → `PROGRESS_ACK` | CNS → Interface |
| `GetActiveUserInputs` | `GET_ACTIVE_USER_INPUTS` → `USER_INPUT_PAYLOAD` | CNS → Interface |
| `EVENT_USER_GOAL_SUBMITTED` | `USER_GOAL_SUBMITTED` | Interface → CNS |
| `EVENT_HUMAN_APPROVAL_VERDICT` | `APPROVAL_VERDICT` | Interface → CNS |
| `EVENT_UI_MODE_CHANGED` | `UI_MODE_CHANGED` | Interface → CNS |
| `EVENT_UI_CLOSED` | `UI_CLOSED` | Interface → CNS |

### Transport (Section 9)

- **Windows target:** `\\.\pipe\hojaiga_interface`, implemented via `pywin32` (`win32pipe`/`win32file`) when available.
- **Portable fallback** (pywin32 absent, or non-Windows host): Unix domain socket at `/tmp/hojaiga_interface.sock`, or TCP loopback `127.0.0.1:47611` as a last resort. The frame protocol is byte-identical across all three transports so CNS-side code never branches on transport.

## 4. CLI

`python organ_11_interface.py --mode cli` launches `CLITerminalShell`:

- `help` — list commands.
- `status` — dumps `InterfaceKernel.snapshot_status()` (UI mode, active prompt count, transport, latest telemetry).
- `goal <text>` or any free-text line — submits a sanitized `EVENT_USER_GOAL_SUBMITTED`.
- `exit` / `quit` — emits `EVENT_UI_CLOSED` and shuts the kernel down.
- Governance approval prompts render as blocking, timeout-bound y/N prompts (`cli_bridge_prompt_approval`) when no GUI is attached.

## 5. GUI

`python organ_11_interface.py --mode gui` launches `GUIBridge`, a PySide6 `QMainWindow` with:

- Organ health tree (`QTreeWidget`), updated via `update_organ_health_tree` and marshalled onto the Qt main thread through `Signal`/slot (never touched directly from the IPC thread — Section 19 compliance).
- Live task progress bar.
- Goal submission field wired to `InterfaceKernel.submit_user_goal`.
- Modal `QDialog` governance approval popup (`_on_modal_main_thread`) with Approve/Deny buttons; auto-resolves to `TIMED_OUT` → `DENIED`-equivalent handling via the shared `GovernanceDialogManager` timer if the operator does not respond within `timeout_ms`.

`os.environ["QT_QUICK_BACKEND"] = "software"` and `QT_OPENGL = "software"` are forced at module import time, **before** any Qt import, guaranteeing zero VRAM allocation (Section 21/22/46).

## 6. API (in-process)

For processes that embed this organ directly (rather than over IPC), `InterfaceKernel` exposes:

```python
from organ_11_interface import InterfaceKernel, ApprovalPromptRequest, RiskLevel

kernel = InterfaceKernel()
kernel.start()
kernel.submit_user_goal("Summarize today's browser automation runs", source="CLI")
kernel.snapshot_status()
kernel.stop()
```

## 7. Notifications

`NotificationEngine` wraps `plyer.notification` when installed, otherwise logs a structured `[NOTIFICATION]` line — never raises, never blocks the dispatch loop.

## 8. Reports

Structured JSON audit records are emitted via `audit_log()` (Policy Manual Chapter 8 required fields: timestamp, component, event, plus contextual fields such as `prompt_id`, `goal_id`, `mode`). Every governance decision, UI mode transition, goal submission, and IPC listener bind event is recorded, append-only, to stdout for downstream log aggregation into External HDD history archives (Section 29).

## 9. Progress

`ProgressUpdatePayload` (`task_id`, `step_name`, `percent_complete`, `status`) received via `RENDER_TASK_PROGRESS` is cached in `StateBridge` under `progress:<task_id>` and reflected in the GUI progress bar when a dashboard is attached.

## 10. Status

UI render states exactly match Section 13:

`HEADLESS_TRAY` → `DASHBOARD_ACTIVE` → `MODAL_AWAITING_HUMAN` → `CLI_MODE`, transitions driven exclusively by `InterfaceKernel.set_ui_mode()`, which always emits `EVENT_UI_MODE_CHANGED` and restores `previous_mode` after a modal resolves.

## 11. Error Messages

- **Validation errors** (`ValidationError`): empty goal, goal > 4096 chars, or a goal that sanitizes to nothing — surfaced to the operator as a `WARNING`-severity notification and never forwarded to CNS (Section 32).
- **Protocol errors** (`FrameProtocolError`): malformed header or payload > 16 MB — connection is dropped and logged; upstream frames are never partially processed.
- **Governance timeout**: unresolved approval past `timeout_ms` auto-resolves to `TIMED_OUT` (Section 31), which the CNS-side security organ is expected to treat as a denial for safety.
- **Unsupported op_code**: replied to with `GENERIC_ACK {"ok": false, "error": ...}` rather than silently dropped, preserving Universal Law 1 (Accountability and Traceability).

## 12. Data Contracts

Implemented as `@dataclass` types with `from_json`/`to_json` matching Section 15's JSON Schemas exactly: `ApprovalPromptRequest`, `HumanApprovalResponse`, plus the operational payloads `TelemetryUpdatePayload`, `NotificationPayload`, `ProgressUpdatePayload`, `UserGoalPayload`.

## 13. State Store (Section 16)

`StateBridge` implements the mandated in-memory (`:memory:`) SQLite tables `ui_session_state(key, value, updated_at)` and `active_prompts(prompt_id, task_id, risk_level, status, created_at)` exactly as specified — transient render cache only, never a system of record.

## 14. Resource Envelope Compliance

- Zero GPU/VRAM usage — enforced at import time (Section 22).
- Single Qt main-thread render loop; IPC service runs on background daemon threads only (Section 19/20).
- Standard user permissions only; no privilege escalation (Section 27).

## 15. Pre-Code Architecture Diagram (Intended Design per .md Specifications)

```
                                   ┌────────────────────────────┐
                                   │        HUMAN OPERATOR       │
                                   └──────────────┬──────────────┘
                                                   │
                       ┌───────────────────────────┼───────────────────────────┐
                       ▼                           ▼                           ▼
                 GUI (PySide6)               CLI Terminal                 System Tray
                 main_window.py              terminal_shell.py            tray_icon.py
                       │                           │                           │
                       └─────────────┬─────────────┴─────────────┬─────────────┘
                                     ▼                           ▼
                         ┌─────────────────────────────────────────────┐
                         │              interface_kernel.py             │
                         │      (Master IPC handler / Event Router)     │
                         └───────────────────┬───────────────────────────┘
                     ┌───────────────────────┼────────────────────────────┐
                     ▼                       ▼                            ▼
           governance_dialogs.py      state_bridge.py             notifications.py
           (Approval + Timeout)     (in-memory SQLite cache)      (OS toast wrapper)
                     │                       │                            │
                     └───────────────────────┼────────────────────────────┘
                                             ▼
                                   sockets/ipc_client.py
                        \\.\pipe\hojaiga_interface  (Windows Named Pipe)
                        [ 4-byte length | 2-byte op_code | JSON payload ]
                                             │
                                             ▼
                              ┌───────────────────────────┐
                              │      CNS — Organ 02        │
                              │ (Task routing, telemetry,   │
                              │  governance/security events)│
                              └──────────────┬───────────────┘
                                             │
                          ┌──────────────────┼───────────────────┐
                          ▼                  ▼                   ▼
                   Brain (Organ 01)   Security (Organ 07)   Other Organs

State transitions (Section 13):
   [*] → HEADLESS_TRAY → DASHBOARD_ACTIVE → MODAL_AWAITING_HUMAN → DASHBOARD_ACTIVE
                     ↘ CLI_MODE (mutually exclusive with GUI/tray)

HumanApprovalPipeline (Section 10):
   CNS detects restricted op → Security requests approval → Interface opens modal
   → Operator inspects → Operator decides / timeout → EVENT_HUMAN_APPROVAL_VERDICT → CNS resumes
```

## 16. Post-Code Architecture Diagram (As Actually Implemented in organ_11_interface.py)

```
 module import time:
   os.environ["QT_QUICK_BACKEND"]="software"; os.environ["QT_OPENGL"]="software"
                                             │
                                             ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                   InterfaceKernel                                   │
│                                                                                       │
│  StateBridge (:memory: sqlite)      GovernanceDialogManager     NotificationEngine   │
│    ui_session_state                    ├─ threading.Timer(timeout_ms) → TIMED_OUT    │
│    active_prompts                      └─ prompt_user_modal(request, on_verdict)     │
│                                                                                       │
│  gui_bridge: Optional[GUIBridge]      cli: Optional[CLITerminalShell]  tray: Optional │
│                                                                                       │
│  _inbound_queue (thread-safe queue.Queue) ◄── enqueued by IPCServer worker threads    │
│         │                                                                             │
│         ▼ _dispatch_loop() [KernelDispatch daemon thread]                            │
│    _handle_inbound(op_code, payload, reply):                                         │
│       DISPLAY_APPROVAL_PROMPT   → GovernanceDialogManager.prompt_user_modal          │
│       UPDATE_TELEMETRY_DISPLAY  → StateBridge.set_state + GUIBridge.update_tree      │
│       SEND_NOTIFICATION         → NotificationEngine.send                            │
│       RENDER_TASK_PROGRESS      → StateBridge.set_state(progress:<task_id>)          │
│       GET_ACTIVE_USER_INPUTS    → StateBridge.get_state(pending_user_inputs)         │
│       * (unknown)                → GENERIC_ACK {ok:false}                            │
└───────────────────────────────────────────────────────────────────────────────────┘
         ▲                                              │
         │ enqueue_inbound()                            │ broadcast() / reply()
         │                                              ▼
┌───────────────────────────────┐          ┌───────────────────────────────────────┐
│         IPCServer(Thread)      │          │      write_frame(sock, op_code, json)  │
│                                 │          │  [4B length|2B op_code|JSON payload]   │
│  Windows: win32pipe (if pywin32)│─────────▶│      \\.\pipe\hojaiga_interface        │
│  else: AF_UNIX socket           │          │      /tmp/hojaiga_interface.sock       │
│  else: TCP 127.0.0.1:47611      │          │      127.0.0.1:47611 (fallback)        │
│  accept() → per-conn thread     │          └───────────────────────────────────────┘
└───────────────────────────────┘
         ▲
         │ frames from CNS
         │
   (external CNS process / test harness connects as IPC client)

Renderer attachment (mutually exclusive top-level modes):
   run_gui()          → GUIBridge(kernel): QApplication + QMainWindow, Qt Signals
                          marshal telemetry_signal/modal_signal onto Qt main thread
   run_cli()           → CLITerminalShell(kernel): blocking input() loop
   run_headless_tray() → TrayManager(kernel): pystray icon, "Open Dashboard"/"Exit"

Validation & safety chain for outbound goals:
   raw_text → sanitize_goal() [strip, len<4096, printable-only]
            → UserGoalPayload → StateBridge.set_state
            → broadcast(USER_GOAL_SUBMITTED) → audit_log()

Governance timeout safety chain:
   prompt_user_modal() → threading.Timer(timeout_ms/1000) armed
            ├─ operator responds first → timer.cancel(), _resolve(verdict)
            └─ timer fires first        → _resolve(TIMED_OUT)  [fail-safe deny]
   _resolve() → StateBridge.resolve_prompt() → audit_log() → on_verdict(response)
            → set_ui_mode(previous_mode) once active_prompt_count()==0
```

## 17. Testing Strategy (Section 33 — implemented scope)

- `sanitize_goal`: empty string, whitespace-only, >4096 chars, control-character stripping.
- `encode_frame`/`decode_frame_header`/`read_frame`/`write_frame`: round-trip correctness, 16 MB boundary rejection.
- `GovernanceDialogManager`: timeout path resolves to `TIMED_OUT` when no operator response is injected within `timeout_ms`.
- `InterfaceKernel._handle_inbound`: each `OpCode` branch produces the documented reply op_code and payload shape; unknown op_codes produce `GENERIC_ACK {ok:false}`.
- `StateBridge`: `register_prompt` → `active_prompt_count()==1` → `resolve_prompt` → `active_prompt_count()==0`.

## 18. Versioning

Semantic Versioning: **v1.0.0** — Organ 11 Interface Specification, implemented against `organ_11_interface.py` v1.0.0.
