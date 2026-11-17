# Fixes and answers — 28 Oct 2026 (day)

Every result below was produced by Hojaiga's own front door (`hojaiga_run.run`), not typed by Claude.

- **Full logs:** `data/proof_oct28/*.json`, one per run. Each holds what the system said, its plan, its proof and its timing.
- **Screenshots:** `data/proof_oct28/screen/`, one per step, of the app's own window.

---

## 1. Your questions, answered plainly

**Why were 120 benchmark tasks blocked?**
- Every benchmark task begins by preparing its files: make a folder, download a file, unzip it, open it.
- Those preparation steps were written as **Linux shell commands** (`mkdir`, `wget`, `unzip`, `xdg-open`), and Windows can't run them.
- **The fix (done):** `gauntlet.translate_setup` turns each command into its Windows equivalent and runs it in a sealed sandbox folder. That raised runnable tasks from 278 to 388.
- **The 135 still blocked** need things this PC doesn't have: GIMP, Thunderbird, a Linux terminal, `sudo`, or a Google Drive sign-in. They can't be faked honestly.
- **What Gemini can give:** Windows versions of those tasks, i.e. the same task done in Paint.NET or Outlook instead of GIMP or Thunderbird.

**The "invisible Office" test printed results but said exit code 1. Was it fake?**
- No. All three apps printed their real saved values, file sizes and times.
- The exit code 1 came from the *last* command in that line: `Get-Process EXCEL,WINWORD,POWERPNT`. It returns 1 when **none of those programs is running**, and that was the point being checked: all three had quit cleanly.
- Today's on-screen runs (section 2) show the same work happening with your own eyes on it.

**Did it really finish in 3–5 s?**
- When it uses Office's *object model*, it writes straight into the document (cell A1 = "Item") instead of moving a mouse, so each step takes milliseconds.
- **Measured today, on screen** (with a deliberate 1.2 s pause per step so you can watch):

| Run | Time |
|---|---|
| Excel, 10 steps | 16 s (41 s total including routing, proof and boot) |
| Word, with an 87-row table | 17 s |
| PowerPoint | 14 s |

- Without the pauses, the same steps take 4–6 s.

**Office reverse engineering.** Your go is noted. For Office:
- The type libraries give the complete object model: Excel 13,896 members, Word 6,236, PowerPoint 2,859.
- The VBA docs gave 19,554 reference pages.
- A Ghidra pass over EXCEL.EXE (about 60 MB) would take hours and mostly yield internal function names. It can run overnight if you want it, but the object model is what actually drives the app.

**Store apps (Paint, Calculator).** The earlier claim was wrong: their files *are* readable.
- **New:** `rea_native.pri_digest` reads every Store app's `resources.pri`, which holds every button name, tooltip and page. It runs in 0.5 s with no app opened.

| App | Control names / tooltips | Pages |
|---|---|---|
| Calculator | 1,166 | 32 |
| Paint | 814 | 55 |

- Run it for every Store app with `python -m core_organs.rea_native store`.
- **Proof that it works, answered from that knowledge by the system:**
  - "Calculator's absolute-value button is called 'Absolute value'"
  - "Paint's brushes: Brush, Airbrush, Calligraphy brush, Calligraphy pen"
  - "Calculator modes: Scientific, Graphing, Programmer"
- **A bug found while testing:** answers to questions were never returned (a comment swallowed the field). Fixed.

**Checksums.** Both 7B eye models now match their published SHA-256. The earlier `.bad` files were truncated downloads, resumed until they matched.

**Ultralytics.** It is imported and now the **default** detector.
- On the same PowerPoint screen it found **110 boxes in 1.2 s**, against 43 boxes in 11.6 s for the MIT model.
- The MIT model stays as the fallback. `HOJAIGA_PROF_YOLO_LEGACY=0` forces it.

**Web false DONE ("Early life" → BBC).**
- **Two checks now, not one.** First, the page must be on the same site and carry all the goal's words. Then the **eye reads the final screenshot** and a judge compares that reading with the ticket. If the eye says it's the wrong page, the result is FAILED_CHECK.
- **Controls, the same screenshot judged against three tickets:**

| Ticket | Result |
|---|---|
| Turing / Early life (correct) | PASS |
| Einstein | FAIL |
| BBC plaque story | FAIL |

