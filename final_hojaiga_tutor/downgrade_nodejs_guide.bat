@echo off
echo ========================================
echo Node.js Downgrade Guide
echo ========================================
echo.
echo CURRENT ISSUE:
echo - Node.js version: 26.4.0 (too new for Electron 30)
echo - Electron version: 30.5.1
echo - Incompatibility: Electron cannot run with Node 26
echo.
echo SOLUTION:
echo - Downgrade to Node.js 20 LTS (Long Term Support)
echo - Node 20 is officially supported by Electron 30
echo.
echo ========================================
echo STEP 1: Download Node.js 20 LTS
echo ========================================
echo.
echo 1. Visit: https://nodejs.org/
echo 2. Click "Downloads"
echo 3. Select "20.16.0 LTS" (Recommended for Most Users)
echo 4. Download the Windows Installer (.msi)
echo.
echo ========================================
echo STEP 2: Install Node.js 20
echo ========================================
echo.
echo 1. Run the installer you downloaded
echo 2. Follow the installation wizard
echo 3. IMPORTANT: Uncheck "Automatically install the necessary tools"
echo    (to avoid conflicts with current installation)
echo 4. Choose installation path: C:\Program Files\nodejs
echo 5. Complete installation
echo.
echo ========================================
echo STEP 3: Verify Installation
echo ========================================
echo.
echo After installation, open a NEW Command Prompt and run:
echo   node --version
echo.
echo Should show: v20.16.0
echo.
echo ========================================
echo STEP 4: Reinstall Clicky Dependencies
echo ========================================
echo.
echo 1. Open Command Prompt in Clicky folder:
echo    cd D:\new_automation\final_hojaiga_tutor
echo.
echo 2. Delete node_modules folder:
echo    rmdir /s /q node_modules
echo.
echo 3. Reinstall dependencies:
echo    npm install
echo.
echo 4. Rebuild:
echo    npm run build
echo.
echo.
echo ========================================
echo STEP 5: Start Clicky
echo ========================================
echo.
echo npm start
echo.
echo.
echo ========================================
echo ALTERNATIVE: Use NVM (Node Version Manager)
echo ========================================
echo.
echo If you want to switch between Node versions easily:
echo.
echo 1. Install NVM for Windows:
echo    https://github.com/coreybutler/nvm-windows/releases
echo.
echo 2. Install Node 20:
echo    nvm install 20.16.0
echo.
echo 3. Switch to Node 20:
echo    nvm use 20.16.0
echo.
echo 4. Then run Clicky:
echo    cd D:\new_automation\final_hojaiga_tutor
echo    npm start
echo.
echo.
echo ========================================
echo IMPORTANT NOTES
echo ========================================
echo.
echo - Node.js 20 LTS is the most stable version for Electron 30
echo - Electron 30 officially supports Node 18, 20, and 22
echo - Node 26 is too new and not officially supported
echo - After downgrade, Electron should work correctly
echo.
echo.
pause
