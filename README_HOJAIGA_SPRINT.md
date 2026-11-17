# HOJAIGA Sprint: Deep App Knowledge

**Status:** Running and verified on this machine (Notepad + Calculator via UIA;
Blender via the OCR fallback — a UIA-blind OpenGL app the OCR path exists for)
**Location:** `D:\new_automation\All codes\core_organs\hojaiga_sprint_*.py`
**Output:** `D:\new_automation\data\knowledge_bases\<app>_knowledge.json`

This is the working version of the sprint spec. The four modules were rewritten
after the first drafts proved non-runnable; everything below is what actually
executes, with measured numbers rather than targets.

---

## Quick start

```powershell
cd "D:\new_automation\All codes\core_organs"

python hojaiga_sprint_main.py --apps              # what is on screen right now
python hojaiga_sprint_main.py --scan Notepad      # launch if needed, learn, save
python hojaiga_sprint_main.py --query Notepad save
python hojaiga_sprint_main.py --list              # what has been learned so far
```

No app has to be opened by hand — `--scan` starts the app if it is not visible
(packaged/UWP apps are resolved through the Start menu AUMID, the same way
`universal_scan.py` does it elsewhere in this repo).

Dependencies (already installed here):

```powershell
pip install uiautomation mss pillow numpy psutil
```

`pyautogui` is deliberately **not** used: this repo refuses physical input outright
(`core_organs/headless_input.py` → `physical_input_blocked()`: *"Always refuses: there is
no opt-out"*) and provides posted-message input instead. The prober now goes through
that layer for every key, click and character.

An OCR engine is **optional** and only loaded when you pass `--ocr`, or when a
window exposes fewer than 5 actionable controls. The engine preference is
**easyocr first, PaddleOCR as fallback**: on this machine PaddleOCR 3.x cannot read
its own `.paddlex\official_models\*\inference.yml` cache (OS access-denied) and takes
~130 s to load, while easyocr's models are already cached in `~\.EasyOCR\model`
(`craft_mlt_25k.pth`, `english_g2.pth`) and run offline. UIA still does the heavy
lifting for every app that publishes labels — OCR is the path for the ones that don't.

---

## What the four modules do

| File | Role |
|---|---|
| `hojaiga_sprint_perception.py` | Finds the window, walks the real UIA tree, screenshots the window region |
| `hojaiga_sprint_prober.py` | Opens menus and reads their commands, actuates controls through UIA patterns, diffs the window, detects dialogs, reverts |
| `hojaiga_sprint_knowledge.py` | Stores elements + verified interactions, derives capabilities, answers queries |
| `hojaiga_sprint_main.py` | CLI: window resolution, app launch, budget, save, query demo |

### Why the approach changed

The first draft used `win32gui.FindWindow(None, "Notepad")` plus
`EnumChildWindows`. Both fail on Windows 11:

- titles are `"Untitled - Notepad"`, not `"Notepad"`;
- Notepad, Calculator, Office, Chrome and every Electron app draw their own
  controls inside **one** top-level window, so child-window enumeration returns
  an empty list even when 300 controls are on screen.

UI Automation sees what the user sees. Calculator's full tree (127 nodes with
pattern detection) walks in **0.4 s** — the screenshot-plus-OCR pipeline the
blueprint proposed is only a fallback for apps that publish no UIA.

---

## Real output

`python hojaiga_sprint_main.py --scan Notepad 75 --text-tab` on a clean, empty
editor (68 elements, 30 interactions stored) - the run that proved typing:

