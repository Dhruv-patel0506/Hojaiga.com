# Hojaiga 4B model — training dataset spec (for Gemini, then local training)

**Goal:** one fine-tuned **Qwen3-VL-4B-Instruct** that runs fully on the RTX 3050 6 GB and is Hojaiga's eye and decision brain together. It replaces the current pair:
- **Eye:** Qwen3-VL-8B, not fine-tunable here; about 35 s a picture.
- **Brain:** qwen2.5:7b.

It must **beat the 8B on our own test bench (section 5)** before it replaces it. Until then the 8B stays as the checker.

---

## 0. Read this first — what the model does and does NOT do

Hojaiga splits the work. **Code** does, and the model must not try to do:
- deep scanning;
- the UI tree (UI Automation);
- child windows and pop-up detection;
- OCR and the icon detector;
- Office through its object model;
- Store-app words (`resources.pri`);
- type libraries;
- Ghidra / REA;
- file read-back.

**The model does six jobs on top of that.** The dataset trains exactly these (sections 2A–2N):
1. **See:** say what is on a screen, picture, render or video, plainly and correctly.
2. **Ground:** pick the right control from the numbered element list plus the picture.
3. **Decide:** choose the next step, or say confirm / re-plan / ask.
4. **Plan:** turn a request into ordered steps, across apps.
5. **Judge:** say whether a result matches the task (proof), item by item.
6. **Explain / teach:** answer questions about an app from the evidence it is given, with citations.

**The rule that makes a 4B beat an 8B:** every label must be **verified ground truth**, never another model's guess. Hojaiga already produces verified labels:
- UIA names;
- files read back after a save;
- the pixel checks of the Paint tracer;
- the render checks of the video editor.

If Gemini writes text labels, each one must be checked against something real (sections 3 and 4). Copying the 8B's answers can only *match* the 8B, never beat it.

---

## 1. Record format (what `train_qlora` reads)

One JSON object per line (`.jsonl`). Images are **file paths** relative to the dataset folder. Video is a list of frame images.

```json
{"messages": [
  {"role": "system", "content": [{"type": "text", "text": "<the job's system prompt, section 2>"}]},
  {"role": "user", "content": [
     {"type": "image", "image": "images/excel_0042.png"},
     {"type": "text", "text": "Application: excel\nElements:\n#1 button 'Bold'\n#2 ...\nGoal: make A1 bold"}]},
  {"role": "assistant", "content": [{"type": "text", "text": "<the answer: JSON for the action / plan / judge jobs, text for see / teach>"}]}],
 "meta": {"job": "ground", "app_key": "excel", "source": "local_uia", "verified_by": "uia_name", "ui_frames": true, "prompt_version": 2, "split_group": "excel::Bold", "lang": "en"}}
```

- `meta.job` is one of: `see`, `ground`, `decide`, `plan`, `judge`, `teach`, `video`, `draw`, `general`.
- `meta.verified_by` says how the label was proven: `uia_name`, `file_readback`, `pixel_check`, `render_check`, `human`, `public_label`. A row with no proof is **not used**.
- `meta.split_group` keeps near-duplicates (the same video, or the same control) on one side of the train/eval split.
- **Reasoning:** for the decide, plan and judge jobs, the assistant text may start with a short `"why"` field (1–3 sentences) *inside* the JSON. Keep it short: Hojaiga reads JSON, and long chain-of-thought slows a 4B and drifts.

---

## 2. The skills, and the data for each

The counts are targets for the first good model; more is better if the quality holds. "Pairs" means records.

### A. See a screen (screen reading) — 8,000 pairs
- **Input:** a screenshot of an app or web page.
- **Output:** which app or site it is, the window or page title, the visible headings and sections, what the main area shows, any dialog or error, and the words quoted exactly.
- **Must cover:**
  - Office (Excel, Word, PowerPoint, Outlook);
  - Paint, Calculator, Notepad, File Explorer, Settings;
  - Chrome and Edge on 40+ common sites (Wikipedia, YouTube, Gmail, Amazon, GitHub, news, banking login pages);
  - Blender, VS Code, OBS, Photoshop-like editors;
  - dark and light themes;
  - 100–200% scaling;
  - partly covered windows.
