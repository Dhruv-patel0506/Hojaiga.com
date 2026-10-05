@echo off
echo ========================================
echo Universal App Teacher - Quick Start
echo ========================================
echo.
echo This is a PRODUCTION-GRADE app teacher with:
echo - Actual OS-level interaction (mouse, keyboard)
echo - UI tree extraction for precise coordinates
echo - Vision LLM (Ollama LLaVA) for understanding
echo - Stateful loop: LISTEN -> OBSERVE -> THINK -> TEACH -> ACT -> VERIFY
echo.
echo ========================================
echo REQUIREMENTS
echo ========================================
echo.
echo 1. Python 3.x with packages:
echo    pip install pyautogui pillow opencv-python
echo.
echo 2. Node.js with packages:
echo    npm install axios
echo.
echo 3. Ollama running:
echo    ollama serve
echo    ollama pull llava
echo.
echo ========================================
echo QUICK START
echo ========================================
echo.
echo 1. Install Python dependencies:
echo    pip install pyautogui pillow opencv-python
echo.
echo 2. Install Node dependencies:
echo    npm install axios
echo.
echo 3. Start Ollama:
echo    ollama serve
echo.
echo 4. Run the teacher:
echo    npx ts-node live_teacher.ts
echo.
echo 5. Type your goal when prompted:
echo    "How do I create a document in Word?"
echo    "How do I format cells in Excel?"
echo    "How do I apply gaussian blur in Photoshop?"
echo.
echo ========================================
echo STOPPING
echo ========================================
echo.
echo Press Ctrl+C to stop teaching at any time
echo.
echo ========================================
pause
