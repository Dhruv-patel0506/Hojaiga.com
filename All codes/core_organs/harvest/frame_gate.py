"""
harvest.frame_gate -- is this frame a SOFTWARE UI at all?

Found on the first real clips: about 40% of the scene changes in tutorial videos are cuts between a presenter, a title card, stock footage or a motion graphic and the screen recording. A pair whose
"screen" is a talking head, labelled "click profile", teaches the model to click faces. Classical features (face detection, long-line share, edge density) did not separate presenters from UI and
motion graphics from UI; a local vision-language model does:  qwen2.5vl:3b (already installed in Ollama, no download) classified 21/25 hand-judged real frames correctly, accepted NO presenter or
talking-head frame, and took ~1.7 s per frame. The disagreements were blank canvases (little UI to learn from) and graphics with an inset screenshot.

Policy: precision over recall.  verdict is True (a UI), False (not a UI) or None (UNVERIFIED: the model is not reachable). Callers must treat None as "do not train on this", never as a pass.
Verdicts are cached by the SHA-1 of the image bytes + model + prompt, so a frame is judged once. The model is unloaded after a batch (keep_alive) so the GPU is not held.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
from typing import Dict, Optional, Tuple

PROMPT = ("Is this image a screenshot or screen recording of a computer or phone software application window, with menus, buttons, text fields or other user-interface controls? "
          "Answer NO if it shows a person, a photo, a cartoon or animation, a title card, or a decorative graphic. Answer with exactly one word: YES or NO.")
DEFAULT_MODEL = "qwen2.5vl:3b"


class UIFrameGate:
    def __init__(self, model: str = DEFAULT_MODEL, url: str = "", cache_path: str = "", side: int = 640, timeout_s: float = 90.0, keep_alive: str = "2m", post=None):
        if not url:
            try:
                from core_organs.professor import config as PC
                url = PC.OLLAMA_URL
            except Exception:
                url = os.environ.get("HOJAIGA_PROF_OLLAMA_URL", "http://127.0.0.1:11434")
        self.model, self.url, self.side, self.timeout_s, self.keep_alive = model, url.rstrip("/"), side, timeout_s, keep_alive
        self._post = post                                           # injectable for tests: post(url, json, timeout) -> parsed json
        self.cache_path = cache_path
        self._lock = threading.Lock()
        self._cache: Dict[str, bool] = {}
        self.stats = {"asked": 0, "cached": 0, "unverified": 0}
        self._down_until = 0.0
        if cache_path and os.path.isfile(cache_path):
            try:
                self._cache = json.load(open(cache_path, encoding="utf-8"))
            except Exception:
                self._cache = {}

    def _key(self, data: bytes) -> str:
        return hashlib.sha1(data + self.model.encode() + PROMPT.encode()).hexdigest()

    def _save(self) -> None:
        if self.cache_path:
            tmp = self.cache_path + ".tmp"
            json.dump(self._cache, open(tmp, "w", encoding="utf-8"))
            os.replace(tmp, self.cache_path)

    def check(self, image) -> Tuple[Optional[bool], str]:
        """(verdict, why). image: a path or a PIL image."""
        import time
        from PIL import Image
        try:
            im = Image.open(image).convert("RGB") if isinstance(image, (str, os.PathLike)) else image.convert("RGB")
        except Exception as exc:
            return False, f"unreadable image: {type(exc).__name__}"
        im0 = im.copy()
        im.thumbnail((self.side, self.side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        data = buf.getvalue()
        k = self._key(data)
        with self._lock:
            if k in self._cache:
                self.stats["cached"] += 1
                return self._cache[k], "cached"
        if time.time() < self._down_until:
            self.stats["unverified"] += 1
            return None, "vision model unreachable (backing off)"
        # MEASURED: on some frames qwen2.5vl:3b answers with degenerate tokens ('8888') at the standard size while the same picture, resized, gets a clean YES / NO. An unparseable answer is therefore
        # asked again at two other sizes before the frame is called unverified.
        ans, why = "", ""
        for attempt, size in enumerate((self.side, 448, 896)):
            if attempt:
                alt = im0.copy()
                alt.thumbnail((size, size))
                bb = io.BytesIO()
                alt.save(bb, "JPEG", quality=85)
                payload = bb.getvalue()
            else:
                payload = data
            body = {"model": self.model, "stream": False, "keep_alive": self.keep_alive, "options": {"temperature": 0, "num_predict": 4},
                    "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(payload).decode()]}]}
            try:
                if self._post:
                    resp = self._post(self.url + "/api/chat", body, self.timeout_s)
                else:
                    import requests
                    r = requests.post(self.url + "/api/chat", json=body, timeout=self.timeout_s)
                    r.raise_for_status()
                    resp = r.json()
                ans = str(resp["message"]["content"]).strip().upper()
            except Exception as exc:
                self._down_until = time.time() + 30.0
                self.stats["unverified"] += 1
                return None, f"vision model unreachable: {type(exc).__name__}"
            self.stats["asked"] += 1
            if ans.startswith("YES") or ans.startswith("NO"):
                break
            why = f"unparseable answer {ans[:20]!r}"
        if not (ans.startswith("YES") or ans.startswith("NO")):
            self.stats["unverified"] += 1
            return None, why
        verdict = ans.startswith("YES")
        with self._lock:
            self._cache[k] = verdict
            self._save()
        return verdict, "model"

    def unload(self) -> None:
        """Release the model's VRAM (Ollama keep_alive 0)."""
        try:
            import requests
            requests.post(self.url + "/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=15)
        except Exception:
            pass
