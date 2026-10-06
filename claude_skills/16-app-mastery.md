---
name: hojaiga-app-mastery
description: The app-knowledge engine - how Hojaiga learns HOW any app works from code only (static program-file harvest, structural frontier exploration with verified unwind, tested conventions, unified command registry, knowledge bridge into the loop), what it stores, how to ask it, and its measured accuracy and limits. 2026-10-05.
---

# Skill 16 - App mastery (learn how ANY app works, with code, not training)

Goal: hand it any app at any moment and it knows how the app works - instantly for what the program file already says, more with
every (invisible, resumable) live run. Nothing is trained; nothing is per-app. Four generic mechanisms feed one database:

```
STATIC      pe_resources + static_knowledge   what the program FILE says, no launch (ms)
STRUCTURAL  organ_63 derive_state / frontier  one bulk UIA read -> state variables + every unopened surface, ranked by info gain
EXPLORED    organ_63 Prober                   open each surface with a defined, VERIFIED unwind; E2 never touched
HYPOTHESIS  organ_63 test_conventions         universal chords (Ctrl+O/F/H...) TESTED on this app; "does it take posted keys at all?"
                      |
                      v   knowledge_store (bm_facts, bm_dialogs, bm_frontier, bm_statevars, bm_conventions, bm_run_log) + organ_48 tables
          command_registry: ONE unified map (merge by canonical label, count independent sources, ordered ROUTES)
                      |
                      v   knowledge_bridge -> desktop_grounding loop: hint / verified direct route / declared-accelerator attempt /
                          precondition + mode repair / transition recording
```

## Entry points
| Call | Does |
|---|---|
| `organ_63_app_mastery.know(app)` | dossier NOW from static knowledge (never launches); `live=True` runs mastery first |
| `organ_63_app_mastery.master(app, runs=N, budget_s=S)` | static -> hidden launch -> scan -> state vars -> frontier explore -> conventions -> unify; cumulative |
| `organ_63_app_mastery.ask(app, "save as")` | ranked commands + ordered routes (WM_COMMAND id / menu path / key / control / context) |
| `command_registry.dossier(model, key)` | identity, toolkit + how to drive it, commands by source, dialogs, state vars, conventions, **gaps** |
| CLI | `python organ_63_app_mastery.py know|master|ask|static <app>` (`HOJAIGA_BEHAVIOR_DB=...` for a scratch DB) |

## 1. Static harvest (no launch, no UI) - `pe_resources.py`, `static_knowledge.py`
* **PE resources** (ctypes + struct, no pefile): RT_MENU (classic + MENUEX), RT_ACCELERATOR, RT_STRING, RT_DIALOG, version, manifest,
  and the `.mui` language file next to the exe. Menu items, accelerators and prompt strings are joined **by command ID**: a command
  has its path, its chord, its `WM_COMMAND` id (headless route) and its Alt-key mnemonic chain. Context menus come free.
  Validated against **Windows' own loader** (`LoadMenuIndirectW`): 60 menu resources, 0 mismatches (suite KP1).
* **Help-string join is gated**: string IDs only describe commands in MFC-style programs (Notepad's string 1 is an error message,
  command 1 is File > New). The join is used only if >= 40% of commands share a word stem with their string.
* **PE headers**: imports (read by seeking: a 75 MB exe = 0 ms), GUI/console, .NET, manifest `requestedExecutionLevel` -> elevation = HITL.
* **Toolkit fingerprint** (data table `FRAMEWORKS`): Electron/Chromium/CEF, WinUI3/UWP-XAML, Qt, Java, GTK, wx, Tk, Flutter, Unity/SDL,
  Office ribbon, MFC, WPF, WinForms. Evidence is weighted: an *import* (3) beats a *file lying nearby* (1); a shared system dir
  (System32, Program Files root) is never scanned for siblings. Each toolkit carries a **strategy** (UIA quality, native menus?,
  input order, posted keys/mouse behaviour, OCR fallback) - measured facts of this repo (XAML ignores posted keys, Chromium builds
  its tree after an accessibility wake, CEF can stay empty).
* **What it opens**: registry file associations (reverse-indexed once) + Store `AppxManifest.xml` (file types, verbs with CLI
  parameters, protocols, alias); `cli_open` = the command line that opens a file.
* **Shipped data found by SHAPE**: keymap/keybinding/settings files, manifest `contributes` (commands + keybindings), Electron
  `package.json` read out of `app.asar`. Settings: only boolean KEY NAMES are recorded, never values.
* **Capability profile** (`infer_profile`): which generic UI vocabularies the labels exhibit + the share of file-type categories the
  app opens -> archetype by evidence. A kind needs >= 2 independent supports AND a *defining* capability (shared file verbs are not
  enough); otherwise `unclassified`. organ_47 `classify_archetype` asks this evidence FIRST and falls back to name tokens only for an
  app nothing is known about.

## 2. Frontier + verified exploration - `organ_63_app_mastery.py`
* **State variables** from one `fast_uia` snapshot (now also toggle state): `toggle`, `exclusive` (tabs/radios/tools -> which is
  active), `expand`. Their signature is the **mode indicator** in every snapshot and transition.
