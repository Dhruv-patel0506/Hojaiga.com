"""
Organ 42 — Navigation & Popup Organ (Visual Interruption Handler)

Responsibility: Monitors for visual interruptions (cookie banners, "Sign in to Google" popups, generic modals).
If the Scanner Organ detects an overlay, this organ temporarily takes over to dismiss or accept it
before returning control to the primary execution agent.

Architecture:
  - Subscribes to Scanner Organ's screen change events
  - Pattern matching for common popup/modal types
  - Automatic dismissal strategies (cookie consent, sign-in prompts, generic dialogs)
  - Returns control to primary agent after handling
  - Escalates to Fallback Organ if popup requires manual intervention
"""

import logging
import os
import sys
import time
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

try:
    from core_organs.organ_02_cns_single_file import EventEnvelope
except ImportError:
    try:
        from organ_02_cns_single_file import EventEnvelope
    except ImportError:
        @dataclass
        class EventEnvelope:
            topic: str
            source_organ: str
            payload: dict[str, Any]
            event_id: str = ""
            timestamp_ms: int = 0
            priority: int = 5
            correlation_id: Optional[str] = None

logger = logging.getLogger("hojaiga.organ42.navigation_popup")


class PopupType(Enum):
    """Classification of popup/modal types."""
    COOKIE_CONSENT = "cookie_consent"
    SIGN_IN_PROMPT = "sign_in_prompt"
    GENERIC_MODAL = "generic_modal"
    ALERT_DIALOG = "alert_dialog"
    UNKNOWN = "unknown"


class PopupAction(Enum):
    """Standard actions for popup handling."""
    DISMISS = "dismiss"
    ACCEPT = "accept"
    CUSTOM = "custom"
    ESCALATE = "escalate"


@dataclass
class PopupPattern:
    """Pattern for detecting and handling specific popup types."""
    name: str
    popup_type: PopupType
    text_patterns: List[str]
    class_patterns: List[str]
    default_action: PopupAction
    action_selectors: Dict[str, str]  # action -> button text/selector


