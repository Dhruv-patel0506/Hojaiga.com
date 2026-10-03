@echo off
echo Starting Clicky...
cd /d "D:\new_automation\final_hojaiga_tutor"
set NODE_ENV=development
set ELECTRON_ENABLE_LOGGING=true
node_modules\.bin\electron.cmd dist/src/main.js
pause
