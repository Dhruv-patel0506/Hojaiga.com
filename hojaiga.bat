@echo off
rem ============================================================================
rem  HOJAIGA - one command.  It boots what is needed and does the task.
rem    hojaiga.bat "go to the Pricing page on todoist.com"
rem    hojaiga.bat "what is the shortcut for bold in Google Docs?"
rem    hojaiga.bat "write a LinkedIn post about launching our app"
rem    hojaiga.bat "open Paint and save the picture as D:\new_automation\scratch\a.png"
rem    hojaiga.bat "<task one>; then <task two>"      (parts run in order; independent web/question/write parts side by side)
rem    hojaiga.bat --yes "<task>"       approve the risky controls this task names (pay / send / delete ...); without it the run stops and asks
rem    hojaiga.bat --dry "<task>"       intake + routing + risk check only, nothing is run
rem    hojaiga.bat --resume             continue the last run: only its unfinished tickets
rem    hojaiga.bat --boot-only          health of every service and the knowledge
rem  Reports: D:\new_automation\data\hojaiga_runs\<run id>\report.json   (library noise goes to stderr.log there)
rem ============================================================================
setlocal
set "HOJAIGA_PY=D:\new_automation\hojaiga_env\Scripts\python.exe"
set "PYTHONPATH=D:\new_automation;D:\new_automation\All codes"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
if not exist "D:\new_automation\data\hojaiga_runs" mkdir "D:\new_automation\data\hojaiga_runs"
cd /d "D:\new_automation\All codes"
"%HOJAIGA_PY%" -X utf8 -W ignore -m core_organs.hojaiga_run %* 2>>"D:\new_automation\data\hojaiga_runs\stderr.log"
endlocal
