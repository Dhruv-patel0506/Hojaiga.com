# HojAIGA — NEXT WORK ORDER (accepted 2026-10-05)

## REV 2 (owner, 2026-10-05 evening) — actuation backbone + item map

**Backbone:** every click/type/scroll routes through `organ_24_dap`: `QueryEngine.resolve(selector:
native|a11y|window|control|ocr|vision) -> DAPNode -> Provider.invoke()/set_value()` (UIA
Invoke/ExpandCollapse/Value, BM_CLICK, WM_CHAR/PostMessage). The virtual cursor is the *visual proxy*
of an action, never its cause. When an app family has no working provider, the fix is a new
`ProviderInterface` implementation in organ_24 — **never** moving the real mouse.

Standing laws (non-negotiable, above every item): zero physical cursor/keyboard ever; zero app-name
strings hardcoded in any organ (routing/decomposition stays DATA); work minimized/BACKGROUND — never
foreground the app over the user, and report honestly which mode an app needs; self-report
`tiers_skipped`, never claim 100%, mark flaky/env vs real; secrets only via env; after EACH item run
the FULL suite `--e2e` and report pass/fail/env-blocked against the baseline at the bottom of this
file; per item report: what failed before / what changed / measured result / will-it-work-100%.

| Item | Owner id | Status |
|---|---|---|
| E2E-1 menu-chain WRONG_STATE | P0-A | grading fix in tree; full-suite proof pending |
| in-suite blank capture | P0-B | **root-caused + fixed (this rev)**; full-suite proof pending |
| pointer-pollution -> ABORTED-ENV | P0-C | another agent is landing `pointer_sentinel` now |
| Excel backstage save-to-path | P1-D | **dialog recognition fixed by shape + stale-file hole closed; measured end-to-end (file lands, workbook empty → cell read-back still open)** |
| Electron/CEF provider | P1-E | not started |
| WinUI provider patterns | P1-F | not started |
| deep scan in seconds | P1-G | not started |
| 1-second capability summary | P1-H | another agent landed `command_registry`/`static_knowledge` |
| parallel child cursors | P1-I | not started |
| preload sources | P2-J | another agent landed `preload_sources.py` |
| crash-relaunch live proof | P2-K | not started |
| escalation screenshot | P2-L | ES1 passes but the PNG's content is unverified (4.7 kB — check pixels) |
| popup engine for any dialog | P2-M | not started |

**COLLISION NOTE (measured, 18:40):** a second agent is working this same work order in this same
working tree — `_tmp_patch_p1h.py`, `_tmp_patch_p2j.py`, `_tmp_patch_p2l.py` landed within 30 s of
each other and a full `--e2e` run (PID 38076, started 18:37:06) is theirs. One GUI suite at a time on
one desktop: any run started alongside it produces numbers that cannot be attributed to anyone.

---

Origin: the "any app, dynamically" readiness answer. Verdict was **no** — ready for classic
desktop apps (~70%), blocked by three structural walls. This file is the execution order that
closes them. **Do them in this order.** The order is not preference: items 1–2 fix the eyes that
every later item is graded by, and unproven eyes make every later "PASS" worthless.

Rules that override this file: `claude_skills/00-master-rules.md` (L1–L7), especially
**L2 honesty**, **L3 no per-app hardcoding**, **L7 suite gates**.

Definition of done for EVERY job below: `py_compile` = 0 → full suite with `--e2e` → **0 new
failures** vs the baseline at the bottom of this file → the job's own acceptance line measured,
numbers pasted into the report → `powershell -File D:\new_automation\build_hojaiga_repo.ps1`
sync step (skill 07).

---

## 0. Human-side tails (not code — do not count as progress)

* **Revoke the GitHub token** `ghp_rB5…` at github.com/settings/tokens. History is already clean;
  only revocation ends the exposure. Owner action, ~1 minute.
* `secure_key_storage.py` no longer exists in the published repo (its history removal deleted the
  file). When the owner says so, re-add it as an env-var-reading version — never a store-with-a-key
  version. Nothing in this work order depends on it.

---

## 1. Fix the eyes: in-suite capture degradation (+ E2E-1)  ← IN PROGRESS

