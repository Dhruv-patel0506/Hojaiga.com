---
name: hojaiga-knowledge-accuracy
description: Measured accuracy and timings of first-contact app knowledge (scan, layout, menu paths, positions), task completion, task compilation and the vision models, with how each number was obtained. 2026-10-05.
---

# Skill 15 — How accurate and how fast is first-contact app knowledge? (measured)

Harnesses (all real runs, nothing mocked; results in `data/*.json`):
`knowledge_bench.py` (fresh empty behavior model per app, real scanner, graded against an INDEPENDENT `uiautomation` walk of the live
window) · `bench_universal.py` (cold + warm scans of apps/websites) · `compile_bench.py` (task -> checkpoints, offline) ·
`vision_accuracy.py` + suite test VQ1 (OmniParser and Qwen2.5-VL vs UIA ground truth) · `task_bench.py` (task completion, independent truth).

## Scorecard (first contact, empty knowledge)
| App | scan total | launch / ready / menus (E0) / layout / probes (E1) | warm re-scan | control recall | real menu paths re-walkable | position within 3% |
|---|---|---|---|---|---|---|
| Calculator | 12.4 s | 4.0 / 3.2 / 3.0 / 1.3 / 0 | 5.1 s | 91% (33 controls) | n/a (no menus) | 3/3 |
| Notepad | 46.0 s | 8.2 / 1.6 / 11.3 / 8.8 / 12.7 | 10.9 s | 74% (36) | 12/12 (33 known) | 37/40 |
| Paint | 58.8 s | 4.5 / 2.9 / 14.1 / 14.0 / 20.2 | 13.4 s | 92% (96) | 12/12 (39 known) | 27/40 |
| Excel | 119 s | 5.3 / 2.0 / 47.8 / 23.6 / 38.3 | 32.7 s | 100% (95) | 12/12 (18 known) | 27/40 |
| Word (bench_universal) | cold 96 s | | warm 21 s | 435 controls, 259 commands | | |
| VS Code (bench_universal) | cold 227 s | | warm 27 s | 6000 controls, 1502 commands | | |

Aggregate over the four graded apps: **control recall 89% (mean), menu-path correctness 100% (36/36 sampled), position accuracy 76% (94/123
sampled)**. Websites (cold / warm): example.org 2.9 / 2.8 s (1 control), Hacker News 5.1 / 5.1 s (235 controls, 198 commands),
Wikipedia 8.5 / 5.3 s (539 controls, 427 commands).

What the numbers mean / known weaknesses
* **Recall misses are not random**: Notepad's scroll-bar parts (`line up`, `page down`) and its Find bar (`search`, `open replace options`,
  hidden until opened); Calculator's memory flyout; Paint's dialog units (`inches`, `pixels`). Surfaces that only exist after an action are
  found only if an E1 probe opens them.
* **"Paths" are two things**: a real menu path from the E0 crawl (`File > Save as`: a UI hierarchy - 100% re-walkable) and a *layout label*
  (`Grid > O8`, `list > Gold`: region kind > control, a location, not a hierarchy; Excel stores 1190 of these, 8% re-walkable). The layout
  labels inflate the command count (Excel 1214) without being usable paths - candidate for pruning.
* **Position accuracy** drops where the live window differs from the scanned one (Paint/Excel ~68%); median error is 1-2% of the window.
* **E1 (behaviour) knowledge**: probes observed their effect 3/3 (Notepad), 2/2 (Paint), 0/2 (Excel); Calculator has no E1 candidates.
* **Contention**: Paint's scan took 58.8 s alone but 319.7 s once the lifecycle + vision stack had run earlier in the same process (E1 alone
  277 s) - first-contact scans should not share a process with active vision/LLM work. Not root-caused beyond that.

## Task completion (independent truth, via the lifecycle)
| Task | first run | repeat | path | verified |
|---|---|---|---|---|
| Notepad: type text + save as file | 38.4 s | 29.0 s | template-first | file on disk has the text |
| Paint: save image as PNG | 48.2 s | 52.3 s | template-first | file is a real PNG (signature) |
| Calculator: 6 * 7 | 30.5 s | 25.1 s | verified loop (PARTIAL: key presses are weak evidence) | display reads 42 |
Repeat runs are 10-25% faster for Notepad/Calculator (cached knowledge), not for Paint.

## Task compilation (offline, 20 hand-labelled tasks; the labels are small and mine)
First run: verdict 95%, app detection 85%, goal plan 90%, risk gate 100%. Defects it exposed and that were fixed: a catalog app named
"Click to Do" matched the verb *click*; "weather" matched the Weather app inside "search for weather"; a stated password left a garbage goal;
"send the report to my boss" asked no question. After the fixes all five metrics are 100% on the same 20 cases (not an unbiased estimate).
Mean intake 5.6 ms, planning 2.7 ms.

