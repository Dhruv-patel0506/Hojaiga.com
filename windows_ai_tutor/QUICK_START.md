# Quick Start Guide - Windows AI Tutor

## Prerequisites Installation

### 1. Install Python 3.10+
Download from https://www.python.org/ and install with "Add to PATH" option.

### 2. Install Ollama
Download from https://ollama.ai/ and install.

### 3. Pull AI Model
Open terminal and run:
```bash
ollama pull llama3
```

### 4. Start Ollama Server
```bash
ollama serve
```

## Application Setup

### 1. Install Dependencies
```bash
cd D:\new_automation\windows_ai_tutor
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python src/core/app.py
```

## First Run Setup

1. **System Tray Icon**: Look for the blue triangle icon in your system tray
2. **Grant Permissions**: Click the icon and grant required permissions:
   - Microphone access
   - Accessibility (for global hotkeys)
   - Screen recording
3. **Configure Settings**: Use the control panel to adjust:
   - AI model selection
   - Hotkey combination
   - Cursor overlay visibility

## Basic Usage

### Voice Interaction
1. Press **Ctrl+Alt** to start talking
2. Speak your question or request
3. Release **Ctrl+Alt** to send
4. AI will respond via text and speech

### Screen Understanding
The AI can see your screen and provide context-aware assistance:
- "What's this button do?"
- "Help me understand this code"
- "How do I navigate this interface?"

### Cursor Pointing
When the AI identifies something relevant on your screen, it can:
- Point at specific elements
- Display speech bubbles with labels
- Animate along bezier curves to targets

## Configuration

Edit `config/settings.json` to customize:

```json
{
  "hotkey": "ctrl+alt",           // Change hotkey
  "model": "llama3",              // AI model
  "transcription_model": "base", // Whisper model size
  "tts_engine": "pyttsx3",       // Text-to-speech engine
  "show_cursor": true             // Show cursor overlay
}
```

## Troubleshooting

### Ollama Connection
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
ollama serve
```

### Audio Issues
- Check Windows microphone settings
- Ensure no other apps are using the mic
- Try different sample rates in config

### Screen Capture
- Grant screen recording permissions in Windows Settings
- Check app is not excluded from capture
- Try lower quality settings

## Next Steps

1. **Customize Prompts**: Edit system prompts in `state_manager.py`
2. **Add More Models**: Pull additional Ollama models
3. **Custom UI**: Modify design system in `design_system.py`
4. **Extend Features**: Add new components following the architecture

## Architecture Reference

See `ARCHITECTURE.md` for detailed architecture documentation.

## Key Files

- `src/core/app.py` - Main entry point
- `src/core/state_manager.py` - Central state machine
- `src/ui/control_panel.py` - Main UI panel
- `src/ai/llm_manager.py` - Ollama integration
- `src/audio/transcription_manager.py` - Whisper integration

## Support

For issues or questions, check the architecture documentation or modify the code to suit your needs.