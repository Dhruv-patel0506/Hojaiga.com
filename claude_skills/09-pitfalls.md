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

## P-20  Win11 Paint ignores posted mouse messages (WinUI canvas)
- **Measured:** `post_drag` of a circle to Paint's 6 windows (frame, MSPaintView, DesktopChildSiteBridge, InputSite...)
  changed 0 pixels, while a UIA invoke on the same parked window changed 597 - so the capture is live and the drag was ignored.
- **Rule:** XAML/WinUI hosts take pointer/keyboard through their own input pipeline, not window messages. `post_drag` is proven
  on a real Win32 canvas (DR1: 2124 px, bbox 223x223 for r=110); on a XAML canvas the draw tools report
  `delivered but INEFFECTIVE`, never success. `headless_input.is_xaml_host()` recognises the stack; the loop annotates a
  failed posted key with it.

## P-21  `find_window` must skip the UWP CoreWindow
- **Symptom:** Calculator grounded, but parking/closing it failed ("window-not-parkable"); the judge saw 4 elements.
- **Root cause:** `Windows.UI.Core.CoreWindow` (process `CalculatorApp`) out-scored the `ApplicationFrameWindow` by process name,
  and a CoreWindow cannot be parked or closed on its own.
- **Fix:** skip that class in `find_window`; UIA on the frame already contains the content.

## P-22  A parked UWP window reports empty rectangles
- A window parked at -24000 lays out only sometimes; `IsOffscreen`/empty rects dropped every control. `_walk_uia` treats a
  parked window like a minimized one (patterns work, rectangles do not). Never use the minimized sentinel -32000 as the park origin.

## P-23  Connecting to a CLOSED local port takes ~2 s on Windows
- **Measured:** `urlopen`/`connect` to 127.0.0.1:11435 with nothing listening: 2.04-2.10 s before "refused" (popup Tier-3 paid
  that for every unseen popup). **Fix:** `_gatekeeper_listening()` probes with a 150 ms connect; down => skip T3 (breaker) => 166 ms.

## P-24  A distilled hint can say verb "type" for a Calculator key
- organ_47 returned `element '2', verb type, conf 0.3, source distilled` for `press Six`; the 7B echoed it and burned the 3-strike
  HITL. **Fix:** exact-name goals ("press Six") are decided by lookup, a hint never advertises `type` when the goal has no typing
  words, and a `type` on a non-editable control with no typing intent is coerced to `click` (the verifier still judges it).

## P-25  `resolve_and_launch` maps nonsense onto a real app
- `gui_search_launch("zzq no such application zzq")` launched Excel (semantic alias fallback). Tests must stub the launcher for
  "nothing" cases; production callers only pass names the compiler already resolved.

## P-26  Drawing was dead for three independent reasons
- (1) every stroke used `mouse_event`/`SendInput`, which the physical-input guard refuses; (2) `CursorShape` had no
  `set_shape/get_shape`, so `drag_to`/`draw_shape` raised AttributeError before delivering a point; (3) the tools claimed
  SUCCESS without measuring anything. Now: posted messages, measured pixel change, honest INEFFECTIVE/UNVERIFIED.

## P-27  Escape is not always an answer, and an unverified answer must not be cached
- Inside the long suite process the UIA read of a plain message box returned NO buttons for the whole 4.5 s re-read window
  (PP1 case 1: decision took 5466 ms, then T4 Escape); standalone the same read takes 541-683 ms and returns them, and 40 busy
  processes on 20 CPUs did not change that - the in-suite cause was not isolated. T4 sent Escape to a Yes/No box, which has no
  Cancel, so nothing happened, and then CACHED that dead `key:escape`, which poisoned the next case. Fix: read classic dialogs
  natively (`hin.native_dialog_parts`, 2-6 ms) and press with a posted `BM_CLICK`; cache a key answer only after the window is
  verified gone. Rule: never cache an unverified answer.
