"""
CNS Socket Bridge — HostAgent <-> AppAgent Communication Layer
Lightning-fast socket coordination for popup interception and screen freeze alerts.
"""

import json
import logging
import socket
import threading
import time
from typing import Any, Dict, Optional, Callable

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("hojaiga.cns_bridge")


class CNSSocketBridge:
    def __init__(self, role: str = "HostAgent", base_port: int = 11436):
        self.role = role
        self.listen_port = base_port if role == "HostAgent" else (base_port + 1)
        self.target_port = (base_port + 1) if role == "HostAgent" else base_port

        self._listener: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._handler: Optional[Callable] = None

    def start_listener(self, on_message: Optional[Callable] = None):
        self._handler = on_message
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.settimeout(1.0)
        self._listener.bind(("127.0.0.1", self.listen_port))
        self._listener.listen(5)
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        logger.info("[%s] CNS listener established on port %d", self.role, self.listen_port)

    def _listen_loop(self):
        while self._running:
            listener = self._listener
            if listener is None:
                break
            try:
                conn, addr = listener.accept()
                data = conn.recv(65536).decode("utf-8")
                if data:
                    try:
                        message = json.loads(data)
                    except json.JSONDecodeError:
                        logger.warning("[%s] Invalid JSON received", self.role)
                        message = None
                else:
                    message = None
                conn.sendall(b"OK")
                conn.close()
                if message and self._handler:
                    threading.Thread(target=self._handler, args=(message,), daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                # Socket was closed by stop(), exit gracefully
                break
            except Exception as e:
                if self._running:
                    logger.error("[%s] Listener error: %s", self.role, e)

    def send_alert(self, message_dict: Dict[str, Any]) -> bool:
        if message_dict.get("type") == "POPUP_DETECTED":
            logger.info("[CNS] Popup data passed across socket: %s", str(message_dict)[:100])
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(3.0)
            client.connect(("127.0.0.1", self.target_port))
            client.sendall(json.dumps(message_dict).encode("utf-8"))
            resp = client.recv(1024)
            client.close()
            return resp == b"OK"
        except Exception as e:
            logger.debug("[%s] Target not listening on port %d: %s", self.role, self.target_port, e)
            return False

    def stop(self):
        self._running = False
        if self._listener:
            try:
                self._listener.close()
            except OSError:
                pass
            self._listener = None
        logger.info("[%s] CNS listener terminated.", self.role)


class CNSPopupInterceptor:
    def __init__(self, role: str = "HostAgent", port: int = 11436):
        self.role = role
        self.port = port
        self.bridge = CNSSocketBridge(role=role, base_port=port)
        self._popup_resolutions: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self._on_popup_callback: Optional[Callable] = None

    def start(self, on_popup_detected: Optional[Callable] = None):
        self._on_popup_callback = on_popup_detected
        self.bridge.start_listener(on_message=self._handle_message)

    def _handle_message(self, message: Dict[str, Any]):
        msg_type = message.get("type", "")
        if msg_type == "POPUP_DETECTED":
            popup_id = message.get("popup_id", "unknown")
            logger.info("[%s] Popup detected: %s", self.role, popup_id)
            if self._on_popup_callback:
                try:
                    self._on_popup_callback(message)
                except Exception as e:
                    logger.error("[%s] Error in popup callback: %s", self.role, e)
        elif msg_type == "POPUP_RESOLUTION":
            popup_id = message.get("popup_id", "unknown")
            with self._lock:
                self._popup_resolutions[popup_id] = message
            logger.info("[%s] Resolution received for: %s", self.role, popup_id)

    def alert_popup_detected(self, title: str, layout_hash: str, x: int, y: int) -> str:
        popup_id = f"{layout_hash}_{int(time.time() * 1000)}"
        self.bridge.send_alert({
            "type": "POPUP_DETECTED",
            "popup_id": popup_id,
            "title": title,
            "layout_hash": layout_hash,
            "x": x,
            "y": y,
            "source": self.role,
        })
        return popup_id

    def wait_for_resolution(self, popup_id: str, timeout: float = 10.0) -> Optional[Dict]:
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if popup_id in self._popup_resolutions:
                    return self._popup_resolutions.pop(popup_id)
            time.sleep(0.1)
        return None

    def send_resolution(self, popup_id: str, action: str, x: int, y: int):
        self.bridge.send_alert({
            "type": "POPUP_RESOLUTION",
            "popup_id": popup_id,
            "action": action,
            "x": x,
            "y": y,
            "source": self.role,
        })

    def stop(self):
        self.bridge.stop()
