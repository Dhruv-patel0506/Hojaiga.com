# Skill 07 — Testing & Honest Reporting (`run_system_intelligence_tests.py`)

## The suite
`All codes/core_organs/run_system_intelligence_tests.py` runs named tests grouped by
subsystem, prints `[PASS]/[FAIL]/[ENV-BLOCKED]  <id>  <ms>`, then a **reconciled ranking**
(70% pass-rate, 30% latency). Full log → `system_intelligence_results.txt`.

Run it:
```powershell
$env:PYTHONPATH="D:\new_automation;D:\new_automation\All codes"
cd "D:\new_automation\All codes\core_organs"
D:\new_automation\hojaiga_env\Scripts\python.exe -X utf8 run_system_intelligence_tests.py 2>&1 | Out-File -Encoding utf8 D:\new_automation\suite.log; Get-Content D:\new_automation\suite.log -Tail 45
```

## Test id conventions (match these when adding)
`B*` brain · `P*` popup · `S*` scanner · `M*` mouse · `L*` launcher · `R*` memory ·
`K*` knowledge · `D*` database · `G*` grounding · `V*` verify · `SK*` skill/recipe ·
`CP*` checkpoint · `W*` app-intelligence · `H*` import health.

## TestOutcome contract (every test returns this)
```python
TestOutcome(
    passed=<bool>,
    evidence="<human-readable proof with real numbers>",   # REQUIRED: measured, not claimed
    metrics={"key": value, ...},
)
```
Register in `GROUP_LABELS` and in the `plan` list (id, group, func). Add the module to
`ORGAN_IMPORTS` so H1 import-health covers it.

## The honesty test (G1) — the most important pattern
A capability may only appear in `tiers_ran` if its engine is actually present:
```python
if not HAS_TORCH and "vision" in tiers_ran: integrity=False  # "claimed vision without torch"
if not HAS_PYTESSERACT and "ocr" in tiers_ran: integrity=False
```
**Never fake a tier.** A skipped tier must show up in `tiers_skipped`. This test exists
because faking perception is the single worst failure mode for autonomy.

## ENV-BLOCKED is a first-class result
When the OS/environment refuses (e.g. a foreign app holds `ClipCursor` so `SetCursorPos`
fails), report `[ENV-BLOCKED] (NOT a code defect)` and prove the code path by an
independent route (e.g. draw the overlay sprite + `list_cursors()` instead of moving the OS
pointer). Do not mark it PASS, do not mark it FAIL — mark it blocked and explain.

## Dry-run / no-side-effect testing
- Keyboard intents: monkey-patch `mgr._execute_key_intent` to capture, not fire (PL1).
- Popup live mitigation: assert on the *decision* (`action`, timing), not on real clicks.
- Destructive/launcher actions: run in DRY-RUN mode; assert the decision, not the effect.

## Definition of done for any change
1. `py_compile` every touched file → `COMPILE=0`.
2. Full suite ≥ prior pass count, **0 new failures**.
3. New capability ships with a new test whose `evidence` contains a measured number.
4. Paste the ranking table + the new test's evidence line into your report.
5. Clean up scratch logs/probe files.

## Current real baseline (do not overclaim beyond this)
23/24 PASS, 0 code failures; the lone ENV-BLOCKED is M1 (OS pointer clip by "Clicky").
Popup group 92.1 (4/4). G1 now grounds notepad to 312 elements via `['uia','ocr','vision']`
with `skipped=[]` — but CPU vision is slow (~2 min in-test); that's real, not faked.
**Nothing has completed a fully unattended end-to-end task yet** — that remains the goal.
