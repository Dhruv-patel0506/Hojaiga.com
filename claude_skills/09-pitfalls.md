---
name: hojaiga-pitfalls
description: Pitfall catalogue of bugs actually hit in this project - Florence-2 transformers version incompatibility, Omniparser class-name spelling, eager easyocr init, external ClipCursor env-block, popup Tier-3 stalls - each with root cause and fix pattern.
---

# Skill 09 — Pitfall Catalogue (bugs we actually hit — do not rediscover)

Each entry: **Bug class → Root cause → Fix pattern → Boundary.**

## P-1  Tier-3 popup stall (~29.5–35 s)
- **Root cause:** unknown popups fell through to a cold Gatekeeper LLM with no cap.
- **Fix:** hard-cap `GATEKEEPER_TIER3_TIMEOUT_S = max(0.5, min(5.0, env))`; add fast Tier-2.5
  lexical intent before the LLM; cache every decision so repeats replay from DB.
- **Boundary:** any external call in the loop needs a bounded timeout. Cap in code, not just env.

## P-2  Virtual mouse "failure" that wasn't a bug
- **Root cause:** a foreign app ("Clicky Infinite Void Overlay") held a `ClipCursor`, so the
  OS refused `SetCursorPos`. Environmental, not a code defect.
- **Fix:** the overlay cursor is *drawn* (UpdateLayeredWindow), not moved — immune to the clip.
  Prefer Invoke/PostMessage over SendInput. Report such cases as ENV-BLOCKED, prove by an
  independent path.
- **Boundary:** never treat an OS-refused input as a logic bug; probe set+get delta first.

## P-3  OmniParser "torch missing" that was really a typo
- **Root cause:** repo class is `Omniparser` (lowercase p); `from util.omniparser import
  OmniParser` raised a swallowed ImportError logged as "deps missing".
- **Fix:** `organ_44` now resolves either spelling via `getattr(mod, "Omniparser", None) or
  getattr(mod, "OmniParser", None)`.
- **Boundary:** never log a generic "X missing" from a bare `except ImportError` — include
  the real exception text.

## P-4  transformers version whack-a-mole
- **Root cause:** 5.x breaks Florence-2 config; 4.44 can't build tokenizers on Py3.13 (PyO3≤3.12).
- **Fix:** pin `transformers==4.51.3`.
- **Boundary:** on Py3.13, a too-old pin can be as fatal as too-new; verify wheel availability.

## P-5  easyocr/paddle hard import at module load
- **Root cause:** `util/utils.py` built `easyocr.Reader(['en'])` and imported paddleocr at
  import time → surprise multi-MB download + crash if paddle absent.
- **Fix:** made Reader lazy (`_get_reader()`), paddle import optional (`try/except → None`).
- **Boundary:** heavy engines import lazily so their absence degrades, never breaks.

## P-6  Web URL derivation → fake domains
- **Root cause:** web steps were routed with derived/guessed URLs, producing non-existent domains.
- **Fix:** `_derive_web_url` / `_is_site_like_target` in organ_01 validate site-likeness before
  treating a target as a URL; otherwise it's a desktop app name.
- **Boundary:** never synthesize a URL from a fuzzy target string.

## P-7  Chrome profile-picker on launch
- **Root cause:** launching Chrome via the Windows search bar / certain flags triggers the
  profile-picker dialog, blocking automation.
- **Fix:** direct launch (organ_40) with an explicit `--user-data-dir`; reuse CDP `:9222`,
  never relaunch per step. Session cookies seeded into the chosen profile.
- **Boundary:** a browser that shows a picker/first-run UI is not controllable — suppress it at launch.

## P-8  CDP navigate timeout vs login gate
- **Root cause:** `networkidle` never arrives when a login wall holds the page; navigate times out.
- **Fix:** detect login page (`_detect_login_page`), HITL with a bounded wait (120 s), then
  extract+seed cookies. Don't raise on the first navigate timeout.

## P-9  organ_36 compiler drops web/Gmail steps
- **Root cause:** the step compiler silently omitted certain web/mixed steps from the plan.
- **Fix:** ensure every compiled step survives to the executor; add a regression test that
  feeds a mixed web+desktop task and asserts step count is preserved.
- **Boundary:** a dropped step is a correctness bug, not a simplification.

