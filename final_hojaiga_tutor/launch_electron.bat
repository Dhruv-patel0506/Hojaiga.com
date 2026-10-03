@echo off
echo Starting Clicky with Electron...
cd /d D:\new_automation\final_hojaiga_tutor
set PATH=D:\new_automation\final_hojaiga_tutor\src;%PATH%
start "" "D:\new_automation\final_hojaiga_tutor\node_modules\electron\dist\electron.exe" "D:\new_automation\final_hojaiga_tutor\dist\main.js"
