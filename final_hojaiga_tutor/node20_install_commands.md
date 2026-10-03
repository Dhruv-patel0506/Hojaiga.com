# Node.js 20 Installation Commands

## ⚠️ IMPORTANT: What Can Be Automated vs Manual

### ✅ CAN BE AUTOMATED (Safe):
- Download Node.js installer
- Delete node_modules
- Reinstall npm packages
- Build TypeScript
- Start app

### ❌ CANNOT BE AUTOMATED (Needs Manual):
- Running the Node.js installer (Windows security policy)
- This REQUIRES user interaction (Next, Next, Next, Install)

---

## 📋 STEP 1: Download Node.js 20 LTS Installer

```powershell
# Download Node.js 20.16.0 LTS installer
Invoke-WebRequest -Uri "https://nodejs.org/dist/v20.16.0/node-v20.16.0-x64.msi" -OutFile "$env:USERPROFILE\Downloads\node-v20.16.0-x64.msi"
```

## 📋 STEP 2: MANUAL INSTALLATION (REQUIRED)

```powershell
# Run the installer manually (Windows requires interaction)
# Navigate to Downloads and run: node-v20.16.0-x64.msi
# Follow the wizard (Next, Next, Next, Install)
# After installation, close ALL Command Prompt windows
# Open a NEW Command Prompt
```

## 📋 STEP 3: Verify Node.js Version

```powershell
# Open NEW Command Prompt after installation
node --version
# Should show: v20.16.0
```

## 📋 STEP 4: Navigate to Clicky Folder

```powershell
cd D:\new_automation\final_hojaiga_tutor
```

## 📋 STEP 5: Delete node_modules

```powershell
rmdir /s /q node_modules
```

## 📋 STEP 6: Reinstall Dependencies

```powershell
npm install
```

## 📋 STEP 7: Build TypeScript

```powershell
npm run build
```

## 📋 STEP 8: Start Clicky

```powershell
npm start
```

---

## 🎯 ALL COMMANDS IN ORDER (Copy-Paste After Manual Step 2)

```powershell
# STEP 1: Download Node.js installer
Invoke-WebRequest -Uri "https://nodejs.org/dist/v20.16.0/node-v20.16.0-x64.msi" -OutFile "$env:USERPROFILE\Downloads\node-v20.16.0-x64.msi"

# STEP 2: MANUAL - Run the installer from Downloads folder
# Then open NEW Command Prompt

# STEP 3: Verify version (in NEW Command Prompt)
node --version

# STEP 4-8: (In NEW Command Prompt, in Clicky folder)
cd D:\new_automation\final_hojaiga_tutor
rmdir /s /q node_modules
npm install
npm run build
npm start
```

---

## ⚠️ HONEST WARNING

The installer CANNOT be automated because:
- Windows security policy blocks silent installs
- User must click through UAC prompts
- User must accept license terms
- User must choose installation path

**Step 2 (running the installer) MUST be done manually.** The rest can be automated.