```
[1] + Window: 'Untitled - Notepad' (hwnd=..., class=Notepad)
[2] Scanning app structure ...
    + 68 UIA elements, 20 actionable, 0 OCR regions in 1.26s
[3] Discovering interactions (budget 75s) ...
[PROBE] Reading menus (12s)...
  [M] File           offers 21 commands: close window, ctrl n, ctrl o, ctrl p, ctrl s ...
[PROBE] 14 actionable elements queued (2 skipped as destructive)
  [2] + Add New Tab                        -> creates_or_opens (uia-invoke, 0.038)
  [6] + Edit                               -> ui_changed (uia-invoke, 0.056)
  [10] + Lists                              -> replaces_view (post-click, 0.963)
[PROBE] Budget exhausted after 29 discoveries
  [T] scratch tab created by ctrl+t
  [+] text input                          -> accepts_text_input
    + 30 verified interactions in 107.1s
[5] + Saved: D:\new_automation\data\knowledge_bases\notepad_knowledge.json
[6] Query demo:
    can save      True
    can create    True
    can open      True
    can find      False     <- Edit menu not read as a menu root this run
    can text      True
    can settings  False
```

Note the honest caveats in that real output: the budget overshot (75 s given, 107 s
spent), only the File menu was enumerated, and `can find` is therefore False - all
covered under Known gaps.

`python hojaiga_sprint_main.py --query Notepad save`:

```
[QUERY] Notepad: save
Answer: True
  1. open the File menu, then choose  Save As   [offers_command]
  2. open the File menu, then choose  Save   [offers_command]
  3. open the File menu, then choose  Save All   [offers_command]
```

`python hojaiga_sprint_main.py --query Calculator calculate`:

```
[QUERY] Calculator: calculate
Answer: True
  1. uia-invoke 'Equals' at (554, 698)   [local_change]
```

Blender is the app the OCR fallback was built for. It draws its entire UI inside one
`GHOST_WindowClass` OpenGL canvas, so UIA sees only ~7 frame elements and names
nothing. The fallback raises the window to the true foreground, screenshots the
region, runs easyocr, turns each text box into a click target, and probes it with a
posted click. `python hojaiga_sprint_main.py --scan Blender 90`:

```
[2] Scanning app structure ...
    + 7 UIA elements, 4 actionable, 93 OCR regions
[3] Discovering interactions (budget 90s) ...
    + 25 OCR click targets added (UIA candidates < 5)
  [+] Layout          -> replaces_view (post-click, 0.42)   [source: ocr]
  [+] Modeling        -> replaces_view (post-click, 0.41)   [source: ocr]
  [+] Scripting       -> replaces_view (post-click, 0.40)   [source: ocr]
  ... (workspace tabs, mode selector, header menus)
    + 16 verified interactions (all source: ocr)
```

The workspace tabs (Layout / Modeling / Sculpting / …) are correctly classified as
`replaces_view` — clicking one swaps the whole viewport, and the pixel diff proves it.

Measured so far (current contents of `data\knowledge_bases`):

| App | UIA elements | Scan time | Interactions stored | Probe time |
|---|---|---|---|---|
| Notepad (plain editor, `--text-tab`) | 68 | 1.3 s | 30 (21 from File menu + text input) | 107 s |
| Calculator (modes view) | 195 | 0.6 s | 6 | 37 s |
| Blender (UIA-blind → OCR) | 7 UIA + 93 OCR regions | 0.4 s UIA + ~60 s OCR | 16 (all `source: ocr`, from 25 click targets) | ~90 s |

Interaction counts are **not** stable across runs - they depend on the live window's
state (menu layout, visible toolbar) and on the recording threshold below, which is
why a Notepad run once stored 63 and the next, on a plainer window, stores 30. The
store is a snapshot of one scan, not a census.

---

## Honest performance note

The blueprint promised "any app in 15-20 seconds". That number is not true for
element probing, and the code does not pretend it is:

- **Perception is fast**: 0.4 s for a 127-element app.
- **Menu reading is fast and cheap**: opening File/Edit/View/Help and reading
  their text yields dozens of commands in a few seconds. This is where
  `save`, `print`, `find` come from — nothing gets clicked.
