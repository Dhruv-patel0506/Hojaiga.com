import http.server
import socketserver
import urllib.request
import urllib.error
import sys
import json
import os
import socket
import logging

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

sys.path.insert(0, r"D:\new_automation\All codes")

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("hojaiga.Brain_Gatekeeper")

try:
    from core_organs.database_manager import DatabaseManager
    print("[GATEKEEPER] DatabaseManager loaded OK", flush=True)
except ImportError as e:
    print(f"[GATEKEEPER] DatabaseManager NOT available: {e}", flush=True)
    DatabaseManager = None

try:
    from core_organs.setup_login import ensure_login
    print("[GATEKEEPER] setup_login loaded OK", flush=True)
except ImportError as e:
    print(f"[GATEKEEPER] setup_login NOT available: {e}", flush=True)
    ensure_login = None

OLLAMA_URL = "http://127.0.0.1:11434"
GATEKEEPER_PORT = 11435
SECRET_PASSCODE = "339680"

class GatekeeperProxyHandler(http.server.BaseHTTPRequestHandler):
    def handle_one_request(self):
        """Intercept raw socket data payloads safely before http.server breaks on missing headers."""
        print(f"[GATEKEEPER] handle_one_request called", flush=True)
        try:
            raw_peek = self.connection.recv(1024, socket.MSG_PEEK)
            clean_peek = raw_peek.decode('utf-8', errors='ignore').strip()
            print(f"[GATEKEEPER] Peek: {clean_peek[:50]}", flush=True)

            if clean_peek.startswith('{'):
                body = self.connection.recv(65536).decode('utf-8')
                print(f"[GATEKEEPER] Raw JSON detected, processing...", flush=True)
                self.process_raw_json(body)
                return
        except Exception as e:
            print(f"[GATEKEEPER] Defensive intercept failure: {e}", flush=True)

        super().handle_one_request()

    def process_raw_json(self, raw_str):
        """Processes raw socket text streams cleanly without HTTP layer overloads."""
        try:
            data = json.loads(raw_str)
            self._normalize_and_log(data)
            self.connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        except Exception as e:
            print(f"[GATEKEEPER] Error handling raw socket string: {e}", flush=True)
            try:
                self.connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
            except Exception:
                pass

    def _normalize_and_log(self, data):
        """Unified dictionary alignment mapping engine with safe SSMS persistence caching."""
        title = data.get("title") or data.get("window_title") or "Unknown Event Window"
        detected_type = data.get("type") or data.get("detected_type") or "Generic State Change"

        if "coordinates" in data and isinstance(data["coordinates"], dict):
            x = data["coordinates"].get("x", 0)
            y = data["coordinates"].get("y", 0)
        else:
            x = data.get("x", 0)
            y = data.get("y", 0)

        event_id = data.get("event_id", "")
        print(f"[GATEKEEPER] Validated Event: [{detected_type}] '{title}' at ({x}, {y}) #{event_id}", flush=True)

        # Safe SSMS Persistent Caching — never crashes the server loop
        if DatabaseManager is not None:
            try:
                db = DatabaseManager()
                layout_hash = data.get("layout_hash") or f"gatekeeper_hash_{hash(title)}"
                print(f"[GATEKEEPER] Writing to DB: {layout_hash} | {title} | {x},{y}", flush=True)
                db.log_new_pathway(
                    layout_hash=layout_hash,
                    element_name=title,
                    x=int(x),
                    y=int(y),
                    action_type=detected_type,
                    parent_path="Gatekeeper_Intercept_Daemon",
                )
                print(f"[GATEKEEPER] DB write SUCCESS", flush=True)
            except Exception as db_err:
                print(f"[GATEKEEPER] DB write FAILED: {db_err}", flush=True)

    def check_auth(self):
        auth_header = self.headers.get('X-Hojaiga-Validation')
        if auth_header == SECRET_PASSCODE:
            return True
        return False

    def _read_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(content_length) if content_length > 0 else b""

    def _parse_popup_event(self, data):
        """Normalize incoming popup event keys (supports both old and new formats)."""
        title = data.get("title") or data.get("window_title", "Unknown")
        layout_hash = data.get("layout_hash", "")
        popup_type = data.get("type") or data.get("detected_type", "unknown")

        if "coordinates" in data:
            x = data["coordinates"].get("x", 0)
            y = data["coordinates"].get("y", 0)
        else:
            x = data.get("x", 0)
            y = data.get("y", 0)

        action = data.get("suggested_action") or data.get("action", "")
        event_id = data.get("event_id", 0)

        return {
            "event_id": event_id,
            "title": title,
            "layout_hash": layout_hash,
            "type": popup_type,
            "x": x,
            "y": y,
            "action": action,
        }

    def do_POST(self):
        # Route /launch_chrome and /popup separately — launching handled by gatekeeper
        if self.path == "/launch_chrome":
            self._handle_launch_chrome()
        elif self.path == "/popup":
            self._handle_popup_event()
        elif self.path == "/api/chat":
            # Handle Ollama chat API with authentication check
            self.do_PROXY("POST")
        else:
            self.do_PROXY("POST")

    def _handle_popup_event(self):
        """Handle popup events from mock_popup_stream.py and scanner."""
        try:
            body = self._read_body()
            data = json.loads(body.decode("utf-8")) if body else {}
            event = self._parse_popup_event(data)

            print(f"[POPUP] Event #{event['event_id']}: "
                  f"'{event['title']}' ({event['type']}) "
                  f"at ({event['x']},{event['y']}) -> {event['action']}",
                  flush=True)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "event": event}).encode())

        except Exception as e:
            print(f"[POPUP] Error: {e}", flush=True)
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_launch_chrome(self):
        """Gatekeeper handles Chrome launching — checks DB for session cookie, only runs setup_login if needed (not every time)."""
        try:
            body = self._read_body()
            data = json.loads(body.decode("utf-8")) if body else {}
            app = data.get("app") or data.get("site") or data.get("url") or "google.com"
            # extract domain if URL
            if "://" in app:
                from urllib.parse import urlparse
                try:
                    app = urlparse(app).netloc or app
                except Exception:
                    pass
            print(f"[LAUNCH] Gatekeeper handling Chrome launch for '{app}'", flush=True)
            if ensure_login is not None:
                import threading
                def _run():
                    try:
                        ensure_login(app)
                    except Exception as e:
                        print(f"[LAUNCH] ensure_login failed for {app}: {e}", flush=True)
                threading.Thread(target=_run, daemon=True).start()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "launching", "app": app, "handled_by": "gatekeeper"}).encode())
                print(f"[LAUNCH] dispatched ensure_login for {app} via gatekeeper", flush=True)
            else:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "setup_login not available"}).encode())
        except Exception as e:
            print(f"[LAUNCH] Error: {e}", flush=True)
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_PROXY(self, method):
        if not self.check_auth():
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized: Invalid Hojaiga Validation Passcode.\n")
            print(f"[BLOCKED] Unauthorized request from {self.client_address[0]}", flush=True)
            return

        print(f"[AUTHORIZED] Valid request from {self.client_address[0]} -> Path: {self.path}", flush=True)
        
        url = OLLAMA_URL + self.path
        
        # Read the body if it exists
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Vision-aware routing: if the request carries an image, route to the best
        # vision model available:
        #   - If llama.cpp vision server is running (port 8081) -> use Qwen2.5-VL-7B
        #   - Otherwise -> use Ollama vision model (moondream/qwen2.5vl:3b)
        if body:
            try:
                data = json.loads(body)
                msgs = data.get("messages", []) if isinstance(data, dict) else []

                def _has_image(m):
                    if not isinstance(m, dict):
                        return False
                    # Ollama chat API: images is a sibling field of the message.
                    if isinstance(m.get("images"), list) and m["images"]:
                        return True
                    # Also handle content-part format (multimodal parts).
                    c = m.get("content")
                    if isinstance(c, list):
                        for part in c:
                            if isinstance(part, dict) and part.get("type") == "image":
                                return True
                    return False

                if any(_has_image(m) for m in msgs):
                    # Check if llama.cpp vision server is available
                    llama_cpp_endpoint = os.environ.get("HOJAIGA_VISION_PRECISION_ENDPOINT", "")
                    if llama_cpp_endpoint.startswith("http"):
                        # Route to llama.cpp (Qwen2.5-VL-7B) - convert Ollama format to OpenAI format
                        print(f"[VISION ROUTE] image detected -> routing to llama.cpp: {llama_cpp_endpoint}", flush=True)
                        
                        # Convert Ollama format to OpenAI-compatible format for llama.cpp
                        openai_messages = []
                        for m in msgs:
                            if isinstance(m, dict):
                                role = m.get("role", "user")
                                content_parts = []
                                
                                # Handle text content
                                text = m.get("content", "")
                                if text:
                                    content_parts.append({"type": "text", "text": text})
                                
                                # Handle images (Ollama format -> OpenAI format)
                                images = m.get("images", [])
                                for img_b64 in images:
                                    content_parts.append({
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                                    })
                                
                                if content_parts:
                                    openai_messages.append({"role": role, "content": content_parts})
                        
                        # Build llama.cpp request
                        llama_request = {
                            "model": "qwen2.5-vl-7b",
                            "messages": openai_messages,
                            "temperature": data.get("options", {}).get("temperature", 0.2),
                            "max_tokens": 2048
                        }
                        
                        # Send to llama.cpp
                        llama_url = f"{llama_cpp_endpoint}/v1/chat/completions"
                        req = urllib.request.Request(
                            llama_url,
                            data=json.dumps(llama_request).encode(),
                            headers={"Content-Type": "application/json"},
                            method="POST"
                        )
                        
                        try:
                            with urllib.request.urlopen(req) as response:
                                result = json.loads(response.read().decode())
                                # Convert OpenAI response back to Ollama format
                                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                                ollama_response = {"message": {"role": "assistant", "content": content}}
                                
                                self.send_response(200)
                                self.send_header("Content-Type", "application/json")
                                self.end_headers()
                                self.wfile.write(json.dumps(ollama_response).encode())
                                return
                        except Exception as llama_err:
                            print(f"[VISION ROUTE] llama.cpp failed: {llama_err}, falling back to Ollama", flush=True)
                    
                    # Fallback to Ollama vision model
                    vision_model = os.environ.get("HOJAIGA_VISION_MODEL", "qwen2.5vl:3b")
                    data["model"] = vision_model
                    body = json.dumps(data).encode()
                    print(f"[VISION ROUTE] image detected -> forcing model '{vision_model}' (bypassing text brain)")
            except Exception:
                pass

        # Build request headers for Ollama
        req_headers = {}
        for key, val in self.headers.items():
            if key.lower() not in ['host', 'x-hojaiga-validation']:
                req_headers[key] = val
        
        # OLLAMA requires Host to be localhost if not configured otherwise
        req_headers['Host'] = 'localhost:11434'
        
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        
        try:
            with urllib.request.urlopen(req) as response:
                self.send_response(response.status)
                for key, val in response.getheaders():
                    if key.lower() not in ['transfer-encoding']:
                        self.send_header(key, val)
                self.end_headers()
                self.wfile.write(response.read())
                
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, val in e.headers.items():
                if key.lower() not in ['transfer-encoding']:
                    self.send_header(key, val)
            self.end_headers()
            self.wfile.write(e.read())
            
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"Bad Gateway: {str(e)}".encode())

    def do_GET(self):
        self.do_PROXY("GET")

    def do_OPTIONS(self):
        self.do_PROXY("OPTIONS")

    def do_PUT(self):
        self.do_PROXY("PUT")

    def do_DELETE(self):
        self.do_PROXY("DELETE")


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    # Allow immediate rebind after a restart (avoids "address already in use"
    # when the .bat is run twice or the previous instance is still in TIME_WAIT).
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    print("==================================================", flush=True)
    print("  HOJAIGA BRAIN GATEKEEPER ONLINE ", flush=True)
    print("==================================================", flush=True)
    print(f"Listening on port {GATEKEEPER_PORT} and protecting Ollama on port 11434.", flush=True)
    print("Ready to block unauthorized connections...\n", flush=True)
    
    with ReusableTCPServer(("", GATEKEEPER_PORT), GatekeeperProxyHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down Gatekeeper...")
