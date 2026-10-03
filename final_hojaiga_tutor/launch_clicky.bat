@echo off
echo ========================================
echo Clicky Launcher
echo ========================================
echo.

echo Method 1: Direct electron executable
echo.
echo Setting up environment...
set NODE_ENV=production
set ELECTRON_ENABLE_LOGGING=true

echo Starting Clicky...
cd /d "D:\new_automation\final_hojaiga_tutor"

echo.
echo Attempting to launch with full path...
"D:\new_automation\final_hojaiga_tutor\node_modules\.bin\electron.cmd" "D:\new_automation\final_hojaiga_tutor\dist\main.js"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Method 1 failed. Trying Method 2...
    echo.
    npx electron "D:\new_automation\final_hojaiga_tutor\dist\main.js"
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Method 2 failed. Trying Method 3...
    echo.
    node "D:\new_automation\final_hojaiga_tutor\node_modules\electron\cli.js" "D:\new_automation\final_hojaiga_tutor\dist\main.js"
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo All methods failed.
    echo.
    echo Please check:
    echo 1. Node.js version: node --version
    echo 2. Electron installation: npm list electron
    echo 3. Build output: dir dist
)

pause
