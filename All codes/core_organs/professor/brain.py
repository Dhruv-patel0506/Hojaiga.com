"""
professor.brain -- the Professor's mind for TEXT: planning a lesson, explaining a control, speaking in teacher voice.

Two local backends can answer text prompts:
  vision   the resident Qwen3-VL on the llama.cpp server (one model in memory, nothing else competing for the 6 GB GPU)
  ollama   a text model (qwen2.5:7b, measured ~1.9 s per short decision on this machine)
`auto` (default) uses the resident vision model whenever its server is up and falls back to Ollama only when it is not (two resident models would
fight for 6 GB of VRAM); `fastest` times both with a 40-token probe (remembered ten minutes) and takes the quicker; HOJAIGA_PROF_BRAIN=vision|ollama pins one. With neither reachable, callers get ok=False and use deterministic code.
Generation can STREAM: the teacher speaks the lesson's opening line while the steps are still being written, which is what makes a few-tokens-per-second
local model feel responsive. The brain never invents UI facts: the teacher hands it a numbered inventory and validates every id it cites.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from . import config as CFG
from . import grounding as G
from .vlm import VisionClient, client as _vlm_client

try:
    import requests
except Exception:                                                                       # pragma: no cover
    requests = None

_PREFERRED = ("qwen2.5:7b", "qwen2.5", "qwen3", "llama3.1", "llama3", "mistral", "gemma")


@dataclass
class BrainResult:
    ok: bool
    text: str = ""
    json: Any = None
    backend: str = ""
    model: str = ""
    seconds: float = 0.0
    error: str = ""
    tokens: int = 0


class Brain:
    def __init__(self, vlm: Optional[VisionClient] = None):
        self.vlm = vlm or _vlm_client()
        self.mode = os.environ.get("HOJAIGA_PROF_BRAIN", "auto")            # auto | vision | ollama
        self._ollama: Dict[str, Any] = {"t": 0.0, "up": False, "model": ""}
        self._pick: Dict[str, Any] = {"t": 0.0, "backend": "", "tps": {}}

    # ---------------------------------------------------------------------------------------------- backends
    def ollama_status(self, refresh: bool = False) -> Dict[str, Any]:
        if requests is None or CFG.OFFLINE:
            return {"up": False, "model": ""}
        if not refresh and time.time() - self._ollama["t"] < 20:
            return dict(self._ollama)
        up, pick = False, ""
        try:
            tags = requests.get(CFG.OLLAMA_URL + "/api/tags", timeout=2).json().get("models", [])
            names = [m.get("name", "") for m in tags if "embed" not in m.get("name", "").lower()]
            pick = CFG.OLLAMA_TEXT_MODEL or ""
            if not pick:
                for want in _PREFERRED:
                    pick = next((n for n in names if n.lower().startswith(want)), "")
                    if pick:
                        break
                pick = pick or (names[0] if names else "")
            up = bool(pick)
        except Exception:
            up = False
        self._ollama = {"t": time.time(), "up": up, "model": pick}
        return dict(self._ollama)

    def candidates(self) -> List[str]:
        out = []
        if self.mode in ("auto", "fastest", "vision") and self.vlm.available():
            out.append("vision")
        if self.mode in ("auto", "fastest", "ollama") and (self.mode != "auto" or not out) and self.ollama_status().get("up"):
            out.append("ollama")                       # `auto` only falls back to Ollama when the vision server is down: two resident models would fight for 6 GB of VRAM
        return out

    def backend(self) -> str:
        """Which backend answers right now. With both up and mode=auto, the faster measured one (probe cached 10 min)."""
        c = self.candidates()
        if not c:
            return ""
        if len(c) == 1 or self.mode != "fastest":
            return c[0]
        if time.time() - self._pick["t"] > 600 or self._pick["backend"] not in c:
            tps: Dict[str, float] = {}
            for be in c:
                r = self._run(be, "You are terse.", "Count from one to twenty in words, separated by commas.", None, 40, 0.0, 60.0, None, None)
                if r.ok and r.seconds > 0:
                    tps[be] = (r.tokens or max(1, len(r.text) // 4)) / r.seconds
            self._pick = {"t": time.time(), "backend": max(tps, key=lambda k: tps[k]) if tps else c[0], "tps": tps}
        return self._pick["backend"]

    def available(self) -> bool:
        return bool(self.candidates())

    # ------------------------------------------------------------------------------------------------ generate
    def generate(self, system: str, user: str, *, schema: Optional[Dict[str, Any]] = None, max_tokens: int = 600, temperature: float = 0.2,
                 timeout: Optional[float] = None, history: Optional[List[Dict[str, Any]]] = None,
                 on_text: Optional[Callable[[str], None]] = None) -> BrainResult:
        be = self.backend()
        if not be:
            return BrainResult(False, error="no language model reachable (vision server and Ollama are both down)")
        return self._run(be, system, user, schema, max_tokens, temperature, timeout or CFG.BUDGETS.text_call_s, history, on_text)

    def _run(self, be: str, system: str, user: str, schema: Optional[Dict[str, Any]], max_tokens: int, temperature: float, timeout: float,
             history: Optional[List[Dict[str, Any]]], on_text: Optional[Callable[[str], None]]) -> BrainResult:
        t0 = time.time()
        if be == "vision":
            r = self.vlm.chat(user, [], system=system, max_tokens=max_tokens, temperature=temperature, schema=schema, timeout=timeout, history=history,
                              on_delta=on_text)
            data = r.json if r.json is not None else (G.extract_json(r.text) if (schema and r.ok) else None)
            ok = r.ok and (bool(r.text) if not schema else data is not None)
            return BrainResult(ok, r.text, data, "vision", (self.vlm.profile.name if self.vlm.profile else ""), r.seconds,
                               r.error or ("" if ok else "model did not return JSON"), r.completion_tokens)
        st = self.ollama_status()
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": system}] + list(history or []) + [{"role": "user", "content": user}]
        body: Dict[str, Any] = {"model": st["model"], "stream": bool(on_text), "messages": msgs,
                                "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 8192, "seed": 7}}
        if schema:
            body["format"] = schema
        try:
            if on_text:
                text, ct = "", 0
                with requests.post(CFG.OLLAMA_URL + "/api/chat", json=body, timeout=(10, 30), stream=True) as r:          # type: ignore[union-attr]
                    r.raise_for_status()
                    for line in r.iter_lines():
                        if time.time() - t0 > timeout:
                            break
                        if not line:
                            continue
                        j = json.loads(line)
                        piece = (j.get("message") or {}).get("content", "")
                        if piece:
                            text += piece
                            try:
                                on_text(text)
                            except Exception:
                                pass
                        if j.get("done"):
                            ct = int(j.get("eval_count") or 0)
                            break
            else:
                r = requests.post(CFG.OLLAMA_URL + "/api/chat", json=body, timeout=timeout)                                # type: ignore[union-attr]
                r.raise_for_status()
                jj = r.json()
                text, ct = (jj.get("message") or {}).get("content", ""), int(jj.get("eval_count") or 0)
        except Exception as exc:
            return BrainResult(False, backend="ollama", model=st["model"], seconds=time.time() - t0, error=f"{type(exc).__name__}: {str(exc)[:160]}")
        data = G.extract_json(text) if schema else None
        ok = bool(text) and (data is not None or not schema)
        return BrainResult(ok, text, data, "ollama", st["model"], time.time() - t0, "" if ok else "model did not return JSON", ct)


_BRAIN: Optional[Brain] = None


def brain() -> Brain:
    global _BRAIN
    if _BRAIN is None:
        _BRAIN = Brain()
    return _BRAIN
