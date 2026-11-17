# Hojaiga

**A Windows assistant that learns any app on its own, does real work in it, and proves the result.**
Independent research project by Dhruv Patel, August to November 2026. **Archived:** this repository is kept as a public record of the work. Take anything useful.

<p align="center"><img src="media/hojaiga_world_build.gif" width="360" alt="A Minecraft-style world built in Blender by Hojaiga"></p>

## The idea

Most automation needs a custom integration for every program. Much of the software people use, especially older Windows programs inside companies, has no API. People still learn those programs by looking at them and trying things.

Hojaiga was meant to be an **automation operating system for Windows**: hand it any application and it learns how that application works, from the program's own files and from its screen, then does the task in a background window without touching your mouse, and proves the result before it says "done". It could also teach: point at the right button and explain it.

**The niche:** Windows-native and any app, its own intelligence running on your machine (no paid model API, your data stays local), background work, and proof with an audit trail.

## How it was built

It started as a written blueprint: an operating system of **15 organs in 7 layers** (Core Intelligence, Knowledge & Decision, Execution, Platform, UI, Runtime, External), with a local LLM as the brain. The specs are in `architechure standards-oragn files/`. In code it grew to **more than 60 organ modules** in `All codes/core_organs/`, about 230k lines of Python and 29 test suites:

- **Learning an app from its files:** menus, shortcuts and dialogs read from the executable (PE resources), Office object models from type libraries, UI words from Store apps, strings from .NET and Electron apps.
- **Learning it from the screen:** UI Automation trees, every menu and safe dialog opened and closed, vision for apps that draw their own interface.
- **Acting without your mouse:** a virtual mouse and keyboard for WinForms, WPF, WinUI and Blender; Office through its object model; the web through Playwright.
- **Proof:** a task is DONE only when the saved file (read back) or the final window (judged by a vision model) shows the result.
- **Safety:** pay, send, delete, install and sign-in controls stop and ask first.

| Measured on one laptop | Result |
|---|---|
| PowerPoint full ribbon map | 11 tabs, ~360 controls, ~980 menu items in ~5 min |
| A program that was never opened | menus and shortcuts read from its file in ~1 s |
| Excel table into PowerPoint, invisible | 24 of 24 cells verified from the saved files |
| Blender object from one sentence | table, chair, bookshelf, lamp built and checked from three views |

## Competitors, and credit

- **HeyClicky** (Clicky, by Farza, open source under MIT: https://github.com/farzaa/clicky) is an AI teacher that sees your screen, talks and points. In October I built Hojaiga's teaching layer ("Professor") for Windows after studying Clicky. On that experience HeyClicky is the direct competitor, and the better product.
- **RPA tools** (UiPath, Power Automate) automate reliably but need a recorded flow per app.
- **Hosted computer-use agents** from the big AI labs reason well over screenshots, from the cloud and per call.
- **Microsoft UFO** (MIT) was studied for how one task is handed between apps. OmniParser's icon detector (MIT) and Qwen3-VL models are used inside.
- Much of the code was written with AI coding assistants (Claude Code, Gemini).

## Why it stopped

The core bet was that Hojaiga could have **its own intelligence**, without a large hosted model. On a 6 GB laptop GPU it could not: the local 4B model found the right spot on professional app screenshots 12.5% of the time, and fine-tuning it on my own data made it worse overall (39% against 53% on 630 held-out items). Every gain came from structure and verification, not from the local model. The teaching experience I most wanted already exists in HeyClicky, built on much larger models.

So the project ends in the form that works: the verified local core plus a **teacher**. A large model (Claude on the user's own key, or a free Gemini / Groq / OpenAI / NVIDIA model) proposes each step, the local "brain" checks it against the controls really on screen, keeps only proven steps, and switches the teacher off once it agrees often enough (`All codes/core_organs/mind/brain.py`, `organ_37_llm_gateway.py`).

## Videos and pictures

- [A world built in Blender by Hojaiga (12 s)](media/hojaiga_world_build.mp4): every object built and rendered through Blender's own commands; the world's design was written by hand as data.
- [The video-editing route (9 s)](media/hojaiga_video_edit.mp4): asked to "cut the silences and filler words" from a test clip, Hojaiga made this edit with captions and checked it.
- [Blender deep scan, 288 controls found](media/fig_scan.jpg) · [Excel task proven from the saved file](media/fig_excel.jpg) · [Blender table, three views](media/fig_table.jpg)
- Honest failures: [the flowchart that Paint mis-drew](media/fig_flow.jpg) · [a Calculator task the proof step refused](media/fig_calc.jpg)

## Full report

`reports/hojaiga_closing/HOJAIGA_REPORT.html` (download and open in a browser): the idea and business, the organ blueprint, methods, results, failures, the exit build, timeline, and videos.

## Run it

1. Windows 11 and Python 3.13. Create `hojaiga_env` in this folder and install the packages the modules ask for.
2. Copy `.env.example` to `.env` and add one key.
3. `hojaiga.bat "open notepad, type hello and save as C:\temp\hello.txt"`

The paths assume the project lives in `D:\new_automation` (set `HOJAIGA_ROOT` to change that). Offline tests: `python -m core_organs.si_tests_mind` from `All codes` (22 groups, 365 checks).
