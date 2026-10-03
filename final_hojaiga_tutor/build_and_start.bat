@echo off
set PATH=D:\new_automation\final_hojaiga_tutor\src;%PATH%
cd D:\new_automation\final_hojaiga_tutor
echo Building TypeScript...
npm run build
echo.
echo Starting Clicky...
npm start
