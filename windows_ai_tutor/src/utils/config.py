"""
Configuration Manager - Application Settings

This manages application configuration and user preferences.
"""

import json
import os
from typing import Any, Dict, Optional
from pathlib import Path


class ConfigManager:
    """
    Manages application configuration and user preferences.
    """

    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize the configuration manager.

        Args:
            config_file: Path to configuration file (default: config/settings.json)
        """
        if config_file is None:
            # Default to config/settings.json in the project directory
            project_root = Path(__file__).parent.parent.parent
            config_file = project_root / "config" / "settings.json"

        self.config_file = Path(config_file)
        self.config: Dict[str, Any] = {}

        # Create config directory if it doesn't exist
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing configuration or create default
        self._load_config()

    def _load_config(self):
        """Load configuration from file or create default."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
                print(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                print(f"Error loading configuration: {e}")
                self.config = self._get_default_config()
        else:
            self.config = self._get_default_config()
            self._save_config()

    def _save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            print(f"Configuration saved to {self.config_file}")
        except Exception as e:
            print(f"Error saving configuration: {e}")

    def _get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration.

        Returns:
            Dict with default configuration values
        """
        return {
            # Hotkey settings
            "hotkey": "ctrl+alt",

            # AI Backend settings
            "backend": "llamacpp",  # 'ollama', 'llamacpp', or 'distributed'
            "model": "Qwen2.5-VL-7B-Instruct-Q4_K_M",
            "backup_model": "llava-llama3",
            "ollama_host": "http://localhost:11434",
            "llamacpp_host": "http://localhost:8081",
            "llamacpp_model_path": "D:\\new_automation\\models\\Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
            "llamacpp_mmproj_path": "D:\\new_automation\\models\\Qwen2.5-VL-7B-Instruct-vision.gguf",
            "llamacpp_binary_path": "C:\\Users\\dhruv\\AppData\\Local\\Microsoft\\WinGet\\Packages\\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe\\llama-server.exe",

            # Audio settings
            "audio_sample_rate": 16000,
            "audio_channels": 1,
            "audio_chunk_size": 1024,

            # Transcription settings
            "transcription_model": "base",  # tiny, base, small, medium, large
            "transcription_language": "en",

            # TTS settings
            "tts_engine": "pyttsx3",  # pyttsx3, edge-tts, coqui-tts
            "tts_voice": "default",
            "tts_rate": 150,

            # Screen capture settings
            "screen_capture_quality": "medium",  # low, medium, high
            "screen_capture_fps": 30,

            # UI settings
            "show_cursor": True,
            "panel_position": "bottom_right",  # top_left, top_right, bottom_left, bottom_right
            "theme": "dark",

            # Onboarding settings
            "has_completed_onboarding": False,

            # Performance settings
            "max_conversation_history": 10,
            "ai_temperature": 0.7,
            "ai_max_tokens": 1024,

            # Advanced settings
            "debug_mode": False,
            "log_level": "INFO"
        }

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """
        Set a configuration value.

        Args:
            key: Configuration key
            value: Value to set
        """
        self.config[key] = value
        self._save_config()

    def get_all(self) -> Dict[str, Any]:
        """
        Get all configuration values.

        Returns:
            Dictionary with all configuration values
        """
        return self.config.copy()

    def reset_to_defaults(self):
        """Reset configuration to default values."""
        self.config = self._get_default_config()
        self._save_config()
        print("Configuration reset to defaults")

    def update(self, updates: Dict[str, Any]):
        """
        Update multiple configuration values.

        Args:
            updates: Dictionary of key-value pairs to update
        """
        self.config.update(updates)
        self._save_config()

    def reload(self):
        """Reload configuration from file."""
        self._load_config()

    @property
    def config_path(self) -> Path:
        """Get the configuration file path."""
        return self.config_file