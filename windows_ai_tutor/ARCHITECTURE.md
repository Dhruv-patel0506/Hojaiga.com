# Windows AI Tutor - Architecture Documentation

## Overview

Windows AI Tutor is a system tray-based AI teaching companion that lives in the Windows system tray and provides voice-activated assistance with screen understanding capabilities. It uses local LLM (Ollama) for AI processing, local TTS for voice output, and screen capture for context awareness.

## Core Philosophy

- **Local-first**: All AI processing runs locally using Ollama, no API keys required
- **Privacy-focused**: No data leaves the user's machine
- **Cost-free**: No subscription or API costs
- **Educational focus**: Designed specifically for teaching and learning assistance
- **Screen-aware**: Can see and understand what's on the user's screen

## Architecture Pattern

Following the MVVM pattern adapted for Python/Windows:
- **Model**: Data structures, business logic, AI processing
- **View**: PyQt5/PySide6 UI components, system tray integration
- **ViewModel**: State management, coordination between components

## Technology Stack

### Core Framework
- **Python 3.10+**: Main application language
- **PyQt5/PySide6**: Windows UI framework (replaces SwiftUI/AppKit)
- **asyncio**: Asynchronous operations (replaces Swift async/await)

### Audio Processing
- **pyaudio**: Audio capture from microphone
- **sounddevice**: Alternative audio capture
- **pydub**: Audio processing and conversion
- **whisper**: Local speech recognition (OpenAI's Whisper model)

### Vision/Screens
- **Pillow (PIL)**: Image processing
- **mss**: High-performance screen capture
- **pywin32**: Windows-specific screen APIs
- **opencv-python**: Advanced image processing

### AI Processing
- **ollama**: Local LLM inference
- **langchain**: AI orchestration framework
- **transformers**: Local model utilities

### Text-to-Speech
- **pyttsx3**: Offline TTS
- **edge-tts**: Microsoft Edge TTS (online option)
- **coqui-tts**: Advanced local TTS

### System Integration
- **pywin32**: Windows API integration
- **keyboard**: Global hotkey detection
- **pynput**: Alternative hotkey/input monitoring
- **win32gui**: Window management

## Component Architecture

### 1. System Tray Manager (`src/core/tray_manager.py`)
**Purpose**: Windows system tray integration (equivalent to MenuBarPanelManager)

**Responsibilities**:
- Create and manage system tray icon
- Handle tray icon clicks and context menu
- Show/hide main control panel
- Manage application lifecycle

**Key Windows APIs**:
- `QSystemTrayIcon` (PyQt5)
- Windows notification area integration

### 2. Global Hotkey Manager (`src/core/hotkey_manager.py`)
**Purpose**: Detect global keyboard shortcuts (equivalent to GlobalPushToTalkShortcutMonitor)

**Responsibilities**:
- Register global hotkeys (Ctrl+Option for Windows)
- Detect hotkey press/release events
- Publish hotkey state changes
- Handle hotkey conflicts

**Key Windows APIs**:
- `keyboard` library or Windows hooks
- Low-level keyboard hook callbacks

### 3. Central State Manager (`src/core/state_manager.py`)
**Purpose**: Central state machine (equivalent to CompanionManager)

**Responsibilities**:
- Coordinate all application components
- Manage voice state (idle/listening/processing/responding)
- Handle conversation history
- Coordinate AI response pipeline
- Manage cursor overlay state
- Handle permission states

**State Management**:
- Voice state tracking
- Permission status
- User preferences
- Conversation context

### 4. Audio Capture Manager (`src/audio/audio_capture.py`)
**Purpose**: Capture microphone audio (equivalent to BuddyDictationManager)

**Responsibilities**:
- Capture audio from microphone
- Convert audio to required format
- Stream audio to transcription service
- Handle audio permissions
- Provide audio level feedback

**Audio Pipeline**:
```
Microphone → Audio Capture → Format Conversion → Transcription Service
```

### 5. Transcription Manager (`src/audio/transcription_manager.py`)
**Purpose**: Convert speech to text (equivalent to AssemblyAIStreamingTranscriptionProvider)

**Responsibilities**:
- Integrate with local Whisper model
- Stream transcription results
- Handle transcription errors
- Provide partial and final transcripts

**Local Models**:
- OpenAI Whisper (various sizes)
- Faster-Whisper (optimized version)

### 6. Screen Capture Utility (`src/vision/screen_capture.py`)
**Purpose**: Capture screen content (equivalent to CompanionScreenCaptureUtility)

**Responsibilities**:
- Capture individual screens
- Handle multi-monitor setups
- Exclude application windows from capture
- Convert captures to AI-compatible format
- Provide screen metadata

**Screen Pipeline**:
```
Screen Selection → Capture → Window Exclusion → Format Conversion → AI Processing
```

### 7. Cursor Overlay Manager (`src/ui/cursor_overlay.py`)
**Purpose**: Custom cursor overlay with animations (equivalent to OverlayWindow)

**Responsibilities**:
- Create transparent overlay window
- Render custom cursor/indicators
- Animate cursor to point at screen elements
- Handle multi-monitor cursor coordination
- Show status indicators (listening, processing, etc.)

**Animation Types**:
- Cursor following (spring animation)
- Pointing animation (bezier curves)
- Status indicators (waveform, spinner)

### 8. Local LLM Manager (`src/ai/llm_manager.py`)
**Purpose**: Integrate with local Ollama (equivalent to ClaudeAPI)

**Responsibilities**:
- Connect to local Ollama instance
- Send prompts with image context
- Stream AI responses
- Handle conversation history
- Manage model selection

**Ollama Integration**:
- Model selection (Llama3, Mistral, etc.)
- Vision capabilities
- Streaming responses
- Local inference

### 9. TTS Manager (`src/audio/tts_manager.py`)
**Purpose**: Convert text to speech (equivalent to ElevenLabsTTSClient)

**Responsibilities**:
- Convert AI responses to audio
- Play audio through system speakers
- Handle playback state
- Support multiple TTS engines

**TTS Options**:
- pyttsx3 (offline, basic)
- edge-tts (online, high quality)
- coqui-tts (offline, advanced)

### 10. Main Control Panel (`src/ui/control_panel.py`)
**Purpose**: Main UI panel (equivalent to CompanionPanelView)

**Responsibilities**:
- Display application status
- Show permission states
- Provide settings interface
- Handle user interactions
- Display conversation history

### 11. Design System (`src/ui/design_system.py`)
**Purpose**: Centralized styling (equivalent to DesignSystem.swift)

**Responsibilities**:
- Define color palette
- Provide component styles
- Ensure visual consistency
- Handle theming

### 12. Permission Manager (`src/core/permission_manager.py`)
**Purpose**: Handle Windows permissions (equivalent to WindowPositionManager)

**Responsibilities**:
- Check microphone permissions
- Check screen recording permissions
- Request missing permissions
- Guide users to Windows settings

## Data Flow

### Voice Interaction Pipeline
```
User presses hotkey
→ HotkeyManager detects press
→ StateManager transitions to listening
→ AudioCapture starts recording
→ TranscriptionManager processes audio
→ ScreenCapture captures screen
→ LLMManager processes transcript + screen
→ TTSManager converts response to audio
→ CursorOverlay shows response
→ StateManager transitions to idle
```

### Pointing Pipeline
```
LLM identifies screen element
→ Returns coordinates in [POINT:x,y:label] format
→ StateManager parses coordinates
→ CursorOverlay animates to location
→ Shows speech bubble with element label
→ Returns to cursor following mode
```

## Project Structure

```
windows_ai_tutor/
├── src/
│   ├── core/                  # Core application logic
│   │   ├── __init__.py
│   │   ├── app.py            # Main application entry
│   │   ├── state_manager.py  # Central state machine
│   │   ├── tray_manager.py   # System tray integration
│   │   ├── hotkey_manager.py # Global hotkey detection
│   │   └── permission_manager.py # Permission handling
│   ├── ui/                    # User interface components
│   │   ├── __init__.py
│   │   ├── control_panel.py  # Main control panel
│   │   ├── cursor_overlay.py # Cursor overlay window
│   │   └── design_system.py # Design tokens and styles
│   ├── audio/                 # Audio processing
│   │   ├── __init__.py
│   │   ├── audio_capture.py  # Microphone capture
│   │   ├── transcription_manager.py # Speech-to-text
│   │   └── tts_manager.py    # Text-to-speech
│   ├── vision/                # Screen capture and vision
│   │   ├── __init__.py
│   │   ├── screen_capture.py # Screen capture utility
│   │   └── image_processor.py # Image processing
│   ├── ai/                    # AI integration
│   │   ├── __init__.py
│   │   ├── llm_manager.py    # Local LLM integration
│   │   └── prompt_engine.py # Prompt engineering
│   └── utils/                 # Utilities
│       ├── __init__.py
│       ├── config.py         # Configuration management
│       └── logger.py         # Logging setup
├── config/                    # Configuration files
│   ├── settings.json         # User settings
│   └── models.json           # Model configurations
├── tests/                     # Unit tests
├── docs/                      # Documentation
├── requirements.txt           # Python dependencies
├── setup.py                  # Installation script
└── README.md                 # Project documentation
```

## Key Differences from Clicky

### Platform-Specific Adaptations

1. **System Integration**
   - macOS: Menu bar + NSStatusItem
   - Windows: System tray + QSystemTrayIcon

2. **Screen Capture**
   - macOS: ScreenCaptureKit
   - Windows: mss library + pywin32

3. **Audio Capture**
   - macOS: AVAudioEngine
   - Windows: pyaudio + sounddevice

4. **Global Hotkeys**
   - macOS: CGEvent tap
   - Windows: keyboard library + Windows hooks

5. **Window Management**
   - macOS: NSPanel + SwiftUI
   - Windows: PyQt5/PySide6 + transparent windows

6. **AI Processing**
   - Clicky: Claude API (cloud)
   - Windows Tutor: Ollama (local)

7. **TTS**
   - Clicky: ElevenLabs (cloud)
   - Windows Tutor: pyttsx3/edge-tts (local/online)

8. **Transcription**
   - Clicky: AssemblyAI (cloud)
   - Windows Tutor: Whisper (local)

## Configuration Management

### Settings Structure
```json
{
  "hotkey": "ctrl+alt",
  "model": "llama3",
  "tts_engine": "pyttsx3",
  "transcription_model": "base",
  "show_cursor": true,
  "auto_start": false
}
```

### Environment Variables
- `OLLAMA_HOST`: Ollama server URL
- `WHISPER_MODEL_SIZE`: Whisper model size
- `TTS_VOICE`: TTS voice selection

## Performance Considerations

### Optimization Strategies
1. **Lazy Loading**: Load AI models only when needed
2. **Caching**: Cache screen captures and responses
3. **Async Operations**: Use asyncio for non-blocking operations
4. **Resource Management**: Proper cleanup of audio/video resources
5. **Model Selection**: Allow users to choose model based on hardware

### Memory Management
- Clean up audio buffers after transcription
- Release screen captures after processing
- Manage AI model memory footprint
- Handle large conversation histories

## Security Considerations

### Local-First Security
- No API keys stored in application
- All processing happens locally
- No network communication (except optional TTS)
- User data never leaves the machine

### Permission Handling
- Request minimum required permissions
- Clear permission status indicators
- Graceful degradation when permissions denied
- User guidance for permission granting

## Extension Points

### Pluggable Components
1. **Transcription Providers**: Swap Whisper for other STT
2. **TTS Engines**: Multiple TTS backends
3. **LLM Models**: Different Ollama models
4. **Screen Capture**: Alternative capture methods
5. **UI Themes**: Custom design system extensions

## Future Enhancements

### Planned Features
1. **Multi-language Support**: Internationalization
2. **Advanced Pointing**: OCR-based element detection
3. **Conversation Memory**: Long-term conversation storage
4. **Custom Prompts**: User-defined prompt templates
5. **Analytics**: Usage tracking (local only)
6. **Plugin System**: Third-party extensions

## Development Guidelines

### Code Style
- Follow PEP 8 for Python code
- Use type hints for better IDE support
- Document complex logic with docstrings
- Write unit tests for critical components

### Testing Strategy
- Unit tests for individual components
- Integration tests for data flow
- Manual testing for UI components
- Performance testing for AI operations

### Debugging
- Comprehensive logging system
- Debug mode for detailed output
- Performance profiling tools
- Error reporting and handling

## Deployment

### Distribution Options
1. **PyInstaller**: Single executable distribution
2. **Python Wheel**: Standard Python package
3. **Source Distribution**: For developers

### Installation
```bash
pip install -r requirements.txt
python setup.py install
```

### Running
```bash
python src/core/app.py
```

## License and Credits

This project is inspired by the Clicky macOS application by Farza, but is a complete reimplementation for Windows using different technologies and a local-first approach.