**Why first.** ES1 (escalation screenshot), S2 (continuous scanner change detection) and E2E-2
(ocr/vision tiers) all fail **inside the suite process and pass in isolation** — measured today:
`--only ES1,S2` → 2/2 PASS, same tests FAIL in the full run. Our day-report is only trustworthy if
the observation feeding it is, and today it flickers exactly during long unattended sessions.

**What is already known (do not re-derive):**
* The blank note comes from `headless_input.capture_window()` → `PrintWindow(PW_RENDERFULLCONTENT)`
  returning pixels that are all black.
* **"GDI/USER quota leak: rejected" — that rejection was WRONG, and it cost a day.** The 40-call
  micro-probes of `organ_24.capture_window_bitmap_bytes` / `headless_input.capture_window` /
  `visual_cursor._render_frame` measured the three *balanced* paths and missed the leaking one,
  because the handle tracer was installed on the main thread only and `ctypes.windll` loaders are
  **thread-local** — a worker thread's allocations were invisible to it (it printed "0 allocations
  seen" for a run whose leaker was the animation thread). It is exhaustion; the meter was blind.
* **ROOT CAUSE (traced, 2026-10-05 18:35, prefix run of the real plan):** 4,154 of 4,188 live GDI
  handles came from one line — `visual_cursor._draw_badge`'s `CreateFontW`, on the overlay animation
  thread. `GetTextExtentPoint32W` is an entry point of **gdi32.dll**, and the badge asked **user32**
  for it, so every badge frame raised `AttributeError` inside a `try: ... except Exception: pass`:
  the per-frame font was stranded and the badge never painted at all. ~27 handles/s at 60 fps →
  the ~10,000 per-process GDI cap → `CreateCompatibleDC` returns NULL → `capture-blank[… obj=10000/42 …
  gdi-create-failed]` → MIN1/E2E-2/ES1/S2 and every escalation screenshot. Budget curve of that run:
  `M1:86 → G1:1773(+1563) → LF2:4206(+887)`, monotonic, never descending. M1 is where the thread
  starts, which is why `--only G1,LF2,TY1,ANY1` grew nothing: the leaker was born earlier.
* **"window never composed" hypothesis: rejected for Notepad.** Launched hidden exactly like the
  suite (`universal_scan.launch_hidden` → minimized from birth → `BackgroundSession` park at
  −24000), PrintWindow succeeded immediately: `pw=1 err=0 dib=760 nonzero=1.000`, and also with the
  plain flag (`nonzero=0.840`). Fresh process, all states OK — including parked off every monitor.
* So the trigger is **process history**, not window state. Which is precisely why the primitive now
  reports the truth instead of a shrug.

**What changed already (this session):**
* **P0-B fix (measured before → after).** `visual_cursor`: the badge font is created ONCE and cached
  (`_badge_font()`, released in `destroy()`), text is measured through `g32.GetTextExtentPoint32W`
  with typed argtypes, every object is deselected then deleted inside `finally`, and the swallow is
  now a logged `logger.debug`. `organ_24.capture_window_bitmap_bytes` (the path the owner named): the
  three handles are now released in `finally` (an exception between create and delete used to strand
  all three), NULL creations return `(0, 0, b"")` honestly instead of drawing on nothing, and the
  bitmap is deselected before `DeleteObject`. `gdi_budget_trace` now wraps the allocators on **every
  thread** (patches `threading.Thread.__init__`) and `_site()` walks frames directly (the old
  `extract_stack` cost ~40x per allocation). Proof, same real overlay with a badge + a sprite, 12 s
  (≈700 frames): allocations 7,748 → **live handles 8** (was 4,154 live fonts), process GDI/USER
  `1/2 → 17/11` (was ~27 handles/s). `GetTextExtentPoint32W` verified on this machine: gdi32 returns
  1 with cx,cy=74,16; user32 does not export it. Side effect, honest: **the state badge now paints
  for the first time** — it has been silently invisible until today, so the overlay is busier on
  screen and any screen-grab tier may now see it.
* `headless_input.capture_window()` carries the Win32 answer in the note and in
  `CAPTURE_DIAG` / `CAPTURE_LOG` (bounded 30):
  `capture-blank[pw=<PrintWindow return> err=<last error> dib=<rows read> obj=<gdi/user>
  px=<non-zero fraction> where=visible|onscreen|parked|min|not-visible xaml=0/1]`.
  A process that cannot make a DC now says `gdi-create-failed` instead of blaming the app.
