---
name: hojaiga-environment-rules
description: Windows environment and command rules - Python 3.13 venv path, PYTHONPATH setup, PowerShell semicolon syntax, UTF-8 flag, and local service ports (Ollama gatekeeper 11435, CNS bridge 11436, Chrome CDP 9222).
---

# Skill 02 — Environment & Command Rules (Windows)

## Interpreter / venv
- **Always** use the project venv, never system python:
  `D:\new_automation\hojaiga_env\Scripts\python.exe`
- Python **3.13.14**. This matters: some wheels have no cp313 build (see skill 06).

## PYTHONPATH (required for `core_organs.*` imports)
```powershell
$env:PYTHONPATH="D:\new_automation;D:\new_automation\All codes"
```
Without the `All codes` entry, `from core_organs.X import Y` fails.

## Shell = Windows PowerShell 5.1
- **No `&&`.** Chain with `;`.
- Long commands: keep under 500 chars; write a `.py`/`.ps1` file and run it instead.
- Capture to file then read, because the console echo garbles multi-line `-c` output:
  ```powershell
  python ... 2>&1 | Out-File -Encoding utf8 D:\new_automation\out.log; Get-Content D:\new_automation\out.log
  ```
- Use `-X utf8` for python when printing non-ASCII (arrows, `—`) to avoid cp1252 crashes.

## Compile-before-run discipline
```powershell
D:\new_automation\hojaiga_env\Scripts\python.exe -m py_compile "path\to\file.py"; echo "COMPILE=$LASTEXITCODE"
```
`COMPILE=0` is the gate. Never run a suite on files you haven't compiled.

## Capability probe (what's actually installed)
```powershell
python -c "from core_organs.desktop_grounding import HAS_UIA,HAS_PIL,HAS_PYTESSERACT,HAS_TORCH; print(HAS_UIA,HAS_PIL,HAS_PYTESSERACT,HAS_TORCH)"
```
These four booleans gate the perception tiers. If one is False, the corresponding tier
must self-report `tiers_skipped` — never pretend it ran.

## Local services (all free, all on localhost)
| Service | Endpoint | Notes |
|---|---|---|
| Gatekeeper LLM proxy | `http://127.0.0.1:11435/api/chat` | header `X-Hojaiga-Validation: 339680`; model `llama3`. Must be pre-warmed; hard timeout in code. |
| CNS bridge (organ_29 IPC) | port `11436` | AppAgent→HostAgent popup events. |
| Chrome CDP | `:9222` | reuse the running browser; NEVER relaunch per step. |
| Tesseract binary | `C:\Program Files\Tesseract-OCR\tesseract.exe` | on PATH; v5.4.0. |

## Live crew launch
- Real swarm runs through `start_hojaiga.bat` / organ_01 live config. Before any live
  run, confirm the Gatekeeper on 11435 answers a 1-token ping, else Tier-3/judge calls
  will eat their full timeout budget.

## Temp-file hygiene
- Write scratch under `D:\new_automation\` and **delete it when done** (probe scripts,
  `*.log`, `_*_smoke.png`). Don't leave `_probe_*.py` or audit-log dirs lying around.
