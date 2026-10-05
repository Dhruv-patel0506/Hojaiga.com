---
name: hojaiga-lifecycle-checkpoints
description: The A-H task lifecycle checkpoint chain, with the honest status of each checkpoint (VERIFIED by a named test / PARTIAL / GAP) and what a run records per checkpoint.
---

# Skill 14 — Task lifecycle: checkpoint chain and its honest status

Code: `task_intake.py` (Phase A) · `task_lifecycle.py` (the chain: `run_lifecycle`, `Chain`, `gate_plans`) ·
`loop_first.py` + `desktop_grounding.py` (B-G, per goal) · `organ_48_app_behavior_model.py` (risk classes, gate, queue, audit, day
report) · product hook: `organ_01_crewai_engine.execute_task` (intake first, then the loop-first pass with the D3 gate; the
checkpoint chain is appended to the evidence the crew receives).

Every run returns `checkpoints: [{id, name, status: PASS|SKIPPED|BLOCKED|ESCALATED|FAIL, evidence}]`. SKIPPED/BLOCKED are
first-class: a checkpoint that did not run says so. Statuses below are as of the 2026-10-04 audit; "VERIFIED" names the test that
exercises it on this machine.

| ID | Checkpoint | Status | Evidence / gap |
|---|---|---|---|
| A1 | sanitize secrets | VERIFIED (LC1) | keys / passwords / cards (Luhn) / JWT / URL-token redacted before any plan or log |
| A1 | split into tickets | VERIFIED (LC1) | a numbered/bulleted list or blank-line blocks = tickets; one line (`;`/`then`) = one task; a failing ticket never stalls the rest (LC1) |
| A1 | clarify | VERIFIED (LC1) | ONE question only when nothing actionable is named; otherwise assumptions are recorded |
| A2 | route web / desktop / mixed / system | VERIFIED (LC1) for classification; **PARTIAL** for web execution | a web ticket is *routed* to the CDP path (existing crew flow); this module does not drive the browser |
| A2 | app resolved by process + largest window, not title | VERIFIED (find_window ranking, G1/LF2; **VS Code groundable**) | the hardcoded title skips (`visual studio`, `antigravity`, ` - editor`) are gone: `find_window` now skips only the agent's OWN host (this process and its ancestors, `_agent_host_pids`) and matches any distinctive word of the hint ('visual studio code' -> process `code`). Proven live: VS Code launched hidden, found, grounded (7 UIA elements; Electron UIA is shallow, OCR takes over when a target is missing) |
| A3 | template first, LLM last | VERIFIED (A3X) | `task_lifecycle._template_first`: a single-app ticket made only of type/save steps, with the template's `{path}`/`{text}` stated in the task, runs the stored template (organ_48 TemplateRunner) before any free-form plan; the chain records PASS/SKIPPED/FAIL and why. A failed template falls back to the verified loop |
| A3 | declare impossible at intake | VERIFIED (LC1) | physical-world, gestures/voice, CAPTCHA, moving money, typing passwords/cards |
| B1 | find existing window | VERIFIED (LF2, ANY1) | |
| B2 | launch (Start-menu catalog, hidden, single instance) | VERIFIED (LF2, E2E, B2X) | `universal_scan.launch_target_status` checks a path-style target on disk before launching; a missing exe is reported (`launch_note`) and neither retried nor replaced by another app. Packaged/ProgID targets report `exists=None` (unknown, not 'yes') |
| B3 | window readiness | VERIFIED (ANY1, OFF1) | progress-aware wait (splash chain), parked/minimized windows grounded |
| C1 | tiered scan ladder, honest skips | VERIFIED (G1, OFF1) | blank/unpainted captures are now reported skipped with a reason (`ocr:capture(<why>)`) |
| C2 | popup sweep + ladder | VERIFIED (PP1, UP1, PL1, PL2, **ES1**) | classic dialogs read natively (3-6 ms); own Save-As is not dismissed; a dialog that needs a human is saved as a real PNG (`data/escalations/`, listed in the run result `escalation_shots` and the C2 chain row) and left open - ES1 |
| C3 | pre/post snapshot | VERIFIED (V1, C3X) | structure + pixels + UIA names + **mode indicators** (`name|selected`, `name|expanded`, read in the same bulk pass); a mode-only change counts as a change, and `mode_on` is an expectation type |
| D1 | trust order learned > catalog > archetype | VERIFIED (W8) | **PARTIAL**: mode-change preconditions exist in organ_48's TemplateRunner, not in the free-form loop |
| D2 | effector choice + recorded | VERIFIED | per-step method is in the trace and organ_48 `bm_effectors` |
| D3 | risk gate | VERIFIED (LC1, LC2) | E2 goals (delete/send/pay/close/don't-save...) are queued for a human, the rest runs; `Don't Save` is also a destructive cue in the loop |
| E1/E2 | virtual input only, popup re-check | VERIFIED (M1, DR1, CN1, TY1, LF2) | the pointer checks gate on external movement: a human's hand can fail M1/LF2 (reported, not a defect) |
| F1 | verdict from the right postcondition | VERIFIED (DE1, task bench) | goals derive their own postcondition: save-as needs the file AND its real format (PNG signature), `expect X` is an assertion, a typed literal must be in the control |
| F2 | sub-goals in order, bounded retries | VERIFIED (LF2, LC2) | |
| G1 | recovery ladder | VERIFIED (bench: Paint save, Excel type) | an opened-but-not-done control is not re-pressed; a text already typed is not typed again |
| G2 | crash relaunch / login / vanished element | VERIFIED live (G2L) for the vanished window | a window that disappears mid-run is relaunched ONCE and the same goal resumes (earlier goals stay done); a second loss fails with evidence (`crashed: true`). Login gates remain the web path |
| G3 | escalate with evidence | VERIFIED (LC2) | |
| H1 | pathway logging | VERIFIED (D2, PL2) for popups | |
| H2 | promote / erode knowledge | VERIFIED | **Known**: a learned shortcut earned from weak evidence once poisoned a step ("type 42" -> Ctrl+N); typing goals now ignore learned shortcuts and carry `text_contains` |
| H3 | task checkpoint / resume | VERIFIED (CP1) | |
| H4 | honest report | VERIFIED (LC1/LC2, DAY1) | per-checkpoint chain + organ_48 day report |

## Application ladder (how far each level goes today)
| Level | App | What is verified | Open |
|---|---|---|---|
| 1 Win32 | Notepad, Calculator | write+save with file truth, 25x4=100, two-app task | restored unsaved tabs can contain old text |
| 2 UWP/WinUI | Settings | open a page, assert text | |
| 3 WinUI menus | Paint | Save as PNG (File > Save as > PNG picture > file dialog; signature verified), tools | WinUI ignores posted mouse (drawing is reported INEFFECTIVE) |
| 4 Office | Excel | start screen, blank workbook, type into A1 (verified by reading the cell back) | **Save to a given path through the backstage is not reliable** (name box rejects the drive colon, pane navigation) |
| 5 CEF/Electron | WhatsApp, Steam | window discovery, OCR read of the parked window | no action rung; GPU-composited content is blank while hidden (reported) |

## Rules this chain enforces
1. No checkpoint is PASS without evidence; SKIPPED/BLOCKED are reported.
2. Irreversible steps (E2) are queued for a human, never "tried".
3. A goal's postcondition comes from its own words (file + format, typed literal, `expect`), not from "the UI changed".
4. Nothing app-specific lives in code: apps come from the Start-menu catalog, formats from file signatures, risk from word cues.
