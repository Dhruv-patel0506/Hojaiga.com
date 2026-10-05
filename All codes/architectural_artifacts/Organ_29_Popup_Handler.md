# Organ 29 — Popup Handler (Desktop Interaction Manager)

**Version:** 1.0
**Authority:** Constitution → LawBook → Diagrams → Legacy Guide → PolicyManual → MasterArchitectureBlueprint → Organ Specification → Popup_Handler_Desktop_Interaction_Manager.md

---

## Metadata

| Field | Value |
|---|---|
| Organ ID | 29 |
| Organ Name | Popup Handler / Desktop Interaction Manager (DIM) |
| Implementation | `organ_29_popup_handler.py` |
| Tests | `test_organ_29_popup_handler.py` |
| Depends On (sockets only) | Workflow Scheduler (pause/resume), Brain (decisions only, via CNS) |
| GPU Usage | None (reserved for Brain LLM) |
| CPU Usage | Event-poll ≤5% single core; OCR/Vision workers async |

## Purpose

Owns 100% of non-browser desktop window interaction: discovery, classification, unlimited-depth hierarchy tracking, modal/focus management, installer wizard automation, native file pickers, and security-prompt isolation. Never performs reasoning; never calls another organ directly.

## Responsibilities

Window discovery • popup/child detection • unlimited hierarchy tracking • modal stack management • installer automation (MSI/Inno/NSIS/InstallShield/WiX) • native file/folder picker resolution • security-prompt escalation • notification capture • 6-layer automation fallback (Accessibility → Framework Native → OCR → Vision → Pixel Geometry → Human Escalation) • focus capture/restore • workflow pause/resume signaling • deadlock prevention.

## Internal Philosophy

Pluggable OS backend (`WindowBackend`) keeps the organ platform-agnostic (Win32/UIA today; AT-SPI2/AXUIElement future). Every fallback layer degrades gracefully to a no-op when the optional driver (pytesseract, opencv, pywinauto) is absent, so the organ imports and runs on any host.

## Internal Modules

| Module | Purpose | Owned State | Failure Mode | Recovery |
|---|---|---|---|---|
| `WindowClassifier` | class/title → `WindowType` | none | unknown title | falls back to `UNKNOWN`/`CHILD_WINDOW` |
| `WindowTreeManager` | unlimited-depth tree, dedup | `_by_handle`, `_roots` | stale handle | `find()` returns `None` |
| `FocusManager` | focus/modal stack | `FocusState` | backend refuses focus | returns `False`, caller retries |
| `OCREngine` | text extraction | none | driver missing | empty `OCRResult` |
| `VisionEngine` | template match | none | driver missing | `VisionMatch(found=False)` |
| `SecurityPolicyGuard` | UAC/auth gating | signed tokens set | unsigned approval | escalates to human, blocks action |
| `InstallerWizardEngine` | wizard page automation | none | unknown page | defaults to `welcome` |
| `NativeFilePickerEngine` | file/folder dialog resolution | directory memory | dialog not found | returns `False` |
| `DeadlockGuard` | timeout/loop-cap waiting | none | predicate never true | returns `False` after cap |

## Folder Structure

```
organ_29_popup_handler/
├── organ_29_popup_handler.py     # single importable module (this organ)
├── test_organ_29_popup_handler.py
└── Organ_29_Popup_Handler.md
```

## Public Interfaces

`DesktopInteractionManager`:

| Method | Input | Output | Errors | Timeout | Version |
|---|---|---|---|---|---|
| `start_event_monitoring()` | — | `bool` | — | — | v1.0 |
| `refresh()` | — | `list[WindowNode]` | — | — | v1.0 |
| `intercept_popup(node, approval_token)` | WindowNode, token? | `bool` | security-block | DeadlockGuard cap | v1.0 |
| `resolve_file_picker(path, is_save, multi, files)` | str, bool, bool, list? | `bool` | not found | 2000ms | v1.0 |
| `execute_ocr_on_window(handle)` | int | `OCRResult` | driver missing | 2000ms | v1.0 |
| `execute_vision_match(handle, template)` | int, str | `VisionMatch` | driver missing | 2000ms | v1.0 |
| `set_focus_to_window(handle)` / `restore_previous_focus()` | int | `bool` | backend refusal | 200ms | v1.0 |

## Socket Definitions (26, per spec table)

`window_discovery, popup, dialog, child_window, modal_window, installer, ocr, vision, accessibility, focus, window_tree, window_event, desktop_interaction, workflow_pause, workflow_resume, security_prompt, file_picker, directory_navigation, file_search, file_validation, file_selection, multi_selection, folder_selection, explorer, upload, download`

Each: bi-directional/request-reply/push-only per role, System/Admin token auth, documented timeout & retry (see implementation `SocketRegistry`), version `v1.0`.

## Pipeline Definitions

| Pipeline | Source | Destination | Payload | Recovery |
|---|---|---|---|---|
| Popup Interception | OS Event Hook | Workflow Scheduler | pause signal + window snapshot | retry ×3 |
| Installer Automation | InstallerWizardEngine | Backend | page action | skip-and-log on unknown page |
| File Picker Resolution | NFPE | Backend / Playwright | path/filenames | fallback NFPE ↔ Playwright |
| Security Escalation | SecurityPolicyGuard | Human Operator (security_prompt socket) | prompt type | block until signed token |

## Data Contracts

