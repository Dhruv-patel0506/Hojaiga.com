# Skill 03 — The Closed Autonomy Loop (`desktop_grounding.py`)

This is the heart. One `DesktopAutonomyLoop.run(goals, app_name)` call loops per goal:
**perceive → decide → act → verify → recover → checkpoint → learn.**

## Perception ladder — cost-ordered, cheapest real signal first
There is no "see the screen" magic. Four physical mechanisms, tried in this order:

| Tier | Mechanism | Cost | What it gives | Useless for |
|---|---|---|---|---|
| 1 | **UIA** (COM accessibility tree) | 5–40 ms | real semantics: `Button 'Apply' @ rect` | Blender viewport, GL canvas, custom-drawn toolbars |
| 2 | **Win32** `EnumChildWindows`+`GetWindowRect` | 2–15 ms | shallow but universal window tree | text inside a canvas |
| 3 | **OCR** `PrintWindow→PNG→Tesseract` | 300–1200 ms | words+bboxes as pseudo-elements, conf ~0.5 | — (this is where pixels first enter) |
| 4 | **Vision** local OmniParser (YOLO detect + Florence-2 caption) | 1.5–4 s CPU | understands a canvas; icon→action labels | — (last resort) |

**Escalation rule (already coded in `ground()`):** past tier 2 ONLY when the caller is
hunting a specific `target_text` AND structural tiers found no match ("2 structural misses").
`max_tier`: 1=uia, 2=+win32 (default, ms-fast), 3=+ocr, 4=+vision.
Every tier reports into `ladder_report = {tiers_ran, tiers_skipped, escalated}` — a tier
whose engine is missing MUST land in `tiers_skipped`, never in `tiers_ran`.

## Readiness backoff (the "still booting" fix)
`_wait_for_ready()` runs at the top of `run()`: bounded growing-wait poll
(`READY_TIMEOUT_S=10`, backoff `0.35→1.5 s`) until hwnd + ≥1 element appear. Heavy apps
(Blender/Office/Electron) show a splash and expose controls seconds later — this prevents
misreading "booting" as "empty/wrong state". A genuinely dead app escalates to HITL
(`awaiting_human=True`) instead of flailing.

## Verification — three snapshots surround every step
1. **Before:** freeze `title + sorted(element ids) → md5` (structural sig) AND a 64×64
   thumbnail hash of the window rect (visual sig). The thumbnail is what catches Blender
   working — the UIA tree never changes when you extrude a face, only pixels do.
2. **Act:** cheapest effective input wins — `UIA Invoke() → PostMessage(WM_LBUTTON) → SendInput`.
   Order matters: Invoke/PostMessage work **under a pointer clip**; SendInput does not.
3. **After:** re-snapshot, diff vs the step's postcondition
   (`title_contains`, `element_appeared/disappeared`, `file_exists`, `region_changed`;
   default = "signature moved").

Verdicts (exactly three):
| Verdict | Meaning | Loop action |
|---|---|---|
| PASS | diff matches postcondition | checkpoint JSON, next step |
| NO_CHANGE | app never saw the input | climb recovery ladder one rung; never repeat a rung |
| WRONG_STATE | UI changed but wrong shape (dialog/menu in way) | popup subsystem first → re-ground → replan |

## Checkpoint / resume
After every PASS a resumable checkpoint is written (`CHECKPOINT_DIR`, per-session).
Resume = relaunch app → replay learned recipe → re-ground (fingerprints re-validate bboxes).
This is what makes multi-hour runs (the 3D-chair case) survivable.

## Recipe distillation (the learn step)
`distill_recipe()` on success ingests a reusable **verified** recipe to organ_04.
Guard: needs ≥2 verified PASS steps — a 1-step trace is refused. First run in Blender costs
100 ladder passes + 4 s vision calls; the fifth costs near-zero because the compiler is
handed a verified prior. That feedback line into the compiler is the whole scalability story.

## The high-level entry tool
`organ_01.operate_desktop_tool(app_name, goals, allow_destructive, agent_label)`:
- auto-launches the app if its window isn't up (organ_40 `resolve_and_launch`),
- spawns a per-agent virtual cursor (`for_agent(agent_label)`) so parallel agents each own an arrow,
- runs `loop.run(...)`, distills a recipe on success, returns a per-step PASS/NO_CHANGE/WRONG_STATE trace.
This is the "just do it" tool the researcher/auditor agents are steered to prefer.