* `_save_escalation_shot()` (desktop_grounding) no longer fails silently: when nothing could be
  captured it records `{"path": "", "capture": <reason>}`, and `task_lifecycle` C2 says
  "NO picture could be captured (<reason>)" rather than "screenshot saved:".
* **E2E-1 root cause found and fixed.** It was not the menu postcondition guess in the original
  draft — it was worse: the GOAL's terminal postcondition (`file_created`, from `expect_map` /
  `derive_expectation`) was applied to EVERY step, so `click File` — which correctly opened the
  menu — could only ever be WRONG_STATE. That (a) eroded the command in knowledge as a failure and
  (b) added "file"/"save as" to the spent set `_opened_not_done`, which is what made run2 wander
  through 12 unrelated clicks. Fix: `split_terminal_expect()` + `TERMINAL_EXPECT_KEYS`
  (desktop_grounding, next to `desktop_verifier`), a `_grade()` closure in `_step_impl` that judges
  the STEP by what a step can prove and asks the goal's terminal condition separately, the same
  split in `_run_kb_route`, `verb == "done"` no longer accepted on the declaration alone, and
  `_run_impl` advances only on `verdict == "PASS" and res.get("goal_done", True)`. Mixed
  UI+terminal postconditions are left whole — every part still checked.
* **EYE1 added** (`si_tests_fixes.run_eye1`, registered LAST in the default plan — the defect is
  process-history dependent, so the soak must run on a process that already did a full day's work).
  300 captures of one parked Notepad with a UIA walk every 10th capture; asserts zero blanks, min
  non-zero pixel fraction, `CAPTURE_LOG` entries for that hwnd, GDI/USER growth ≤ 60 each, and the
  pointer guard.

**Remaining work (the actual fix):**
1. Read the diagnostics from the full `--e2e` run (`_suite_capture_diag_run.log`). The `pw/err/obj`
   triple separates "Windows refused", "out of objects", and "the app really did not paint".
   *Log-reading trap, measured:* launching through PowerShell's `>` re-wraps every line at console
   width (so `Select-String 'capture-blank'` misses matches that straddle a wrap) and Python blocks
   stdout when redirected (the `[PASS]/[FAIL]` evidence lines, which is where the blank notes live,
   only land at flush). Use `cmd /c "…python.exe -u … > log 2>&1"` for the next runs.
2. Implement the fix the numbers point to. Expected shapes, in the order the evidence should pick:
   * refusal/error → a bounded retry ladder inside the capture rung (re-park nudge, then
     `background_window.sliver()` + `_await_paint`, then one screen-grab fallback **only** when the
     window is genuinely visible, with the source tag saying so — never silently).
   * object/handle growth → find the leaking path with the same `GetGuiResources` sampler and fix
     the ordering (`SelectObject(old)` before `DeleteObject`) wherever it occurs.
   * app genuinely unpainted → make the composition nudge part of the hold, not an afterthought.
3. Re-run E2E-1 (`--only E2E-1`, then in the full suite) and read the trace: no WRONG_STATE on menu
   leaves, run1 and run2 both reach the file, run2 not slower than run1.

**Acceptance:** MIN1, E2E-1, E2E-2, ES1, S2 pass in a FULL suite run (not `--only`); E2E-2 shows
`tiers_ran` containing `ocr` (and `vision` when the vision server is up) instead of
`tiers_skipped: ocr:capture(capture-blank…)`; E2E-1's trace contains no WRONG_STATE on the menu
leaves and run2 steps ≤ run1 steps; `EYE1` (group HEADLESS, last in the default plan) passes with
the measured numbers in `evidence`.

---

## 2. 3.7 — Excel "save where I said" (proves real third-party dialogs)

**Consequence today:** the flagship save-to-path task is unreliable; file lands in the wrong place
or not at all. This is the proof-case that real dialogs beat us — and skill 14 already records it:
*"Save to a given path through the backstage is not reliable (name box rejects the drive colon, pane
navigation)"*.

