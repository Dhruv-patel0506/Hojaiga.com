"""
professor.vlm -- the Professor's eyes: a bounded client for the LOCAL vision-language model (llama.cpp `llama-server`, OpenAI-compatible).

Design facts measured on this host (RTX 3050 6 GB laptop + 32 GB RAM, Qwen3-VL-8B Q4_K_M) that shape every caller:
  * one control located = ~8 s, a full-screen "list every button" answer = minutes (generation, not seeing, is the cost)
    => the VLM is used for SHORT answers (a label, one box, a numbered list), never as the enumerator of last resort. See sweeper.
  * boxes come back on Qwen3-VL's 0..1000 grid => `grounding.CoordMap` converts (and a calibration scene verifies it once per model).
  * images cost ~ (w/32)*(h/32) tokens, so every picture is fitted to a token budget before it is sent.
No keys, no cloud. Every call has a hard timeout and returns a result object instead of raising.
"""

from __future__ import annotations

import base64
import io
import json
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image

from . import config as CFG
from . import grounding as G
from .schema import Box

try:
    import requests
except Exception:                                                                       # pragma: no cover
    requests = None


@dataclass
class VlmResult:
    ok: bool
    text: str = ""
    seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str = ""
    finish: str = ""
    sent_size: Tuple[int, int] = (0, 0)
    orig_size: Tuple[int, int] = (0, 0)
    json: Any = None

    @property
    def truncated(self) -> bool:
        return self.finish == "length"


@dataclass
class VlmStats:
    calls: int = 0
    failures: int = 0
    seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    gen_tps: float = 0.0                       # smoothed generation speed, tokens/s
    prefill_tps: float = 0.0                   # smoothed prompt-processing speed

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def fit_image(img: Image.Image, budget_tokens: int, patch: int = 32, min_side: int = 0) -> Image.Image:
    """Scale a picture DOWN so it costs at most `budget_tokens` image tokens (never up, unless min_side asks for legibility)."""
    w, h = img.size
    tokens = (w / patch) * (h / patch)
    s = 1.0
    if tokens > budget_tokens:
        s = math.sqrt(budget_tokens / tokens)
    if min_side and min(w, h) * s < min_side:
        s = max(s, min_side / min(w, h))
        if (w * s / patch) * (h * s / patch) > budget_tokens * 1.5:
            s = math.sqrt(budget_tokens * 1.5 / ((w / patch) * (h / patch)))
    if abs(s - 1.0) < 0.02:
        return img
    nw, nh = max(patch, int(round(w * s))), max(patch, int(round(h * s)))
    return img.resize((nw, nh), Image.LANCZOS)


