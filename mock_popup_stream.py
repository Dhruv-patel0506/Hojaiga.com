"""
Mock popup stream for testing purposes.
"""

import json
import socket
import time

import logging

logging.basicConfig(level=logging.INFO)

class MockPopupStream:
    def __init__(self):
        self.url = "127.0.0.1"
        self.port = 11435

    def send_popup(self, popup_data: dict) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.url, self.port))
            sock.sendall(json.dumps(popup_data).encode("utf-8"))
            sock.close()
            logging.info("Mock popup stream sent: %s", popup_data)
        except socket.error as e:
            logging.error("Error sending mock popup stream: %s", e)

    def run(self) -> None:
        while True:
            time.sleep(0.1)
            popup_data = {
                "type": "POPUP_DETECTED",
                "title": "Mock Popup",
                "x": 100,
                "y": 200,
            }
            self.send_popup(popup_data)
