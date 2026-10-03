"""
Design System - Clicky-style Design Tokens

Centralized design system using coral-red accent on dark surfaces.
Converted from DesignSystem.swift to Windows Python.
"""

from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtCore import Qt


class DesignSystem:
    """Design system namespace for all UI tokens."""

    class Colors:
        """Color tokens for the UI."""

        # Backgrounds
        BACKGROUND = QColor("#101211")
        SURFACE1 = QColor("#171918")
        SURFACE2 = QColor("#202221")
        SURFACE3 = QColor("#272A29")
        SURFACE4 = QColor("#2E3130")

        # Borders
        BORDER_SUBTLE = QColor("#373B39")
        BORDER_STRONG = QColor("#444947")

        # Text
        TEXT_PRIMARY = QColor("#ECEEED")
        TEXT_SECONDARY = QColor("#ADB5B2")
        TEXT_TERTIARY = QColor("#6B736F")
        TEXT_ON_ACCENT = QColor("#FFFFFF")

        # Coral-red accent (Clicky style - replacing blue)
        ACCENT = QColor("#FF3B30")  # Coral red
        ACCENT_HOVER = QColor("#E62A20")  # Darker coral

        # Overlay cursor blue (for traditional blue cursor)
        OVERLAY_CURSOR_BLUE = QColor("#3B82F6")

    class CornerRadius:
        """Corner radius tokens."""

        SMALL = 4
        MEDIUM = 6
        LARGE = 8
        XLARGE = 12

    class Spacing:
        """Spacing tokens."""

        XS = 4
        SM = 8
        MD = 12
        LG = 16
        XL = 20
        XXL = 24

    class Typography:
        """Typography tokens."""

        @staticmethod
        def heading1():
            """Heading 1 font."""
            font = QFont("Arial", 20, QFont.Bold)
            return font

        @staticmethod
        def heading2():
            """Heading 2 font."""
            font = QFont("Arial", 16, QFont.Bold)
            return font

        @staticmethod
        def body():
            """Body font."""
            font = QFont("Arial", 12)
            return font

        @staticmethod
        def caption():
            """Caption font."""
            font = QFont("Arial", 10)
            return font

        @staticmethod
        def monospace():
            """Monospace font."""
            font = QFont("Consolas", 11)
            return font

    @staticmethod
    def apply_dark_theme(widget):
        """
        Apply dark theme to a widget.

        Args:
            widget: QWidget to apply theme to
        """
        palette = widget.palette()
        palette.setColor(QPalette.Window, DesignSystem.Colors.BACKGROUND)
        palette.setColor(QPalette.WindowText, DesignSystem.Colors.TEXT_PRIMARY)
        palette.setColor(QPalette.Base, DesignSystem.Colors.SURFACE1)
        palette.setColor(QPalette.AlternateBase, DesignSystem.Colors.SURFACE2)
        palette.setColor(QPalette.Text, DesignSystem.Colors.TEXT_PRIMARY)
        palette.setColor(QPalette.Button, DesignSystem.Colors.SURFACE2)
        palette.setColor(QPalette.ButtonText, DesignSystem.Colors.TEXT_PRIMARY)
        palette.setColor(QPalette.Highlight, DesignSystem.Colors.ACCENT)
        palette.setColor(QPalette.HighlightedText, DesignSystem.Colors.TEXT_ON_ACCENT)
        widget.setPalette(palette)
        widget.setAutoFillBackground(True)

    @staticmethod
    def get_button_style():
        """
        Get button stylesheet string.

        Returns:
            str: CSS stylesheet for buttons
        """
        return f"""
            QPushButton {{
                background-color: {DesignSystem.Colors.ACCENT.name()};
                color: {DesignSystem.Colors.TEXT_ON_ACCENT.name()};
                border: none;
                border-radius: {DesignSystem.CornerRadius.MEDIUM}px;
                padding: {DesignSystem.Spacing.SM}px {DesignSystem.Spacing.LG}px;
                font-family: Arial;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {DesignSystem.Colors.ACCENT_HOVER.name()};
            }}
            QPushButton:pressed {{
                background-color: {DesignSystem.Colors.ACCENT_HOVER.name()};
            }}
            QPushButton:disabled {{
                background-color: {DesignSystem.Colors.SURFACE3.name()};
                color: {DesignSystem.Colors.TEXT_TERTIARY.name()};
            }}
        """

    @staticmethod
    def get_input_style():
        """
        Get input field stylesheet string.

        Returns:
            str: CSS stylesheet for input fields
        """
        return f"""
            QLineEdit, QTextEdit {{
                background-color: {DesignSystem.Colors.SURFACE2.name()};
                color: {DesignSystem.Colors.TEXT_PRIMARY.name()};
                border: 1px solid {DesignSystem.Colors.BORDER_SUBTLE.name()};
                border-radius: {DesignSystem.CornerRadius.MEDIUM}px;
                padding: {DesignSystem.Spacing.SM}px;
                font-family: Arial;
                font-size: 12px;
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border: 1px solid {DesignSystem.Colors.ACCENT.name()};
            }}
        """

    @staticmethod
    def get_card_style():
        """
        Get card stylesheet string.

        Returns:
            str: CSS stylesheet for cards
        """
        return f"""
            QWidget {{
                background-color: {DesignSystem.Colors.SURFACE1.name()};
                border: 1px solid {DesignSystem.Colors.BORDER_SUBTLE.name()};
                border-radius: {DesignSystem.CornerRadius.LARGE}px;
            }}
        """