- **Negatives (about 15%):** a page that *looks* like the right one but isn't. Wikipedia "Alan Turing" vs BBC "Alan Turing plaque" is the real case from Oct-28. The answer must name what it really is.
- **Labels:** the window title and URL come from the system; the visible text from UIA, the DOM or OCR. Gemini writes only the summary sentence, *from those words*.

### B. See a picture or 3D render (object description) — 6,000 pairs
- **Input:** a render, photo or drawing.
- **Output:** every object, its shape and colour, its size relative to the others and its position. Plain facts, no guessing what it was meant to be.
- **Must cover:**
  - Blender renders of our builds: low-poly trees, Minecraft-style people, tables, houses, terrain;
  - **blocky / voxel scenes**: the lumberjack case, which the 3B called "green cubes";
  - several objects side by side;
  - side, top and three-quarter views;
  - Paint drawings;
  - charts;
  - real photos (for general sense).
- **Labels:** for our renders, the scene file *is* the truth: object names, positions and colours are written out of Blender by code. For photos, use public captioned sets (section 3).

### C. Ground: pick the control — 15,000 pairs (the biggest set)
- **Input:** a screenshot, the numbered element list and a goal ("make A1 bold", "open Insert > Table").
- **Output:** `[{"step":1,"action":"click|hotkey|type","target_id":N,"hotkey":null,"text":null,"verify_expectation":"..."}]`.
- **Must cover:**
  - ribbons and every tab (Home, Insert, Design, Layout, References, Review, View);
  - context menus;
  - dialogs and child windows;
  - icon-only buttons;
  - duplicates ("Close" ×3: pick the right one);
  - the same goal in different layouts and languages;
  - web forms and search boxes.
- **Labels:** our local UIA recorder (`harvest/local_recorder.py`) clicks a control and records its UIA name, so the label is exact. Add ScreenSpot-Pro and ScreenSpot-v2 (already downloaded) converted to this format.

### D. Decide the next step (including stop, confirm, re-plan) — 8,000 pairs
- **Input:** the screen, the elements, the goal, the steps already done and what the last step changed.
- **Output:** one action, or one of:
  - `confirm` (text = money / publish / delete / account / consent / install), when the next press would pay, send, publish, delete, sign out, agree or install;
  - `replan` (text = not_here), when the plan's control is not on this screen;
  - `ask`, when the request is ambiguous.