* **Frontier** (`bm_frontier`, persistent): `tab`, `opener` (ellipsis), `expander`, `toggle`, `button`, `context` (spatial targets).
  Window chrome (title bar, Minimize/Maximize/Keep on top...) and destructive-looking controls are recorded `unsafe` and never probed.
* **Probes** (each: act -> observe -> capture -> UNWIND -> verify):
  tab (select, read revealed controls, reselect; then explore *inside* the tab), expander (expand/read/collapse), toggle (flip and flip
  back), opener (open, capture the dialog **schema** - fields, commit/cancel buttons - close via Escape then WM_CLOSE), inline button
  (SURFACE = flyout/pane: items become commands + deeper `@via:` frontier rows, closed by a ladder popups -> toggle opener -> its own
  Close/Back; MUTATION = content changed: recorded as a transition from the new state, never blindly undone), **context menu** (posted
  `WM_CONTEXTMENU` to the child window under the target; measured ~0.4 s on a XAML host; closed with `WM_CLOSE`).
* **Guards**: `ensure_baseline()` before each probe (a left-open surface is closed first), window-lost detection (a probe that minimises
  the window stops the run), per-family stop after 2 unwind failures, `pristine` check (mutating probes only on a clean disposable
  instance: no modified marker, no editable content), polite mode (a window the user can see is read passively only).
* **Budget**: `DiscoveryBudget` extends while probes keep yielding, stops on a flat patience window or the hard cap.
* **Conventions**: Ctrl+O / F / H / G / , / Ctrl+Shift+P / Ctrl+Shift+S (the last only on a pristine untitled document) are pressed, a
  new window/control is the evidence, the dialog is captured and unwound. After 3 ignored chords the rest are skipped. Outcome also
  stored as fact `key_delivery` (works | not-delivered) which the route planner obeys.
* **Runs are cumulative**: run N+1 continues from the persisted frontier; `bm_run_log` holds the learning curve.

## 3. Unified registry - `command_registry.py` (backlog 2.6)
Rows from static / live-menu / explored / layout / pack sources merge on the canonical label (no `&`, ellipsis, embedded
`(Ctrl+B)`). Each unified command keeps every shortcut with the **sources that agree**, menu IDs, automation IDs, help, Alt chain, trust,
`corroborated` (= number of independent source kinds), pre/post conditions. `routes_for`: WM_COMMAND (native-menu toolkit) -> UIA menu
path -> key (only if key delivery is proven) -> context -> control invoke -> Alt chain. `gaps()` lists what is NOT known and why.

## 4. The seam into the loop - `knowledge_bridge.py` (+ desktop_grounding, organ_47)
* Hint always: the best unified command ranks the judge's shortlist (`pro_hint` shape).
* **Direct control** only for a VERIFIED command: >= 2 verified successes (6.4; organ_47 `successes` counts PASSes only - `hits` also
  counts failures and used to enable direct control after ONE weak pass), a postcondition, the label covers the whole goal, not E2.
* **Declared accelerator attempt** (4.2): shortcut declared by >= 2 independent sources + key delivery proven + never failed.
* **Preconditions / modes** (3.2): a command with `mode_is` pre is never fired in the wrong mode; `path_to_mode` repairs (Tab -> edit),
  else the step is refused.
