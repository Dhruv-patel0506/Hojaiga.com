---
name: hojaiga-atlas
description: The Atlas layer - learn how ANY application works at developer level (stack, object model, data model, extension surfaces), how it answers every mouse gesture, what each control opens, and plan tasks from that knowledge. Four speed tiers, evidence-bound claims, free keyless sources, honest about what cannot be learned. 2026-10-08.
---

# Skill 17 - Atlas (learn any app, deeply, with evidence)

One entry point: `All codes/core_organs/hojaiga_atlas.py` (package `core_organs/atlas/`). No per-app code anywhere; data tables
(`atlas/data/lib_signatures.json`, `taxonomy.json`) describe LIBRARIES and KINDS of software, never applications.

```
python hojaiga_atlas.py learn   <app> [--tier instant|fast|deep|full] [--budget S] [--hwnd N] [--no-web] [--json]
python hojaiga_atlas.py know    <app>        developer-level report (Markdown) from everything stored
python hojaiga_atlas.py ask     <app> "<q>"  answer ONLY from evidenced knowledge (facts + trust + evidence)
python hojaiga_atlas.py plan    <app> "<task>" [--execute --hwnd N]   grounded plan (+ headless execution with verification)
python hojaiga_atlas.py gestures <app>       the gesture atlas (measured + published)
python hojaiga_atlas.py web     <name>       public knowledge only (works for apps that are not installed)
python hojaiga_atlas.py loop    a b c --cycles N --tier deep   overnight: each app in its own watchdog subprocess
python hojaiga_atlas.py selftest [--live]    AT1-AT14 offline + AL1-AL4 against the fixture app
```