`WindowNode`, `WindowRect`, `FocusState`, `SocketMessage`, `SocketResponse`, `OCRResult`, `VisionMatch` — all `@dataclass`, JSON-serializable via `asdict`.

## State Management

`WindowTreeManager` holds the authoritative tree; `FocusManager` holds a stack-based modal/focus state. Both rebuilt from `backend.enumerate_windows()` each `refresh()` — no cross-call mutation drift.

## Events

`EVENT_WINDOW_CREATED/CLOSED/HIDDEN/RESTORED/ACTIVATED/MINIMIZED/MAXIMIZED/TITLE_CHANGED/FOCUS_CHANGED/OWNER_CHANGED/POPUP_CREATED/DIALOG_CREATED/WIZARD_CREATED/TOOLTIP_CREATED/CONTEXT_MENU_OPENED` — modeled as `WindowEvent` enum, dispatched over `window_event` socket (push-only, 100ms, retry 5).

## Thread Safety

Implementation is single-process `asyncio`; all socket I/O is coroutine-based with `asyncio.wait_for` timeout+retry. No shared mutable state crosses threads — a real OS-hook thread (Win32 `SetWinEventHook`) would push events into the asyncio loop via `call_soon_threadsafe` in a production backend.

## Resource Management / Performance Targets

RAM ceiling 512MB (spec). CPU ≤5% single core polling. OCR ≤250ms, Vision ≤100ms per spec — enforced by optional-driver design so absence never blocks the organ.

## Hardware Considerations

GPU (RTX 3050) is reserved exclusively for Brain (Qwen3-8B); DIM performs CPU-only OCR/vision. SSD used for runtime config; HDD unused by this organ (no persistent datasets).

## Security

`SecurityPolicyGuard` hard-blocks UAC/Authentication/Security-prompt auto-approval unless a signed token is present — enforced in code (`SECURITY_SENSITIVE_TYPES`), matching PolicyManual Chapter 14.

## Failure Recovery

`DeadlockGuard` caps wait time and loop iterations to prevent infinite blocking (LawBook Foundational Law 8, Universal Law 8). Socket layer retries per documented count then reports `status="error"` rather than raising.

## Versioning

Module version `v1.0`; every socket independently versioned `v1.0` for future non-breaking evolution (LawBook Universal Law 12).

## Testing

30 unit tests in `test_organ_29_popup_handler.py` covering classifier, tree (unlimited depth + dedup), focus stack, security guard, installer page detection/advance, NFPE resolve + Playwright fallback, deadlock guard, and socket round-trip/timeout behavior. All passing.

## Extension Points

Swap `WindowBackend` for Linux (`AT-SPI2`) or macOS (`AXUIElement`) drivers without touching orchestration logic. Add new `WindowType`/classifier rules without breaking existing contracts.

## Future Roadmap

Real OS hook thread integration; YOLO-UI/OmniParser vision model; multi-monitor DPI coordinate mapper; multi-touch input injection.

---

## Pre-Implementation Design Diagram

```
                        DESKTOP DISPLAY (Multi-monitor / DPI)
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │  DESKTOP INTERACTION MANAGER    │
                    │              (DIM)              │
                    │ Window Manager Subsystem        │
                    │ Native File Picker Engine (NFPE) │
                    │ Desktop Interaction Engine (DIE) │
                    └────────────────┬─────────────────┘
                                     ▼
                    WORKFLOW SCHEDULER (Pause→Resolve→Resume)
                          [via Socket, never direct call]
```

## Actual Code Topology Diagram (post-implementation)

```
DesktopInteractionManager (facade)
 ├── SocketRegistry (26 sockets)
 ├── WindowBackend → NullWindowBackend | Win32WindowBackend
 ├── WindowClassifier
 ├── WindowTreeManager
 ├── FocusManager
 ├── OCREngine / VisionEngine (optional drivers)
 ├── SecurityPolicyGuard
 ├── InstallerWizardEngine
 ├── NativeFilePickerEngine
 └── DeadlockGuard

intercept_popup(): detect → pause socket → read (accessibility→OCR→escalate)
  → security check → modal push → installer/NFPE/click → deadlock-guarded
  close verification → modal pop → focus restore → resume socket
```

## Sequence Diagram — Popup Interception

```
Scheduler        DIM              Backend        SecurityGuard
   │  running     │                  │                  │
   │──run step───▶│                  │                  │
   │              │──enumerate─────▶│                  │
   │◀─pause───────│                  │                  │
   │              │──classify/read──▶│                  │
   │              │──check──────────────────────────────▶│
   │              │◀─approved/blocked────────────────────│
   │              │──act (click/installer/NFPE)─────────▶│
   │              │──verify closure (DeadlockGuard)──────▶│
   │              │──restore focus──▶│                  │
   │◀─resume──────│                  │                  │
```

## State Diagram — Window Lifecycle

```
[Created] → [Discovered] → [Classified] → {Modal? → Focus-Locked}
   → [Action Executed] → [Closure Verified] → [Focus Restored] → [Idle]
                     └─(timeout)→ [Human Escalation]
```

## Implementation Checklist

- [x] All 15 required sections present
- [x] 26 sockets documented & implemented
- [x] Pipelines documented
- [x] Diagrams: pre-implementation, post-implementation, sequence, state
- [x] Public interfaces defined with versioned contract
- [x] Single importable `.py` file, syntax-validated
- [x] 30 passing unit tests, no placeholders/TODOs
