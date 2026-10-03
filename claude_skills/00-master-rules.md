# Skill 00 — Master Rules (Non-Negotiable)

These laws override every other instruction. If a task conflicts with one, stop and say so.

## L1 — FREE, CHEAP, LOCAL, NO PAID APIS
1. **Never** introduce a paid/cloud API (OpenAI, Anthropic, Azure, AWS, Google Cloud,
   Groq cloud, etc.) into any runtime path. All intelligence runs locally:
   - LLM decisions → **Gatekeeper proxy** `http://127.0.0.1:11435/api/chat` (local llama3).
   - OCR → **Tesseract** (free binary) + `pytesseract`.
   - Vision → **local OmniParser repo** at `D:\new_automation\OmniParser` with local weights.
   - Browser automation → own Chrome via **CDP `:9222`**, no browser-API services.
2. Prefer stdlib → then free OSS wheels → then local repos. Never add a service.
3. Cost check before any `pip install`: is it OSI-licensed, does it phone home,
   does it require an account/key? If yes to the last two → reject and find a free substitute.
4. Models must be downloaded **once** from HuggingFace (free) and cached locally;
   runtime must work offline after warmup.

## L2 — HONESTY OVER COMPLETION
1. A capability that cannot run must **report that it was skipped** (e.g.
   `tiers_skipped: ["ocr:engine-missing"]`). Faking a tier's output is the worst
   possible failure mode — we have tests that detect fabrication (G1 honesty-integrity).
2. Never quote a latency/accuracy number that wasn't measured in this repo.
3. ENV-blocked ≠ code defect: label environmental failures as such, but still prove the
   code path works by an independent route.
4. "Done" = compiled + tested + evidence pasted. Not "it should work".

## L3 — DYNAMIC, DATA-DRIVEN, NO PER-APP HARDCODING
1. All fixes must be generic: UI **categories** (crash dialog, consent banner, UAC),
   not app names. Adding `if app == "blender"` is a rejected design.
2. App-specific knowledge belongs in the **runtime learning layer** (organ_47
   pro-knowledge, organ_04 recipes, DB pathway cache) — never in source code.
3. New capability = new rung on an existing ladder (perception tier, mitigation tier,
   recovery rung), not a special-case branch.

## L4 — VERIFY, DON'T BELIEVE
1. No action is trusted until a before/after snapshot diff proves the outcome
   (verdicts: PASS / NO_CHANGE / WRONG_STATE only — no fourth verdict).
2. Unverified LLM guesses and archetype predictions may only **rank hints for the judge**;
   direct control requires a verified/learned record (confidence ≥ 0.97 shortcuts).
3. Every step gets a postcondition; the default postcondition is "the signature moved".

## L5 — SAFETY FIRST (see 08-safety-hitl.md)
1. Elevation/credential prompts and destructive-commit prompts are **never auto-accepted** —
   escalate to human (HITL), even if escape "would work".
2. The 3-strike rule: after 3 invalid/rejected judge choices, freeze → capsule
   "Agent needs your input" → checkpoint. Never attempt a 4th hallucinated retry.

## L6 — BOUNDED TIME EVERYWHERE
1. Every network/LLM call has a hard timeout cap (popup Tier-3 ≤ 5 s, clamped in code).
2. Every poll/wait has a deadline + backoff cap (readiness: 10 s, 0.35→1.5 s backoff).
3. An unbounded wait is a bug, even when it eventually succeeds.

## L7 — NOTHING IS DONE UNTIL THE SUITE SAYS SO
1. After any change: `py_compile` touched files → run the system intelligence suite →
   report pass/fail table honestly (see 07-testing.md).
2. New capability ships with a new named test (G1, P3, PL1, W8 style) or it doesn't ship.