## Vision (llama.cpp Qwen2.5-VL-7B from `start_hojaiga.bat` + in-process OmniParser, CPU torch)
| | Notepad | Paint |
|---|---|---|
| OmniParser parse (one window) | 80.2 s, 34 detections | 261.6 s, 101 detections |
| OmniParser: box contains the control's centre / caption matches its name | 100% / 30% | 100% / 10% |
| Qwen2.5-VL `locate <control>` hit rate, per request | 90% at 4.5 s | 20% at 4.8 s |
OmniParser load 22.5 s. VQ1 (live, 4 controls): 2/4 at 4.9 s. Consequence (implemented): the vision tier first asks Qwen to LOCATE the one
control being sought (~5 s) and falls back to the full OmniParser parse only if that finds nothing (`HOJAIGA_QWEN_VL=0` disables it). A wrong
box still cannot produce a false PASS - the postcondition verifier judges the click.
Local judge `qwen2.5:7b` (ladder): valid decisions 100% on Notepad/Paint/Excel at ~1.8 s, but 33% valid at 8.6 s on Calculator's first call.

## Environment sensitivities found while measuring (so a failing number is not misread)
* **Notepad persists state across launches** (tabs, window size, last file). Two measured effects: (1) a remembered tiny window (415x253)
  collapsed its toolbar and halved the layout (92 -> 36 controls, `File` at y=0.28 instead of 0.09) - fixed: a parked window is laid out
  at >= 1100x760 and its original placement is restored on exit; (2) a restored file tab delays the app's startup self-activation, so MIN1's
  `target-held-foreground` read 6.5-10.9 s with a polluted session and 55 ms with a clean one (verified both ways). Tests that type into
  Notepad leave tabs behind; a clean slate is `LocalState\TabState` (backed up before any reset in `_archive/`).
* **Paint's parked capture goes blank inside the long suite process** (E2E-2 fails there, passes alone with 101 vision elements); the cause
  was not isolated (CPU spin-wait after a vision parse was measured and ruled out: 0-4% idle).
* **Window-matching** (`find_window`) now skips only the agent's ancestor processes; excluding the agent's own process broke every test
  that creates its own fixture window.

## App-mastery engine (organ_63 + static harvest; `mastery_bench.py`, measured 2026-10-05)
Method: a brand-new empty database per app, then N cumulative `master()` runs, graded afterwards against INDEPENDENT readings of the live
window (a plain `uiautomation` walk; the live Win32 HMENU for classic menu bars). Hosts: msinfo32 (Win32), Notepad and Paint (WinUI), Calculator (UWP).

| App | runs (s) | commands | transitions | recall of resting controls | menu-path precision | explored frontier |
|---|---|---|---|---|---|---|
| msinfo32 | 53 / 21 / 18 | 108 -> 108 -> 108 | 0 | 1.00 (60 controls) | 0.92 (14 paths, HMENU grader) | 3/8 |
| Calculator | 52 / 22 / 16 | 40 -> 40 -> 40 | 16 | 0.83 (46) | no menu paths | 19/19 |
| Notepad | 38 / 43 / 20 | 84 -> 92 -> 92 | 0 -> 5 -> 5 | 0.65 (17) | 0.33 (36 paths, UIA-expand grader) | 13/13 |
| Paint (2 runs) | 85 / 40 | 206 -> 207 | 9 -> 10 | 0.90 (10) | 0.92 (41) | 14/55 |

What the numbers do NOT say (read before quoting them):
* **Run-to-run variance is real.** Calculator persists its mode: one session reached 72 -> 115 -> 124 commands (Programmer mode on screen), the
  next three sessions 40 commands (Standard). Knowledge is measured per UI state, so the same app can yield different totals.
* **Notepad's menu-path precision is a GRADER limit, not necessarily a knowledge error**: its menus are XAML flyouts that the UIA-expand grader
  opens unreliably headless (0.67 in one session, 0.33 in the next, same code). msinfo32 and Paint grade exactly (HMENU) or near it.
* **Replay (probe a surface again, same effect?)** is mostly not comparable: 0 comparable for msinfo32/Calculator/Paint, 1 for Notepad,
  because the controls a replay needs are absent in the state the app is in after the first pass. No replay rate is claimed.
* Paint explored 14 of 55 explorable surfaces in two runs: the frontier is large and each run is time-boxed.
* **Paint's `Edit colours` dialog freezes Paint** (not responding, ~100% CPU, reproduced 3 times, found only by a stack dump). The
  explorer now has a per-probe deadline, a post-probe responsiveness check, marks the control `unsafe` ("froze the app, not pressed
  again"), and terminates only a process THIS run launched (by pid). A third Paint run in a fresh database still reaches that control once
  and loses the app, so Paint is graded on 2 runs.

## Known limits found by the exploration work (kept so nobody re-discovers them)
* WinUI Paint ignores posted mouse input: no context menu and no drawing headless. Posted keys never reach XAML hosts.
* Exclusive tool toggles (Pencil, Fill, Text, Eraser) cannot be switched off; the previously active tool is not exposed as a toggle,
  so their unwind is reported FAILED (honestly) and `left_as_found` is False for Paint.
* "What's new" opens a popup host that does not count as restored; reported as an unwind failure.