- **Element probing costs ~2 s per actionable element** (activate, before
  frame, actuate, settle, after frame, dialog check, revert). A 40-button app
  therefore needs 60-90 s, not 20.

Budget is a parameter, not a promise: `--scan <app> <seconds>`. Menu reading
and shortcuts always run first, so a short budget still produces useful
knowledge instead of a truncated click sweep.

---

## Safety rules baked into the prober

Probing drives a real, running app, so every action is bounded:

- **No physical input.** Clicks, keys and characters are *posted* to one specific
  `hwnd` through `core_organs/headless_input.py` (`post_click`, `post_key_combo`,
  `post_text`, `focused_control`). No cursor moves, no global keystroke is fired,
  and a message cannot land in whichever window happens to hold focus. The repo
  refuses physical input outright — `physical_input_blocked()` is documented as
  *"Always refuses: there is no opt-out"* — and an early draft that ignored this
  both lost its keystrokes silently and once scribbled probe text into a document
  the scan did not own.
- **Delivery is proven, not assumed.** A capability is recorded only when the text
  actually appears in the field, read back through `ValuePattern`. Pixels changing
  somewhere else is *not* evidence of typing (a flyout opening moves pixels).
- **Cleanup is verified.** After typing, the prober deletes what it sent and then
  compares the field against the exact string it found there. Only a field that
  was empty before the probe gets a select-all + delete reset — there, clearing
  everything is provably the same as undoing the probe. If the restore cannot be
  confirmed, the run prints the residue and stops instead of moving on to the next
  field.
- **No `Ctrl+S` probing.** A document with a path saves silently. Save/Open are
  learned from menu text instead. `--shortcuts` only tries `Ctrl+N` and `Ctrl+F`.
- **Dialogs are dismissed with Cancel/No/Don't Save — never OK**, which would
  write the file the dialog was about to create. Labels are matched with all
  punctuation stripped, because `"Don't save"` normalises to `"don t save"` and a
  silently unmatched button leaves the prompt open in front of every later probe.
- **Destructive and chrome controls are skipped** (close, exit, delete, format,
  minimize/maximize/restore, the account avatar) unless `--dangerous` is passed.
- **`TabItem` is not clicked** — those are the user's open documents.
- **Clicks are clamped to the target window's rectangle**; the prober never
  addresses a point outside the app it is teaching.
- **`--text-tab` goes one step further and never touches the user's document at
  all**: it creates a scratch tab or window itself, proves the new document is the
  one it just made (tab count went up, or exactly one new window appeared), types
  there, clears it, and closes it answering only "Don't save". If it cannot prove
  ownership, it declines to type and reports the capability as unproven.

Side effect that remains: a scan opens and closes menus and activates the window.
Run scans on apps you do not mind being handled.

---

## JSON format (schema_version 2)

```json
{
  "schema_version": 2,
  "app_name": "Notepad",
  "properties": {"scan_time": 0.42, "probe_time": 29.8, "hwnd_title": "...", "window_class": "..."},
  "elements": [{"label": "Save", "control_type": "Button", "x": 0, "y": 0,
                "width": 0, "height": 0, "action": "invoke", "enabled": true}],
  "interactions": [{"label": "File: Save As", "effect_type": "offers_command",
                    "method": "read-menu", "source": "uia", "change_magnitude": 0.0}],
  "capabilities": [{"verb": "save", "confidence": 0.8, "evidence": [...]}]
}
```

The field names mirror the tables in `DATABASE_SCHEMA.md`, so a scanned app can
be pushed into SQLite (and into `organ_63`) without a conversion layer. The JSON
is the source of truth for now; the database is the next layer, not a
prerequisite.

---

## CLI reference

