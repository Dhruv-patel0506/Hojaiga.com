@echo off
rem Scan the applications of the checklist (tier 1 by default), keep pictures of every checkpoint in ONE folder, and zip it.
rem   scan_apps.bat                      tier 1, picks up at the first application that is not done yet
rem   scan_apps.bat --apps notepad       only these applications (comma list; a key of the plan OR ANY application name: --apps "visual studio code,calculator")
rem   scan_apps.bat --tier 2             another tier
rem   scan_apps.bat --list               show the checklist and stop
rem   scan_apps.bat --again              run applications again even if their checkpoint says done
rem   scan_apps.bat --no-guide           scan only (no guide procedures)      --no-vision  without the vision model
rem Every run also writes the guide's workflows for each app (workflows.md / workflows.json in its folder; the whole library: data\professor\workflows\INDEX.md)
rem Results: D:\new_automation\scan_output\<date_time>\   (INDEX.html, CHECKLIST.md, <app>\ pictures + report.html, run.log)  and the same folder as a .zip
setlocal
cd /d D:\new_automation
set PYTHONPATH=D:\new_automation;D:\new_automation\All codes
set PYTHONUTF8=1
"D:\new_automation\hojaiga_env\Scripts\python.exe" -X utf8 -u -m core_organs.professor.checkpoints %*
echo.
echo Done. Open the newest folder under D:\new_automation\scan_output\ (INDEX.html), or attach its .zip.
pause
