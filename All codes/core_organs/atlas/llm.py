"""
atlas.llm -- a bounded client for the LOCAL language model (Ollama on 127.0.0.1). No keys, no cloud.

Used for exactly two jobs, and never as an authority:
  * distilling public documents into claims (every claim must quote its source; atlas.distill verifies the quote)
  * writing narrative / decomposing tasks from facts that are handed in (atlas.architect, atlas.planner verify the output)

Everything has a hard timeout. When the model is not reachable the callers fall back to deterministic code and say so.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

from . import common as C

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

_STATE: Dict[str, Any] = {"model": None, "checked": 0.0, "up": None, "models": []}
_PREFERRED = ("qwen2.5:7b", "qwen2.5", "qwen3", "llama3.1", "llama3", "mistral", "gemma")


def _get(path: str, timeout: float = 3.0):
    if requests is None:
        return None
    try:
        r = requests.get(C.LLM_URL + path, timeout=timeout)
        return r.json() if r.ok else None
    except Exception:
        return None


def status(refresh: bool = False) -> Dict[str, Any]:
    """{'up': bool, 'model': str|None, 'models': [...]} -- cached for 20 s."""
    if not refresh and _STATE["up"] is not None and time.time() - _STATE["checked"] < 20:
        return {"up": _STATE["up"], "model": _STATE["model"], "models": _STATE["models"]}
    tags = _get("/api/tags")
    models = [m.get("name", "") for m in (tags or {}).get("models", [])]
    chat = [m for m in models if "embed" not in m.lower()]
    pick = C.LLM_MODEL or None
    if not pick:
        for want in _PREFERRED:
            for m in chat:
                if m.lower().startswith(want):
                    pick = m
                    break
            if pick:
                break
        pick = pick or (chat[0] if chat else None)
    _STATE.update(up=bool(tags is not None and pick), model=pick, models=models, checked=time.time())
    return {"up": _STATE["up"], "model": pick, "models": models}


def available() -> bool:
    return bool(status().get("up"))


def _extract_json(text: str) -> Optional[Any]:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    try:
        return json.loads(t)
    except Exception:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        a, b = t.find(open_c), t.rfind(close_c)
        if a >= 0 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except Exception:
                continue
    return None


def chat(system: str, user: str, *, timeout: float = 90.0, max_tokens: int = 900, json_mode: bool = True,
         temperature: float = 0.0, num_ctx: int = 8192) -> Dict[str, Any]:
    """One bounded chat call. Returns {'ok', 'text', 'json', 'seconds', 'model', 'error'}; never raises."""
    t0 = time.time()
    st = status()
    if requests is None or not st["up"]:
        return {"ok": False, "error": "local model not reachable", "text": "", "json": None, "seconds": 0.0, "model": None}
    body = {"model": st["model"], "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": num_ctx, "seed": 7}}
    if json_mode:
        body["format"] = "json"
    try:
        r = requests.post(C.LLM_URL + "/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
        text = (r.json().get("message") or {}).get("content", "")
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}", "text": "", "json": None,
                "seconds": round(time.time() - t0, 2), "model": st["model"]}
    data = _extract_json(text) if json_mode else None
    return {"ok": (data is not None) if json_mode else bool(text), "text": text, "json": data,
            "seconds": round(time.time() - t0, 2), "model": st["model"], "error": "" if (data is not None or not json_mode) else "model did not return JSON"}


def embed(texts: List[str], timeout: float = 30.0) -> Optional[List[List[float]]]:
    """Embeddings from the local embedding model, or None when unavailable."""
    if requests is None or not texts:
        return None
    st = status()
    if not st["up"] or not any(C.EMBED_MODEL.split(":")[0] in m for m in st["models"]):
        return None
    try:
        r = requests.post(C.LLM_URL + "/api/embed", json={"model": C.EMBED_MODEL, "input": texts}, timeout=timeout)
        r.raise_for_status()
        return r.json().get("embeddings")
    except Exception:
        return None
