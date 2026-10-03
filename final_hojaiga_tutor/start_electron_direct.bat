@echo off
set PATH=D:\new_automation\final_hojaiga_tutor\src;%PATH%
cd D:\new_automation\final_hojaiga_tutor
echo Starting Clicky with direct Electron...
"D:\new_automation\final_hojaiga_tutor\node_modules\electron\dist\electron.exe" dist/main.js
