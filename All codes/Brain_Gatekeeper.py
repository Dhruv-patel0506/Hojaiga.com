"""
Brain Gatekeeper — CNS Bridge Server
Handles incoming popup detection requests from mock_popup_stream.py
"""

import json
import logging
import http.server
import socketserver

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


class BrainGatekeeperHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def handle_one_request(self):
        try:
            raw_data = self.rfile.read().decode('utf-8')
            if raw_data.startswith('{'):
                self.process_raw_json(raw_data)
            else:
                self.process_http_request(raw_data)
        except Exception as e:
            logger.error("Error processing request: %s", str(e))
            self.send_response(400)
            self.end_headers()

    def process_raw_json(self, raw_json):
        try:
            request = json.loads(raw_json)
            title = request.get("title") or request.get("window_title")
            x = request.get("x") or request.get("coordinates", {}).get("x")
            y = request.get("y") or request.get("coordinates", {}).get("y")
            logger.info("Received popup detection request: %s", request)
            self.send_response(200)
            self.end_headers()
        except Exception as e:
            logger.error("Error processing raw JSON: %s", str(e))
            self.send_response(400)
            self.end_headers()

    def process_http_request(self, http_request):
        try:
            self.send_response(200)
            self.end_headers()
        except Exception as e:
            logger.error("Error processing HTTP request: %s", str(e))
            self.send_response(400)
            self.end_headers()

class BrainGatekeeperServer(socketserver.TCPServer):
    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)


def run_server():
    PORT = 11435
    Handler = BrainGatekeeperHTTPRequestHandler
    With = socketserver.TCPServer
    server_address = ("", PORT)
    httpd = With(server_address, Handler)
    print(f"Brain Gatekeeper started on port {PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
