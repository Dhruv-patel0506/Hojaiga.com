# What the Qwen + RAG + REA brain needs to learn everything on the list

Written 2026-10-27. No new Python files: every change below goes into files that already exist.

## 1. How it works today (measured on this machine)

| Piece | What it really is now | Size today |
|---|---|---|
| **RAG** (`core_organs/rag/`) | 5 sub-RAGs: icons, UI graph, procedures, hotkeys, recovery + lexicon. Router picks the cheapest answer first. | 7,708 procedures, 3,114 knowledge chunks, 863 fast paths, 11,859 commands across 205 apps, 304 UI states / 687 edges, 51 error playbooks. LanceDB 4.9 GB. |
| **Qwen (thinking/eyes)** | Ollama: `qwen2.5:7b`, `qwen2.5-coder:7b`, `qwen2.5vl:3b` (CPU, slow: a plan takes ~140 s). Trained: Qwen3-VL-2B + LoRA (`train_qlora.py`) | Round 3: 5,122 training rows (pick 3,347 / resume 1,031 / confirm 444 / replan 300), stopped at step 200 of 700. Mostly web pages. |
| **REA** (`rea_bridge.py`, `harvest/rea_sweep.py`) | Reverse engineering: 49 apps read (31 .NET, 18 Electron). | ~80 native programs need Ghidra (not installed, needs your yes). |
| **Front door** (`hojaiga_run.py`) | One command: read the task -> decide the route -> do it -> prove it -> learn. | Works for Paint, web pages, drafts, Q&A. |

**Where it is still hardcoded** (this is what you are unhappy about, and you are right):
- `hojaiga_run.classify()` picks the route with regexes (`_WRITE`, `_BUILD`, `_Q`, `_DO`), not with Qwen.
- `hojaiga_run.do_write()` guesses channel and relationship with regex tables (`_CHANNEL`, `_REL`).
- `mind/persona.py`, `mind/consequence.py`, `mind/workflow.py` are rule tables. The round-3 "confirm" labels were made from those rules, so Qwen learned the rules, not judgement.
- The trained adapter only knows **which button to press next**. It was never trained on planning, writing, code, describing, quizzes or replying.
- `world_designer.py` is a new file and hand-written logic. It breaks your rule. I suggest deleting it.

## 2. The idea: one shared "decision record"

Every capability becomes the same loop, which already exists in pieces:

```
task -> RAG gives the closest past cases + facts -> Qwen decides (route, plan, next step, words)
     -> act -> check the result -> the record (task, evidence, decision, outcome, score) goes back into the RAG
     -> good records become training rows for the next LoRA round
```

- **Decisions** (which route, which button, go on or ask first, resume or start fresh, reply or not) -> the **trained 2B adapter**. Small outputs, so the 6 GB GPU can train it.
- **Long output** (code, websites, emails, posts, quizzes, descriptions) -> the **7B models**, given your best examples from the RAG as samples. 7B cannot be trained on a 6 GB GPU, so writing quality improves through **better examples in the RAG**, not new weights.
- **Scan once, then remember**: this already exists (plan cache, `procedures`, app registry, `web_actions`). The first run scans or uses REA. Later runs answer from the pool. Each capability below just has to write its result back.

## 3. Data per capability

"Self" = the system can collect it itself. "You" = only you can give it (taste, real examples, the right answers).

