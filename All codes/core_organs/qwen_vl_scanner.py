"""
qwen_vl_scanner.py -- EXPERIMENTAL vision tier backed by the local Qwen-VL llama.cpp precision
server (:8081). The loaded weights are auto-selected by start_hojaiga.bat: Qwen3-VL-8B once
downloaded, else the current Qwen2.5-VL-7B (server-agnostic OpenAI endpoint, so this client
works with either). The payload "model" label is ignored by a single-model llama-server.

Gated: only used when HOJAIGA_QWEN_VL=1. OmniParser stays the primary vision tier unless
benchmark_vision.py shows this one measurably wins on the same screens.
Free + local: talks to the llama-server already started by start_hojaiga.bat
(default http://127.0.0.1:8081, OpenAI-compatible /v1/chat/completions). No cloud.
"""

import base64
import io
import json
import os
import re
import time
import urllib.request
from typing import Any, Dict, List, Tuple

ENDPOINT = os.environ.get("HOJAIGA_QWEN_VL_URL", "http://127.0.0.1:8081") + "/v1/chat/completions"
TIMEOUT_S = float(os.environ.get("HOJAIGA_QWEN_VL_TIMEOUT_S", "60"))
MAX_SIDE = int(os.environ.get("HOJAIGA_QWEN_VL_MAX_SIDE", "1024"))

_PROMPT = (
    "You are a UI element detector. List every clickable or editable control visible in this "
    "screenshot (buttons, menu items, tabs, text fields, icons with labels). Return ONLY a JSON "
    'array: [{"name": "<visible label>", "bbox": [x1, y1, x2, y2]}] using pixel coordinates of '
    "THIS image. At most 40 items."
)


def available() -> bool:
    try:
        urllib.request.urlopen(ENDPOINT.rsplit("/v1/", 1)[0] + "/health", timeout=2)
        return True
    except Exception:
        return False


def parse_image(img) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """img: PIL.Image. Returns (elements[{name,bbox}] in ORIGINAL image pixels, meta{ms,raw_len,error})."""
    t0 = time.perf_counter()
    meta: Dict[str, Any] = {"ms": 0, "error": ""}
    w, h = img.size
    scale = min(1.0, MAX_SIDE / max(w, h))
    send = img.resize((int(w * scale), int(h * scale))) if scale < 1.0 else img
    buf = io.BytesIO()
    send.convert("RGB").save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    payload = {
        "model": "qwen3-vl", "temperature": 0.0, "max_tokens": 1500,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            {"type": "text", "text": _PROMPT}]}],
    }
    try:
        req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        meta["raw_len"] = len(content)
        m = re.search(r"\[.*\]", content, re.DOTALL)
        items = json.loads(m.group(0)) if m else []
    except Exception as exc:  # noqa: BLE001
        meta["error"] = f"{type(exc).__name__}: {exc}"
        items = []
    out = []
    inv = 1.0 / scale
    for it in items:
        try:
            x1, y1, x2, y2 = [float(v) * inv for v in it["bbox"]]
            if x2 > x1 and y2 > y1:
                out.append({"name": str(it.get("name", "")).strip(), "bbox": (int(x1), int(y1), int(x2), int(y2))})
        except Exception:
            continue
    meta["ms"] = int((time.perf_counter() - t0) * 1000)
    return out, meta


# ---------------------------------------------------------------------------
# Targeted grounding: "where is the <control>?" -> one box (cheap: ~20 output tokens).
# A full-screen parse costs hundreds of tokens (minutes at ~2 tok/s on a 6 GB laptop GPU);
# locating ONE control is the only per-step-viable use of a 7B VLM here.
# ---------------------------------------------------------------------------

OLLAMA_URL = os.environ.get("HOJAIGA_OLLAMA_URL", "http://127.0.0.1:11434") + "/api/chat"


def locate(img, description: str, backend: str = "llamacpp", timeout_s: float = 90.0) -> Tuple[Any, Dict[str, Any]]:
    """Return (bbox|None in ORIGINAL image pixels, meta{ms,error,backend}).
    backend: 'llamacpp' (llama-server :8081) or 'ollama:<model>' (e.g. ollama:qwen2.5vl:3b)."""
    t0 = time.perf_counter()
    meta: Dict[str, Any] = {"backend": backend, "error": "", "ms": 0}
    w, h = img.size
    scale = min(1.0, MAX_SIDE / max(w, h))
    send = img.resize((int(w * scale), int(h * scale))) if scale < 1.0 else img
    buf = io.BytesIO()
    send.convert("RGB").save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    q = (f"Locate the UI control '{description}'. Reply with ONLY its bounding box as "
         "[x1, y1, x2, y2] in pixels of this image, or [] if it is not visible.")
    try:
        if backend.startswith("ollama:"):
            payload = {"model": backend.split(":", 1)[1], "stream": False, "options": {"temperature": 0, "num_predict": 40},
                       "messages": [{"role": "user", "content": q, "images": [b64]}]}
            url = OLLAMA_URL
        else:
            payload = {"model": "qwen2.5-vl", "temperature": 0, "max_tokens": 40,
                       "messages": [{"role": "user", "content": [
                           {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
                           {"type": "text", "text": q}]}]}
            url = ENDPOINT
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = (body.get("message", {}).get("content") if "message" in body
                   else body["choices"][0]["message"]["content"]) or ""
        m = re.search(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]", content)
        box = None
        if m:
            x1, y1, x2, y2 = [float(v) / scale for v in m.groups()]
            if x2 > x1 and y2 > y1:
                box = (int(x1), int(y1), int(x2), int(y2))
    except Exception as exc:  # noqa: BLE001
        meta["error"] = f"{type(exc).__name__}: {exc}"
        box = None
    meta["ms"] = int((time.perf_counter() - t0) * 1000)
    return box, meta