* **Transitions** (3.3): every verified step writes (state signature incl. mode indicators, action, effector) -> (state', evidence),
  reinforces the command and records the effector outcome.
* **Template first** (3.1): `task_lifecycle.try_template_first` runs from `_loop_first_preamble` before any goal planning.

## Rules for extending
1. Knowledge is DATA or a generic rule (a toolkit row, a label vocabulary, a convention row). Never `if app == "X"`.
2. A new source = a new harvester that returns command dicts; it enters at `catalog` trust. Only an observed effect + verified unwind
   (`_promote`) or a verified loop PASS earns `learned`.
3. A new probe kind = a method on `Prober` that ends with an UNWIND and a verification; register it in `_GAIN`/`_KIND_ORDER`.
4. Every number you report comes from a run (`mastery_bench.py`, suite KM1/KC1/KT1...).

## Pitfalls found building it (see also 09)
* `id(connection)` as a cache key is wrong - Python reuses ids after GC; a new DB was believed to have its tables (KC1/KT1 failed).
* A posted Escape is not delivered to a XAML popup; `WM_CLOSE` on the popup window closes it. UIA `ShowContextMenu` and Shift+F10 do nothing
  on a XAML host; a posted `WM_CONTEXTMENU` to the child window under the point works.
* Pressing "Minimize Calculator"/"Keep on top" as an exploration probe destroys the scan: window chrome is never a frontier item.
* "Open Navigation" is not "open a file": file-operation capabilities match only when the word IS the label.
* Calculator's converter list ("Volume") made it a media player until single-keyword evidence was disallowed.
* A single `.nfo` file type + shared file verbs made `msinfo32` a text editor until a *defining* capability was required.


## 5. Added 2026-10-05 (work order rev 2): what is built, measured, and what is not
| Piece | Module | Measured |
|---|---|---|
| Pointer sentinel (who moved the mouse) | `pointer_sentinel.py` + runner | PTR1 12/12; hardware vs injected vs unattributed; KM1 ended ABORTED-ENV (hand, 971 px) instead of FAIL |
| Escalation screenshot on every need-human row | `task_lifecycle.capture_evidence` | ES2 7/7; LC2 live: PNG 4544 bytes attached to the queue row |
| Shipped command lists, DEMOTED | `preload_sources.py`, `pe_imports.py` | OBS: 154 request names from the websocket plugin in 0.8 s; VS Code 518; every one `archetype` trust until a live probe corroborates it |
| 1-second capability summary | `command_registry.capability_summary` | CAP1 9/9, 15 ms; surfaces with a verified task are named, the rest say "only READ" |
| First contact in seconds | `fast_scan.deep_scan`, `scan_desktop(fast=True)` | Calculator 11.0 s, Notepad 14.5 s INCLUDING app start (excl. launch 8.4 / 9.3 s); Word 25, PowerPoint 33, Excel 34, OBS 29.5: NOT under 10 s for complex apps |
| One place every action leaves | `dap_actuator.py` (family -> ordered providers, trace) | ACT1 9/9; no physical provider; Chromium provider acts through the RAW view |
| Popup that exposes nothing | `popup_visual.py` + `OCREngine.words` | PV1 8/8: painted dialog read by DAP capture+OCR, `Not now` pressed by a posted click, an elevation prompt in the same disguise escalated |
| Parallel child cursors | `loop_first.run_loop_first(parallel=True)` | Word + Excel at once: 201 s vs ~288 s sequential, two sprites, distinct paths, both files valid |
| Canvas drawing without pointer input | `canvas_paste.py` | image -> clipboard -> app Paste -> save; clipboard overwritten only with the user's OK, text restored. See the open item below |

Office save-to-path (the proof case): Excel 139 s / Word 149 s / PowerPoint 168 s, all unattended, files verified valid OOXML (see 09 P-30 for the three
root causes). Crash relaunch (4.3) was already proven live by G2L and passes.

Open / not proven: Paint draw end-to-end (the paste goal needed a canvas-change postcondition and the run was disturbed by another suite);
Steam not exercised; Discord/WhatsApp (tray-parked Chromium) accept ValuePattern writes but the page applies them seconds later; GDI leak not
reproduced after one occurrence; E2E-1 passes but is slow (patience waits).

## 6. Added overnight 2026-10-06 (complex apps: OBS, VS Code, Zoom, Discord/WhatsApp read-only, YouTube)

What was measured (fresh behaviour DB per app, `mastery_bench.py`; Discord/WhatsApp were READ only - no typing, no probing, the user's own windows):
- **OBS Studio**: recall of resting controls 0.5 -> 0.955, 4 -> 44 controls, menu-path precision 1.0 (65 paths), once its "Crash Detected - Run in Safe Mode / Run in
  Normal Mode" start-up question was answered (it had been scanned AS the application). `popup_policy.looks_like_dialog` + `choose_button` (body buttons first).
- **VS Code (Electron)**: 2057 commands, 11 transitions; `master()` failed with "window not found after the scan" until it used the window the scan LAUNCHED
  (the typed name "vscode" never matched the title "Visual Studio Code"). `resolve_app` now handles abbreviations (`_abbrev_match`).
- **Zoom**: 2380 "commands" were the client's INTERNAL class library (Get/Set names) read as an API; `MAX_API_NAMES = 500` rejects it, API-derived entries
  rank below controls and are never a quick answer.
- **Discord**: static harvest by NAME found nothing (versioned install folder); retried by WINDOW: Electron/Chromium, 121 static + 53 live commands.
  A contact's name ("Open conversation with <name>") reached the knowledge DB: `redact` now covers person-bearing labels, list/tree ITEMS are not commands.
- **YouTube / web** (`universal_scan.scan(url)`, own headless Chrome, no profile): home 34 controls in 6.9 s, watch page 251 in 18.4 s, results 141 in 11.9 s;
  Excalidraw (canvas app) 36 controls, "canvas-interior:needs-ocr-or-vision" is reported, not hidden.
- **Steam**: sign-in screen (credentials) -> escalate; CEF exposes only its title bar through UIA (4 nodes), OCR reads the text. The loop pressed the
  title-bar Close and "passed" `open the Library tab` and LEARNED it at 0.97 (CHR1 fixes it: title-bar buttons are never offered / taught, a vanished window
  is WRONG_STATE, a blank "names changed" pass is not reinforced).

Root cause of the old "in-suite degradation" and DAY1: the popup guard gave the foreground back to the user the moment a parked WinUI app took it when its
flyout opened; that DEACTIVATES the window and the flyout closes (`empty-menu:File`). A Paint menu crawl returned 13-41 commands (35% of runs degraded);
with the hand-back off: 41/41 in 4 of 4 runs and ~30% faster. Policy now (`FOCUS_IDLE_MS`, `user_idle_ms`): while nobody has touched the keyboard or mouse
for 1.5 s the app may hold the foreground; the instant a person does, it is handed back, and always at session end (`restore_focus`).
