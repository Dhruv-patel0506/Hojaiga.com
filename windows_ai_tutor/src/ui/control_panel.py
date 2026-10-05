"""
Control Panel - Main UI Panel

This is the main control panel UI shown from the system tray.
Equivalent to CompanionPanelView.swift in Clicky.
"""

from typing import Optional, TYPE_CHECKING
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QTextEdit, QComboBox, QCheckBox, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QFont, QColor

if TYPE_CHECKING:
    from ..core.state_manager import StateManager, VoiceState

from ..ui.design_system import DesignSystem
from ..utils.logger import setup_logger


class ControlPanel(QWidget):
    """
    Main control panel for the Windows AI Tutor.
    Shown when clicking the system tray icon.
    """

    # Signals
    close_requested = pyqtSignal()

    def __init__(self, state_manager: 'StateManager'):
        """
        Initialize the control panel.

        Args:
            state_manager: State manager instance
        """
        super().__init__()

        self.logger = setup_logger("ControlPanel")
        self.state_manager = state_manager
        self.design_system = DesignSystem()

        # Window properties
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(500, 600)

        # Build UI
        self._build_ui()

        # Connect signals (but block them during init)
        self._connect_signals()

        self.logger.info("Control panel initialized")

    def _build_ui(self):
        """Build the control panel UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create background container
        background = QWidget()
        background.setStyleSheet(f"""
            QWidget {{
                background-color: {self.design_system.colors.background};
                border-radius: 12px;
                border: 1px solid {self.design_system.colors.border_subtle};
            }}
        """)

        bg_layout = QVBoxLayout(background)
        bg_layout.setContentsMargins(16, 16, 16, 16)
        bg_layout.setSpacing(12)

        # Header
        header = self._create_header()
        bg_layout.addWidget(header)

        # Separator
        separator = self._create_separator()
        bg_layout.addWidget(separator)

        # Status section
        status_section = self._create_status_section()
        bg_layout.addWidget(status_section)

        # Permissions section
        permissions_section = self._create_permissions_section()
        bg_layout.addWidget(permissions_section)

        # Settings section
        settings_section = self._create_settings_section()
        bg_layout.addWidget(settings_section)

        # Footer
        footer = self._create_footer()
        bg_layout.addWidget(footer)

        layout.addWidget(background)

    def _create_header(self) -> QWidget:
        """Create the header section."""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title = QLabel("Windows AI Tutor")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet(f"color: {self.design_system.colors.text_primary};")
        layout.addWidget(title)

        layout.addStretch()

        # Status indicator
        self.status_indicator = QLabel()
        self.status_indicator.setFixedSize(12, 12)
        from ..core.state_manager import VoiceState
        self._update_status_indicator(VoiceState.IDLE)
        layout.addWidget(self.status_indicator)

        # Status text
        self.status_text = QLabel("Ready")
        self.status_text.setFont(QFont("Arial", 10))
        self.status_text.setStyleSheet(f"color: {self.design_system.colors.text_secondary};")
        layout.addWidget(self.status_text)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setFont(QFont("Arial", 12, QFont.Bold))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {self.design_system.colors.text_secondary};
                border: none;
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {self.design_system.colors.surface3};
            }}
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        return header

    def _create_separator(self) -> QFrame:
        """Create a separator line."""
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet(f"background-color: {self.design_system.colors.border_subtle};")
        separator.setFixedHeight(1)
        return separator

    def _create_status_section(self) -> QWidget:
        """Create the status section."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Instructions
        instructions = QLabel("Type below to chat with AI:")
        instructions.setFont(QFont("Arial", 11))
        instructions.setStyleSheet(f"color: {self.design_system.colors.text_secondary};")
        layout.addWidget(instructions)

        # Text input field
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type your message here...")
        self.text_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.design_system.colors.surface2};
                color: {self.design_system.colors.text_primary};
                border: 1px solid {self.design_system.colors.border_subtle};
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
            }}
        """)
        self.text_input.returnPressed.connect(self._on_send_message)
        layout.addWidget(self.text_input)

        # Send button
        send_btn = QPushButton("Send")
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.design_system.colors.accent};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.design_system.colors.accent_hover};
            }}
        """)
        send_btn.clicked.connect(self._on_send_message)
        layout.addWidget(send_btn)

        # Response display
        self.response_display = QTextEdit()
        self.response_display.setReadOnly(True)
        self.response_display.setPlaceholderText("AI responses will appear here...")
        self.response_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: {self.design_system.colors.surface2};
                color: {self.design_system.colors.text_primary};
                border: 1px solid {self.design_system.colors.border_subtle};
                border-radius: 6px;
                padding: 8px;
                font-size: 11px;
            }}
        """)
        self.response_display.setMaximumHeight(100)
        layout.addWidget(self.response_display)

        # Voice state display
        self.voice_state_label = QLabel("Status: Idle")
        self.voice_state_label.setFont(QFont("Arial", 10))
        self.voice_state_label.setStyleSheet(f"color: {self.design_system.colors.text_tertiary};")
        layout.addWidget(self.voice_state_label)

        return section

    def _create_permissions_section(self) -> QWidget:
        """Create the permissions section."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Section title
        title = QLabel("PERMISSIONS")
        title.setFont(QFont("Arial", 9, QFont.Bold))
        title.setStyleSheet(f"color: {self.design_system.colors.text_tertiary};")
        layout.addWidget(title)

        # Permission rows
        self.mic_permission = self._create_permission_row("Microphone", "mic")
        layout.addWidget(self.mic_permission)

        self.accessibility_permission = self._create_permission_row("Accessibility", "hand")
        layout.addWidget(self.accessibility_permission)

        self.screen_permission = self._create_permission_row("Screen Recording", "display")
        layout.addWidget(self.screen_permission)

        return section

    def _create_permission_row(self, label: str, icon_name: str) -> QWidget:
        """Create a permission row."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Icon placeholder (using text for now)
        icon = QLabel("●")
        icon.setFont(QFont("Arial", 12))
        icon.setStyleSheet(f"color: {self.design_system.colors.text_tertiary};")
        layout.addWidget(icon)

        # Label
        name = QLabel(label)
        name.setFont(QFont("Arial", 11))
        name.setStyleSheet(f"color: {self.design_system.colors.text_secondary};")
        layout.addWidget(name)

        layout.addStretch()

        # Status
        status = QLabel("Check")
        status.setFont(QFont("Arial", 9))
        status.setStyleSheet(f"color: {self.design_system.colors.text_tertiary};")
        layout.addWidget(status)

        return row

    def _create_settings_section(self) -> QWidget:
        """Create the settings section."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Section title
        title = QLabel("SETTINGS")
        title.setFont(QFont("Arial", 9, QFont.Bold))
        title.setStyleSheet(f"color: {self.design_system.colors.text_tertiary};")
        layout.addWidget(title)

        # Backend selection
        backend_label = QLabel("AI Backend:")
        backend_label.setFont(QFont("Arial", 10))
        backend_label.setStyleSheet(f"color: {self.design_system.colors.text_secondary};")
        layout.addWidget(backend_label)

        self.backend_combo = QComboBox()
        self.backend_combo.addItems(["ollama", "llamacpp", "distributed"])
        # Set current backend from config
        current_backend = self.state_manager.config.get("backend", "llamacpp")
        index = self.backend_combo.findText(current_backend)
        if index >= 0:
            self.backend_combo.setCurrentIndex(index)
        self.backend_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {self.design_system.colors.surface2};
                color: {self.design_system.colors.text_primary};
                border: 1px solid {self.design_system.colors.border_subtle};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        # Block signals during initialization to prevent backend change
        self.backend_combo.blockSignals(True)
        layout.addWidget(self.backend_combo)
        self.backend_combo.blockSignals(False)

        # Model selection
        model_label = QLabel("AI Model:")
        model_label.setFont(QFont("Arial", 10))
        model_label.setStyleSheet(f"color: {self.design_system.colors.text_secondary};")
        layout.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems(["Qwen2.5-VL-7B-Instruct", "llava-llama3", "llama3-vision", "mistral", "gemma"])
        # Set current model from config
        current_model = self.state_manager.config.get("model", "Qwen2.5-VL-7B-Instruct")
        # Try to match by partial name
        for i in range(self.model_combo.count()):
            if current_model in self.model_combo.itemText(i):
                self.model_combo.setCurrentIndex(i)
                break
        self.model_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {self.design_system.colors.surface2};
                color: {self.design_system.colors.text_primary};
                border: 1px solid {self.design_system.colors.border_subtle};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        # Block signals during initialization to prevent model change
        self.model_combo.blockSignals(True)
        layout.addWidget(self.model_combo)
        self.model_combo.blockSignals(False)

        # Cursor toggle
        self.cursor_toggle = QCheckBox("Show Cursor Overlay")
        self.cursor_toggle.setChecked(True)
        self.cursor_toggle.setStyleSheet(f"""
            QCheckBox {{
                color: {self.design_system.colors.text_secondary};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid {self.design_system.colors.border_subtle};
                background-color: {self.design_system.colors.surface2};
            }}
            QCheckBox::indicator:checked {{
                background-color: {self.design_system.colors.accent};
                border-color: {self.design_system.colors.accent};
            }}
        """)
        layout.addWidget(self.cursor_toggle)

        return section

    def _create_footer(self) -> QWidget:
        """Create the footer section."""
        footer = QWidget()
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Version info
        version = QLabel("v1.0.0")
        version.setFont(QFont("Arial", 9))
        version.setStyleSheet(f"color: {self.design_system.colors.text_tertiary};")
        layout.addWidget(version)

        layout.addStretch()

        # Quit button
        quit_btn = QPushButton("Quit")
        quit_btn.setFont(QFont("Arial", 10))
        quit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.design_system.colors.surface2};
                color: {self.design_system.colors.text_secondary};
                border: 1px solid {self.design_system.colors.border_subtle};
                border-radius: 6px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {self.design_system.colors.surface3};
            }}
        """)
        quit_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(quit_btn)

        return footer

    def _connect_signals(self):
        """Connect signals from state manager."""
        self.state_manager.state_changed.connect(self._on_state_changed)
        self.state_manager.permission_changed.connect(self._on_permission_changed)

        self.cursor_toggle.stateChanged.connect(self._on_cursor_toggle_changed)
        # Don't connect combo box signals during initialization to prevent unwanted changes
        # self.backend_combo.currentTextChanged.connect(self._on_backend_changed)
        # self.model_combo.currentTextChanged.connect(self._on_model_changed)

    def _update_status_indicator(self, state: 'VoiceState'):
        """Update the status indicator color."""
        from ..core.state_manager import VoiceState

        color_map = {
            VoiceState.IDLE: self.design_system.colors.success,
            VoiceState.LISTENING: self.design_system.colors.accent,
            VoiceState.PROCESSING: self.design_system.colors.warning,
            VoiceState.RESPONDING: self.design_system.colors.info
        }

        color = color_map.get(state, self.design_system.colors.text_tertiary)
        self.status_indicator.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 6px;
            }}
        """)

    def _on_state_changed(self, state: str):
        """Handle state changes."""
        from ..core.state_manager import VoiceState
        voice_state = VoiceState(state)
        self.voice_state_label.setText(f"Status: {state.title()}")
        self._update_status_indicator(voice_state)

    def _on_permission_changed(self, perm_type: str, granted: bool):
        """Handle permission changes."""
        status_text = "Granted" if granted else "Denied"
        color = self.design_system.colors.success if granted else self.design_system.colors.warning

        # Update the appropriate permission row
        if perm_type == "microphone":
            # Update mic permission status
            pass
        elif perm_type == "accessibility":
            # Update accessibility permission status
            pass
        elif perm_type == "screen_recording":
            # Update screen recording permission status
            pass

    def _on_cursor_toggle_changed(self, state: bool):
        """Handle cursor toggle changes."""
        self.state_manager.set_cursor_enabled(state)

    def _on_model_changed(self, model: str):
        """Handle model selection changes."""
        self.state_manager.llm_manager.set_model(model)

    def _on_backend_changed(self, backend: str):
        """Handle backend selection changes."""
        self.state_manager.llm_manager.set_backend(backend)

    def _on_send_message(self):
        """Handle send message button press."""
        message = self.text_input.text().strip()
        self.logger.info(f"Send button pressed. Message: '{message}'")
        if message:
            self.text_input.clear()
            self.voice_state_label.setText("Status: Processing...")
            self.response_display.append(f"You: {message}")

            # Send to LLM
            try:
                self.logger.info("Sending to LLM...")
                response = self.state_manager.llm_manager.generate_simple_response(message)
                self.logger.info(f"Got response: {response[:100]}...")
                self.response_display.append(f"AI: {response}")
                self.voice_state_label.setText("Status: Idle")
            except Exception as e:
                self.logger.error(f"Failed to get AI response: {e}")
                self.response_display.append(f"Error: {str(e)}")
                self.voice_state_label.setText("Status: Error")
        else:
            self.logger.warning("Empty message, not sending")