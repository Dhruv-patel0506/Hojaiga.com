# Morning report — 28 Oct 2026

Everything below was measured. Nothing is committed since fc936c96.

## 1. The 01:00 night run (old code) — mostly failed, honestly
| Task | Result | Why |
|---|---|---|
| Excel prices.xlsx | FAILED | the Office window was BLOCKED (start screen / lost handle) |
| PowerPoint | FAILED | same |
| Chrome→Excel | FAILED | same, on the Excel half |
| Excel→PowerPoint | FAILED | same |
| Web "Wikipedia → Alan Turing → early life" | reported DONE, **actually wrong**: it landed on a BBC page carrying only "early" | already fixed: `web_executor.landed` now requires the same site, and both words for a two-word goal |
| Blender lumberjack | FAILED_CHECK | 25/25 parts built, geometry score 70, but the 3B picture eye scored it 2/5 ("stack of green cubes"); the blocky style fools the small eye |

## 2. Fixes made overnight, then re-run invisibly (no window, no focus taken)
- **Office runs in a hidden instance** (`office_om.Headless`, a DispatchEx new instance): no start screen, no window to lose, closed without saving extra documents.
- **Re-runs:**
  - Excel: DONE.
  - PowerPoint: DONE.
  - Chrome→Excel: DONE (40/40 cells proven in the .xlsx).
  - Excel→PowerPoint: the PowerPoint half was DONE (24/24 cells on the slide). The Excel "read" half had *nothing to check*, so the chain stayed PARTIAL.
- **Fixed this morning:**
  - A ticket that only reads a file is now proven by its own data: the cells it kept must be in that source file. A read that kept the wrong cells fails.
- **Other fixes:**
  - Excel's `41913860` counts as the same cell as `"41,913,860"`.
  - A click or paste on a kept table's name becomes an insert-table step, and the Office menu walk before it is dropped.
  - The real data table beats Wikipedia's navigation box.
  - Only files the task *makes* must be new.
  - A read-only web task reads the page without a browser.

## 3. Knowledge pool (RAG) — filled overnight
| Source | Amount |
|---|---|
| Office VBA docs + Blender docs | 26,492 docs → **44,643 chunks** (finished 02:17) |
| COM type libraries | Excel 13,896 / Word 6,236 / PowerPoint 2,859 members |
| Blender API | 2,415 operators |
| Store manifests | Paint, Calculator |
| Import speed | 259 → 588 chunks/min. The real bottleneck was the lexicon lookup, not embedding. |

## 4. Training — round 3
- **Training:** Qwen3-VL-2B QLoRA, 700 steps (resumed from a checkpoint after the night run freed the GPU). Loss went 1.70 → 0.31; it exited cleanly at 03:26.
- **Evaluation** (finished 04:29, 300 held-out examples, `reports/eval_mind.log`):

| | valid JSON | right action kind | exact |
|---|---|---|---|
| base Qwen3-VL-2B | 0.80 | 0.22 | 0.18 |
| round-3 adapter | 1.00 | 0.99 | 0.96 |

  Caveat: the held-out set comes from the same generated pick/confirm/resume/replan data, so this shows the adapter learned the format and the decisions. It does not show it on new live tasks yet.

## 5. Downloads
All priority items were verified by SHA-256 with a SOURCE.txt each (two Qwen GGUFs had arrived truncated and were resumed until they matched).

## 6. Tests
- `si_tests_mind` **AR65–AR85: 21/21 PASS**.
- **AR85 is new (12 checks)**: multi-app proof, number-as-text cells, kept-table insert, the navigation-box table, read-only proof.
- **AR79:** its sketch check now uses an unknown word, because "house" correctly comes from the Quick, Draw! human sketches first.

## 7. Still open (needs you or a decision)
1. **Paint drawing and Calculator buttons while hidden.** Unsolved: Paint ignores posted pointer input, and the Calculator UWP shows 0 controls while parked. A visible mode, or a VM, needs your go.
2. **Blocky scenes and the picture eye.** The bigger eye (UI-TARS 1.5 7B or Qwen2.5-VL 7B GGUF, both downloaded) is wired at :8081 but not running. Starting it takes the GPU.
3. **Downloads not yet made:** rigged humans (Quaternius / CMU) and batch 2 (ScreenSpot-Pro, GUI-Odyssey, bge reranker, Kenney). Each needs a download go.
4. A video-editing bench task has not been added yet.
5. **Uncommitted:** all overnight edits (`hojaiga_run`, `loop_first`, `office_om`, `web_executor`, `gestures`, `icon_detector`, `rea_native`, `gauntlet`, `video_pipeline`, `train_qlora`, `si_tests_mind`, and others).