| # | Capability | Training data (for Qwen) | Knowledge data (for the RAG) | Test set (right answers to measure against) | Who |
|---|---|---|---|---|---|
| 1 | **Write code / build websites** | Not needed at first: `qwen2.5-coder:7b` is already good. Later: spec -> code pairs that **passed** a test/screenshot check. | Docs for the stack you want (HTML/CSS/JS, React, Tailwind, Python). Public sets to check the licence of: WebSight (screenshot -> HTML), Design2Code (real pages). | 30-50 specs, each with a picture of the result you would call "good". | You: the specs + 20-50 sites you like (URL + why). Self: docs. |
| 2 | **Draw and trace anything** | Image -> plan of strokes (what to draw, in what order) rows. | Stroke data (Google QuickDraw is CC-BY), your own traced examples. | 30 images + the tracing you call correct. | You: 30-100 images you want drawn/traced, with a reference drawing if you have one. |
| 3 | **Teach any app** | Screenshot + UI tree + goal -> next action. Needs **desktop** rows, not only web: target 10-25k rows over 50+ apps. | REA results, UI scans, manuals, tutorial transcripts (YouTube rate-limits us to ~3 videos per window). | 20 apps x 10 "how do I ..." with the right steps. | You: the list of apps that matter for the demo + **permission** to record while you use them yourself (`harvest/local_recorder.py`, opt-in). Self: REA, manuals. |
| 4 | **Pick up left-over work or start fresh** | Screen/file at stage X + goal -> "resume at step N" / "start again" (1,031 rows exist, built from web). | Saved run reports (`data/hojaiga_runs`). | 30 real half-done jobs (a half deck, half doc, half site) + what the right next step is. | You: half-done files from your real work (copies). |
| 5 | **Make quizzes** | Source text -> quiz in your style. | The teaching material (your notes, PDFs, app manuals). | 20 sources + quizzes you would accept. | You: 30-50 quizzes you like + the material they came from. |
| 6 | **Watch videos and explain them** | Frames + transcript -> what is happening, per time window. | Already built: `video_pipeline.py`, `video_explain.py`, `consolidate.py`. | 20-30 videos with **your** written notes "at 1:20 they open X, at 2:05 ...". This is the only honest way to score it. | You: video links + notes. |
| 7 | **Describe a photo in full detail** | Image -> dense description. Public sets to check: DOCCI (CC-BY), PixMo-Cap. | - | 50 photos with a description you wrote, with every detail you would expect. | You: 50 photos (no private people unless you want that) + descriptions. |
| 8 | **Dig through many pages of a site** | Page -> "scroll / next page / open link / done" rows (web crawl gives these). | `web_learn.py`, `web_actions.py` already store paths. | 100 tasks "on site Y find X" + the right answer. | You: the 100 tasks. Self: the crawl (headless, only with your go). |
| 9 | **Deep UI tree, REA, full app understanding** | Questions about the app -> answers from REA facts. | REA sweep (49 done), native programs need Ghidra. | 20 apps x 10 questions with known answers. | You: yes/no on installing Ghidra; the questions. Self: the rest. |
| 10 | **Write content in Gmail / Word / PPT / LinkedIn in the best style** | Brief -> text, **and good-vs-bad pairs** (same brief, the version you prefer). | Your best real writing per channel, with names removed. | 20 briefs per channel, you score the drafts 1-5. | You: 100-300 examples per channel you are proud of (sent emails, posts that did well, slides). Only you know "your" quality. |
| 11 | **Read messages and reply correctly** | Thread -> decision (reply / ask / ignore / escalate / needs approval) + the reply. | Your past threads with the reply you really sent. | 50 threads with the decision you would make. | You: 300-1,000 past threads (export, names hidden). Reading your Gmail needs your explicit yes; **sending always asks first**. |
| 12 | **The "Jarvis" decision itself** (what kind of task is this, which tool, which order, when to ask) | Task -> route + plan + "ask first?". This replaces the regexes in `classify()`. Every run report becomes a labelled row automatically. | All past run reports. | Your 200-500 commands. | **You: the most useful single thing.** Write 200-500 real commands, the way you would really say them to Jarvis (Hinglish and typos welcome), plus what you expect it to do. |

## 4. What to send me, in priority order

1. **200-500 real commands** with what you expect (item 12). This shapes the brain more than anything else.
2. **Your best writing**: 100-300 per channel (item 10) + 300+ message threads with your real replies (item 11).
3. **The demo list**: which 5-10 apps and 3-5 tasks go in the fundraising video. We make those perfect first, then widen.
4. **Test sets with right answers**: videos + your notes (6), photos + your descriptions (7), site tasks (8), app questions (9). Without these, any "92%" would be made up.
5. **Yes/no**: install Ghidra; record while you use apps; read your Gmail (read only); web crawl runs.

Easiest format: one folder per item, e.g. `data/inbox/commands/`, `data/inbox/writing/linkedin/`, plain files (txt, md, docx, pptx, png, mp4, csv). One line per command is fine. I convert them; you don't need any special format.

## 5. Going past the local limits (added 2026-10-27, built and measured)

