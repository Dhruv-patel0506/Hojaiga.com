"""
CNS Socket Bridge — HostAgent ↔ AppAgent Communication Layer
Lightning-fast socket coordination for popup interception and screen freeze alerts.

Usage:
  HostAgent (Gatekeeper): Listens for alerts, dispatches popup intercepts
  AppAgent (Crawler): Receives alerts, pauses execution, applies bypass coordinates
"""

import json
import logging
import socket
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("hojaiga.cns_bridge")


class CNSSocketBridge:
    """Socket-based message bus for HostAgent ↔ AppAgent communication."""

    def __init__(self, role: str, port: int = 11436, host: str = "127.0.0.1"):
        """
        Args:
            role: "HostAgent" or "AppAgent"
            port: Socket port (default 11436, separate from Gatekeeper's 11435)
            host: Bind address
        """
        self.role = role
        self.port = port
        self.host = host
        self.running = False
        self._server_socket = None
        self._listener_thread = None
        self._message_queue = []
        self._queue_lock = threading.Lock()

    def start_listener(self, message_callback: Callable[[Dict], None]) -> None:
        """Start a non-blocking background thread to listen for CNS alerts.
        Args:
            message_callback: Function called with parsed message dict for each incoming alert
        """
        if self.running:
            logger.warning("[CNS] Already running on port %d", self.port)
            return

        self.running = True

        def _listen():
            try:
                self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._server_socket.settimeout(1.0)
                self._server_socket.bind((self.host, self.port))
                self._server_socket.listen(5)
                logger.info("[CNS] %s listener active on %s:%d", self.role, self.host, self.port)

                while self.running:
                    try:
                        client_conn, addr = self._server_socket.accept()
                        data = b""
                        while True:
                            chunk = client_conn.recv(4096)
                            if not chunk:
                                break
                            data += chunk
                            if len(data) > 65536:
                                break
                        client_conn.close()

                        if data:
                            try:
                                parsed = json.loads(data.decode("utf-8"))
                                logger.debug("[CNS] Received: %s", str(parsed)[:100])
                                message_callback(parsed)
                            except json.JSONDecodeError as e:
                                logger.warning("[CNS] Invalid JSON: %s", e)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self.running:
                            logger.warning("[CNS] Accept error: %s", e)
            except Exception as e:
                logger.error("[CNS] Listener failed: %s", e)
            finally:
                if self._server_socket:
                    try:
                        self._server_socket.close()
                    except Exception:
                        pass

        self._listener_thread = threading.Thread(target=_listen, daemon=True)
        self._listener_thread.start()

    def send_alert(self, message_dict: Dict[str, Any]) -> bool:
        """Dispatch an event payload across the CNS loop.
        Args:
            message_dict: JSON-serializable message payload
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(5.0)
            client_socket.connect((self.host, self.port))
            payload = json.dumps(message_dict).encode("utf-8")
            client_socket.sendall(payload)
            client_socket.close()
            logger.debug("[CNS] Sent: %s", str(message_dict)[:100])
            return True
        except ConnectionRefusedError:
            logger.debug("[CNS] Peer not ready on port %d", self.port)
            return False
        except Exception as e:
            logger.warning("[CNS] Send failed: %s", e)
            return False

    def stop(self):
        """Stop the listener."""
        self.running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass


class CNSPopupInterceptor:
    """High-level popup interception coordinator using CNS bridge.

    Flow:
      1. AppAgent detects popup -> sends POPUP_DETECTED alert
      2. HostAgent receives alert -> checks DB cache
      3. If cache hit: sends POPUP_RESOLVED with action
      4. If cache miss: runs vision -> sends POPUP_RESOLVED with new action
      5. AppAgent receives POPUP_RESOLVED -> executes action
    """

    POPUP_DETECTED = "POPUP_DETECTED"
    POPUP_RESOLVED = "POPUP_RESOLVED"
    SCREEN_FREEZE = "SCREEN_FREEZE"
    SCREEN_UNFREEZE = "SCREEN_UNFREEZE"

    def __init__(self, role: str, port: int = 11436):
        self.bridge = CNSSocketBridge(role=role, port=port)
        self._handlers = {}
        self._pending_resolutions = {}
        self._resolution_lock = threading.Lock()

    def start(self, on_popup_detected: Callable = None, on_popup_resolved: Callable = None):
        """Start the CNS interceptor with callbacks."""
        def _handle_message(msg: Dict):
            msg_type = msg.get("type", "")

            if msg_type == self.POPUP_DETECTED and on_popup_detected:
                on_popup_detected(msg)

            elif msg_type == self.POPUP_RESOLVED:
                popup_id = msg.get("popup_id", "")
                with self._resolution_lock:
                    if popup_id in self._pending_resolutions:
                        self._pending_resolutions[popup_id] = msg
                if on_popup_resolved:
                    on_popup_resolved(msg)

            elif msg_type == self.SCREEN_FREEZE:
                logger.info("[CNS] Screen freeze requested")
            elif msg_type == self.SCREEN_UNFREEZE:
                logger.info("[CNS] Screen unfreeze requested")

        self.bridge.start_listener(_handle_message)

    def alert_popup_detected(self, title: str, layout_hash: str, x: int = 0, y: int = 0) -> str:
        """Alert CNS that a popup was detected. Returns popup_id for tracking."""
        popup_id = f"{layout_hash}_{int(time.time())}"
        self.bridge.send_alert({
            "type": self.POPUP_DETECTED,
            "popup_id": popup_id,
            "title": title,
            "layout_hash": layout_hash,
            "x": x,
            "y": y,
            "timestamp": time.time(),
        })
        return popup_id

    def alert_popup_resolved(self, popup_id: str, action: str, success: bool = True):
        """Alert CNS that a popup was resolved."""
        self.bridge.send_alert({
            "type": self.POPUP_RESOLVED,
            "popup_id": popup_id,
            "action": action,
            "success": success,
            "timestamp": time.time(),
        })

    def wait_for_resolution(self, popup_id: str, timeout: float = 30.0) -> Optional[Dict]:
        """Wait for a popup resolution from the peer agent."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._resolution_lock:
                if popup_id in self._pending_resolutions:
                    return self._pending_resolutions.pop(popup_id)
            time.sleep(0.1)
        return None

    def freeze_screen(self):
        """Request screen freeze (pause UI interactions)."""
        self.bridge.send_alert({"type": self.SCREEN_FREEZE, "timestamp": time.time()})

    def unfreeze_screen(self):
        """Release screen freeze."""
        self.bridge.send_alert({"type": self.SCREEN_UNFREEZE, "timestamp": time.time()})

    def stop(self):
        """Stop the CNS bridge."""
        self.bridge.stop()