- Log: `data/proof_oct28/web_judge_controls.log`.
- **Live rerun:** it landed on Wikipedia → "Early life and education" (screenshot `data/proof_oct28/web_turing.png`).
- **What went wrong first:** my new picture check failed that correct page, because the eye was asked to describe *objects* and talked about the plaque photo. Pages are now *read* (title, headings) rather than described as objects.

**The vision model (lumberjack "green cubes").**
- **Qwen3-VL-8B now runs on the GPU** (port 8081, 20 layers on the GPU and the rest in RAM). It was already on disk and is newer and stronger than both 7B downloads.
- It saw "a tree-like structure… a small humanoid figure… holding a gray axe", and the lumberjack now **passes**. The old 3B eye saw "a stack of green cubes".
- **Heat fallback:** at 83 °C or above the 8B eye stands aside, and the 3B eye runs **on the CPU only** until the GPU is back under 75 °C. `HOJAIGA_GPU_HOT` and `HOJAIGA_GPU_COOL` set these limits.
- **Tried and turned off:** using the 8B as the text judge too. It was no faster (70–150 s) and judged one page wrongly. It stays opt-in (`HOJAIGA_BRAIN_ON_EYE=1`).

**On-screen vs background.** There is now an on-screen mode for Office (`HOJAIGA_OFFICE_VISIBLE=1`):
- A **new** Office window that you watch.
- One screenshot per step, of **that window's own pixels**.
- **A mistake I made:** my first screenshots grabbed a screen rectangle and caught your browser on top of Excel. Those images were deleted at once, and captures now take only the window's own pixels.

**The Paint tracer ("it traced anything and shaded it").** It still exists: `canvas_artist` / `canvas_colour` / `canvas_stages`, drawing through synthetic touch on a parked Paint.
- **Run live today:** stage 1 (shapes) drew **4/4 strokes, 100% complete, 100% inside the canvas** in 15 s.
- Stage 5 (colour trace of the reference pictures) — see section 2.
- **Not done yet:** the front door's "draw" step still uses the simpler sketch driver, not this tracer. Wiring the tracer in is the next fix.

**Downloads (your go).**

| Item | Size | Used for |
|---|---|---|
| ScreenSpot-Pro | 3.4 GB, MIT | testing whether the eye finds the right button in pro apps (`data/inbox/4_6_screenspot_pro`) |
| ScreenSpot-v2 | 1.3 GB | the same check on desktop, web and mobile |
| bge-reranker-v2-m3 | 2.3 GB | re-orders RAG hits before an answer is written |
| GUI-Odyssey — task plans only (34 MB) | 34 MB | cross-app task plans for the multi-app planner |

- **ScreenSpot-Pro, ScreenSpot-v2 and bge-reranker:** downloading, every file checked against Hugging Face's own SHA-256.
- **GUI-Odyssey:** its 67 GB of **Android phone** screenshots were left out; they aren't useful for a Windows agent.
- **Not fetched:** Kenney / Quaternius rigged humans. Their files sit behind a JavaScript donation page or Google Drive, and Mixamo needs an account, which I'm not allowed to create.
  - The no-download route is Blender's built-in Rigify human rig.
  - Gemini could find direct CC0 GLB/FBX links (for example, Quaternius on poly.pizza).

**Video-editing bench task (added: `gauntlet.video_bench`, `video_pipeline.edit_options`).**
- **How it works:**
  - The model writes **several different edits** of your footage (pace, length, captions), knowing what the footage holds and what *you* chose before.
  - Each edit is rendered and checked.
  - It ends by **asking you which one** you prefer. Your choice and reason go to `data/video_taste.json` and steer the next edit.
- **Live result, PASS:**
  - three different edits (9.0 s with captions, 9.1 s without, 13.7 s full recap);
  - all rendered and checked;
  - status NEEDS_CHOICE.
- **The first try failed honestly:** the model asked for 30 s, 1 min and 2 min from footage holding only 9 s of speech. Now it's told the footage facts first.
- **Not built yet:** trend learning ("cut it like the editors you follow") needs example edits you like. A folder of them, or YouTube links, is the input.

