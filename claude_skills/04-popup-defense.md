# Skill 04 — Popup Defense (`organ_29_popup_handler.py`)

`DesktopInteractionManager.resolve_and_mitigate(node) -> (success, x, y, action)` is the
universal roadblock solver for native Win32, Qt, WinUI 3, WPF, Chromium, and Web modals.
It runs a **tiered pipeline, cheapest first.** The whole design lesson of this organ:
*never pay for the slow LLM when a fast deterministic rule can decide.*

## The tiers (in exact order)
1. **Tier 1 — Semantic button extraction.** Walk the popup's UIA tree for known
   confirm/dismiss buttons (`_matches_button_semantic`) and fire `InvokePattern` (falls
   back to physical click). Cached via `log_new_pathway(..., "organ_29_tier1_semantic")`.
2. **Tier 2 — DB history cache.** `db.check_popup_history(title)` returns a stored
   `{x, y, action}`. Replays it via `_replay_cached_action` — which understands BOTH a
   click coordinate AND a keyboard intent (`action.startswith("key:")`).
3. **Tier 2.5 — Lexical intent (the fast, data-driven classifier).** `_lexical_intent_decision(node)`
   reads `title + text_content + class_name` and returns `(action, need_human)` or `None`.
   This is a **UI-category matcher, not per-app strings.**
4. **Tier 3 — Gatekeeper LLM** (`/api/chat`), only reached when 1–2.5 are all inconclusive.
   **Hard-capped ≤ 5 s** (`GATEKEEPER_TIER3_TIMEOUT_S = max(0.5, min(5.0, env))`), falls
   through on timeout.
5. **Tier 4 — Escape fallback.** `pyautogui.press("escape")`, returns action `"escape_fallback"`.
   Now also **caches** `key:escape` so a repeat of the same unknown popup hits Tier 2 instantly.

## The lexical intent lexicon (Tier 2.5) — the safety-critical part
Categories defined as keyword sets at module top: `ELEVATION_KEYWORDS`,
`DESTRUCTIVE_COMMIT_KEYWORDS`, `CRASH_KEYWORDS`, `COOKIE_CONSENT_KEYWORDS`,
`BROWSER_PROMPT_KEYWORDS`. Decision table:

| Category | Action | need_human |
|---|---|---|
| Elevation / credentials / UAC (`AUTHENTICATION`) | — | **True → escalate, fire NOTHING** |
| Destructive commit ("save changes", "are you sure", "permanently delete") | — | **True → escalate** |
| Crash reporter / "not responding" | `key:escape` | False |
| Consent / cookie / browser prompt (no button) | `key:escape` | False |
| Plain info message box / notification | `key:enter` | False |
| Genuinely ambiguous | `None` (→ pay Tier 3) | — |

**The law:** Tier 2.5 NEVER auto-accepts elevation or destructive-commit. Those return
`(False, x, y, "need_human")` with **zero keystrokes fired.** Auto-confirming a UAC or a
"delete permanently" is unacceptable regardless of whether escape "would work".

## Why it got faster (real numbers)
Before: unknown popups fell straight to Tier 3 → a cold local model once took **~29.5 s**.
After Tier 2.5 + caching: a novel cookie consent resolves in **~0.12 s**; a repeat of any
popup replays from the DB in ~0.1 s; worst-case ambiguous popup is now ~5–6 s (capped Tier 3
+ Tier 4), never 29.5 s. organ_29 group score went 70.0 → 92.1 (4/4 tests).

## Gotchas
- `check_popup_history` matches by `title LIKE '%"title"%'` and returns `action = detected_type`.
  So a cached `key:...` action would be mis-read as a click unless Tier 2 routes through
  `_replay_cached_action` (it does). Keep that routing when editing.
- `escape_fallback` string is consumed downstream by `organ_30_app_scanner.py` — don't rename it.
- Test pattern: monkey-patch `mgr._execute_key_intent = lambda a: ...` to capture intents
  without firing real keystrokes (see PL1 test).