def _encode(img: Image.Image) -> str:
    buf = io.BytesIO()
    big = img.width * img.height > 900 * 900
    if big:
        img.convert("RGB").save(buf, format="JPEG", quality=92)
        mime = "image/jpeg"
    else:
        img.convert("RGB").save(buf, format="PNG", optimize=False)
        mime = "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class VisionClient:
    """One local VLM endpoint. Thread-safe (calls are serialised: the server runs a single slot, and a queued call must not burn its own timeout waiting)."""

    def __init__(self, url: Optional[str] = None, profile: Optional[CFG.ModelProfile] = None):
        self.url = (url or CFG.VISION_URL).rstrip("/")
        self.profile = profile or CFG.active_profile()
        self.stats = VlmStats()
        self._lock = threading.RLock()
        self._health: Dict[str, Any] = {"t": 0.0, "up": False, "model": ""}
        self._map: Optional[G.CoordMap] = None
        self._session = requests.Session() if requests is not None else None

    # ------------------------------------------------------------------------------------------------ health
    def health(self, refresh: bool = False) -> Dict[str, Any]:
        if CFG.OFFLINE or self._session is None:
            return {"up": False, "model": "", "why": "offline"}
        if not refresh and time.time() - self._health["t"] < 6.0:
            return dict(self._health)
        up, model = False, ""
        try:
            r = self._session.get(self.url + "/health", timeout=2.0)
            up = r.status_code == 200 and (r.json().get("status", "ok") in ("ok", "no slot available"))
        except Exception:
            up = False
        if up:
            try:
                r = self._session.get(self.url + "/v1/models", timeout=2.0)
                model = (r.json().get("data") or [{}])[0].get("id", "")
            except Exception:
                model = ""
        self._health = {"t": time.time(), "up": up, "model": model}
        return dict(self._health)

    def available(self) -> bool:
        return bool(self.health().get("up"))

    # --------------------------------------------------------------------------------------------------- chat
    def chat(self, prompt: str, images: Sequence[Image.Image] = (), system: str = "", max_tokens: int = 300, temperature: float = 0.0,
             schema: Optional[Dict[str, Any]] = None, grammar: str = "", timeout: Optional[float] = None, stop: Optional[List[str]] = None,
             image_budget: Optional[int] = None, min_side: int = 0, history: Optional[List[Dict[str, Any]]] = None,
             on_delta: Optional[Any] = None) -> VlmResult:
        """One bounded request. Images are fitted to the token budget; `schema` (JSON schema) or `grammar` (GBNF) constrains the answer.
        `on_delta(text_so_far)` streams the answer as it is generated (the lesson speaks its opening line while the steps are still being written)."""
        t0 = time.time()
        if CFG.OFFLINE or self._session is None:
            return VlmResult(False, error="offline")
        if not self.available():
            return VlmResult(False, error="vision server not reachable at " + self.url)
        prof = self.profile
        budget = image_budget or (prof.image_tokens_budget if prof else 1800)
        patch = prof.patch if prof else 32
        content: List[Dict[str, Any]] = []
        sent = (0, 0)
        orig = (0, 0)
        for im in images:
            orig = im.size if not orig[0] else orig
            fitted = fit_image(im, budget // max(1, len(images)), patch, min_side)
            sent = fitted.size if not sent[0] else sent
            content.append({"type": "image_url", "image_url": {"url": _encode(fitted)}})
        content.append({"type": "text", "text": prompt})
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": content if images else prompt})
        body: Dict[str, Any] = {"model": (prof.name if prof else "vlm"), "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
                                "stream": bool(on_delta), "cache_prompt": True}
        if on_delta:
            body["stream_options"] = {"include_usage": True}
        if stop:
            body["stop"] = stop
        if grammar:
            body["grammar"] = grammar
        elif schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}}
        tmo = timeout or CFG.BUDGETS.vlm_call_s
        res = self._post(body, tmo, on_delta)
        if not res.ok and (schema or grammar) and ("400" in res.error or "grammar" in res.error.lower() or "schema" in res.error.lower()):
            body.pop("grammar", None)
            body.pop("response_format", None)
            res = self._post(body, max(10.0, tmo - (time.time() - t0)), on_delta)
        res.sent_size, res.orig_size = sent, orig
        if schema and res.ok:
            res.json = G.extract_json(res.text)
        return res

    def _post(self, body: Dict[str, Any], timeout: float, on_delta: Optional[Any] = None) -> VlmResult:
        t0 = time.time()
        with self._lock:
            try:
                if on_delta:
                    return self._post_stream(body, timeout, on_delta, t0)
                r = self._session.post(self.url + "/v1/chat/completions", json=body, timeout=timeout)       # type: ignore[union-attr]
                if r.status_code != 200:
                    self._count(time.time() - t0, 0, 0, False)
                    return VlmResult(False, seconds=time.time() - t0, error=f"HTTP {r.status_code}: {r.text[:200]}")
                j = r.json()
                ch = (j.get("choices") or [{}])[0]
                text = (ch.get("message") or {}).get("content") or ""
                u = j.get("usage") or {}
                pt, ct = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
                dt = time.time() - t0
                self._count(dt, pt, ct, True)
                return VlmResult(True, text=text, seconds=dt, prompt_tokens=pt, completion_tokens=ct, finish=ch.get("finish_reason") or "")
            except Exception as exc:
                self._count(time.time() - t0, 0, 0, False)
                self._health["t"] = 0.0
                return VlmResult(False, seconds=time.time() - t0, error=f"{type(exc).__name__}: {str(exc)[:160]}")

    def _post_stream(self, body: Dict[str, Any], timeout: float, on_delta: Any, t0: float) -> VlmResult:
        """Server-sent events: accumulate delta.content, call on_delta(text_so_far) per chunk; the wall-clock cap applies to the whole stream."""
        r = self._session.post(self.url + "/v1/chat/completions", json=body, timeout=(10, 30), stream=True)         # type: ignore[union-attr]
        if r.status_code != 200:
            self._count(time.time() - t0, 0, 0, False)
            return VlmResult(False, seconds=time.time() - t0, error=f"HTTP {r.status_code}: {r.text[:200]}")
        text, finish, pt, ct = "", "", 0, 0
        try:
            for raw in r.iter_lines(decode_unicode=True):
                if time.time() - t0 > timeout:
                    r.close()
                    self._count(time.time() - t0, pt, ct, False)
                    return VlmResult(False, text=text, seconds=time.time() - t0, error="stream timeout", finish="length")
                if not raw or not raw.startswith("data:"):
                    continue
                payload = raw[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    j = json.loads(payload)
                except Exception:
                    continue
                ch = (j.get("choices") or [{}])
                if ch:
                    delta = (ch[0].get("delta") or {}).get("content") or ""
                    if delta:
                        text += delta
                        try:
                            on_delta(text)
                        except Exception:
                            pass
                    finish = ch[0].get("finish_reason") or finish
                u = j.get("usage")
                if u:
                    pt, ct = int(u.get("prompt_tokens") or pt), int(u.get("completion_tokens") or ct)
        finally:
            r.close()
        dt = time.time() - t0
        self._count(dt, pt, ct or max(1, len(text) // 4), True)
        return VlmResult(True, text=text, seconds=dt, prompt_tokens=pt, completion_tokens=ct, finish=finish)

    def _count(self, dt: float, pt: int, ct: int, ok: bool) -> None:
        s = self.stats
        s.calls += 1
        s.seconds += dt
        s.prompt_tokens += pt
        s.completion_tokens += ct
        if not ok:
            s.failures += 1
        if ok and ct >= 8 and dt > 0.2:
            # generation dominates for short prompts; attribute prefill at a rough 6x generation speed so the two estimates stay separable
            gen = ct / max(0.1, dt - pt / max(50.0, (s.prefill_tps or 300.0)))
            s.gen_tps = gen if not s.gen_tps else 0.7 * s.gen_tps + 0.3 * gen
        if ok and pt >= 200 and dt > 0.2 and ct < 20:
            pre = pt / dt
            s.prefill_tps = pre if not s.prefill_tps else 0.7 * s.prefill_tps + 0.3 * pre

    # ----------------------------------------------------------------------------------------------- coordinates
    @property
    def coord_map(self) -> G.CoordMap:
        if self._map is None:
            self._map = self._load_map() or G.default_map(self.profile.coord if self.profile and self.profile.coord != "auto" else "norm1000")
        return self._map

    def _cal_key(self) -> str:
        p = self.profile
        if not p:
            return "none"
        try:
            import os
            st = os.stat(p.gguf)
            return f"{p.name}:{st.st_size}"
        except Exception:
            return p.name

    def _load_map(self) -> Optional[G.CoordMap]:
        try:
            with open(CFG.CALIBRATION_FILE, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            e = d.get(self._cal_key())
            return G.CoordMap.from_dict(e) if e else None
        except Exception:
            return None

    def calibrate(self, force: bool = False) -> Dict[str, Any]:
        """Measure how THIS model writes coordinates (one call on a scene with four known buttons) and remember it. Never trusts a convention blindly."""
        if not force:
            m = self._load_map()
            if m is not None and m.measured:
                self._map = m
                return {"ok": True, "cached": True, "map": m.to_dict()}
        img, truth = G.calibration_scene()
        r = self.chat(G.CALIBRATION_PROMPT, [img], max_tokens=220, timeout=CFG.BUDGETS.vlm_call_s, image_budget=1500)
        if not r.ok:
            return {"ok": False, "error": r.error, "map": self.coord_map.to_dict()}
        m = G.calibrate_from_answer(r.text, truth, r.sent_size or img.size)
        if m is None:
            return {"ok": False, "error": "model did not locate enough buttons", "answer": r.text[:300], "map": self.coord_map.to_dict()}
        self._map = m
        try:
            CFG.ensure_dirs()
            try:
                with open(CFG.CALIBRATION_FILE, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
            except Exception:
                d = {}
            d[self._cal_key()] = m.to_dict()
            with open(CFG.CALIBRATION_FILE, "w", encoding="utf-8") as fh:
                json.dump(d, fh, indent=1)
        except Exception:
            pass
        return {"ok": True, "cached": False, "map": m.to_dict(), "seconds": r.seconds}

    def to_pixels(self, det: G.Detection, result: VlmResult) -> Optional[Box]:
        sent = result.sent_size if result.sent_size[0] else result.orig_size
        orig = result.orig_size if result.orig_size[0] else sent
        if det.box is not None:
            return self.coord_map.box_to_px(det.box, sent, orig)
        if det.point is not None:
            x, y = self.coord_map.point_to_px(det.point, sent, orig)
            return Box(x - 8, y - 8, x + 8, y + 8)
        return None

    # --------------------------------------------------------------------------------------------- vision tasks
    def ground(self, img: Image.Image, query: str, timeout: Optional[float] = None) -> Tuple[Optional[Box], VlmResult]:
        """Where is <query>? One box in the picture's own pixels, or None. ~20 generated tokens, so the only per-step-viable grounding on this hardware."""
        prompt = (f'Locate the user-interface control described as: "{query}". If it is visible, reply ONLY with JSON '
                  '[{"label": "...", "bbox_2d": [x1, y1, x2, y2]}] for that single control; if it is not visible reply [].')
        r = self.chat(prompt, [img], max_tokens=80, timeout=timeout)
        if not r.ok:
            return None, r
        for d in G.parse_detections(r.text):
            b = self.to_pixels(d, r)
            if b is not None:
                return b, r
        return None, r

    def ground_refined(self, img: Image.Image, query: str, timeout: Optional[float] = None, zoom_min: int = 640) -> Tuple[Optional[Box], Dict[str, Any]]:
        """Two-step grounding (coarse on the whole picture, then again on a native-resolution crop around the first answer). Zooming in is what lifts GUI
        grounding accuracy on small targets (published specialists gain several points from it); costs a second ~20-token call, so it is used for the
        fallback path only, never for the bulk scan."""
        coarse, r1 = self.ground(img, query, timeout)
        meta: Dict[str, Any] = {"coarse": coarse.to_list() if coarse else None, "seconds": r1.seconds, "refined": False}
        if coarse is None:
            return None, meta
        side = max(zoom_min, int(max(coarse.w, coarse.h) * 3.0))
        crop_box = Box(coarse.cx - side / 2, coarse.cy - side / 2, coarse.cx + side / 2, coarse.cy + side / 2).clip(img.width, img.height)
        if crop_box.w < 64 or crop_box.h < 64 or (crop_box.w >= img.width * 0.9 and crop_box.h >= img.height * 0.9):
            return coarse, meta
        fine, r2 = self.ground(img.crop(crop_box.ituple()), query, timeout)
        meta["seconds"] += r2.seconds
        if fine is None:
            return coarse, meta
        fine = fine.shift(crop_box.x1, crop_box.y1)
        meta["refined"] = True
        meta["fine"] = fine.to_list()
        # a refinement that jumps far from the first answer is a different control; keep it only when it still overlaps the coarse region's neighbourhood
        if coarse.expand(max(coarse.w, coarse.h)).overlap_frac(fine) < 0.5 and fine.overlap_frac(coarse.expand(max(coarse.w, coarse.h))) < 0.5:
            meta["refined"] = False
            return coarse, meta
        return fine, meta

    def detect(self, img: Image.Image, instruction: str, max_items: int = 30, max_tokens: Optional[int] = None,
               timeout: Optional[float] = None, min_side: int = 0) -> Tuple[List[Tuple[str, Box]], VlmResult]:
        """Boxes (picture pixels) with labels for everything the instruction asks about. Truncated answers keep every complete item."""
        prompt = (f"{instruction}\nReply ONLY with a JSON list of at most {max_items} objects "
                  '{"label": "<visible text or function, 1-3 words>", "bbox_2d": [x1, y1, x2, y2]}.')
        r = self.chat(prompt, [img], max_tokens=max_tokens or min(1400, 28 * max_items + 20), timeout=timeout, min_side=min_side)
        out: List[Tuple[str, Box]] = []
        if not r.ok:
            return out, r
        for d in G.parse_detections(r.text):
            b = self.to_pixels(d, r)
            if b is not None:
                out.append((d.label, b))
        return out, r

    def describe(self, img: Image.Image, question: str, max_tokens: int = 160, timeout: Optional[float] = None) -> VlmResult:
        return self.chat(question, [img], max_tokens=max_tokens, timeout=timeout)


_CLIENT: Optional[VisionClient] = None


def client() -> VisionClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = VisionClient()
    return _CLIENT