## P-10  Windows named-pipe IPC list handling
- **Root cause:** the IPC server mishandled list-typed payloads (popup button lists).
- **Fix:** normalise list fields before crossing the pipe boundary; JSON-encode explicitly.
- **Boundary:** anything through `cns_bridge` must be JSON-safe primitives.

## P-11  PowerShell command length / `&&`
- **Root cause:** `&&` unsupported in PS 5.1; very long inline commands get mangled by console echo.
- **Fix:** use `;`; write scripts to a file for long logic; capture to a `.log` then `Get-Content`.

## P-12  cp1252 UnicodeEncodeError on print
- **Root cause:** printing `—`/`→`/emoji to the PS console crashes non-utf8 python.
- **Fix:** run python with `-X utf8`; avoid decorative glyphs in log strings.

## P-13  pip check: crewai-cli vs litellm (pydantic-settings) - IRRECONCILABLE, pinned
- **Symptom:** `pip check` reports `crewai-cli 1.15.1 requires pydantic-settings~=2.10.1`, venv has 2.15.0.
- **Root cause:** `litellm` needs `pydantic-settings>=2.14.1`; the two requirements cannot both hold.
- **Decision:** keep `pydantic-settings==2.15.0` (crewai imports and runs fine). Downgrading to 2.10.1 breaks litellm.
- **Boundary:** do NOT "fix" pip check by downgrading. Documented in the `desktop_grounding.py` header too.

## P-14  Physical input is gone - everything is headless (product law)
- **Rule:** no `SetCursorPos`/`mouse_event`/`keybd_event`/`SendInput`/`pyautogui` in any loop path. All input goes
  through `headless_input.py` (UIA patterns, then window messages to the exact HWND). A process-wide guard
  (`install_physical_input_guard`) refuses and records any legacy call (`headless_input.VIOLATIONS`).
- **Boundary:** an undeliverable action returns `UNDELIVERABLE: <why>`; it never falls back to physical input.
  Posted keys reach classic Win32 apps (modifiers via AttachThreadInput+SetKeyboardState); XAML/WinUI apps ignore
  them - drive those through UIA (menu item Invoke), not accelerators.
- **Legacy still to convert:** organ_01 draw/shape tools (absolute mouse_event strokes) are now REFUSED by the guard.

## P-15  `\b` inside a patch heredoc becomes a backspace char (0x08)
- **Root cause:** writing regex `\b` through shell heredocs/non-raw strings silently produced control characters.
- **Fix:** write patch scripts with the Write tool or build with `chr(92)`; scan touched files for `[\x00-\x08]`.

## P-16  Packaged (Store) apps redirect writes under %LOCALAPPDATA%
- **Symptom:** Notepad "saved" `%TEMP%\x.txt` but the file does not exist from outside.
- **Fix:** E2E output dirs live outside AppData (`D:\new_automation\_e2e_tmp`).

## P-17  Notepad 11 resurrects every killed session as extra windows
- **Root cause:** `taskkill` on Notepad with unsaved tabs persists them in
  `%LOCALAPPDATA%\Packages\Microsoft.WindowsNotepad_*\LocalState\{TabState,WindowState}`; next launch reopens them all.
- **Fix:** never taskkill a document app in tests; close it with WM_CLOSE after saving; clear stale TabState by hand.
- **Boundary:** `find_window` must rank by process/class and exclude cloaked/tiny/browser windows (an Edge tab titled
  "notepad" was once typed into).

## P-18  Menus/dialogs are separate top-level windows
- **Symptom:** after clicking `File`, the loop re-clicked `File` forever. **Root cause:** the XAML menu is a
  `PopupWindowSiteBridge` window the main-frame UIA walk cannot see, and it populates after the click returns.
- **Fix:** ground same-process popup windows (different class than the frame) and `_settle()` (bounded wait until the
  element tree stops changing) after every click.

## P-19  Qwen2.5-VL-7B on a 6 GB laptop GPU
- **Measured:** ~2.3 tokens/s; boxes are accurate but a full-screen parse = minutes. llama-server (-ngl 24) and Ollama's
  7B Brain fight for the same 6 GB and spill to CPU.
- **Rule:** use the VLM only for targeted `locate(one control)` (~40 tokens); OmniParser (warmed in a daemon thread at
  startup, never in a goal's path) stays the bulk vision tier.
