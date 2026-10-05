@echo off
echo ========================================
echo Setting up Node 20.16.0 from src folder
echo ========================================
echo.

REM Add Node 20 to PATH temporarily
set PATH=D:\new_automation\final_hojaiga_tutor\src;%PATH%

echo Node version:
node --version
echo.

echo NPM version:
npm --version
echo.

echo ========================================
echo Installing Clicky dependencies
echo ========================================
echo.

cd D:\new_automation\final_hojaiga_tutor
rmdir /s /q node_modules
npm install

echo.
echo ========================================
echo Building TypeScript
echo ========================================
echo.

npm run build

echo.
echo ========================================
echo Starting Clicky
echo ========================================
echo.

npm start
