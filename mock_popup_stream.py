"""
Mock popup stream for testing purposes.
"""

import json
import requests
import time

import logging

logging.basicConfig(level=logging.INFO)

class MockPopupStream:
    def __init__(self):
        self.url = "http://127.0.0.1:11435"

    def send_popup(self, popup_data: dict) -> None:
        try:
            response = requests.post(self.url, json=popup_data)
            response.raise_for_status()
            logging.info("Mock popup stream sent: %s", popup_data)
        except requests.exceptions.RequestException as e:
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
