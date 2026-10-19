"""
vision_server -- the trained Qwen3-VL-2B (+ the newest adapter) behind a tiny local HTTP door, for callers whose Python cannot load it.

The project environment pins transformers 4.51.3 (the OmniParser / Florence-2 stack); Qwen3-VL needs the newer one that the training environment has. So the model lives in the process of whichever Python has
the right libraries, and the project process asks it:

    python vision_server.py --port 8765        # started by vision_ground.VisionGrounder when it is needed

    POST /ground  {"image": "<png path>", "som": {...}, "goal": "Click the Export", "app_key": "x", "controls": [...]}
               -> {"action": {...} | null, "reply": "...", "seconds": 4.2}
    GET  /ping    -> {"ok": true, "adapter": "<dir>", "loaded": true | false}

Local only (127.0.0.1); the image is a file the caller wrote; nothing leaves the machine.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join("D:" + os.sep, "new_automation", "All codes"))

_STATE = {"g": None, "adapter": "", "which": ""}


def adapters():
    """{'new': (dir, prompt_version), 'old': (dir, prompt_version)}: the Top-40 adapter and the full-list adapter, from runs/ADAPTER_CHOICE.json (alternatives) or the newest runs."""
    from core_organs import app_teaching_automation as ATA
    d, v = ATA.newest_adapter()
    out = {"default": (d, v)}
    with __import__("contextlib").suppress(Exception):
        c = json.load(open(os.path.join(os.path.dirname(os.path.dirname(d)), "ADAPTER_CHOICE.json"), encoding="utf-8"))
        out["old"] = (c["adapter"], int(c["prompt_version"]))
        out["new"] = (c["alternatives"]["v3"], 3)
    return out


def grounder(which: str = "default"):
    """The requested adapter, loaded on first use; asking for the other one unloads the first (the card holds one at a time)."""
    from core_organs import agent_executor as AE
    table = adapters()
    which = which if which in table else "default"
    if _STATE["g"] is None or _STATE["which"] != which:
        if _STATE["g"] is not None:
            _STATE["g"].unload()
        d, v = table[which]
        _STATE.update(adapter=d, which=which, g=AE.AdapterGrounder(d, prompt_version=v))
    return _STATE["g"]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        b = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send({"ok": True, "adapter": _STATE["adapter"], "loaded": _STATE["g"] is not None})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(n).decode("utf-8"))
            from PIL import Image
            img = Image.open(req["image"]).convert("RGB")
            t0 = time.time()
            g = grounder(req.get("which", "default"))
            action, reply = (g(img, req["som"], req.get("app_key", "screen"), req["goal"], req.get("controls"), hint=req.get("hint", "")) if getattr(g, "prompt_version", 1) == 3 else g(img, req["som"], req.get("app_key", "screen"), req["goal"], req.get("controls")))
            self._send({"action": action, "reply": reply, "seconds": round(time.time() - t0, 2), "conf": getattr(g, "last", {}), "which": _STATE["which"], "prompt_version": getattr(g, "prompt_version", 1)})
        except Exception as exc:
            self._send({"error": f"{type(exc).__name__}: {str(exc)[:200]}"}, 500)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18765)
    a = ap.parse_args()
    HTTPServer(("127.0.0.1", a.port), H).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
