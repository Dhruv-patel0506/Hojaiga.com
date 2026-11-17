@echo off
rem  try.bat <app / web app / website>   -- scans it ON SCREEN (visible window, cursor shows what it finds), recognises it, teaches it back, prints a scorecard.
rem  examples:   try excalidraw.com      try https://trello.com      try notepad      try "Visual Studio Code"
rem  extra flags are passed on:  --pace 0.8 (slower)   --hold 15 (keep the window up longer)   --budget 40 (desktop scan time)   --no-scan (only what the pool already knows)
setlocal
set "PYTHONPATH=D:\new_automation;D:\new_automation\All codes"
cd /d "D:\new_automation\All codes"
"D:\new_automation\hojaiga_env\Scripts\python.exe" -X utf8 -m core_organs.try_app --show %*
endlocal
