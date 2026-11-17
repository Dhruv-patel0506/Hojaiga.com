# Hojaiga — resources to fetch (spec for Gemini NotebookLM)

Written 2026-10-27. Give this whole file to Gemini. Gemini's job: **find each item at its official source, confirm the exact name / version / licence / size, and produce download links.** The owner downloads them (1 TB free) and drops them into the folders named below. Claude then integrates them into the EXISTING code (no new Python files).

**Rules for Gemini**
1. Official sources only (the project's own site, its GitHub/Hugging Face page, Microsoft / Google / Blender official pages). No re-uploads, no mirrors.
2. For every item report: exact name, version, official URL, licence (and whether commercial use is allowed), download size, file format, SHA-256 if the source publishes one.
3. If an item below does not exist under that name, or is discontinued, say so and propose the closest official alternative. Do not invent names.
4. Mark anything that is research-only / non-commercial: Hojaiga is a product that will be shown to investors.

**Delivery format** — one folder per item: `D:\new_automation\data\inbox\<section>_<item>\` containing the download plus a `SOURCE.txt`:
```
name: ...
version: ...
url: ...
licence: ...   commercial_use: yes/no/unclear
downloaded: YYYY-MM-DD
sha256: ...
notes: ...
```

---

## 0. What Hojaiga is (context for Gemini)

Hojaiga is a local, private, all-in-one computer worker: the person says what they want in plain words (any language, Hinglish included) and it does it in any app or website, alone or across several apps together (Chrome → Excel, Paint → Word, Excel → PowerPoint, video → document). It learns each app by **scanning and reverse-engineering it**, plans like a skilled human, acts with every input (click, type, shortcut, drag, draw, the app's own scripting / object model), **proves** the result (reads the saved file, looks at the picture), and learns from every run. Beyond app control: writing (Gmail / Word / PPT / LinkedIn), replying to messages, code and websites, watching videos, describing photos, quizzes, resuming unfinished work, **video editing**, drawing, 3D building in Blender.

Runs on: Windows 11 **Home**, RTX 3050 **6 GB VRAM**, local Ollama (Qwen2.5 7B / 3B, Qwen2.5-VL 3B), a local Qwen2.5-VL 7B server, LanceDB RAG (~5 GB, 7.7k procedures, 11.9k app commands), Node 22 for REA, Python 3.13.

## 1. Already present — do NOT fetch again

- REA (Reverse Engineer Anything, `rea-agents` 6.8.0, MIT) — installed in `tools\rea`, bridged. Handles web pages, web bundles, APIs from recorded traffic, Electron apps. **Cannot open native binaries without a disassembler (see 2.1).**
- Ollama models: qwen2.5:7b, qwen2.5:3b, qwen2.5vl:3b, qwen2.5-coder:7b, nomic-embed-text, minicpm-v, llava, llama3.2-vision.
- OmniParser (local repo), Playwright Chromium, pywin32, uiautomation, python-docx / python-pptx / openpyxl, Blender 5.2 (D:\blender.exe), Microsoft Office (Word, Excel, PowerPoint).

---

## 2. Reverse engineering — understanding apps from the inside (HIGHEST PRIORITY)

| # | Item | What to fetch | Why |
|---|---|---|---|
| 2.1 | **Ghidra** (NSA, Apache-2.0) | Latest stable release zip from github.com/NationalSecurityAgency/ghidra/releases | REA's native-binary analysis needs a disassembler. Without it Excel, Word, Paint, Calculator binaries cannot be reverse-engineered: only their menus/UI are known. |
| 2.2 | **Eclipse Temurin JDK 21** (LTS, GPL+CE) | Windows x64 zip (not the installer) from adoptium.net | Ghidra's required Java runtime; kept portable inside the project, nothing installed system-wide. |
| 2.3 | **ILSpy** (MIT) | Latest release zip from github.com/icsharpcode/ILSpy | Decompiles .NET / WPF apps (many Windows tools) into readable code: commands, dialogs, settings. |
| 2.4 | **Detect It Easy** (MIT) | Portable Windows zip from github.com/horsicq/Detect-It-Easy | Tells which toolkit an app is built with (Win32, WPF, Qt, Electron, WinUI) so the right route is chosen first. |
| 2.5 | **@electron/asar** (MIT) | npm package name and version only (Claude installs it into the isolated Node) | Unpacks Electron apps (Discord, VS Code, Teams…) for REA's JavaScript analysis. |
| 2.6 | **Accessibility Insights for Windows** (Microsoft, MIT) | MSI from accessibilityinsights.io | Ground truth of every app's accessibility tree, to check our own scanner against. |
| 2.7 | **Windows App SDK / WinUI 3 docs + UWP app manifest schema** (Microsoft Learn) | Official doc pages listed as URLs | Store apps (Paint, Calculator) hide their controls from background input; their manifests and XAML resources say what exists. |

## 3. App knowledge — official documentation, downloaded whole

Format wanted: offline HTML zip, or the official GitHub docs repository, or PDF. One folder per app.

| # | App | Official source to find |
|---|---|---|
| 3.1 | **Office object models** (Word, Excel, PowerPoint, Outlook VBA reference) | The Microsoft "VBA-Docs" GitHub repository (MicrosoftDocs) — confirm name and licence (believed CC BY 4.0) |
| 3.2 | **Office keyboard shortcuts** | Microsoft Support pages: "Keyboard shortcuts in Word / Excel / PowerPoint / Outlook" — list of URLs |
| 3.3 | **Blender manual + Blender Python API** | docs.blender.org — the downloadable HTML zips for the installed version 5.x (manual licence CC BY-SA) |
| 3.4 | **Chrome DevTools Protocol** | chromedevtools.github.io/devtools-protocol (GitHub source repo) |
| 3.5 | **Windows UI Automation** (control patterns, events) | Microsoft Learn pages, as a URL list |
| 3.6 | **Paint, Calculator, Notepad, Photos, Clipchamp** | Microsoft Support help pages, URL list |
| 3.7 | **LibreOffice** (Writer / Calc / Impress) help + SDK API reference | help.libreoffice.org offline help pack; api.libreoffice.org — a fully scriptable free office suite to test on |
| 3.8 | **GIMP, Inkscape, Krita** user manuals | Official offline manual downloads (drawing / image apps to learn) |
| 3.9 | **VS Code** docs | github.com/microsoft/vscode-docs |
| 3.10 | **FFmpeg** full documentation | ffmpeg.org/documentation — every filter (video editing engine, section 7) |

## 4. Computer-use agent datasets (tasks across one and SEVERAL apps)

For each: tasks (JSON), screenshots if provided, the evaluation scripts, licence. **Multi-app tasks are the most wanted.**

| # | Dataset | What it teaches | Look for |
|---|---|---|---|
| 4.1 | **OSWorld** | Real desktop tasks incl. multi-app (browser + office + files) with automatic checkers | GitHub repo + task JSONs |
| 4.2 | **Windows Agent Arena** (Microsoft) | Windows-specific tasks incl. multi-app, with checkers | GitHub repo + tasks |
| 4.3 | **OmniACT** | Desktop + web tasks → executable action scripts | dataset card + licence |
| 4.4 | **Mind2Web** (and Multimodal-Mind2Web) | Website tasks with action sequences | Hugging Face dataset + licence |
| 4.5 | **GUI-Odyssey** | Cross-app tasks (one task moving through several apps) — the multi-app pattern | dataset + licence |
| 4.6 | **ScreenSpot / ScreenSpot-v2 / ScreenSpot-Pro** | "Where is this button on screen?" test sets (desktop, web, pro apps) | Hugging Face |
| 4.7 | **OS-Atlas grounding data** | Large screenshot → element training data across Windows / web / mobile | Hugging Face + licence |
| 4.8 | **AgentNet / OpenCUA desktop trajectories** (if released) | Human demonstrations on real desktop apps | Confirm existence, licence |
| 4.9 | **MASSIVE** (Amazon, 51 languages incl. Hindi), **CLINC150**, **LinCE** (code-mixed Hindi–English) | Understanding requests, Hinglish | Hugging Face / official pages |

## 5. Models — must RUN locally on 6 GB VRAM (quantized GGUF or ≤ 7B)

| # | Model | Why | Ask Gemini for |
|---|---|---|---|
| 5.1 | **UI-TARS-1.5-7B** (ByteDance) | A model trained specifically to see screens and act on them | Official HF repo + an official or well-known GGUF Q4 quant; licence |
| 5.2 | **OS-Atlas-Base-7B** | Screen-element grounding (find the button for an instruction) | HF repo, licence |
| 5.3 | **OmniParser v2** (Microsoft) weights | Icon detector + captioner upgrade over our current version | HF repo `microsoft/OmniParser-v2.0` — confirm; licences differ per part |
| 5.4 | **Qwen2.5-VL-7B-Instruct GGUF** (Q4_K_M) | Stronger local eye than the 3B for the proof step | Official Qwen GGUF if published |
| 5.5 | **faster-whisper large-v3-turbo** (CTranslate2) | Speech-to-text for video editing / video watching | HF repo, MIT |
| 5.6 | **A small reranker** (e.g. bge-reranker-v2-m3) | Better RAG retrieval ordering | HF repo, licence |

## 6. Drawing, 3D building, worlds with people

| # | Item | Why |
|---|---|---|
| 6.1 | **Quick, Draw! dataset** (Google, CC BY 4.0) — the *simplified* ndjson files | Millions of human sketches as pen strokes: exactly the format our drawing engine plays back. "Draw a house / cat / bicycle" from real sketches. |
| 6.2 | **Kenney asset packs** (CC0) — nature, city, characters, low-poly | Ready low-poly pieces for Blender worlds (trees, houses, roads, people) |
| 6.3 | **Poly Haven** (CC0) — models, textures, HDRIs | Realistic materials and lighting for renders |
| 6.4 | **Mixamo** (Adobe; free with an Adobe account; check licence wording) — 2–3 rigged human characters + animations: chopping, walking, sitting, waving, typing | **"A human doing something complicated"**: a real rigged person with a real animation, placed in the world by Blender's Python API |
| 6.5 | **CMU Graphics Lab Motion Capture database** (free; check terms) — BVH conversions | More human actions for animation |
| 6.6 | **PartNet / ShapeNet** — ONLY if licence allows commercial use (likely research-only: flag it) | Real objects split into parts with real proportions |

## 7. Video editing (point 8)

| # | Item | Why |
|---|---|---|
| 7.1 | **FFmpeg full build for Windows** (gyan.dev "full" release, GPL) | The editing engine: cuts, joins, captions, music, transitions, render — no window needed |
| 7.2 | **auto-editor** (WyattBlue, Unlicense) | Cuts silences / dead air automatically |
| 7.3 | **PySceneDetect** (BSD) | Finds shot changes |
| 7.4 | **Shotcut** (GPL) and/or **Kdenlive** (GPL) — portable builds | Free editors with open project files (MLT XML): Hojaiga writes a real project the person can keep editing |
| 7.5 | **DaVinci Resolve (free)** + its scripting README | Pro editor with a Python API — Gemini: confirm whether external scripting works in the FREE version |
| 7.6 | **TVSum**, **SumMe**, **QVHighlights** datasets | Which moments of a video matter (highlights, summaries) |
| 7.7 | **Free music**: YouTube Audio Library or Free Music Archive (per-track licence) — 30–50 tracks of different moods | Background music that is legal to use |
| 7.8 | **Sample raw footage**: Pexels / Pixabay videos (free licence) — 30–50 clips (talking head, travel, product, cooking) | Test material, since the owner has no own footage |

## 8. Watching videos, describing photos, writing, quizzes

| # | Dataset | Use |
|---|---|---|
| 8.1 | **ActivityNet Captions**, **YouCook2**, **MSR-VTT** | Describe what happens in a video, step by step |
| 8.2 | **DOCCI** (Google, very detailed image descriptions), **Localized Narratives** | "Describe this photo in every detail" |
| 8.3 | **Enron email corpus** | Real work-email style and threads (writing + replies) |
| 8.4 | **WebSight**, **Design2Code** | Screenshot / request → website code |
| 8.5 | **SciQ**, **RACE**, **SQuAD 2.0** | Making and checking quizzes |

## 9. "Jarvis" — which repository

The owner offered a "Jarvis" repo. Gemini: identify these and report licence, last update, what it runs on (cloud API or local), and Windows support:
- **microsoft/UFO** (Windows UI agent: a host agent chooses apps, app agents act through UI Automation and the apps' own APIs — the closest match to multi-app Windows work)
- **microsoft/JARVIS** (HuggingGPT: one planner choosing among many models)
- **simular-ai/Agent-S**
- **OpenInterpreter/open-interpreter** (note licence)
- Any repo the owner means by "Jarvis" — paste its URL.

How Claude will use it: **not run it as a second product.** Take its proven parts (how it splits a task between apps, how it hands data from one app to the next, its per-app API adapters, its help-document retrieval) and fold them into Hojaiga's existing loop, driven by the local Qwen + RAG + REA.

## 10. A safe place to test without taking over the owner's screen

Windows 11 **Home** has no Windows Sandbox and no Hyper-V. Gemini: confirm and give links for:
- **Oracle VirtualBox** (free) + a **Windows 11 Enterprise evaluation ISO** (Microsoft Evaluation Center, 90 days) → a separate Windows where Hojaiga can click and draw visibly all night. Report RAM / disk needs (the laptop's RAM should be stated by the owner).
- Whether Microsoft Office can be legally installed in such a test VM with the owner's licence.

---

## Priority order (fetch first → last)

1. Ghidra + Temurin JDK 21 (2.1, 2.2) — unlocks reverse engineering of native apps.
2. Office VBA-Docs + shortcuts + Blender manual/API (3.1–3.3) — knowledge for the apps used in demos.
3. OSWorld + Windows Agent Arena + GUI-Odyssey task sets (4.1, 4.2, 4.5) — the multi-app test bench.
4. UI-TARS-1.5-7B GGUF + OmniParser v2 (5.1, 5.3) — stronger eyes.
5. FFmpeg full + auto-editor + PySceneDetect + sample footage + music (7.1–7.3, 7.7, 7.8) — video editing.
6. Quick, Draw! + Kenney + Mixamo (6.1, 6.2, 6.4) — drawing and the Blender world with a person.
7. VirtualBox + evaluation ISO (10) — night testing without touching the owner's screen.
8. Everything else.
