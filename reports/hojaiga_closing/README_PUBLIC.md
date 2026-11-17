# Hojaiga

A research build of a Windows assistant that learns an app on its own and then does real work in it, proving each result before it reports "done". Built by Dhruv Patel, August to November 2026. **Archived: this is a research release, not a finished product.**

## What it does
- **Learns apps from code and from the screen.** Reads menus, dialogs and shortcuts out of a program's own files (PE resources, type libraries, Store-app UI strings), then maps the live interface through Windows UI Automation and vision.
- **Acts in the background.** A virtual mouse and keyboard deliver clicks, drags and typing to a window without moving the person's cursor. Office apps are driven through their object model.
- **Proves the result.** A task is DONE only when the saved file (read back) or the window (judged by a vision model) shows what was asked.
- **Stops before risky actions.** Pay, send, delete, install and sign-in controls need the person's yes.
- **Learns from a teacher.** A hosted model (Claude on your own key, or a free Gemini / Groq / OpenAI / NVIDIA model) proposes each step; the local "brain" checks it against the real controls on screen, keeps only proven steps, and turns the teacher off once it agrees often enough.

## Run it
1. Windows 11, Python 3.13. `python -m venv hojaiga_env` and install `requirements.txt`.
2. Copy `.env.example` to `.env` and add one key.
3. `hojaiga.bat "open notepad, type hello and save as C:\temp\hello.txt"`

Reports land in `data/hojaiga_runs/<run id>/report.json`. The brain's ledger is `data/ai_root/brain/ledger.jsonl`.

## What works and what does not
See the full report (`HOJAIGA_REPORT.html`), sections 5 and 6. In short: Office tasks through the object model, scanning and mapping apps, Blender builds and verification work well; small local models as the only eyes and brain, hidden packaged (Store) apps, and drawing in Paint do not.

## Credits
- The teaching layer ("Professor": see the screen, point, explain) was inspired by **Clicky** by Farza, an open-source AI teacher (MIT): https://github.com/farzaa/clicky and https://www.heyclicky.com/
- Microsoft UFO (MIT) was studied for the multi-app hand-off design. OmniParser icon detection (MIT) is used for icon finding. Qwen3-VL models for local vision.
- Built with help from AI coding assistants (Claude Code, Gemini).

## Contributing
Open problems are listed in the pinned issue. Take anything useful.