class NavigationPopupOrgan:
    """
    Visual Interruption Handler for popups, modals, and banners.

    Features:
    - Subscribes to Scanner Organ's screen change events
    - Pattern matching for common popup types
    - Automatic dismissal strategies
    - Returns control to primary agent after handling
    - Escalates to Fallback Organ for manual intervention
    """

    # Predefined popup patterns
    POPUP_PATTERNS = [
        PopupPattern(
            name="cookie_consent",
            popup_type=PopupType.COOKIE_CONSENT,
            text_patterns=["accept", "accept all", "agree", "consent", "cookie", "privacy"],
            class_patterns=["cookie", "consent", "privacy", "banner"],
            default_action=PopupAction.ACCEPT,
            action_selectors={
                "accept": "accept",
                "dismiss": "reject",
            },
        ),
        PopupPattern(
            name="sign_in_google",
            popup_type=PopupType.SIGN_IN_PROMPT,
            text_patterns=["sign in", "login", "continue with google", "authentication"],
            class_patterns=["signin", "login", "auth", "credential"],
            default_action=PopupAction.ESCALATE,
            action_selectors={
                "accept": "sign in",
                "dismiss": "cancel",
            },
        ),
        PopupPattern(
            name="generic_modal",
            popup_type=PopupType.GENERIC_MODAL,
            text_patterns=["ok", "cancel", "close", "dismiss", "continue"],
            class_patterns=["modal", "dialog", "popup", "overlay"],
            default_action=PopupAction.CUSTOM,
            action_selectors={
                "accept": "ok",
                "dismiss": "cancel",
            },
        ),
    ]

    def __init__(self, cns_publisher=None, scanner_organ=None):
        self.cns = cns_publisher
        self.scanner = scanner_organ
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._active_popup: Optional[Dict[str, Any]] = None
        self._handling_popup = False
        self._visual_cursor = None  # Will be set externally for visual feedback

        # Action execution callback (will be set by primary agent)
        self._execute_click: Optional[Callable[[str, str], bool]] = None
        self._execute_type: Optional[Callable[[str], bool]] = None

    def set_visual_cursor(self, visual_cursor):
        """Set visual cursor instance for feedback during popup handling."""
        self._visual_cursor = visual_cursor

    def set_action_callbacks(self, click_callback: Callable, type_callback: Callable):
        """Set callbacks for executing UI actions."""
        self._execute_click = click_callback
        self._execute_type = type_callback

    def start(self):
        """Start popup monitoring loop."""
        if self._running:
            logger.warning("[NavigationPopup] Already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("[NavigationPopup] Started popup monitoring")

    def stop(self):
        """Stop popup monitoring loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("[NavigationPopup] Stopped popup monitoring")

    def _monitor_loop(self):
        """Main monitoring loop for popup detection."""
        while self._running:
            try:
                # Check current screen state from Scanner Organ
                if self.scanner:
                    current_state = self.scanner.get_current_state()
                    if current_state:
                        self._check_for_popups(current_state)

                time.sleep(0.5)  # Check every 500ms

            except Exception as e:
                logger.error(f"[NavigationPopup] Monitor loop error: {e}")

    def _check_for_popups(self, screen_state: Dict[str, Any]):
        """Check if any popup patterns match the current screen."""
        if self._handling_popup:
            return  # Already handling a popup

        elements = screen_state.get("elements", [])
        change_type = screen_state.get("change_type", "")

        # Only check for popups on significant changes
        if change_type not in ["modal_or_popup", "content_update"]:
            return

        for pattern in self.POPUP_PATTERNS:
            matched = self._match_pattern(pattern, elements)
            if matched:
                logger.info(f"[NavigationPopup] Detected popup: {pattern.name}")
                self._handle_popup(pattern, matched)
                break

    def _match_pattern(self, pattern: PopupPattern, elements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Check if popup pattern matches current screen elements."""
        matched_elements = []

        for elem in elements:
            text = elem.get("text", "").lower()
            class_name = elem.get("class_name", "").lower()

            # Check text patterns
            text_match = any(p in text for p in pattern.text_patterns)
            # Check class patterns
            class_match = any(p in class_name for p in pattern.class_patterns)

            if text_match or class_match:
                matched_elements.append(elem)

        if matched_elements:
            return {
                "pattern": pattern.name,
                "popup_type": pattern.popup_type.value,
                "elements": matched_elements,
                "default_action": pattern.default_action.value,
            }

        return None

    def _handle_popup(self, pattern: PopupPattern, matched: Dict[str, Any]):
        """Handle detected popup based on its type and default action."""
        self._handling_popup = True
        self._active_popup = matched

        # Show cursor as active during popup handling
        if self._visual_cursor:
            self._visual_cursor.set_active_state("ACTIVE")
            self._visual_cursor.set_buffering(True)

        try:
            action = PopupAction(matched["default_action"])

            if action == PopupAction.ESCALATE:
                self._escalate_to_fallback(matched)
            elif action == PopupAction.ACCEPT:
                self._perform_action(pattern, "accept")
            elif action == PopupAction.DISMISS:
                self._perform_action(pattern, "dismiss")
            elif action == PopupAction.CUSTOM:
                # Try to determine best action based on context
                self._handle_custom_popup(matched)

        except Exception as e:
            logger.error(f"[NavigationPopup] Error handling popup: {e}")
            self._escalate_to_fallback(matched)
        finally:
            self._handling_popup = False
            self._active_popup = None
            # Reset cursor after handling
            if self._visual_cursor:
                self._visual_cursor.set_buffering(False)

    def _perform_action(self, pattern: PopupPattern, action: str):
        """Execute the specified action on the popup."""
        if not self._execute_click:
            logger.warning("[NavigationPopup] No click callback set - cannot perform action")
            self._escalate_to_fallback({"pattern": pattern.name, "reason": "no_callback"})
            return

        selector = pattern.action_selectors.get(action)
        if not selector:
            logger.warning(f"[NavigationPopup] No selector for action: {action}")
            return

        # Find element matching the selector
        elements = self._active_popup.get("elements", [])
        for elem in elements:
            text = elem.get("text", "").lower()
            if selector in text:
                bounds = elem.get("bounds")
                if bounds:
                    # Execute click at center of element
                    cx = (bounds[0] + bounds[2]) // 2
                    cy = (bounds[1] + bounds[3]) // 2
                    success = self._execute_click(str(cx), str(cy))
                    if success:
                        logger.info(f"[NavigationPopup] Successfully performed {action} on {pattern.name}")
                        self._emit_popup_handled(pattern.name, action)
                    else:
                        logger.warning(f"[NavigationPopup] Failed to perform {action} on {pattern.name}")
                        self._escalate_to_fallback({"pattern": pattern.name, "reason": "click_failed"})
                return

        logger.warning(f"[NavigationPopup] Could not find element for action: {action}")

    def _handle_custom_popup(self, matched: Dict[str, Any]):
        """Handle custom popup by analyzing its content."""
        elements = matched.get("elements", [])

        # Simple heuristic: if we see "OK" or "Continue", click it
        for elem in elements:
            text = elem.get("text", "").lower()
            if "ok" in text or "continue" in text or "accept" in text:
                bounds = elem.get("bounds")
                if bounds and self._execute_click:
                    cx = (bounds[0] + bounds[2]) // 2
                    cy = (bounds[1] + bounds[3]) // 2
                    success = self._execute_click(str(cx), str(cy))
                    if success:
                        logger.info(f"[NavigationPopup] Handled custom popup by clicking: {text}")
                        self._emit_popup_handled("custom", "click")
                        return

        # If no clear action, escalate
        self._escalate_to_fallback(matched)

    def _escalate_to_fallback(self, popup_info: Dict[str, Any]):
        """Escalate popup handling to Fallback Organ for manual intervention."""
        logger.warning(f"[NavigationPopup] Escalating to Fallback Organ: {popup_info}")

        if self.cns:
            try:
                event = EventEnvelope(
                    topic="popup.requires_manual_intervention",
                    source_organ="organ_42_navigation_popup",
                    payload=popup_info,
                    event_id=f"popup_esc_{int(time.time() * 1000)}",
                    timestamp_ms=int(time.time() * 1000),
                    priority=9,  # Highest priority
                )
                self.cns.publish(event)
            except Exception as e:
                logger.error(f"[NavigationPopup] Failed to emit escalation event: {e}")

    def _emit_popup_handled(self, pattern_name: str, action: str):
        """Emit event when popup is successfully handled."""
        if self.cns:
            try:
                event = EventEnvelope(
                    topic="popup.handled",
                    source_organ="organ_42_navigation_popup",
                    payload={
                        "pattern": pattern_name,
                        "action": action,
                        "timestamp": time.time(),
                    },
                    event_id=f"popup_handled_{int(time.time() * 1000)}",
                    timestamp_ms=int(time.time() * 1000),
                    priority=5,
                )
                self.cns.publish(event)
            except Exception as e:
                logger.error(f"[NavigationPopup] Failed to emit handled event: {e}")

    def add_custom_pattern(self, pattern: PopupPattern):
        """Add a custom popup pattern to the detection list."""
        self.POPUP_PATTERNS.append(pattern)
        logger.info(f"[NavigationPopup] Added custom pattern: {pattern.name}")

    def is_handling_popup(self) -> bool:
        """Check if currently handling a popup."""
        return self._handling_popup

    def get_active_popup(self) -> Optional[Dict[str, Any]]:
        """Get information about the currently active popup."""
        return self._active_popup
