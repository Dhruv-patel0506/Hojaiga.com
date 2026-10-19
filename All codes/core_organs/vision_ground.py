"""
vision_ground -- the picture-reading fallback of the tutor: when the accessibility tree has no control of that name and no repeated-cell grid holds it, the trained Qwen3-VL-2B (the newest adapter) is asked
where it is on the screenshot.

    g = VisionGrounder(engine)
    box = g.locate(screenshot, "Export")        # (x1, y1, x2, y2) in the screenshot's pixels, or None

What the model is given is the SAME kind of input it was trained on - the picture, the numbered elements the scan finds on it, the zoomed strips of dense toolbars - but trimmed to the ~40 elements that matter
for THIS goal (the Top-40 trim): the ones whose label shares words with the goal first, then unlabeled icons, so the prompt stays short and fast. The adapter was trained on full lists: the trim keeps the
same format, only fewer rows (measured effect on accuracy: see the report; not retrained on trimmed lists yet).
"""
from __future__ import annotations

import contextlib
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


def tokens(s: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 1]


def trim_som(som: Dict[str, Any], goal: str, k: int = 60) -> Dict[str, Any]:
    """The Set-of-Marks list cut to the k elements that matter for the goal: label overlap first (best first), then unlabeled / short-label elements (icons), then the rest by position. Ids are kept."""
    els = list(som.get("elements", []))
    want = set(tokens(goal)) - {"click", "the", "button", "tool", "icon", "tab", "menu"}

    def score(e: Dict[str, Any]) -> float:
        lab = e.get("label") or ""
        hit = len(want & set(tokens(lab)))
        icon = 0.3 if len(lab) <= 3 else 0.0
        return hit * 2.0 + icon
    ranked = sorted(els, key=lambda e: (-score(e), e.get("box", (0, 0, 0, 0))[1], e.get("box", (0, 0, 0, 0))[0]))[:k]
    keep = {e["id"] for e in ranked}
    return dict(som, elements=[e for e in els if e["id"] in keep])


PORT = 18765


def vision_python() -> str:
    """The Python that can load Qwen3-VL + the adapter (transformers new enough, peft): this one when it can, else the first installed Python that can."""
    import os
    import subprocess
    import sys
    cands = [sys.executable, os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python313", "python.exe"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312", "python.exe")]
    test = "import peft, transformers; v=tuple(int(x) for x in transformers.__version__.split('.')[:2]); raise SystemExit(0 if v >= (4, 57) else 1)"
    for c in cands:
        if c and os.path.isfile(c):
            with contextlib.suppress(Exception):
                if subprocess.run([c, "-c", test], capture_output=True, timeout=300).returncode == 0:
                    return c
    return ""


def label_elements(image: Any, som: Dict[str, Any], limit: int = 60) -> int:
    """Read the words ON each element (OCR of its own small crop, enlarged) into its `label` when the scan left it empty. Returns how many got a label."""
    n = 0
    with contextlib.suppress(Exception):
        import pytesseract
        for e in som.get("elements", [])[:limit]:
            if (e.get("label") or "").strip():
                continue
            x, y, w, h = e["box"]
            if w < 10 or h < 8:
                continue
            crop = image.crop((max(0, x - 3), max(0, y - 3), x + w + 3, y + h + 3)).convert("L")
            crop = crop.resize((crop.width * 3, crop.height * 3))
            txt = re.sub(r"[^A-Za-z0-9 +&'.-]", "", pytesseract.image_to_string(crop, config="--psm 7")).strip()
            if len(txt) >= 2:
                e["label"] = txt[:40]
                n += 1
    return n