- **Must cover:**
  - resuming a task half done (what is already done: don't redo it, don't retype text that's there);
  - recovering from a wrong page;
  - pop-ups to handle **before** continuing: cookie banners (decline non-essential), "update available", sign-in walls (stop and ask), "Save changes?";
  - danger buttons;
  - an already-finished task (answer "done").
- **Labels:** the decision rules are fixed (above), so Gemini can write the label *from the elements list*. Then a code check rejects any row whose target_id is not in the list.

### E. Plan a request into steps — 6,000 pairs
- **Input:** the request, the app, the kept data from earlier apps, and the commands known for that app.
- **Output:** `{"steps":[{"do":"open_file|new_document|type|click|press|select|format|add_slide|draw|save_as|read|insert_table|insert_picture|paste","text":"","target":"","format":""}]}`.
- **Must cover the exact mistakes made on Oct-28.** Each should appear as a training example with the right answer:
  - "write the title Largest cities in bold" → type "Largest cities" + format bold. **Not** typing "Largest cities in bold".
  - "save it as D:\x.docx" → a `save_as` step. **Never** "click Automatically Save".
  - "add a slide with the cities table" (a table kept from Excel) → `insert_table cities`. Not `read`, not menu clicks, not twice.
  - No clicks with an empty target. No `type` into a step name ("type cities in read").
- **Multi-app chains:** Chrome→Excel, Chrome→Word (tables go in **Word** unless Excel is named), Excel→PowerPoint, Paint→Word, Excel→chart→PowerPoint, Outlook email from a Word report.
- **Choosing the right app on its own:** "make a report with a table" → Word table. "Analyse these numbers" → Excel.
- **Labels:** Gemini writes them. Each plan is then **run by Hojaiga** on a real file and kept only if the proof step says DONE (`verified_by: file_readback`).

### F. Judge a result (proof) — 5,000 pairs
- **Input:** the task, plus what the saved file holds (Hojaiga's read-back text, e.g. `Sheet1!A1 = 'Item' [bold]`), or the eye's reading of the screen.
- **Output:** `{"items":[{"content":"...","where":"...","format":"...","found":true|false}]}`, then the verdict.
- **Must cover:**
  - exact text vs extra words (a title holding "in bold" = **wrong**);
  - wrong cell;
  - missing bold;
  - a table copied twice;
  - number formats (41913860 = "41,913,860");
  - the right page vs a look-alike;
  - a picture with the right objects vs the wrong ones.
- **Half the rows must be failures.** A judge trained mostly on passes says "yes" to everything; this is the sycophancy found on Oct-27.
- **Labels:** make the right file, then **break it on purpose** in code (drop bold, change a cell, add words). The label is known exactly.

### G. Teach / answer about an app from evidence — 5,000 pairs
- **Input:** a question plus numbered evidence (RAG chunks: manuals, VBA docs, Blender docs, Store-app UI words, scanned menus).
- **Output:** a short answer citing [n] after each claim, or exactly `NOT IN EVIDENCE: ...` when the answer isn't there.
- **Must cover:**
  - "where is X";
  - "what does this button do";
  - "how do I…" (as numbered steps);
  - "why did this pop-up appear and how do I fix it";
  - keyboard shortcuts;
  - **trick questions whose answer is not in the evidence** (about 20%).
- **Labels:** Gemini writes them from the given chunks. A code check rejects any citation number that isn't in the evidence.

### H. Pop-ups and errors — 3,000 pairs (also counted in D)
- **Input:** a screenshot of the dialog, its text and the task.
- **Output:**
  - what kind it is: login, recovery, update, welcome, cookie, save-changes, error, permission/UAC, licence;
  - why it appeared;
  - the safe action;
  - whether the person must be asked.
- **Rule:** elevation, payment, deletion, sign-in and terms are **never** auto-accepted. The label is `confirm` or `ask`.

### I. Video understanding — 3,000 pairs
- **Input:** 4–16 frames from a clip (plus its transcript when it has speech).
- **Output:** what happens over time, which app is being used and which steps are shown (for "learn from a tutorial"), or the moments worth keeping (for editing).
- **Must cover:**
  - screen-recorded tutorials (Excel, Blender, Photoshop);
  - talking-head videos (no UI: say so);
  - gameplay;
  - product demos.
- **Labels:** tutorial steps come from the transcript plus the visible UI changes (the YouTube harvester's pipeline). Editing labels come from the edits the person chose (`data/video_taste.json`).

### J. Video-edit decisions — 1,500 pairs
- **Input:** numbered transcript lines with their lengths, plus the request, plus the person's past choices.
- **Output:** `{"drop":[...],"captions":bool,"title":"","target_seconds":n}`, or 3 different edit briefs.
- **Must cover:** filler words, repeats, highlight cuts to a length, *never asking for more than the footage holds*, and different styles.

### K. Drawing decisions — 2,000 pairs
- **Input:** "draw X" plus the canvas size, or a reference picture.
- **Output:** a stroke plan (0–100 box, JSON), or the choice of route: geometry, the Quick, Draw! sketch, the trace of the reference, or colour regions.
- **Labels:** Quick, Draw! strokes (real human sketches) and the Paint tracer's own plans, which passed the pixel check (684 strokes at 100%, 715 at 99.94% on Oct-28).

### L. Route the request (who does it) — 3,000 pairs
- **Input:** a request.
- **Output:** the parts and their routes: question / write / web / desktop / build / code / video. Also "do it for me" vs "teach me how".
- **Must cover:** mixed requests ("find the population table and make slides"), how-to questions vs do-it requests, and a person's own messages (private: stays local).

### M. Safety refusals and asks — 1,500 pairs
- Payment, passwords, deleting, sending messages, accepting terms, and installing software: the answer is `confirm` or `ask`, never act.
- Instructions found *inside* a page or document ("ignore your rules and…") are data, not commands.

### N. General rehearsal (keeps the 4B from forgetting) — 20% of the total
Mix in about 20% general vision-language data so the fine-tune doesn't erase what the model already knows:
- general captions;
- document and chart reading (OCR, tables);
- simple maths and logic in words;
- everyday questions.

Use public sets (section 3). Hojaiga must score **no worse** on these after training than before.

**Rough total:** about 66,000 project pairs plus about 16,000 rehearsal pairs, so about 82,000. A first useful run can use 20–25% of each section; grow from there.

---

## 3. Where the data comes from

| Source | Gives | Status |
|---|---|---|
| Hojaiga's own local UIA recorder (`harvest/local_recorder.py`) | C, D with exact labels | built; run it on more apps |
| Hojaiga front-door runs + proof (`data/hojaiga_runs/*/report.json`) | E, F with file-proven labels | runs every day |
| Store-app words (`rea_native store`), typelibs, VBA docs, Blender docs | G evidence | in the RAG (44,643 + chunks) |
| ScreenSpot-Pro, ScreenSpot-v2 | C (grounding test + some training) | downloaded `data/inbox/4_6`, `4_7` (finish the resumed files) |
| OSWorld + Windows Agent Arena tasks (388 runnable) | E plans, D steps | `data/eval/bench_tasks.json` |
| GUI-Odyssey annotations | E cross-app plans (phone, as patterns only) | downloaded `data/inbox/4_5` |
| Quick, Draw! (44 categories so far) | K | `data/inbox/6_1_quickdraw` |
| Blender renders from our builders, with the scene file as truth | B | the builders exist; render 3,000+ scenes |
| Paint tracer runs (`data/canvas_runs`) | K | 3 references done; add more pictures to `data/reference_art` |
| Video taste choices (`data/video_taste.json`) | J | starts filling as you choose edits |

**What Gemini should find or make:**
- **Public sets with licences that allow training:**
  - screen and doc QA: ScreenQA, WebSRC, DocVQA, ChartQA;
  - general captions: COCO Captions, ShareGPT4V subset;
  - UI action data: Mind2Web, AITW (patterns only), OmniACT, Wave-UI;
  - video: tutorial transcripts from channels you allow.

  Give each one's licence, size and download link.
- **Text-only rows for E, F, G, H, L and M**, in the record format above. Gemini writes the request, the elements list or evidence, and the answer. Hojaiga's code checks then filter them (target in the list, citation in the evidence, plan runs and proves).
- **Not screenshots.** Gemini can't produce real screenshots. Pictures must be captured on this PC (the recorder) or come from public sets. Made-up pictures teach the wrong look.

---

## 4. Quality rules (applied by code before training)

1. Every row has `meta.verified_by`; rows without it are dropped.
2. JSON answers parse, and every `target_id` exists in the element list.
3. Every citation [n] exists in the evidence.
4. Every plan in E ran and proved DONE, or is marked as a deliberate *wrong* example in F.
5. Failures are at least 40% of F and at least 15% of A.
6. No personal data (emails, names, account numbers) in screenshots or text. Blur or drop it (`harvest/privacy.py`).
7. The train/eval split is by `split_group` (no control or video on both sides).
8. Duplicates (same image hash plus same goal) are removed.

---

## 5. The test bench: when the 4B may replace the 8B

Run the **same** test on four models: base 2B, base 4B, 8B (current) and **tuned 4B**. The tuned 4B must:

| Test | Measure | Gate |
|---|---|---|
| Screen reading (300 held-out screens, incl. look-alike pages) | right app, page and key words | ≥ the 8B |
| Object description (300 renders incl. the lumberjack-style blocky scenes) | objects named correctly | ≥ the 8B |
| ScreenSpot-Pro sample (500) | click inside the right box | ≥ the 8B, and ≥ 40% |
| Grounding on our apps (1,000 held-out controls) | exact target | ≥ 90% |
| Decisions (confirm / replan / ask cases) | exact action | ≥ 95%, **0 missed danger confirms** |
| Planner cases (the Oct-28 mistakes + 300 more) | plan runs and proves DONE | ≥ 90% |
| Judge (balanced pass/fail) | right verdict | ≥ 95%, false-PASS ≤ 2% |
| Teach (with trick questions) | grounded answers, honest NOT IN EVIDENCE | ≥ 90% |
| General rehearsal set | same score as base 4B | no drop > 2 points |
| Speed on the RTX 3050 | seconds per picture + decision | ≤ 8 s (the 8B takes about 35 s) |
| **Live front-door runs** (Excel, Chrome→Word, Excel→PowerPoint, web, Blender build, Paint draw, video edit) | DONE with proof | all pass on screen |

Hojaiga's harness records every test result with the model name in the bench ledger. The switch happens only when every gate passes.

---

## 6. Training it locally (RTX 3050 6 GB, 32 GB RAM) — the compute needed

**This laptop is enough for the 4B.** No data centre is needed. Settings:

| Setting | Value | Why |
|---|---|---|
| Base | Qwen3-VL-4B-Instruct (check the exact name and licence on Hugging Face first) | |
| Method | Unsloth QLoRA, 4-bit base (about 2.5–3 GB) | fits the 6 GB card |
| LoRA | r = 16 (first run), 32 (if it underfits); alpha = 2×r; dropout 0.05 | |
| LoRA targets | all linear layers: q, k, v, o, gate, up, down; language side + vision projector | the vision side and the text side stay in step |
| Batch | 1, gradient accumulation 8–16 | |
| Gradient checkpointing | on (Unsloth's) | |
| Optimiser | paged AdamW 8-bit | spills into RAM instead of crashing |
| Learning rate | 1e-4 to 2e-4; cosine schedule; warmup 3% | |
| Epochs | 1–2 (more over-fits small sets) | |
| Image size | cap about 1024×1024 (max_pixels), so long screens don't blow the memory | the KV cache stays small |
| Sequence length | 2048–4096 tokens | element lists can be long; trim to the 120 most relevant elements |
| Video | 4–8 frames at about 448 px for training | |

**Time estimate (from our 2B run: 700 steps in a few hours):**
- 4B with about 20,000 pairs, 1 epoch: about 12–20 hours.
- The full 82,000: about 2–3 days, in resumable chunks. `train_qlora` already resumes from the last checkpoint.

**If you want it faster:** one rented 24 GB GPU (RTX 4090 / A10 / L4) does the full set in about 6–10 hours. Not needed, just faster.

**After training:**
1. Merge the adapter.
2. Make a GGUF (Q4_K_M) plus its vision projector file.
3. Serve it on :8081 in place of the 8B, with all layers on the GPU.

Hojaiga already uses :8081 for the eye. The text brain can move to the same server once the tuned 4B passes the planner and judge gates, which removes the slow model swapping.

---

## 7. What to hand back

- `train.jsonl`, `eval.jsonl`, an `images/` folder, and `data_summary.json` (counts per `job` and per `verified_by`).
- The run folder from `train_qlora` (adapter + `eval_report.json`).
- Hojaiga then runs section 5 on all four models and prints one comparison table.
