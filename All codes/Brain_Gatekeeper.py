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
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length).decode('utf-8')
        try:
            request = json.loads(body)
            title = request.get("title") or request.get("window_title")
            x = request.get("x") or request.get("coordinates", {}).get("x")
            y = request.get("y") or request.get("coordinates", {}).get("y")
            logger.info("Received popup detection request: %s", request)
            self.send_response(200)
            self.end_headers()
            return True

    def log_request(self, code, size):
        logger.info(f"Received request: {code} {size}")


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