def ocr_match(som: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    """The element whose OCR'd label IS the name (exact, case-insensitive), else the single clear best word-overlap. Cheap and exact for anything with text on it; the model is for what has none."""
    want = tokens(name)
    if not want:
        return None
    exact = [e for e in som.get("elements", []) if (e.get("label") or "").strip().lower() == name.strip().lower()]
    if len(exact) == 1:
        return exact[0]
    scored = []
    for e in som.get("elements", []):
        have = tokens(e.get("label") or "")
        if have and set(have) & set(want):
            scored.append((len(set(have) & set(want)) / max(len(set(have) | set(want)), 1), e))
    scored.sort(key=lambda x: -x[0])
    if scored and scored[0][0] >= 0.66 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
        return scored[0][1]
    return None


class VisionGrounder:
    def __init__(self, engine: Any, app_key: str = "screen", port: int = PORT) -> None:
        self.engine, self.app_key, self.port = engine, app_key, port
        self._ground: Any = None
        self._proc: Any = None
        self.calls = 0
        self.mode = ""
        self.last: Dict[str, Any] = {}

    def _in_process(self) -> bool:
        try:
            import peft  # noqa: F401
            import transformers
            return tuple(int(x) for x in transformers.__version__.split(".")[:2]) >= (4, 57)
        except Exception:
            return False

    def _server(self) -> bool:
        """The model's own process (started once, kept for the session) when this Python cannot hold the model."""
        import json as _j
        import subprocess
        import time
        import urllib.request
        url = f"http://127.0.0.1:{self.port}/ping"
        with contextlib.suppress(Exception):
            if _j.loads(urllib.request.urlopen(url, timeout=2).read().decode()).get("ok"):
                return True
        py = vision_python()
        if not py:
            return False
        import os
        self._proc = subprocess.Popen([py, "-u", "-W", "ignore", os.path.join(os.path.dirname(os.path.abspath(__file__)), "vision_server.py"), "--port", str(self.port)], creationflags=0x08000000)
        for _ in range(60):
            with contextlib.suppress(Exception):
                if _j.loads(urllib.request.urlopen(url, timeout=2).read().decode()).get("ok"):
                    return True
            time.sleep(1.0)
        return False

    def _ask(self, image: Any, som: Dict[str, Any], goal: str, controls: Optional[Sequence[Dict[str, Any]]], hint: str = "", which: str = "default") -> Tuple[Optional[Dict[str, Any]], str]:
        if self._ground is None and self.mode == "":
            self.mode = "in-process" if self._in_process() else ("server" if self._server() else "none")
            if self.mode == "in-process":
                self._ground = self.engine.grounder()
        if self.mode == "in-process":
            return self._ground(image, som, self.app_key, goal, controls, hint=hint)
        if self.mode == "server":
            import json as _j
            import os
            import tempfile
            import urllib.request
            fd, path = tempfile.mkstemp(suffix=".png", prefix="hojaiga_vg_")
            os.close(fd)
            try:
                image.save(path)
                body = _j.dumps({"image": path, "som": {k: v for k, v in som.items() if k in ("elements", "size", "tiers_used", "all_elements")}, "goal": goal, "hint": hint, "which": which, "app_key": self.app_key,
                                 "controls": [{k: v for k, v in c.items() if k in ("name", "type", "box")} for c in (controls or [])]}, default=str).encode("utf-8")
                r = urllib.request.Request(f"http://127.0.0.1:{self.port}/ground", data=body, headers={"Content-Type": "application/json"})
                out = _j.loads(urllib.request.urlopen(r, timeout=300).read().decode())
            finally:
                with contextlib.suppress(Exception):
                    os.remove(path)
            if out.get("error"):
                raise RuntimeError(out["error"])
            self.last_conf = out.get("conf") or {}
            return out.get("action"), out.get("reply", "")
        return None, "no Python on this machine can load the vision model"

    @staticmethod
    def _tau() -> float:
        """The router threshold: HOJAIGA_ROUTER_CONF if set, else the one measured on held-out rows (data/router_tau.json, written from router_calibrate), else 0.85."""
        if os.environ.get("HOJAIGA_ROUTER_CONF"):
            return float(os.environ["HOJAIGA_ROUTER_CONF"])
        try:
            import json as _j
            return float(_j.load(open(os.path.join(os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data")), "router_tau.json"), encoding="utf-8"))["tau"])
        except Exception:
            return 0.85

    CONF_MIN = property(lambda self: self._tau())

    def routed(self, image: Any, full: Dict[str, Any], short: Dict[str, Any], name: str, controls: Any, hint: str) -> Tuple[Optional[Dict[str, Any]], str, str]:
        """The router, cheapest and surest first (the name layers - UIA / OCR - ran before this): (1) the Top-40 adapter, accepted when it is sure of its own answer (geometric-mean token probability >= CONF_MIN) and
        the id it names is one it was shown; (2) otherwise the full-list adapter, which sees every element. When only one adapter exists, it is used as it is."""
        import os as _os
        goal = f"Click the {name}"
        if self.mode == "server" and _os.environ.get("HOJAIGA_ROUTER", "on").lower() not in ("off", "0") and self.CONF_MIN <= 1.0:          # a threshold above 1 means the measurement found no gain: the full-list adapter answers alone
            try:
                act, reply = self._ask(image, short, goal, controls, hint, which="new")
                conf = (getattr(self, "last_conf", {}) or {}).get("conf")
                shown = {e.get("id") for e in short.get("elements", [])}
                if act and act.get("action") == "click" and act.get("target_id") in shown and conf is not None and conf >= self.CONF_MIN:
                    return act, reply, f"top40 (conf {conf})"
                act2, reply2 = self._ask(image, dict(full, elements=full.get("elements", [])), goal, controls, "", which="old")
                return act2, reply2, f"full-list (top40 conf {conf})"
            except Exception:
                pass
        act, reply = self._ask(image, short, goal, controls, hint)
        return act, reply, "single"

    def close(self) -> None:
        with contextlib.suppress(Exception):
            if self._proc is not None:
                self._proc.kill()

    def locate(self, image: Any, name: str, controls: Optional[Sequence[Dict[str, Any]]] = None, k: int = 60) -> Optional[Tuple[float, float, float, float]]:
        from core_organs.agent_executor import element_by_id
        from core_organs.harvest import video_pipeline as VP
        if image is None or not name:
            return None
        self.calls += 1
        som = VP.som_of_frame(image)
        labelled = label_elements(image, som)
        hit = ocr_match(som, name)
        if hit is not None:                                                  # the name is written on the screen: no model call needed
            x, y, w, h = hit["box"]
            self.last = {"layer": "ocr", "elements": len(som.get("elements", [])), "shown": 0, "reply": "", "action": None}
            return (float(x), float(y), float(x + w), float(y + h))
        from core_organs.harvest import prompt_v3 as P3
        short = dict(trim_som(som, name, k=P3.TOP_K), all_elements=som.get("elements", []))                              # the Top-40 the v3 adapter was trained on (the same ids are looked up in the answer below)
        hint = ""
        with contextlib.suppress(Exception):                                 # what the Mind remembers for this goal in this program, as one short line (the training rows carried it half the time)
            pw = self.engine.pathways(f"Click the {name}", self.app_key)
            for pl in pw.get("plans", []):
                if pl.get("steps") and float(pl.get("reliability", 0)) >= 0.4 and pl.get("scope", "own") == "own":
                    hint = re.sub(r"\s+", " ", str(pl["steps"][0]))[:110]
                    break
        named = [{"name": e["label"], "type": "Text", "box": tuple(e["box"])} for e in short.get("elements", []) if e.get("label")]       # the words read off the screen go in as the `Names:` line, as UI Automation's names do in training
        action, reply, route = self.routed(image, som, short, name, list(controls or []) or named, hint)
        self.last = {"layer": "model", "route": route, "elements": len(som.get("elements", [])), "labelled": labelled, "shown": len(short.get("elements", [])), "reply": str(reply)[:120], "action": action,
                     "conf": dict(getattr(self, "last_conf", {}) or {})}
        if not action or action.get("action") != "click":
            return None
        el = element_by_id(short, action.get("target_id"))
        if not el:
            return None
        x, y, w, h = el["box"]
        return (float(x), float(y), float(x + w), float(y + h))

    def ground_fn(self, shot: Any, controls: Optional[Sequence[Dict[str, Any]]] = None) -> Any:
        """A `ground(name) -> box` for micro_beats.plan_beats; `shot` is an image or a function returning the live screenshot."""
        def ground(name: str) -> Optional[Tuple[float, float, float, float]]:
            img = shot() if callable(shot) else shot
            with contextlib.suppress(Exception):
                return self.locate(img, name, controls)
            return None
        return ground


def _bbox_fractions(obj: Dict[str, Any], size: Tuple[int, int]) -> Optional[List[float]]:
    """A box from the model's JSON: 'bbox' / 'bbox_2d' in pixels of the picture it was shown (size = that picture's width, height) or already as fractions; returned as fractions 0-1, or None when it is not a sane box."""
    bb = obj.get("bbox_2d") or obj.get("bbox")
    if not (isinstance(bb, list) and len(bb) == 4 and all(isinstance(v, (int, float)) for v in bb)):
        return None
    W, H = size
    x0, y0, x1, y1 = (float(v) for v in bb)
    if max(x0, y0, x1, y1) > 1.5:                                       # pixels
        x0, x1, y0, y1 = x0 / W, x1 / W, y0 / H, y1 / H
    if not (0 <= x0 < x1 <= 1.02 and 0 <= y0 < y1 <= 1.02):
        return None
    return [round(x0, 4), round(y0, 4), round(min(x1, 1.0), 4), round(min(y1, 1.0), 4)]


def look_at(image: Any, concept: str, port: int = 8081, timeout: float = 240.0) -> Dict[str, Any]:
    """What is on this screen, and is a diagram of `concept` already visible? Asked of the local Qwen2.5-VL-7B (llama.cpp server on `port`, 127.0.0.1 only). Returns {description, diagram_visible, bbox (fractions of the picture) | None,
    seconds, error}. A screen the model cannot read gives diagram_visible None (unknown), never a guess."""
    import base64
    import io
    import json as _j
    import time
    import urllib.request
    out: Dict[str, Any] = {"description": "", "diagram_visible": None, "bbox": None, "seconds": 0.0, "error": ""}
    try:
        im = image.convert("RGB")
        im.thumbnail((896, 896))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
        q = ('Describe in one sentence what is on this screen. Then say whether a diagram or figure that explains "%s" is ALREADY visible on it (a chart, drawing or picture of that concept; a photo, video frame or '
             'page of text about something else is NOT). Reply JSON {"description": "...", "diagram_visible": true|false, "bbox_2d": [x0,y0,x1,y1] in pixels of this picture, or null}' % concept)
        body = {"model": "x", "max_tokens": 200, "temperature": 0.1, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}, {"type": "text", "text": q}]}]}
        t0 = time.time()
        r = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=_j.dumps(body).encode(), headers={"Content-Type": "application/json"})
        text = _j.loads(urllib.request.urlopen(r, timeout=timeout).read().decode())["choices"][0]["message"]["content"]
        out["seconds"] = round(time.time() - t0, 1)
        m = re.search(r"\{.*\}", text, re.S)
        obj = _j.loads(m.group(0)) if m else {}
        out["description"] = str(obj.get("description", text))[:240]
        out["diagram_visible"] = bool(obj["diagram_visible"]) if isinstance(obj.get("diagram_visible"), bool) else None
        out["bbox"] = _bbox_fractions(obj, im.size)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return out


