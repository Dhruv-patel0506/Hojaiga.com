# Hojaiga

Cognitive organ-based automation system: orchestrates **any** desktop or web
application through a closed autonomy loop (perceive → decide → act → verify →
recover → learn), backed by local-only AI (Ollama llama3 gatekeeper, YOLO/OWL,
UI Native — **no paid cloud APIs, no keys**).

## Layout

| Path | What |
|---|---|
| `All codes/core_organs/` | The organ system (55+ organs): brain, memory, popup defense (organ_29), pro-knowledge (organ_47), enhanced scanner (organ_44), virtual cursor/HUD (organ_52), teaching assistant (organ_53), orchestrator, runners, test suite |
| `All codes/` (root files) | Engines, integrations, UIs, DB manager, routers, services around the organs |
| `claude_skills/` | The Hojaiga skill set for AI agents (rules, architecture, pitfalls, scenario playbook) — start with `CLAUDE.md` |
| `OmniParser/` | Screen-parsing vision model code (weights are NOT committed — download locally) |
| `PIXEL_16BIT/` | Native pixel-finder library (source; build outputs not committed) |
| `clicky/` | Companion Flutter app source |
| `architecture/`, `architechure standards-oragn files/`, `diagrams/`, `extra MD files/` | Architecture standards, diagrams & docs |
| `data/`, `memory/`, `organ_03_memory/`, `organ_04_knowledge/`, `organ_10_infrastructure/` | Persistence & knowledge layer |
| `config/`, `pipelines/`, `plugins/`, `pixel-agents/`, `cosmos_system/` | Runtime config & subsystems |
| `visual_world/`, `windows_ai_tutor/`, `hojaiga-workspace/`, `hojaiga_pixel_automation/`, `final_hojaiga_tutor/` | Supporting projects |
| `llama.cpp/` | Local inference integration (source) |

## Setup (local working environment — never committed)

```powershell
# Python 3.13 venv with the pinned-free/local stack:
python -m venv hojaiga_env
hojaiga_env\Scripts\pip install pyautogui pygetwindow psutil pillow opencv-python pytesseract numpy pandas
hojaiga_env\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
hojaiga_env\Scripts\pip install easyocr ultralytics supervision "transformers==4.51.3" timm einops
# Windows-only: uiautomaci2 / UI Native via COM (see claude_skills/02-environment.md)
# Local LLM: Ollama serving llama3 on 127.0.0.1:11435 (Gatekeeper)
```

## Verify

```powershell
$env:PYTHONPATH = "<repo>;<repo>\All codes"
python "All codes\core_organs\run_system_intelligence_tests.py" -k Hojaiga
```

## Rules

See `claude_skills/CLAUDE.md` — the 8 laws (free/local/no-API, honesty,
dynamic knowledge, verify-don't-believe, HITL safety, bounded time, cheapest
signal first, suite gates). Model weights, environments, binaries and runtime
output stay out of this repo by design (see `.gitignore`).