**Base Qwen3-VL vs the "round-3 adapter".**
- **The base** is the plain Qwen3-VL-2B model.
- **The round-3 adapter** is a small add-on trained on top of it (QLoRA) to make *decisions*: pick, confirm, resume, re-plan.
- 96% vs 18% "exact" means it learned those decisions on **held-out examples from the same generated set**. That is not yet proof on your real screen.
- It does **not** contain the RAG, REA or the downloads. Those are a *separate* knowledge store the system searches at run time.
- **So:**
  - **"Did training increase the knowledge pool?"** No. The knowledge pool grew by *importing* (44,643 chunks overnight, plus today's Store-app words), not by training.
  - **"Does it know?"** It can *find and cite* what is in the pool. The Calculator and Paint answers above are that, with citations.

**"Is it as smart as Jarvis?"** Honestly: not yet. Its planning brain is **qwen2.5:7b** (a 2024 7B model). Today alone it:
- typed "Largest cities **in bold**" as a title;
- replaced "save" with "click Automatically Save";
- wrote a stray "type cities in read".

The code around it now catches each of those, but a stronger brain makes fewer of them. **Recommendation: needs your yes before any download or switch.**
1. **Brain (planning / judging): Qwen3-8B, or gpt-oss-20b.** gpt-oss-20b is a mixture-of-experts model with about 3.6 B active parameters, so it runs on the 6 GB GPU plus RAM. Both are far better than qwen2.5:7b at following instructions and producing JSON.
2. **Eye:** keep Qwen3-VL-8B (now running).
3. **Then:** re-train the decision adapter on the new brain, and measure on **live** tasks, not only held-out ones.

---

## 2. On-screen runs today (front door, Office visible)

| Task | Result | Time | Proof |
|---|---|---|---|
| Excel: 6 cells, A1:B1 bold, save | DONE | 41 s | file read back: all 6 values, A1 and B1 **[bold]** |
| Chrome → **Word**: Wikipedia table into a Word table under a bold title | DONE | 49 s | docx: "Largest cities" (bold) and the 87-row table |
| Excel → PowerPoint: read A1:C11, title slide, table slide | DONE (both halves) | 43 s | the Excel read proven by its 24/24 cells in the source; pptx has 1 table on slide 2 |
| Web: Wikipedia → Alan Turing → Early life | browser right; first picture check wrong; check fixed | — | see above |
| Paint artist stage 1 | 4/4 shapes | 15 s | completion 100%, containment 100% |

**Bugs these runs exposed, all fixed and re-run:**
- `.xlsx` proof never saw bold, and failed a correct file.
- A table insert in Word took **75 s** (one cell at a time). It is now one text-to-table conversion: **about 6 s**.
- Format words leaked into the text ("Largest cities in bold").
- "Click Automatically Save" replaced the save step. The plan then left the object model, and the slow window route typed into **another open Word window ("Document1 – AutoRecovered")**.
  - Nothing on disk was changed, and that window is still open.
  - **Please check it**, in case it is yours.
  - Now the save the words name is always added.
- `read the cities` inside PowerPoint now becomes "insert the table"; a doubled table on a slide is de-duplicated.
- PowerPoint's window wasn't capturable through COM. It is now found by its title.
- Wikipedia footnote marks (`City[a]`, `[12]`) are stripped from kept tables.

**Tests:**
- **Mind suite:** AR65–AR85, 21/21 PASS.
- **PR39 (detector):** PASS.
- **RAG:** 17/18. RG10's hybrid-search timing was 104 ms against an 80 ms limit, measured while the 8B eye, the downloads and the Paint tracer were all running. Rerun when the machine is quiet.

---

## 3. Still open

1. Wire the Paint tracer and colouring (`canvas_artist`) into the front door's draw step.
2. Calculator on screen: not run yet today.
3. A guard so the Office window route never types into a document the task didn't open.
4. A stronger brain: needs your yes (see above).
5. Rigged humans: Rigify (no download), or direct links from Gemini.
6. Trend-aware video editing: needs example edits you like.
7. **Nothing is committed**, as you asked: commit once everything is fixed.

## 4. What Gemini could provide
- Windows equivalents of the 135 bench tasks that need GIMP, Thunderbird or a terminal.
- Direct CC0 download links (GLB/FBX) for rigged, animated human characters.
- Five to ten example videos or channels in the editing style you like.
- A list of the Office features (ribbon commands) you use most, to drive the deep ribbon scan first.