def find_on_screen(image: Any, target: str, port: int = 8081, timeout: float = 240.0) -> Dict[str, Any]:
    """Where is `target` ('the laptop', 'the play button') on this picture? The local Qwen2.5-VL-7B answers with a box in fractions of the picture; {found, bbox, description, seconds, error}. Not found / unreadable -> found False."""
    import base64
    import io
    import json as _j
    import time
    import urllib.request
    out: Dict[str, Any] = {"found": False, "bbox": None, "description": "", "seconds": 0.0, "error": ""}
    try:
        im = image.convert("RGB")
        im.thumbnail((896, 896))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
        q = ('Find "%s" on this screen. Reply ONLY JSON {"found": true|false, "bbox_2d": [x0,y0,x1,y1] in pixels of this picture, tight around it, "description": "what it is, in a few words"}' % target)
        body = {"model": "x", "max_tokens": 120, "temperature": 0.05, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}, {"type": "text", "text": q}]}]}
        t0 = time.time()
        r = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=_j.dumps(body).encode(), headers={"Content-Type": "application/json"})
        text = _j.loads(urllib.request.urlopen(r, timeout=timeout).read().decode())["choices"][0]["message"]["content"]
        out["seconds"] = round(time.time() - t0, 1)
        m = re.search(r"\{.*\}", text, re.S)
        obj = _j.loads(m.group(0)) if m else {}
        out["description"] = str(obj.get("description", ""))[:120]
        fr = _bbox_fractions(obj, im.size)
        if obj.get("found") is True and fr is not None:
            out.update(found=True, bbox=fr)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return out