**Thinking and eyes: free hosted models, through the gateway that already existed** (`organ_37_llm_gateway.py`, `mind/app_qa.ask_llm`).
- Bug found: the gateway read keys from `All codes\.env`, but your keys are in `D:\new_automation\.env`, so the Groq/OpenRouter fallback **never ran**. Fixed.
- Two default model names had been retired by the providers. The gateway now checks the providers' own lists (`cloud_models(name)`), and you can set the model per provider with `HOJAIGA_<NAME>_MODEL`.
- Measured today with your keys:

| Provider | Model | Task | Time | Result |
|---|---|---|---|---|
| Groq | gpt-oss-120b | route/plan a task | 1.3 s | right answer |
| NVIDIA | nemotron-3.5-super-vl-120b | text | 1.4 s | right answer |
| NVIDIA | same model, with an image | describe a picture | 3.4 s | every object, colour, position and the text were correct |
| local qwen2.5:7b (before) | | world plan | ~140 s | |

- **Google Gemini 3.8 Flash** is free on Google AI Studio (text, images, video). To add it, get a key at aistudio.google.com and put `GEMINI_API_KEY=...` in `D:\new_automation\.env` (you do this yourself; I don't create accounts or type keys).
- Modes (`HOJAIGA_CLOUD` in `.env`): `fallback` (default: local first, cloud when local fails), `first` (cloud first: fast and smart), `off`.
- **Privacy rule built in:** anything marked private (replies to someone's message, and later your mail, your files, screenshots of your screen) and any prompt that carries a password, OTP, card number or key **never leaves the machine**. Google states that free-tier content is used to improve its products.
- Test AR75 (15 checks) covers this offline; the suite is 11/11 groups green.

**Training: free GPUs instead of the 6 GB laptop GPU**
- **Kaggle**: free P100 16 GB, about 30 h per week (from Kaggle's docs). That fits a 4-bit LoRA of an **8B** Qwen-VL, which the laptop can't do. `train_qlora.py` runs there as it is: upload the script and the `runs/<id>` train/eval files as a Kaggle dataset, then bring the adapter back. Colab's free T4 also works but disconnects more often.
- **Teacher -> student (the way past the limit):** the big hosted model works as the **teacher**. It writes the plans, routes, descriptions and drafts. The checker keeps only the ones that worked, they go into the RAG and become training rows, and the local Qwen learns from them. The demo then runs fast and private on the laptop, and the cloud is only needed for new kinds of task.
  - Check each provider's terms before training on its outputs. Some forbid using outputs to build competing models. gpt-oss is an Apache-2.0 open-weights model, so its outputs are the safest teacher data.

## 6. Honest limits

- **Laptop GPU 6 GB**: local training stays at 2B-3B; 8B trains on Kaggle (section 5). For the video, the trained local model should run as GGUF in llama.cpp (`train_qlora.export_plan`).
- **Free tiers have daily limits** and can change without notice. The gateway moves to the next provider on a 429, and to the local model when every provider is busy. A demo should not depend on one provider.
- With 120B-class hosted models as the thinker, the ceiling is much higher. It is still **measured per job** on your test sets (section 4), not assumed.
- Still some code is needed: Qwen cannot press keys or read the screen without the existing executors. The change is that the **decisions** move from rules in code into Qwen + RAG. The code only does the actions and checks.

## 7. Changes in existing files (no new .py files)

1. `hojaiga_run.py` `classify()` / `do_write()`: ask Qwen with the nearest past runs from the RAG; regex only as a fallback when Ollama is down. Write each outcome back.
2. `mind/train_rows.py`: add row kinds `route`, `plan`, `reply_decision`, `describe`, built from run reports and your inbox. Labels come from **outcomes and your answers**, not from rules.
3. `rag/procedures.py` (+ `harvest/rag_feed.py`): an "exemplar" kind (your best writing/quizzes/sites) that `do_write` and the code path retrieve as samples.
4. `mind/persona.py`, `mind/consequence.py`: the rule tables become the fallback/teacher; the adapter decides once it beats them on your test set.
5. `train_qlora.py`: score each row kind separately in `evaluate_run` so every round shows real numbers per capability.
6. Delete `world_designer.py` (with your OK).
