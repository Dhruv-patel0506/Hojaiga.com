---
name: hojaiga-performance
description: Performance budget and caching discipline - DB-backed pathway cache, capped LLM calls, cheapest-signal-first ordering, latency regression guards, and the popup hardening case study that cut 29.5s to 0.12s.
---

# Skill 10 — Performance Budget & Caching Discipline

The autonomy loop is only usable if each step is fast. The cost model is the ladder:
structural tiers are milliseconds, pixel tiers are seconds. **Spend pixels only when
structure fails.**

## Latency budget per perception tier (targets; measure before quoting)
| Tier | Budget | Rule |
|---|---|---|
| UIA | ≤ 40 ms | default for named-target lookups |
| Win32 | ≤ 15 ms | fallback when UIA tree is empty |
| OCR | ≤ 1.2 s | ONLY on 2 structural misses for a specific `target_text` |
| Vision (OmniParser, CPU) | 1.5–4 s / call | LAST resort; budget-capped per goal |
| DB cache replay | ≤ 1 ms | always try cached pathway first |
| Gatekeeper LLM (Tier 3) | ≤ 5 s hard cap | never uncapped |

## The cardinal rules
1. **Escalate lazily, never eagerly.** Default `max_tier=2` (UIA+Win32). Only climb to OCR/
   vision when hunting a specific string that structure missed. Do not "scan everything with
   the neural net" — that turns a 40 ms step into a 4 s step.
2. **Cache every decision.** Popup resolutions, element pathways, app shortcuts, distilled
   recipes — all persisted (organ_24 DAP, organ_29 pathway, organ_04 recipes, organ_47).
   A second run must reuse, not re-perceive. The 5th run of a task should cost near-zero
   because the compiler is handed a verified prior.
3. **Model init is expensive (17–24 s), inference less so.** Warm heavy engines once at
   startup (background thread), never per-call. easyocr/Florence download on first use —
   pre-warm so a real task never stalls on a download.
4. **Cap vision calls per goal** (proposed `HOJAIGA_VISION_MAX_CALLS`, default ~2). A step
   loop must not call OmniParser 5×.
5. **Cache vision results by (hwnd, window-signature-hash)** with a short TTL (~2 s) so
   re-grounding within one step doesn't re-parse identical pixels.
6. **Reuse the browser.** Chrome on CDP `:9222` is launched once and reused; relaunching per
   step is the single biggest latency mistake possible.

## Where the time actually goes (measured, this host)
- Popup group avg ~2.6 s (dominated by capped Tier-3 on the rare ambiguous popup); known
  categories now ~0.12 s via Tier-2.5.
- G1 grounding with all tiers ON ≈ 121 s because it deliberately exercises OCR+vision on
  notepad — that is the *worst case*, not the per-step cost of a normal run.
- DAP batch element round-trip ≈ 1.5 ms/element (this is the number structural tiers approach).

## Anti-patterns (reject in review)
- Calling vision to find a button that UIA already exposes.
- Re-instantiating OmniParserScanner / easyocr.Reader per screenshot.
- Polling a fixed short `sleep()` loop instead of bounded backoff (wakes CPU / too slow).
- Awaiting an LLM with no timeout.
- Re-scanning an unchanged window: always diff the structural/visual signature first.
- Quoting "5–40 ms" as fact without a fresh `ground()` measurement in the results file.

## Measuring discipline
Every perf claim must come from a test `evidence` line with a real number from THIS repo
(the suite times each test). If you optimise, measure before and after and put both in the
report. Prefer fewer ladder passes over faster individual passes.