```
--scan <app> [budget_seconds]     learn an app and save its knowledge
    --shortcuts                   also probe Ctrl+N / Ctrl+F
    --ocr                         force OCR (easyocr) on top of UIA
    --dangerous                   allow destructive controls to be probed
    --max-elements <n>            cap probed elements (default 60)
    --out <path>                  write the JSON somewhere else
    --no-launch                   only scan a window that is already open
    --keep-open                   leave an app the scan started running
    --text-tab                    create a scratch tab/window, prove typing there,
                                  then clear it and close it (opt-in)
--query <app> <question>          can it do X, and how
--apps                            list visible windows (title / process / size)
--list                            summary of the knowledge library
```

---

## Known gaps

- `accepts_text_input` is now **proven live** through posted input: a clean
  Notepad scan created its own `Ctrl+T` scratch tab, typed the marker there, read it
  back, cleared it and closed the tab - `notepad_knowledge.json` records "typed into
  a fresh tab we created, then closed it". This was hard-won: an earlier capture had
  leaked the marker into the user's own document and only checked the field's
  `ValuePattern`, so it was withdrawn as a false capability. That incident is why the
  text probe now ALSO diffs window titles before/after and treats any marker showing
  up in a title as residue it refuses to record.
- Sensitivity threshold discards real knowledge. An interaction is only recorded
  when something visibly moved (`>2%` of the window, a dialog, or a menu expand),
  so single keystrokes in an app whose display is mostly empty are dropped: one
  Calculator run stored 6 interactions from 195 elements, and the Notepad `File`
  menu button itself measured 0.009 and was kept only because it expands. This is
  a deliberate safety trade, not a bug, but the number of *learned* verbs is not
  the number of *known* controls.
- The budget is only checked between element probes, so a run overshoots by the
  length of the probe that was already in flight plus the trailing text probe: Notepad
  scans given 45 s spent 78.6 s, and given 75 s spent 107.1 s. A single probe costs
  ~2 s (settle waits up to 1 s), so the overshoot is bounded but real.
- Menu reading is not exhaustive: a clean Notepad re-scan enumerated only the
  **File** menu (21 commands) as a readable menu root; **Edit** was probed as a
  button and **View** opened a flyout, so neither contributed their command text and
  `--query Notepad find` still returns False (Find lives under Edit). `_menu_roots`
  finds the first reliably-expandable menu, not all of them.
- OCR path is now **tested live on Blender** (see Real output above): easyocr reads
  the OpenGL canvas UI that UIA never names, and posted clicks turn those regions into
  verified `source: ocr` interactions. Honest caveats: OCR is slow (~60-90 s per
  full-window read on CPU, so a Blender scan overshoots a 90 s budget); OCR labels carry
  noise (title-bar text, stray digits like `1z Global` / `72 84`); and the query path
  deliberately matches control LABELS on whole words only, so `--query Blender text`
  is now correctly **False** — it used to light up on "Texture Paint" as a substring
  false positive. The one hard requirement the OCR path forced: because mss/PIL capture
  reads the *physically visible* pixels, the target must be truly foreground before the
  grab, or OCR reads whatever window is on top (the wrong app). `ensure_foreground()`
  does this with an `AttachThreadInput` raise — `Window.SetActive()` alone is refused by
  the Windows foreground lock when another process holds focus.
- Only three apps have been scanned (Notepad, Calculator via UIA; Blender via OCR).
  The system is proven, not yet broad.

## Roadmap from here

1. ~~Build/enable the screenshot+OCR perception path.~~ **Done** — a live Blender scan
   (UIA-blind, 7 elements) now yields 16 verified `source: ocr` interactions via the
   easyocr fallback. Remaining polish: OCR label noise filtering and cost.
2. Cut cost per probe (skip the dialog sweep when pixels did not move) so budgets bite.
3. Push `schema_version 2` JSON into the SQLite tables from `DATABASE_SCHEMA.md`
   and bridge into `organ_63` — additive, so `organ_63` keeps working.
4. Scan set: Word, Excel, Chrome, OBS, File Explorer — and more UIA-blind apps
   (games, GPU canvases) to keep exercising the OCR path.
