# Windows AI Tutor

A Windows-based AI teaching companion that lives in the system tray and provides voice-activated assistance with screen understanding capabilities. Built with Python and local AI models for privacy and cost-free operation.

## Features

- **System Tray Integration**: Lives in Windows system tray for easy access
- **Voice Interaction**: Push-to-talk voice input using Ctrl+Alt
- **Screen Understanding**: Can see and understand what's on your screen
- **Local AI Processing**: Uses Ollama for local LLM inference (no API keys needed)
- **Privacy-First**: All processing happens locally on your machine
- **Cost-Free**: No subscription fees or API costs
- **Multi-Monitor Support**: Works seamlessly across multiple monitors
- **Custom Cursor Overlay**: Animated cursor that can point at screen elements
- **Educational Focus**: Designed specifically for teaching and learning assistance

## Architecture

This project is inspired by the Clicky macOS application but is a complete reimplementation for Windows using different technologies and a local-first approach.

### Technology Stack

- **Python 3.10+**: Main application language
- **PyQt5**: Windows UI framework
- **Ollama**: Local LLM inference
- **Whisper**: Local speech recognition
- **pyttsx3**: Offline text-to-speech
- **mss**: High-performance screen capture

### Key Components

- **System Tray Manager**: Windows system tray integration
- **State Manager**: Central state machine coordinating all components
- **Hotkey Manager**: Global keyboard shortcut detection
- **Audio Capture**: Microphone audio recording
- **Transcription Manager**: Speech-to-text using Whisper
- **Screen Capture**: Multi-monitor screen capture
- **LLM Manager**: Local Ollama integration
- **TTS Manager**: Text-to-speech conversion
- **Cursor Overlay**: Custom animated cursor overlay
- **Control Panel**: Main UI panel

## Installation

### Prerequisites

1. **Python 3.10+**: Download from [python.org](https://www.python.org/)
2. **Ollama**: Download from [ollama.ai](https://ollama.ai/)
3. **Git**: For cloning the repository

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd windows_ai_tutor
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Install Ollama and pull a model:
```bash
# After installing Ollama
ollama pull llama3
```

4. Run the application:
```bash
python src/core/app.py
```

## Configuration

The application uses a configuration file at `config/settings.json`. Default settings are automatically created on first run.

### Key Settings

- `hotkey`: Global hotkey combination (default: "ctrl+alt")
- `model`: Ollama model to use (default: "llama3")
- `ollama_host`: Ollama server URL (default: "http://localhost:11434")
- `transcription_model`: Whisper model size (default: "base")
- `tts_engine`: TTS engine to use (default: "pyttsx3")
- `show_cursor`: Enable cursor overlay (default: true)

## Usage

1. **Start the Application**: Run `python src/core/app.py`
2. **Grant Permissions**: The app will request microphone, accessibility, and screen recording permissions
3. **Use Voice Interaction**: Press Ctrl+Alt to start talking, release to send
4. **View Responses**: The AI will respond via text and speech
5. **Screen Pointing**: The AI can point at screen elements when helpful

## Permissions

The application requires the following Windows permissions:

- **Microphone**: For voice input
- **Accessibility**: For global hotkey detection
- **Screen Recording**: For screen capture

These permissions are requested through the Windows settings when first used.

## Project Structure

```
windows_ai_tutor/
├── src/
│   ├── core/              # Core application logic
│   ├── ui/                # User interface components
│   ├── audio/             # Audio processing
│   ├── vision/            # Screen capture and vision
│   ├── ai/                # AI integration
│   └── utils/             # Utilities
├── config/                # Configuration files
├── tests/                 # Unit tests
├── docs/                  # Documentation
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
black src/
mypy src/
```

### Building Executable

```bash
pyinstaller --onefile --windowed src/core/app.py
```

## Troubleshooting

### Ollama Connection Issues

1. Ensure Ollama is running: `ollama serve`
2. Check the Ollama host URL in settings
3. Verify the model is installed: `ollama list`

### Audio Issues

1. Check microphone permissions in Windows settings
2. Ensure no other application is using the microphone
3. Try different audio sample rates in configuration

### Screen Capture Issues

1. Grant screen recording permissions in Windows settings
2. Check if the application is excluded from screen capture
3. Try different screen capture quality settings

## Credits

This project is inspired by the Clicky macOS application by Farza, but is a complete reimplementation for Windows using different technologies and a local-first approach.

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please read the contributing guidelines before submitting pull requests.

## Support

For issues and questions, please open an issue on the GitHub repository.