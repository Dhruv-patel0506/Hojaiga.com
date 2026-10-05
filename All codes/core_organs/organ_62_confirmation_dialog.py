"""
Organ 62 — User Confirmation Dialog System

Responsibility: Provide actual user confirmation dialogs for critical actions.
Uses tkinter for native Windows dialogs (lightweight, no dependencies).

Features:
- Yes/No confirmation dialogs
- Custom message dialogs
- Input dialogs for user input
- Warning dialogs
- Error dialogs
- Native Windows UI
- Non-blocking (can be made async)
"""

import asyncio
import logging
import sys
import tkinter as tk
from tkinter import simpledialog, messagebox
from typing import Any, Dict, List, Optional
from enum import Enum

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

logger = logging.getLogger("hojaiga.organ62.confirmation_dialog")


class DialogType(Enum):
    """Types of dialogs."""
    YES_NO = "yes_no"
    YES_NO_CANCEL = "yes_no_cancel"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    INPUT = "input"
    CHOICE = "choice"


class DialogResult:
    """Result from a dialog."""
    def __init__(self, confirmed: bool, user_input: str = None, choice: str = None):
        self.confirmed = confirmed
        self.user_input = user_input
        self.choice = choice


class UserConfirmationDialog:
    """
    User confirmation dialog system.
    
    Uses tkinter for native Windows dialogs (lightweight, no extra dependencies).
    Provides Yes/No, custom messages, input dialogs, and more.
    """
    
    def __init__(self):
        self._root = None
        self._dialog_queue = asyncio.Queue()
        self._running = False
    
    def _ensure_root(self):
        """Ensure tkinter root is created (hidden)."""
        if self._root is None:
            self._root = tk.Tk()
            self._root.withdraw()  # Hide the main window
    
    async def ask_yes_no(self, title: str, message: str) -> DialogResult:
        """
        Ask user Yes/No question.
        
        Args:
            title: Dialog title
            message: Dialog message
        
        Returns:
            DialogResult with confirmed status
        """
        logger.info(f"[ConfirmationDialog] Yes/No: {title}")
        
        self._ensure_root()
        
        # Run in thread to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._ask_yes_no_sync, title, message)
        
        return result
    
    def _ask_yes_no_sync(self, title: str, message: str) -> DialogResult:
        """Synchronous Yes/No dialog."""
        confirmed = messagebox.askyesno(title, message)
        return DialogResult(confirmed=confirmed)
    
    async def ask_yes_no_cancel(self, title: str, message: str) -> DialogResult:
        """
        Ask user Yes/No/Cancel question.
        
        Args:
            title: Dialog title
            message: Dialog message
        
        Returns:
            DialogResult with choice (yes, no, cancel)
        """
        logger.info(f"[ConfirmationDialog] Yes/No/Cancel: {title}")
        
        self._ensure_root()
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._ask_yes_no_cancel_sync, title, message)
        
        return result
    
    def _ask_yes_no_cancel_sync(self, title: str, message: str) -> DialogResult:
        """Synchronous Yes/No/Cancel dialog."""
        choice = messagebox.askyesnocancel(self._root, title, message)
        if choice is True:
            return DialogResult(confirmed=True, choice="yes")
        elif choice is False:
            return DialogResult(confirmed=False, choice="no")
        else:
            return DialogResult(confirmed=False, choice="cancel")
    
    async def show_info(self, title: str, message: str):
        """
        Show info dialog.
        
        Args:
            title: Dialog title
            message: Dialog message
        """
        logger.info(f"[ConfirmationDialog] Info: {title}")
        
        self._ensure_root()
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._show_info_sync, title, message)
    
    def _show_info_sync(self, title: str, message: str):
        """Synchronous info dialog."""
        messagebox.showinfo(self._root, title, message)
    
    async def show_warning(self, title: str, message: str):
        """
        Show warning dialog.
        
        Args:
            title: Dialog title
            message: Dialog message
        """
        logger.warning(f"[ConfirmationDialog] Warning: {title}")
        
        self._ensure_root()
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._show_warning_sync, title, message)
    
    def _show_warning_sync(self, title: str, message: str):
        """Synchronous warning dialog."""
        messagebox.showwarning(self._root, title, message)
    
    async def show_error(self, title: str, message: str):
        """
        Show error dialog.
        
        Args:
            title: Dialog title
            message: Dialog message
        """
        logger.error(f"[ConfirmationDialog] Error: {title}")
        
        self._ensure_root()
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._show_error_sync, title, message)
    
    def _show_error_sync(self, title: str, message: str):
        """Synchronous error dialog."""
        messagebox.showerror(self._root, title, message)
    
    async def ask_input(self, title: str, prompt: str, default: str = "") -> DialogResult:
        """
        Ask user for text input.
        
        Args:
            title: Dialog title
            prompt: Input prompt
            default: Default value
        
        Returns:
            DialogResult with user input
        """
        logger.info(f"[ConfirmationDialog] Input: {title}")
        
        self._ensure_root()
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._ask_input_sync, title, prompt, default)
        
        return result
    
    def _ask_input_sync(self, title: str, prompt: str, default: str) -> DialogResult:
        """Synchronous input dialog."""
        user_input = simpledialog.askstring(self._root, title, prompt, initialvalue=default)
        return DialogResult(confirmed=user_input is not None, user_input=user_input or "")
    
    async def ask_choice(self, title: str, prompt: str, choices: List[str]) -> DialogResult:
        """
        Ask user to choose from options.
        
        Args:
            title: Dialog title
            prompt: Choice prompt
            choices: List of choices
        
        Returns:
            DialogResult with selected choice
        """
        logger.info(f"[ConfirmationDialog] Choice: {title}")
        
        self._ensure_root()
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._ask_choice_sync, title, prompt, choices)
        
        return result
    
    def _ask_choice_sync(self, title: str, prompt: str, choices: List[str]) -> DialogResult:
        """Synchronous choice dialog."""
        # Use simpledialog for choice (simulated)
        choice_str = "\n".join([f"{i+1}. {c}" for i, c in enumerate(choices)])
        user_input = simpledialog.askstring(self._root, title, f"{prompt}\n\n{choice_str}\n\nEnter number:")
        
        if user_input:
            try:
                index = int(user_input) - 1
                if 0 <= index < len(choices):
                    return DialogResult(confirmed=True, choice=choices[index])
            except ValueError:
                pass
        
        return DialogResult(confirmed=False, choice=None)
    
    def cleanup(self):
        """Cleanup tkinter resources."""
        if self._root:
            self._root.destroy()
            self._root = None