## The law of the layer: knowledge is measured or sourced, never asserted
`atlas.common.AtlasStore.put_claim` REFUSES a claim without evidence. Trust classes: `measured` (a probe observed it) > `static` (read from the
program's own files) > `published` (public document, with the exact quote) > `inferred`. Same statement from two sources merges: strongest trust
kept, evidence unioned. The language model (local Ollama) never adds facts: every distilled claim must quote its source and the quote must (a)
exist in the document and (b) carry the claim (`distill.supported`).

## Tiers
| tier | what runs | measured |
|---|---|---|
| instant | devscan (developer harvest) + program-file harvest + CACHED public knowledge; no launch, no network wait | 0.4-2.3 s per program |
| fast | + live structure scan (engine deep_scan: UIA tree, menus, ribbon, layout); OCR labels when UIA is empty | ~25 s |
| deep | + `explorer` (menus, tabs, openers, dialog protocol) + `gestures` + blind-app perception | fixture: 100% of ground truth, ~45 s explorer + ~35 s gestures |
| full | + independent UIA recall, exhaustion proof (second pass finds nothing new), oracle coverage, engine explorer (bounded) | minutes |

## Modules (what each one knows)
* `devscan` - install tree (own files only when the program sits in a shared folder/drive root), PE imports of the WHOLE tree -> libraries/APIs ->
  toolkit, language, rendering, audio, video, network, storage, scripting, AI/compute; build tags; CLI switches; endpoints; plugin folders; COM
  classes + URL protocols; persisted-data SCHEMA (key and column NAMES only, never values) = the data model.
* `comlib` - registry index (program -> COM classes, protocols, App Paths; cached) and type-library enumeration = the program's OBJECT MODEL
  (Word: 767 types / 14,778 members in 0.05 s, every method name kept for planning).
* `webknow` - Wikidata (kind, written in, platforms, licence, SOURCE REPO), Wikipedia text, GitHub (languages, README, tree, shipped keymaps). Keyless, cached
  with provenance (`atlas_docs`), replayable offline (`HOJAIGA_ATLAS_OFFLINE=1`, or cache-only in the instant tier). Name-only works (Blender, Mixxx verified).
* `keymaps` - shipped keymaps in 5 shapes (python tuples, json, ini, xml, text tables) -> input grammar. Blender: MMB press = view3d.rotate, Shift+MMB = move,
  Ctrl+MMB = zoom, left drag = transform.translate - from its own source.
* `motion` - what a gesture did, from pictures: pan / zoom / rotate / scroll / nonrigid / rubber_band / shape_draw / stroke / translate_object / local_change /
  none, every rigid estimate VERIFIED by warping (19/19 synthetic, plus live ground truth). Volatility masks make blinking/animated pixels invisible; painted-extent
  detection crops unpainted margins (DPI-virtualised windows).
* `gestures` - headless posted input (hover, click, right-click, double-click, hold, wheel, drag with every button, Shift/Ctrl/Alt) on regions AND on objects found by
  segmentation. Each gesture is undone and the undo PROVED by pixels (leftover object = not restored; 1-4 px backlash = restored).
* `explorer` - menus (read from the open menu), tabs, openers, dialog protocol (master/detail list/tree/tab, wizard pages, Cancel never commit) with verified unwind.
* `blind` - for UIA-blind apps: OCR labels, menu-bar cluster by gap analysis, hover reactivity + tooltip OCR, menu opening (only when posted pointer input works).
* `scanner` - the orchestrator; `coverage` - independent recall / exhaustion / oracles (truth file, PE menu resources); `architect` - kind by evidence voting + report;
  `planner` - task -> routes (control, dialog path, shortcut, COM method, CLI switch, gesture, scripting) ranked by evidence and measured input channels, `execute()` for
  headless effectors; `qa` - retrieval + cite-checked synthesis; `evolve` - prediction ledger, active ordering, drift, overnight loop.

## Measured facts that shaped the design (do not re-learn them)
1. **A UIA Invoke on a control whose handler opens a MODAL dialog blocks every UIA call into that process** (>25 s, also from a second process). Open modal surfaces
   asynchronously (Win32 `BM_CLICK` to the button window; posted click) or invoke on a worker thread and read the dialog with Win32 (`EnumChildWindows`, `LB_GETTEXT`).
   `explorer.trigger` is that ladder. The engine's own explorer spent 145 s and learned 0 dialogs on a WinForms app before this.
2. **A modal menu loop reads the PHYSICAL pointer**: a posted click on a drop-down item closes the menu. Invoke menu ITEMS through UIA on a worker thread.
3. **Unowned drop-downs (WinForms ToolStripDropDown, WPF popups) appeared on the real screen** because the popup guard matched only owned windows;
   `background_window.is_target_popup` now also matches an unowned caption-less WS_POPUP tool/topmost window of the same process.
4. **Non-DPI-aware windows**: UIA/screen coordinates are physical, the app paints LOGICAL pixels (PrintWindow returns a bitmap with an unpainted margin) and Windows scales
   posted lParam itself: never convert coordinates when posting, only when mapping pictures (`gestures.dpi_ratio`).
5. **Capture a region from its own child window** when it has one: PrintWindow of a parked, resized top-level window painted only the OLD size.
6. **A freshly parked window's UIA tree is empty for a while** (frame buttons only): `scanner.ensure_tree` nudges the layout and waits before calling a window blind;
   start CPU-heavy analysis AFTER the park (GIL contention made the park fail).
7. **`ctypes.windll.user32` is shared and other modules rewrite its argtypes**: a pointer LPARAM overflowed silently. Use a private `ctypes.WinDLL("user32")` with explicit
   signatures (explorer does).
8. **Some applications ignore posted pointer AND key input entirely** (GHOST/OpenGL tools read the physical pointer): Blender 5.2: wheel, middle-drag, hover, F3 all
   delivered, none effective. Recorded as `input.channel` (measured); planner demotes pointer routes and promotes scripting/COM/CLI routes. See Blender section.

## Blender (live test on the user's own window, read-only/view-only)
UIA sees 7 nodes (frame only). Invisible parking + PrintWindow captures the full OpenGL UI. OCR reads menus, workspace tabs, outliner, transform fields. The static harvest
gives OIDN/Embree/OpenVDB/USD/OpenEXR/OCIO/CUDA/Vulkan + embedded Python + `5.2/scripts` (490 files). The published keymap gives the pointer grammar. What cannot be done
headlessly: hover/click/drag/keys (ignored). Routes left: the embedded Python (`blender --python`), command line, or a human/physical channel (HITL).

## Tests
`si_tests_atlas.py`: AT1-AT14 offline (evidence law, signatures, static harvest of real programs, COM model, motion accuracy, keymap formats, quote-verified distillation,
cache determinism, learning, planning, Q&A, classification, restore logic, blind structure); AL1-AL4 live against `atlas/fixture/AtlasFixture.exe` (C# 5, built by
`fixture/build.py`; it exposes its own state in a label and its truth in `--truth <file>`).

## Host-API introspection (atlas/introspect.py)
Programs that embed a scripting API can be asked what they have, headless, in a SEPARATE invisible process (never the user's running window).
Recipes live in `atlas/data/introspect_recipes.json` (chosen by exe-name / marker-file evidence), scripts in `atlas/data/recipe_*.py`. Opt-out: `HOJAIGA_ATLAS_INTROSPECT=0`.
Blender (bpy 5.2.2): 4 s, 2499 operators, 399 replayed menus, 1235 panels, 31 RNA structs -> 528 claims (api.*, model.struct, ui.workspace); planner route `api_operator`
(execute() reports it as not-executable-headlessly and gives the call, e.g. `bpy.ops.mesh.primitive_cube_add()`). Keymaps are empty in background mode: they come from the published keymap file.
Tests: AT15 (offline). Suite: 15 offline + 4 live = 19/19.

## UI cartographer + teacher (atlas/uimap.py, teach.py, manual.py) - added 2026-10-09
Goal: a person-level map of an application's command surface and a way to ask it "how do I ...".
* `uimap.Cartographer` (run inside the explorer as pass "ribbon"): ensures a working document (clicks the start-screen "Blank ..." choice, generic), widens the parked window so the
  ribbon does not collapse, selects every tab (verified: selected flag + changed group set), maps tab > group > control (kind, automation id, shortcut, enabled, toggle state),
  EXPANDS every drop-down/gallery (items = UI-tree difference; submenus 2 deep; collapsed again, unwind verified), opens ellipsis controls and ellipsis MENU ITEMS (dialog fields captured),
  walks the File/backstage view, the quick-access bar, the menu bar, then CONTEXTS (in a document the scan created: insert actions taken from the map, new contextual tabs read, disabled
  controls that become enabled recorded as `enabled_when`, undo verified). Output: data/atlas/uimap/<app>.json + claims ui.ribbon.* + commands with full ribbon paths.
* Safety learned the hard way (all measured on PowerPoint): an ellipsis does NOT mean "dialog" ("From Beginning..." starts the slide show, "Screen Recording..." starts capture);
  `SENSITIVE_RX` (capture/share/send/account/print...) and `RUNTIME_RX` (play/present/preview/rehearse/record...) are NAMED but never opened; a `Sentinel` thread ends any
  full-screen takeover window of the program (Escape, then close) and logs the action that caused it; personal lists (Recent/Favorites/History) and file-chooser contents are never recorded;
  file dialogs keep fields/buttons only.
* `teach.howto(app, "insert a picture")`: ranked step-by-step routes + shortcut + dialog fields + preconditions (a control disabled when scanned needs a selection) + a PROGRAMMATIC
  route from the COM type library (`Shapes.AddPicture(FileName, LinkToFile, ...)`; signatures of Add/Insert/Save/... verbs are stored) or the program's own runtime (bpy operators).
  `explain`, `overview`, `manual` (data/atlas/reports/<app>/manual.md). `hojaiga_atlas.py howto|explain|overview|manual`. `ask` answers how-to questions from the map first.
* Planner effector `ribbon_path` + `uimap.drive()` follow a route headlessly with UI Automation only.
* comlib: Office click-to-run registers PowerPoint.Application without a TypeLib key; the library is found beside the exe (MSPPT.OLB), chosen by coclass "Application" + name affinity.
