"""
Companion Panel View - Clicky-style Floating Panel

Custom floating panel with companion voice controls.
Converted from CompanionPanelView.swift to Windows Python.
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, pyqtProperty
from PyQt5.QtGui import QFont, QColor

from ..core.companion_manager import CompanionManager
from ..ui.design_system import DesignSystem
from ..utils.logger import setup_logger


class CompanionPanelView(QWidget):
    """
    Companion panel view for the floating control panel.
    Clicky-style dark theme with push-to-talk instructions.
    """

    def __init__(self, companion_manager: CompanionManager):
        """
        Initialize the companion panel view.

        Args:
            companion_manager: Companion manager instance
        """
        super().__init__()

        self.logger = setup_logger("CompanionPanelView")
        self.companion_manager = companion_manager

        # Apply Clicky styling
        self._apply_clicky_styling()

        # Build UI
        self._build_ui()

        self.logger.info("Companion panel view initialized")

    def _apply_clicky_styling(self):
        """Apply Clicky's dark theme styling."""
        DesignSystem.apply_dark_theme(self)

    def _build_ui(self):
        """Build the companion panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header with status
        header = self._create_header()
        layout.addWidget(header)

        # Voice state display
        voice_section = self._create_voice_section()
        layout.addWidget(voice_section)

        # Instructions
        instructions = self._create_instructions()
        layout.addWidget(instructions)

        # Permissions section
        permissions = self._create_permissions_section()
        layout.addWidget(permissions)

        # Quit button
        quit_btn = QPushButton("Quit")
        quit_btn.setStyleSheet(DesignSystem.get_button_style())
        quit_btn.clicked.connect(self._on_quit)
        layout.addWidget(quit_btn)

        layout.addStretch()

    def _create_header(self) -> QWidget:
        """Create the header section."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title = QLabel("Clicky")
        title.setFont(DesignSystem.Typography.heading2())
        title.setStyleSheet(f"color: {DesignSystem.Colors.TEXT_PRIMARY.name()};")
        layout.addWidget(title)

        layout.addStretch()

        # Status indicator
        status_label = QLabel("●")
        status_label.setStyleSheet(f"color: {DesignSystem.Colors.ACCENT.name()}; font-size: 12px;")
        layout.addWidget(status_label)

        return widget

    def _create_voice_section(self) -> QWidget:
        """Create the voice state section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # State label
        state_label = QLabel("Status: Idle")
        state_label.setFont(DesignSystem.Typography.body())
        state_label.setStyleSheet(f"color: {DesignSystem.Colors.TEXT_SECONDARY.name()};")
        layout.addWidget(state_label)

        return widget

    def _create_instructions(self) -> QWidget:
        """Create the instructions section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Instruction text
        instruction = QLabel("Press Ctrl+Alt to talk")
        instruction.setFont(DesignSystem.Typography.caption())
        instruction.setStyleSheet(f"color: {DesignSystem.Colors.TEXT_TERTIARY.name()};")
        layout.addWidget(instruction)

        return widget

    def _create_permissions_section(self) -> QWidget:
        """Create the permissions section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Permission labels
        mic_perm = QLabel("Microphone: ✓")
        mic_perm.setFont(DesignSystem.Typography.caption())
        mic_perm.setStyleSheet(f"color: {DesignSystem.Colors.ACCENT.name()};")
        layout.addWidget(mic_perm)

        screen_perm = QLabel("Screen: ✓")
        screen_perm.setFont(DesignSystem.Typography.caption())
        screen_perm.setStyleSheet(f"color: {DesignSystem.Colors.ACCENT.name()};")
        layout.addWidget(screen_perm)

        return widget

    def _on_quit(self):
        """Handle quit button click."""
        from PyQt5.QtWidgets import QApplication
        QApplication.quit()