**Work:** the backstage/SaveAs path must be driven as a *dialog chain*, not a click sequence:
detect the separate dialog window (it is a new top-level window of the app pid, `popup_policy
.blocking_dialogs` already enumerates those), address its File-name edit by UIA ValuePattern with
the full path, drive the folder navigation by path text rather than list clicking, then verify the
file on disk (organ-level truth, not a title change). The name-box colon rejection is an input
delivery detail: set the whole path via ValuePattern (which does not run the shell's per-keystroke
filter), or type the drive letter and colon as one `WM_CHAR` string — measure which and keep it.

**Acceptance:** a new named test (suggest `XLS1`, group E2E) — start Excel, type into a cell, save
as `D:\new_automation\_e2e_tmp\hj_<id>.xlsx`, assert the file exists at that exact path with the
workbook signature (`PK\x03\x04`), close and re-open it and read the cell back; run it twice
(cold, then learned) and the second run must not be slower than the first by more than 20 %.
E2E-1-style honesty: `wrong-place` and `no-file` are distinct failure reasons in the evidence.

**MEASURED 21:30 (rev 2.1 — this item was picked up by both agents; the other one holds the loop
fixes, this one holds the recognizer and the verifier):**

* Root cause of "Excel never saves where it was told" is neither parking nor vision: **the loop was
  blind to the dialog.** Recognition was `class == "#32770" AND the title says save/open/export`,
  and the app's own picker is an UNTITLED window of another class (`NUIDialog`), so every step
  answered `no-file-dialog-visible` while the app sat modal behind it. The blank-looking pane was the
  dialog, not the capture path.
* What landed here:
  - **one recognizer, by shape** — `organ_24` SECTION 11B (`file_dialog_shape`, `find_file_dialogs`,
    `is_owned_top_level`). What counts as a dialog is DATA (`DIALOG_CLASS_CERTAIN` = the OS contract,
    `DIALOG_NAME_FIELD_AIDS` = Win32 IDFILENAME, `DIALOG_CLASS_RECOGNISED` = window kinds, title words
    = ordering hints only). No app name and no vendor branch in the control flow. Verified on the real
    dialog: `{'class': 'NUIDialog', 'nodes': 21, 'name_edit': True, 'name_settable': True,
    'accept': True, 'fs_visible': False, 'certain': False, 'plausible': True}` with `owned=True`, and
    `VERDICT: shapes-only recognizer SAWS the dialog`.
  - `NativeFilePicker.locate_dialog/confirm` and organ_48's `file_dialog` readiness wait now use the
    same tables instead of their own literals (one dialog cannot be a file dialog to one caller and not
    to another).
  - **the rung was unscoped:** organ_48 called `handle_native_file_dialog(path)` with no owner, so
    `want_proc` was empty and ANY picker on the desktop — including one the user opened — could be
    filled in and confirmed. It now passes `owner_hwnd`.
  - a dialog that will not take an absolute path is walked by **declared routes**
    (`DIALOG_PATH_ROUTES`), hop by hop, with patience for a pane that is still loading; when nothing
    answers, the reason is attached to the step evidence instead of a silent `logger.debug`.
  - **the stale-file hole closed** (the false positive the owner found: an old `e1.xlsx` on disk made a
    run that saved nothing look green). `file_created`/`file_saved` now need a WRITE after the goal
    began (`file_fresh_since`, stamped per goal and carried through the terminal split — it had to join
    `TERMINAL_EXPECT_KEYS`, otherwise the leftover key made every intermediate step, like clicking
    File, grade WRONG_STATE and erode a command that was right), and 0 bytes is not a save.
    DE1 carries three new checks; E2E-1's own ground truth checks mtime and size, not existence.
  - **`type 42 in cell A1` had no postcondition at all**: the `in` made the literal reader say "needs
    composing", so the goal had nothing to check and a ribbon-tab click completed it. The location
    tail is now cut off (`_LOCATION_TAIL_RE`), so the goal carries `text_contains: 42`, and pronouns
    (`it/this/that/…`) can no longer masquerade as the literal.
* Measured, Excel through `operate_app` (goals: type 42 in A1, save as `<unique>.xlsx`):
  `completed=True steps=9 270.9s awaiting_human=False`, trace
  `… click File Tab / Save As / Browse -> file-dialog PASS (name set + Enter)`, file at that exact
  path, 8440 bytes, a real xlsx zip, written during the run, `input-guard violations=0`, pointer
  untouched. **And the workbook is empty** (`0 non-empty cell(s)`) — that is the proof of the
  goal-level false positive above, found by reading the file instead of trusting the verdict.
