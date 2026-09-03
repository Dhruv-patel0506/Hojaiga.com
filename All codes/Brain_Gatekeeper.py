"""
Brain Gatekeeper — CNS Bridge Server
Handles incoming popup detection requests from mock_popup_stream.py
"""

import json
import logging
import socket

import logging.config

logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'standard': {'format': '[%(asctime)s] [%(levelname)s] %(message)s'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'standard',
        },
    },
    'loggers': {
        'hojaiga': {
            'level': 'INFO',
            'handlers': ['console'],
        },
    },
})

logger = logging.getLogger("hojaiga.Brain_Gatekeeper")


class BrainGatekeeper:
    def __init__(self):
        self.port = 11435

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", self.port))
        self.server.listen(1)
        logger.info("Brain Gatekeeper started on port %s", self.port)

    def handle_request(self, request):
        try:
            data = json.loads(request)
            if "type" in data and data["type"] == "POPUP_DETECTED":
                # New payload keys: "type", "title", "x", "y"
                if "title" in data and "x" in data and "y" in data:
                    # New payload format: {"type": "POPUP_DETECTED", "title": "Mock Popup", "x": 100, "y": 200}
                    logger.info("Received new popup detection request: %s", data)
                    # ... (rest of the code remains the same)
                # Old payload keys: "window_title", "layout_hash", "coordinates"
                elif "window_title" in data and "layout_hash" in data and "coordinates" in data:
                    # Old payload format: {"window_title": "Mock Popup", "layout_hash": "abc123", "coordinates": [100, 200]}
                    logger.info("Received old popup detection request: %s", data)
                    # ... (rest of the code remains the same)
                else:
                    logger.error("Invalid request payload: %s", data)
                    return False
            else:
                logger.error("Invalid request type: %s", request)
                return False
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON request: %s", e)
            return False
        return True

    def run(self):
        self.start()
        while True:
            client, address = self.server.accept()
            request = client.recv(1024).decode("utf-8")
            if self.handle_request(request):
                client.sendall(b"OK")
            else:
                client.sendall(b"BAD_REQUEST")
            client.close()
