@echo off
echo Starting Live Interactive Teaching Engine...
echo.
echo Prerequisites:
echo   - Ollama running on http://localhost:11434
echo   - llava:latest model installed
echo   - Python with pyautogui, pillow, pywin32
echo.
cd /d D:\new_automation\final_hojaiga_tutor
set PATH=D:\new_automation\final_hojaiga_tutor\src;%PATH%
npx ts-node index.ts