* Still open on this item: the cell read-back (nothing reads a spreadsheet grid yet, so after the
  literal fix the type goal should honestly block rather than fake a pass), and `XLS1` as a named
  suite test with cold/learned timing.

**MEASURED 22:20 (rev 2.2 — the false-positive work finished; every save proof is now a WRITE proof):**

* **The file must HOLD what it was told to write.** `file_holds_text()` reads the artifact the way the format
  stores it: plain bytes for a text format, the value/text leaves of each compressed member for the document
  containers (`PLAIN_TEXT_EXTS` / `CONTAINER_TEXT_EXTS` — the format decides the reader, no app name
  anywhere). A container with **no text or value at all is a FAIL, not "unreadable"** — that distinction is the
  empty-workbook case; an unknown binary says `not checkable` out loud instead of buying a free PASS.
  `_run_impl` stamps `file_text_contains` from the run's own typed literal (`literal_typed_text` over the
  earlier goals), so 'type 42 in cell A1' + 'save as <path>' cannot complete on an empty sheet. Measured:
  empty workbook -> `the .xlsx holds no text or value at all (an empty document)`; a workbook with
  `<c r="A1"><v>42</v>` -> `'42' IS inside`; '42' is NOT satisfied by '1422' (whole-piece rule).
  `file_text_contains` joins `TERMINAL_EXPECT_KEYS` for the same reason `file_fresh_since` did.
* **The name box is recognised by what it IS.** Two loop sites asked the control for the English words
  'file name' (the whole-path override and the Enter-commit). They now ask `_is_name_box_element()`: an
  editable role, then ANY of — the caption hint, the Win32 IDFILENAME automation id (`DIALOG_NAME_FIELD_AIDS`),
  or the window's own shape from `file_dialog_shape`. The commit button likewise stopped carrying its own
  ("save","ok") literals and reads `DIALOG_ACCEPT_WORDS` / `DIALOG_NEVER_PRESS` / `DIALOG_ACCEPT_ROLES`.
  Verified: a French-labelled box with the IDFILENAME id is seen, a 'Search' box in a dead window is not.
* **One test's failure must not ENV-BLOCK the next five.** The 21:53 run left
  `'hj_tpl1_d76b24.txt - Notepad'` on the desktop after a failed save, and LC2/A3X/G2L/VQ1/KC1 each correctly
  refused to drive "the user's Notepad" — the guard was right, the LEAK was the bug. The runner now reclaims
  windows whose title carries the harness's own artifact namespace (`_HARNESS_ARTIFACT_PATTERN`, the
  `hj_<tag>_<hex>.<ext>` every test already writes) between tests; a user document is never a candidate
  (`Notes.txt`, `budget_2026.xlsx` -> not ours; `hj_tpl1_d76b24.txt` -> ours). A close the app refuses is
  reported, not assumed.
* **V1's contract was the stale one.** It asserted "an empty file proves file_created", which the new
  verifier refuses; it now writes content for the PASS case and asserts the empty file as its own
  `empty_file_is_not_a_save` transition (measured `8/8 verdict transitions correct`).
