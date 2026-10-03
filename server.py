"""HOJAIGA // Holographic CNS Server (Abilities #38 + #46-49 backbone)

Single process, two listeners:
  * HTTP  127.0.0.1:8000  -> static 3D worlds + /api/emit + /api/intent + /api/vault + SSE
  * WS    127.0.0.1:8765  -> live telemetry push + inbound Living Interface commands

Run:  python server.py      (then open http://localhost:8000)
Agent: python hojaiga_agent.py  (POSTs every scan / decision / actuation here)
"""

import asyncio
import json
import queue
import sqlite3
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
HTTP_HOST, HTTP_PORT = "127.0.0.1", 8000
WS_HOST, WS_PORT = "127.0.0.1", 8765
MAX_BODY = 1_000_000
HARVEST_DB = ROOT / "hojaiga_harvest.db"

try:
    import websockets
    from websockets.asyncio.server import serve as ws_serve
    WS_AVAILABLE = True
except Exception:
    WS_AVAILABLE = False


class CNSState:
    def __init__(self):
        self.lock = threading.Lock()
        self.buffer = deque(maxlen=200)        # recent events for /api/events
        self.sse_clients = set()               # queue.Queue per SSE browser
        self.ws_clients = set()                # websockets connections
        self.loop = None                       # asyncio loop of the WS thread
        self.stats = {"events": 0, "sse": 0, "ws": 0}

    def broadcast(self, event: dict):
        """Thread-safe fan-out: SQLite harvest -> buffer -> SSE queues -> WS clients."""
        _harvest(event)
        with self.lock:
            self.buffer.append(event)
            self.stats["events"] += 1
            sse = list(self.sse_clients)
        for q in sse:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass
        if self.loop is not None and WS_AVAILABLE:
            payload = json.dumps(event)
            asyncio.run_coroutine_threadsafe(_ws_broadcast(payload), self.loop)


state = CNSState()


# --------------------------------------------------------------------------
# Ability #49: SQLite WAL harvest store (every broadcast event is sealed here)
# --------------------------------------------------------------------------
_harvest_lock = threading.Lock()


def _harvest_db():
    conn = sqlite3.connect(HARVEST_DB, timeout=4)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS harvest (
            id TEXT PRIMARY KEY,
            ts REAL,
            sector TEXT,
            event_type TEXT,
            record_title TEXT,
            log_line TEXT,
            payload TEXT
        )
    """)
    return conn


def _harvest(event: dict):
    try:
        with _harvest_lock:
            conn = _harvest_db()
            conn.execute(
                "INSERT OR IGNORE INTO harvest VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.get("id") or uuid.uuid4().hex[:12],
                    event.get("ts") or time.time(),
                    event.get("sector", "hub"),
                    event.get("event_type", "EVENT"),
                    event.get("record_title") or "",
                    event.get("log_line") or "",
                    json.dumps({k: v for k, v in event.items()
                                if k in ("intent", "metrics", "coordinates")}),
                ),
            )
            conn.commit()
            conn.close()
    except Exception:
        pass


def harvest_read(limit: int = 30):
    try:
        with _harvest_lock:
            conn = _harvest_db()
            rows = conn.execute(
                "SELECT id, ts, sector, event_type, record_title, log_line, payload "
                "FROM harvest ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
        out = []
        for r in rows:
            item = {
                "id": r[0], "ts": r[1], "sector": r[2], "event_type": r[3],
                "record_title": r[4], "log_line": r[5],
            }
            try:
                item.update(json.loads(r[6] or "{}"))
            except Exception:
                pass
            out.append(item)
        return out
    except Exception:
        return []


# --------------------------------------------------------------------------
# Ability #46: Live Conductor Intent routing (Living Interface -> agent goal)
# --------------------------------------------------------------------------
CURRENT_LIVING_INTENT = {
    "goal": "Find 500 interior designers in Texas",
    "updated_at": time.time(),
}


def set_living_intent(goal: str) -> dict:
    goal = (goal or "").strip() or "Autonomous Desktop Mission"
    CURRENT_LIVING_INTENT["goal"] = goal
    CURRENT_LIVING_INTENT["updated_at"] = time.time()
    state.broadcast({
        "id": uuid.uuid4().hex[:12],
        "ts": time.time(),
        "sector": "hub",
        "event_type": "DATA_CRYSTALLIZED",
        "record_title": f"Intent Locked: {goal[:36]}",
        "log_line": f"> [CONDUCTOR] New Living Intent materialized: '{goal}'",
        "intent": goal,
        "coordinates": None,
        "metrics": None,
    })
    return {"ok": True, "goal": goal, "updated_at": CURRENT_LIVING_INTENT["updated_at"]}


def handle_living_command(cmd: dict) -> dict:
    """Inbound WebSocket commands from living-ws-adapter.js (Ability #46/#48)."""
    action = str(cmd.get("action", ""))[:48]
    if action == "SET_LIVING_INTENT":
        return set_living_intent(str(cmd.get("intent", ""))[:300])
    if action == "EMP_POPUP_PURGE":
        state.broadcast({
            "id": uuid.uuid4().hex[:12],
            "ts": time.time(),
            "sector": "hub",
            "event_type": "EMP_POPUP_PURGE",
            "record_title": "EMP Purge Pulse",
            "log_line": "> [CONDUCTOR] EMP popup-purge pulse dispatched from Living Interface",
            "coordinates": None, "metrics": None,
        })
        return {"ok": True}
    return {"ok": False, "error": f"unknown action '{action}'"}


async def _ws_broadcast(payload: str):
    conns = list(state.ws_clients)
    if conns:
        try:
            websockets.broadcast(conns, payload)
        except Exception:
            for c in conns:
                try:
                    await c.send(payload)
                except Exception:
                    state.ws_clients.discard(c)


async def _ws_handler(ws):
    state.ws_clients.add(ws)
    state.stats["ws"] = len(state.ws_clients)
    try:
        await ws.send(json.dumps({
            "sector": "hub", "event_type": "CNS_LINKED",
            "log_line": "> [CNS] WebSocket link established",
            "intent": CURRENT_LIVING_INTENT["goal"],
            "coordinates": None, "metrics": None,
        }))
        async for msg in ws:
            # Inbound Living Interface commands (Ability #46): intent dispatch, EMP purge
            if getattr(msg, "type", "text") != "text":
                continue
            try:
                cmd = json.loads(msg)
            except Exception:
                continue
            if isinstance(cmd, dict) and cmd.get("action"):
                try:
                    handle_living_command(cmd)
                except Exception:
                    pass
    finally:
        state.ws_clients.discard(ws)
        state.stats["ws"] = len(state.ws_clients)


def _ws_server_thread():
    async def main():
        async with ws_serve(_ws_handler, WS_HOST, WS_PORT, max_size=2 ** 20):
            state.loop = asyncio.get_running_loop()
            print(f"[CNS] WebSocket bridge listening on ws://{WS_HOST}:{WS_PORT}")
            await asyncio.Future()
    asyncio.run(main())


MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml",
    ".ico": "image/x-icon", ".db": "application/octet-stream",
}


class CNSRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "HojaigaCNS/1.0"

    # ---------- helpers ----------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _log(self, fmt, *args):
        pass  # silence per-request noise; telemetry is printed by the agent itself

    # ---------- static ----------
    def _serve_static(self, path: str):
        rel = unquote(path.split("?", 1)[0].split("#", 1)[0])
        rel = rel.lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        target = (ROOT / rel).resolve()
        if not str(target).startswith(str(ROOT)):
            return self._send_json({"error": "forbidden"}, 403)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return self._send_json({"error": "not found", "path": rel}, 404)
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(target.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    # ---------- GET ----------
    def do_GET(self):
        route = urlparse(self.path).path

        if route == "/api/health":
            return self._send_json({"ok": True, "uptime": round(time.time() - START, 1), **state.stats})
        if route == "/api/events":
            with state.lock:
                return self._send_json(list(state.buffer))
        if route == "/api/intent":
            return self._send_json(CURRENT_LIVING_INTENT)
        if route == "/api/vault":
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            try:
                limit = max(1, min(int(qs.get("limit", ["30"])[0]), 200))
            except Exception:
                limit = 30
            return self._send_json(harvest_read(limit))
        if route == "/api/stream":
            return self._sse_stream()
        if route.startswith("/api/"):
            return self._send_json({"error": "unknown api route"}, 404)
        return self._serve_static(route)

    # ---------- POST /api/emit | /api/intent ----------
    def do_POST(self):
        route = urlparse(self.path).path
        if route not in ("/api/emit", "/api/intent"):
            return self._send_json({"error": "unknown api route"}, 404)
        try:
            length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("payload must be object")
        except Exception as e:
            return self._send_json({"ok": False, "error": str(e)}, 400)

        # Ability #46 HTTP fallback: browser sets the agent's live goal
        if route == "/api/intent":
            return self._send_json(set_living_intent(str(payload.get("intent", ""))))

        def _txt(v, n):
            return str(v)[:n] if v is not None else ""

        event = {
            "id": uuid.uuid4().hex[:12],
            "ts": time.time(),
            "sector": _txt(payload.get("sector", "hub"), 24) or "hub",
            "event_type": _txt(payload.get("event_type", "EVENT"), 48) or "EVENT",
            "log_line": _txt(payload.get("log_line"), 500),
            "record_title": _txt(payload.get("record_title"), 120),
            "coordinates": payload.get("coordinates"),
            "metrics": payload.get("metrics"),
        }
        if payload.get("intent"):
            event["intent"] = str(payload.get("intent"))[:300]
        state.broadcast(event)
        return self._send_json({"ok": True, "id": event["id"]})

    # ---------- SSE ----------
    def _sse_stream(self):
        q: queue.Queue = queue.Queue(maxsize=64)
        state.lock.acquire()
        state.sse_clients.add(q)
        state.stats["sse"] = len(state.sse_clients)
        state.lock.release()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b": cns stream open\n\n")
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=15)
                    self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            state.lock.acquire()
            state.sse_clients.discard(q)
            state.stats["sse"] = len(state.sse_clients)
            state.lock.release()


START = time.time()

if __name__ == "__main__":
    print("=" * 64)
    print(" HOJAIGA // CNS TELEMETRY SERVER")
    print(f" 3D Worlds : http://localhost:{HTTP_PORT}  (index + 3 sector worlds)")
    print(f" WS Bridge : ws://{WS_HOST}:{WS_PORT}" + ("" if WS_AVAILABLE else "  [websockets lib MISSING - SSE only]"))
    print(f" Emit API  : POST http://localhost:{HTTP_PORT}/api/emit")
    print(f" Intent API: GET  http://localhost:{HTTP_PORT}/api/intent   (agent goal)")
    print(f" Vault API : GET  http://localhost:{HTTP_PORT}/api/vault    (SQLite harvest)")
    print(f" SSE Feed  : GET  http://localhost:{HTTP_PORT}/api/stream")
    print(f" Harvest DB: {HARVEST_DB.name}")
    print("=" * 64)

    if WS_AVAILABLE:
        threading.Thread(target=_ws_server_thread, daemon=True).start()
    else:
        print("[CNS] install 'websockets' for WebSocket push (SSE still works)")

    httpd = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), CNSRequestHandler)
    httpd.daemon_threads = True
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[CNS] server stopped")
