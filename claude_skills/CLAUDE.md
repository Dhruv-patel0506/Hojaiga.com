# CLAUDE.md — Hojaiga Automation (paste to repo root / import into context)

> Condensed always-on rules. Full detail lives in the numbered skill files `00`–`13` in
> this folder; load those per task. This file is the 60-second version.

## Mission
A **fully local, zero-paid-API** desktop + web automation agent that can operate ANY app
like a pro, verify its own actions, learn at runtime, and stop safely for a human.

## The 8 laws (never break)
1. **FREE / LOCAL / NO-API.** No OpenAI/Anthropic/AWS/cloud. LLM = local llama3 on
   `127.0.0.1:11435`. Vision = local OmniParser repo + local weights. OCR = local Tesseract.
   Only HTTP allowed is to `127.0.0.1`. No keys, no telemetry, works offline after warmup.
2. **HONESTY.** A capability that can't run must self-report `skipped`. NEVER fake a tier.
   Never quote unmeasured numbers. ENV-blocked ≠ code defect — say so and prove the path
   another way. "Done" = compiled + tested + evidence pasted.
3. **DYNAMIC, NO PER-APP HARDCODING.** Match UI *categories*, not app names. App knowledge
   lives in the runtime learning layer (organ_47 / organ_04 / DB), never in `if app == "X"`.
4. **VERIFY, DON'T BELIEVE.** Before/after snapshot diff around every action. Verdicts are
   only PASS / NO_CHANGE / WRONG_STATE. Unverified LLM guesses rank hints only; direct
   control needs a verified/learned record (conf ≥ 0.97).
5. **SAFETY / HITL.** Never auto-accept UAC, credentials, destructive-commit, payment/ToS →
   `need_human`, fire nothing. 3-strike judge rule → freeze + checkpoint. Default
   `allow_destructive=False`.
6. **BOUNDED TIME.** Every LLM/network call hard-capped (popup Tier-3 ≤ 5 s). Every poll has
   deadline + backoff cap. An unbounded wait is a bug.
7. **CHEAPEST SIGNAL FIRST.** Perception ladder UIA→Win32→OCR→vision; escalate only on 2
   structural misses. Cache every decision; reuse the browser; warm heavy models once.
8. **SUITE GATES.** Compile → run `run_system_intelligence_tests.py` → report the ranking
   honestly. New capability ships with a new named test or it doesn't ship.

## Environment (memorize)
```
python:  D:\new_automation\hojaiga_env\Scripts\python.exe   (3.13.14)
PYTHONPATH: D:\new_automation;D:\new_automation\All codes
shell: PowerShell — use ';' not '&&'; capture to .log then Get-Content; python -X utf8
services: Gatekeeper :11435 · CNS :11436 · Chrome CDP :9222 · Tesseract on PATH
pins: transformers==4.51.3 (NOT 5.x, NOT 4.44) · torch==2.14.1+cpu · easyocr lazy
```

## Where things are
- Organs: `All codes/core_organs/organ_NN_*.py` · loop: `desktop_grounding.py` ·
  cursor: `visual_cursor.py` · tests: `run_system_intelligence_tests.py` ·
  results: `system_intelligence_results.txt` · OmniParser: `D:\new_automation\OmniParser`.
- Element contract everywhere: `{id, name, role, bbox, provider_tier, confidence}`.

## Before you add any dependency, answer
free-licence? · fully-local-no-key? · cp313 wheel exists? · can't already use an installed
lib? · importable lazily? — if any "no/unknown", **don't add it**.

## Skill index (load per task)
`00` master rules · `01` architecture · `02` environment · `03` autonomy loop ·
`04` popup defense · `05` virtual cursor/HUD · `06` dependency policy · `07` testing ·
`08` safety/HITL · `09` pitfalls · `10` performance · `11` web/CDP · `12` pro app knowledge ·
`13` scenario playbook.