* **The 21:53 numbers were not a clean measurement.** Two suites ran on one desktop at the same time
  (their section stamped 21:47:13, mine 21:53:40 — mine started 21:34:04, so they overlapped ~13 min).
  Proof it was contention and not code: **TPL1, FAIL in that run, passes alone on a quiet desktop in 69.9 s
  with all four leaves green** — `type_text PASS / open_save_as PASS / save_to_path PASS / verify_content PASS`
  (the last one is the template's own file-reads-back-the-text check) and paint `save_to_path PASS`.
  A third run was started alone at 22:27:15 with the same desktop checked empty first.
* No app-name or vendor-name equality test survives in the four files this item touches
  (`desktop_grounding`, `organ_24_dap`, `organ_48_app_behavior_model`, `loop_first`): routing is by window
  class/role/shape facts and the words live in the data tables.

---

## 3. 2.4 — the Electron/CEF half of the desktop (WhatsApp / Steam / Discord and everything else)

**Consequence today:** those three are read-only, and they are the tip of a much larger family:
VS Code, Slack, Teams, Figma, most trading platforms — same Chromium content window. Today: window
discovery + OCR of the parked window works; **no reliable clicking**.

**Work:** build the effectors for Chromium-hosted UIs, keeping L3 (UI categories, never app names):
* UIA into the Chromium tree: Chromium exposes its accessibility tree only when asked — the
  `launch_hidden` code path already pokes `WM_GETOBJECT (0x3D)` with `OBJID_CLIENT/WClientId`.
  Make that a first-class, permanent step of grounding for any window whose class is
  `Chrome_WidgetWin_*` / `CefBrowserWindow` / whose UIA subtree reports a `document`/`web area`
  control, then use real UIA patterns (Invoke/Toggle/Value/ScrollItem) on the found elements.
* `WM_LBUTTONDOWN/UP` posted to the exact child `Chrome_RenderWidgetHostHWND` at client coordinates
  — the current posted-mouse primitive plus a hit-test against the render child.
* Keyboard route (tab/arrows/Enter/accelerators) already exists; wire it as the third rung.
* Report which effector worked per element in the knowledge layer, so the two-pass promotion
  decides the trusted route — the same machinery that already works for classic apps.

**Acceptance:** one code path, zero app names: for every installed app whose window class matches
the Chromium/CEF category, a new test (suggest `ELC1`, group EFFECTOR) grounds the parked window,
finds ≥5 named elements via UIA inside the web area, performs one non-destructive action per
route (UIA-invoke, posted-mouse, keyboard), and each is graded by the verifier's before/after
snapshot; WhatsApp/Steam/Discord move from "read-only" to at least one verified effector, and the
skill-14 table row 5 gets its action rung filled in.

---

## 4. 1.3 — WinUI/XAML: the arm that only reaches half the world

**Consequence today:** Hojaiga can see Paint but cannot do anything in it, and the same wall blocks
every modern WinUI app — Files, Widgets, new Microsoft software. This is the biggest hole.
Measured and recorded: *"WinUI Paint ignores posted mouse input: no context menu and no drawing
headless. Posted keys never reach XAML hosts."*

**Work:** stop posting input at XAML hosts and use the effectors XAML actually honours:
* UIA patterns on the target element (Invoke/Toggle/RangeValue/Value/ScrollItem) — the route the
  mastery engine already uses for tool toggles; make it the *default* for any `is_xaml_host()`
  window and have the route planner refuse the posted path (the refusal note exists:
  `xaml-ignores-posted-keys`).
* For genuine canvas drawing (no element to invoke): UIA `Transform`/`LegacyIAccessible` where
  available, else `SendInput`-free **real** input is impossible by product law — so the honest
  outcome is a *documented, tested* INEFFECTIVE capability with a working alternative (e.g. Paint's
  own geometry tools via UIA), not a fake PASS.
* Exclusive tool toggles cannot be switched off (Pencil/Fill/Text/Eraser) — model that as a known
  app behaviour (`left_as_found=False` is already reported) instead of reporting FAILED forever.

**Acceptance:** a new test (suggest `WIN1`, group EFFECTOR) that, on Paint (WinUI) and one other
WinUI host discovered dynamically (no name list): opens File ▸ Save as and writes a PNG verified by
its file signature, selects each canvas tool through UIA and reads the toggle state back, and —
for anything that truly cannot be driven headless — returns a structured `INEFFECTIVE` with the
reason and never a PASS. Skill 15's "known limits" section gets updated with the measured line.

---

## 5. 4.3 + 4.1 — prove the recovery promises (crash-relaunch, escalation pictures)

**Consequence today:** G2L passes in the suite, but the promise "I'll resume if the app dies" has
never been demonstrated on a *real task in a real app*, and 4.1's screenshots were blank whenever
the eyes were blank (job 1). Trust is the whole product; unproven paper is not trust.

**Work:**
* Run the crash-relaunch path inside a real multi-goal task (Notepad or Excel): kill the process
  mid-run, let the loop relaunch once, resume the same goal, finish, and verify the on-disk result;
  then kill twice and confirm it fails with evidence instead of looping. Record it in the day-report
  (`--day-live`, DAY3) so the proof is in the unattended flow, not only in a unit test.
* Escalation: make the escalation record carry path + why + title + capture reason (done in job 1),
  and make the human-facing inbox (`data/escalations`) list newest-first with the task ticket, so a
  human can answer without re-investigating.

**Acceptance:** `G2L`-style test on a REAL task with the file verified after the relaunch; a new
`DAY3`-line evidence field `crash_recovery_proven=true/false (<app>, <seconds>, resumed goal
<n/m>)`; ≥1 escalation in a real run carrying a >2 KB valid PNG, or the explicit
`capture=<reason>` when Windows refused.

---

## 6. 3.5 — use the preload sources the apps already ship

**Consequence today:** when an app ships its own command list (OBS WebSocket, Blender `bpy.ops`,
`.keys`/keymap files, VS Code `package.json` commands), we throw that free textbook away and
rediscover by clicking. Slows first-contact; doesn't block it.

**Work:** the harvest side exists (`static_knowledge`, `command_registry.py` unified registry,
backlog 2.6) and the K-series tests pass on synthetic artifacts. What is missing is the *route*:
make the planner consult preloaded (unverified, catalog-tier) commands as ranked hints for the judge
before exploring by click, and promote them only through the normal verified two-pass. Wire
`command_registry` so `corroborated` static entries reach `_consult_intel` as hints with their
source tag, and add the app-specific loaders as *categories* of artifact (json keybindings, python
keymap literal, ini accelerator table, settings schema, cli registry dump) — all five already have a
parser and a test.

**Acceptance:** on a never-before-seen app that ships an artifact (Blender if installed, else OBS,
else any installed app with a keymap file): first-contact mastery reaches the same command count in
**fewer than half the runs/seconds** of the same app with the artifact hidden by an env flag, and
the preloaded commands are reported as `unverified` until a verified run promotes them — measured in
`mastery_bench.py` output pasted into the report.

---

## Baseline to beat (this is the number "0 new failures" is measured against)

**Corrected 2026-10-05 after reading the results file instead of the commit message.** The most
recent FULL run before this work — `system_intelligence_results.txt`, header `2026-10-05 16:07:33`,
78 tests, 1280 s of test time — was **67 pass / 9 fail / 2 env-blocked**, not the
"56 pass / 6 fail / 1 env-blocked" quoted from commit 6012613e (that was an earlier 63-test plan).
The honesty rule (L2) applies to our status numbers as much as to a PASS.

The nine failures, read from their own evidence strings:

| Test | What the evidence actually says | Class |
|---|---|---|
| MIN1 | parked Notepad AND parked Paint both `capture=capture-blank` | job 1 — the eyes |
| E2E-1 | run1 `type PASS, click File WRONG_STATE, click Save as WRONG_STATE, file-dialog PASS`; run2 = 12 steps, no file, wandering over 'Autumn leaves fall' / 'Minimize' / 'Restore' | job 1 — fixed, re-run pending |
| ANY1 | only failing check = `physical-pointer-untouched`: 440 px teleport, **guard violations = 0** | external mover, or the check is too strict |
| KM1 | only failing check = the user's pointer moved | same |
| LC2 | pointer teleport 820 px **and** `calculator-shows-42 FAIL (display='Display is 0')`, `irreversible-delete … status=FAILED`, 3 checkpoint marks failing | needs triage — not the capture bug |
| B2X | `nothing-else-got-started FAIL (new windows=2)` — it counts every new window in the session | contamination from a co-running process |
| KP1 | `static harvest fast (1592 ms < 1500)=FAIL` | threshold on a loaded machine |
| DAY1 | `T2 save drawing blocked at leaf 'open_save_as'` (Paint) | job 4 — 1.3 WinUI |
| VQ1 | `0/4 controls located by Qwen2.5-VL` | vision server not running |
| ENV ×2 | TG1 (no 3D suite installed), E2E-2 (**Paint already open and it is the USER'S** — the test refuses to drive or close it) | environment |

Two consequences for how this file gets executed:
* Run the suite on an otherwise-**idle** machine with **no other Hojaiga process alive**, or the
  pointer and window-count checks contaminate it. `--e2e` APPENDS to the results file — always read
  the LAST header, never the file.
* "The capture cluster is ES1/S2/MIN1/E2E-2" from the readiness report is only partly true: in this
  run ES1 and S2 **passed**, and three of the nine failures are pointer contamination.

Target for job 1: **no new failures vs the 16:07 run, MIN1 and E2E-1 flipped to PASS, and EYE1
PASS**. Update this section with the run's own header time after every suite run.
