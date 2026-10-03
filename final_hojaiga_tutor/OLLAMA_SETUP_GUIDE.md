# Ollama + LLaVA Setup Guide for Clicky Vision Platform

## **📋 COMPLETE SETUP INSTRUCTIONS**

### **Step 1: Install Ollama to D Drive**

Run the automated setup script:

```batch
setup_ollama_d_drive.bat
```

**What this does:**
- Downloads Ollama installer
- Installs Ollama to `D:\Ollama`
- Sets environment variables
- Downloads LLaVA vision model automatically

**OR Manual Setup:**

1. Download Ollama from: https://ollama.ai/download
2. Run installer and install to: `D:\Ollama`
3. Open Command Prompt and run:
   ```batch
   setx OLLAMA_HOME "D:\Ollama"
   setx PATH "%PATH%;D:\Ollama"
   ```

---

### **Step 2: Pull LLaVA Vision Model**

**Option A: Automated (included in setup script)**
- The setup script automatically pulls LLaVA

**Option B: Manual**
Run the pull script:
```batch
pull_llava.bat
```

**OR Command Line:**
```batch
cd D:\Ollama
ollama pull llava
```

**What this does:**
- Downloads LLaVA vision model (~4GB)
- Installs it to your D drive
- Makes it available for Clicky

---

### **Step 3: Start Ollama Server**

**Option A: Use the start script**
```batch
start_ollama.bat
```

**Option B: Command Line**
```batch
cd D:\Ollama
ollama serve
```

**What this does:**
- Starts Ollama server on `http://localhost:11434`
- Keeps it running in the background
- Makes it available for Clicky to use

---

### **Step 4: Verify Installation**

Open Command Prompt and run:
```batch
cd D:\Ollama
ollama list
```

You should see:
```
NAME            ID              SIZE    MODIFIED
llava:latest    a879b9efbb09    4.7 GB  2 hours ago
```

Test the server:
```batch
ollama run llava "Describe this image"
```

---

### **Step 5: Start Clicky**

```batch
cd D:\new_automation\final_hojaiga_tutor
npm start
```

---

## **🎯 INTEGRATION WITH CLICKY**

### **Automatic Integration**

The vision platform is now **automatically integrated** with:
- ✅ Ollama installed to `D:\Ollama`
- ✅ LLaVA model automatically detected
- ✅ Server auto-start when needed
- ✅ Model auto-download if missing

### **What Happens When You Use Vision Teaching:**

1. You click "Teach Me Everything" in Clicky
2. Clicky checks if Ollama is running
3. If not running, Clicky starts it automatically from `D:\Ollama`
4. Clicky checks if LLaVA model is downloaded
5. If not downloaded, Clicky downloads it automatically
6. Clicky starts teaching the app

### **No Manual Configuration Needed**

The code automatically:
- Uses `D:\Ollama` as the installation directory
- Starts Ollama server when needed
- Downloads LLaVA model if missing
- Checks server availability before teaching
- Handles all errors gracefully

---

## **📁 FILE STRUCTURE**

After setup, your D drive will have:

```
D:\
└── Ollama\
    ├── ollama.exe (Ollama server)
    ├── models\
    │   └── llava (LLaVA vision model)
    └── ollama_user (User data)
```

---

## **🔧 TROUBLESHOOTING**

### **Issue: Ollama server won't start**

**Solution:**
```batch
# Check if port 11434 is in use
netstat -ano | findstr :11434

# Kill any process using the port
taskkill /PID <PID> /F

# Start Ollama manually
cd D:\Ollama
ollama serve
```

### **Issue: LLaVA model download fails**

**Solution:**
```batch
# Try again with verbose output
cd D:\Ollama
ollama pull llava --verbose

# Or use a different mirror
set OLLAMA_HOST=https://registry.ollama.ai
ollama pull llava
```

### **Issue: Clicky can't find Ollama**

**Solution:**
1. Verify Ollama is in `D:\Ollama`
2. Check environment variable:
   ```batch
   echo %OLLAMA_HOME%
   ```
3. Should output: `D:\Ollama`
4. If not, set it manually:
   ```batch
   setx OLLAMA_HOME "D:\Ollama"
   ```

### **Issue: Vision teaching doesn't work**

**Solution:**
1. Ensure Ollama server is running:
   ```batch
   curl http://localhost:11434/api/tags
   ```
2. Check Clicky console for errors
3. Verify LLaVA model is downloaded:
   ```batch
   ollama list
   ```

---

## **🚀 QUICK START COMMANDS**

### **One-Time Setup:**
```batch
# 1. Install Ollama to D drive
setup_ollama_d_drive.bat

# 2. Pull LLaVA model (if not done automatically)
pull_llava.bat
```

### **Every Time You Use Clicky:**
```batch
# 1. Start Ollama server
start_ollama.bat

# 2. Start Clicky
cd D:\new_automation\final_hojaiga_tutor
npm start
```

---

## **💾 STORAGE REQUIREMENTS**

- **Ollama installation:** ~200 MB
- **LLaVA model:** ~4.7 GB
- **Total on D drive:** ~5 GB

---

## **🔄 UPDATING OLLAMA**

To update Ollama to the latest version:
```batch
cd D:\Ollama
ollama --version
# If update available:
ollama update
```

To update LLaVA model:
```batch
cd D:\Ollama
ollama pull llava
```

---

## **📊 MONITORING**

### **Check Ollama Server Status:**
```batch
curl http://localhost:11434/api/tags
```

### **Check Available Models:**
```batch
ollama list
```

### **Check Server Logs:**
Ollama logs are displayed in the command window when you run `ollama serve`

---

## **🎯 SUMMARY**

### **Files Created:**
1. `setup_ollama_d_drive.bat` - Automated installation to D drive
2. `pull_llava.bat` - Pull LLaVA model
3. `start_ollama.bat` - Start Ollama server

### **Integration Points:**
1. `OllamaVision.ts` - Auto-starts server, auto-downloads model
2. `DynamicAppTeacher.ts` - Initializes Ollama before teaching
3. `CompanionManager.ts` - Configured to use `D:\Ollama`
4. `index.ts` - Factory functions use D drive by default

### **What You Need to Do:**
1. Run `setup_ollama_d_drive.bat` (one-time)
2. Run `start_ollama.bat` before using Clicky
3. Clicky handles everything else automatically

---

## **✅ VERIFICATION CHECKLIST**

- [ ] Ollama installed to `D:\Ollama`
- [ ] LLaVA model downloaded
- [ ] Ollama server running (`ollama serve`)
- [ ] Can see `llava` in `ollama list`
- [ ] Clicky builds successfully (`npm run build`)
- [ ] Clicky starts successfully (`npm start`)
- [ ] Vision teaching works (test with any app)

---

## **🆘 SUPPORT**

If you encounter issues:
1. Check the troubleshooting section above
2. Check Ollama logs in the command window
3. Check Clicky console for errors
4. Verify D drive has at least 10 GB free space
5. Ensure you have admin permissions for installation

---

**Setup is complete! Clicky Vision Platform is now integrated with Ollama on your D drive.**
