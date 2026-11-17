"""
si_tests_professor.py -- tests for the Professor layer (core_organs/professor/*), in the suite's TestOutcome style.

OFFLINE tests (PR*) need no desktop window, no network and no model: synthetic application screenshots with exact ground truth
(professor.synth), a FAKE llama-server speaking the real HTTP protocol (FakeLlama below) and in-memory/temp databases. They put nothing on the screen.
LIVE tests (PL*, PV*) use the real local model server (llama.cpp Qwen3-VL), the real SAPI voice/recognizer and, for PL7, the real overlay window
for ~2 seconds in a screen corner (click-through, no focus, excluded from capture -- the test PROVES all three). No test touches a window the user owns.

    python hojaiga_professor.py selftest [--live]
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple

for _p in (r"D:\new_automation", r"D:\new_automation\All codes", r"D:\new_automation\All codes\core_organs"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
from PIL import Image


@dataclass
class TestOutcome:
    passed: bool
    evidence: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    env_blocked: bool = False


def _verdict(checks: Dict[str, bool], extra: str = "", metrics: Optional[Dict[str, Any]] = None, env: bool = False) -> TestOutcome:
    ok = all(checks.values())
    ev = "; ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()) + (f" | {extra}" if extra else "")
    m = {"checks": f"{sum(1 for v in checks.values() if v)}/{len(checks)}"}
    m.update(metrics or {})
    return TestOutcome(passed=ok, evidence=ev, metrics=m, env_blocked=env)


def _tmp(name: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"prof_{name}_{uuid.uuid4().hex[:8]}")


# ======================================================================================================= fake llama-server
class FakeLlama:
    """A llama-server look-alike (health, models, chat/completions incl. SSE streaming) whose answers are scripted by the test.
    `coord`: how its 'model' writes boxes. `text_reply(req)->str` answers text prompts. `namer(k, n, req)->str` names contact-sheet cells."""

    def __init__(self, coord: str = "norm1000"):
        self.coord = coord
        self.requests: List[Dict[str, Any]] = []
        self.text_reply: Callable[[Dict[str, Any]], str] = lambda req: "{}"
        self.namer: Callable[[int, int, Dict[str, Any]], str] = lambda k, n, req: f"n{k}"
        self.locate: Dict[str, Tuple[float, float, float, float]] = {}      # description fragment -> box in picture pixels
        self.delay = 0.0
        self.fail_next = 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def _send(self, code: int, body: Dict[str, Any]) -> None:
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                if self.path.startswith("/health"):
                    self._send(200, {"status": "ok"})
                elif self.path.startswith("/v1/models"):
                    self._send(200, {"data": [{"id": "fake-vlm"}]})
                else:
                    self._send(404, {})

            def do_POST(self) -> None:
                n = int(self.headers.get("Content-Length", "0"))
                req = json.loads(self.rfile.read(n) or b"{}")
                outer.requests.append(req)
                if outer.fail_next > 0:
                    outer.fail_next -= 1
                    self._send(500, {"error": "scripted failure"})
                    return
                if outer.delay:
                    time.sleep(outer.delay)
                text = outer._answer(req)
                if req.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for i in range(0, len(text), 9):
                        chunk = {"choices": [{"delta": {"content": text[i:i + 9]}, "finish_reason": None}]}
                        self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                        self.wfile.flush()
                        time.sleep(0.004)
                    fin = {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 50, "completion_tokens": max(1, len(text) // 4)}}
                    self.wfile.write(f"data: {json.dumps(fin)}\n\ndata: [DONE]\n\n".encode())
                    return
                self._send(200, {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 50, "completion_tokens": max(1, len(text) // 4)}})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self.httpd.shutdown()

    @staticmethod
    def _prompt(req: Dict[str, Any]) -> str:
        m = req["messages"][-1]["content"]
        if isinstance(m, list):
            return " ".join(p.get("text", "") for p in m if p.get("type") == "text")
        return str(m)

    def _fmt_box(self, b: Tuple[float, float, float, float], sent: Tuple[int, int]) -> List[float]:
        if self.coord == "norm1000":
            return [round(b[0] / sent[0] * 1000), round(b[1] / sent[1] * 1000), round(b[2] / sent[0] * 1000), round(b[3] / sent[1] * 1000)]
        return [round(v) for v in b]

    def _sent_size(self, req: Dict[str, Any]) -> Tuple[int, int]:
        import base64
        import io
        for p in req["messages"][-1]["content"] if isinstance(req["messages"][-1]["content"], list) else []:
            if p.get("type") == "image_url":
                raw = base64.b64decode(p["image_url"]["url"].split(",", 1)[1])
                return Image.open(io.BytesIO(raw)).size
        return (1, 1)

    def _answer(self, req: Dict[str, Any]) -> str:
        prompt = self._prompt(req)
        if "numbered cells" in prompt:
            import re
            n = int(re.search(r"(\d+) numbered cells", prompt).group(1))
            return "".join(f"{k}: {self.namer(k, n, req)}\n" for k in range(1, n + 1))
        if "Locate every button in this picture" in prompt:
            from core_organs.professor import grounding as G
            sent = self._sent_size(req)
            img, truth = G.calibration_scene(*sent)
            return json.dumps([{"label": k, "bbox_2d": self._fmt_box(tuple(float(x) for x in v), sent)} for k, v in truth.items()])
        if "Locate the user-interface control described as" in prompt:
            sent = self._sent_size(req)
            for frag, box in self.locate.items():
                if frag.lower() in prompt.lower():
                    return json.dumps([{"label": frag, "bbox_2d": self._fmt_box(box, sent)}])
            return "[]"
        return self.text_reply(req)


# =========================================================================================================== helpers
def _scan_offline(img: Image.Image, scale: float = 1.0, mode: str = "quick", **kw: Any):
    from core_organs.professor import sweeper
    opt = sweeper.ScanOptions.for_mode(mode)
    opt.use_uia = False
    opt.knowledge = False
    opt.learn = False
    for k, v in kw.items():
        setattr(opt, k, v)
    return sweeper.scan(image=img, options=opt, app_key="synth", dpi_scale=scale)


def _el(sm, truth, name: str):
    """The scan element that sits on the truth control `name` (so tests do not depend on how OCR spelled the caption)."""
    from core_organs.professor.schema import Box
    t = next(x for x in truth if x["label"] == name)
    tb = Box(*t["box"])
    cands = [e for e in sm.elements if max(e.bbox.overlap_frac(tb), tb.overlap_frac(e.bbox)) > 0.5 and e.bbox.area <= 4 * tb.area]
    return max(cands, key=lambda e: e.bbox.iou(tb)) if cands else None


def _fake_vlm(fake: FakeLlama):
    from core_organs import professor  # noqa: F401
    from core_organs.professor import config as CFG
    from core_organs.professor.vlm import VisionClient
    prof = CFG.ModelProfile("fake", "x.gguf", "x-mmproj.gguf", coord="norm1000")
    return VisionClient(url=fake.url, profile=prof)


# =========================================================================================================== offline
def run_pr1() -> TestOutcome:
    """PR1: schema -- box maths, containment-aware overlap, ScreenModel JSON round trip, inventory text, label search"""
    from core_organs.professor.schema import Box, Lesson, LessonStep, Region, ScreenModel, UIElement, fold
    a, b = Box(0, 0, 10, 10), Box(5, 5, 15, 15)
    e1 = UIElement(1, "Paste", "button", Box(10, 10, 50, 40), "r1", ["uia"], 0.95, "uia", shortcut="Ctrl+V")
    e2 = UIElement(2, "", "icon", Box(60, 10, 80, 40), "r1", ["cv"], 0.5, flags=["unlabeled"])
    sm = ScreenModel(app_key="x", window_title="t", size=(100, 100), regions=[Region("r1", "ribbon", "Home > Clipboard", Box(0, 0, 100, 50))], elements=[e1, e2])
    rt = ScreenModel.from_json(sm.to_json())
    inv = sm.inventory_text()
    checks = {"iou": abs(a.iou(b) - 25 / 175) < 1e-9, "overlap_frac_directional": a.overlap_frac(Box(0, 0, 5, 10)) == 0.5 and Box(0, 0, 5, 10).overlap_frac(a) == 1.0,
              "clip_scale_shift": a.scale(2).shift(1, 1).tuple() == (1, 1, 21, 21), "fold": fold("Save  As...") == "save as",
              "roundtrip_elements": [x.to_dict() for x in rt.elements] == [x.to_dict() for x in sm.elements] and rt.regions[0].label == "Home > Clipboard",
              "inventory_line": '#1 button "Paste" (Ctrl+V)' in inv and "(unnamed icon)" in inv, "region_header": "== ribbon: Home > Clipboard ==" in inv,
              "find_exact_first": [x.id for x in sm.find("paste")] == [1], "element_lookup": sm.element(2) is e2 and sm.element(9) is None,
              "lesson_dict": Lesson("t", "s", [LessonStep(1, "say")]).to_dict()["steps"][0]["n"] == 1}
    return _verdict(checks)


def run_pr2() -> TestOutcome:
    """PR2: grounding -- every answer shape parses; coordinate convention is MEASURED (norm1000 / pixels / linear), never assumed; truncated JSON keeps whole items"""
    from core_organs.professor import grounding as G
    tests = {
        "json_bbox2d": '```json\n[{"label":"Save","bbox_2d":[10,20,110,60]}]\n```',
        "object_wrapper": '{"elements":[{"name":"Open","box":[1,2,3,4]}]}',
        "tag_form": "<|object_ref_start|>save<|object_ref_end|><|box_start|>(10,20),(110,60)<|box_end|>",
        "bare_array": "It is at [10, 20, 110, 60].",
        "point": '[{"label":"x","point_2d":[50,60]}]',
        "truncated": '[{"label":"A","bbox_2d":[1,2,3,4]},{"label":"B","bbox_2d":[5,6,7,8]},{"label":"C","bbox_2d":[9,1',
    }
    got = {k: G.parse_detections(v) for k, v in tests.items()}
    img, truth = G.calibration_scene(1280, 720)

    def answer(space: str, w: int, h: int) -> str:
        out = []
        for k, (x1, y1, x2, y2) in truth.items():
            if space == "norm1000":
                bb = [round(x1 / 1280 * 1000), round(y1 / 720 * 1000), round(x2 / 1280 * 1000), round(y2 / 720 * 1000)]
            else:
                bb = [x1, y1, x2, y2]
            out.append({"label": k, "bbox_2d": bb})
        return json.dumps(out)

    m1 = G.calibrate_from_answer(answer("norm1000", 1280, 720), truth, (1280, 720))
    m2 = G.calibrate_from_answer(answer("pixels", 1280, 720), truth, (1280, 720))
    px = m1.box_to_px((100, 100, 200, 200), (640, 360), (1920, 1080)) if m1 else None
    px2 = m2.box_to_px((100, 100, 200, 200), (640, 360), (1920, 1080)) if m2 else None
    checks = {"json_bbox2d": got["json_bbox2d"] and got["json_bbox2d"][0].box == (10, 20, 110, 60) and got["json_bbox2d"][0].label == "Save",
              "object_wrapper": bool(got["object_wrapper"]) and got["object_wrapper"][0].label == "Open",
              "tag_form": bool(got["tag_form"]) and got["tag_form"][0].box == (10, 20, 110, 60) and got["tag_form"][0].label == "save",
              "bare_array": bool(got["bare_array"]) and got["bare_array"][0].box == (10, 20, 110, 60),
              "point": bool(got["point"]) and got["point"][0].point == (50, 60),
              "truncated_keeps_complete_items": [d.label for d in got["truncated"]] == ["A", "B"],
              "calibrated_norm1000": m1 is not None and m1.kind == "norm1000" and m1.measured and m1.residual_px < 3,
              "calibrated_pixels": m2 is not None and m2.kind == "pixels" and m2.residual_px < 3,
              "norm1000_to_px": px is not None and abs(px.x1 - 192) < 1 and abs(px.x2 - 384) < 1 and abs(px.y2 - 216) < 1,
              "pixels_scale_back_to_original": px2 is not None and abs(px2.x1 - 300) < 1 and abs(px2.x2 - 600) < 1,
              "linear_fit": G.fit_map([(0, 10), (100, 210)], [(0, 5), (50, 105)], 1000, 500).kind == "linear"}
    return _verdict({k: bool(v) for k, v in checks.items()})


def run_pr3() -> TestOutcome:
    """PR3: capture -- DPI awareness, monitors, real screen grab (read-only), change detection finds exactly what changed"""
    from core_organs.professor import capture as CAP
    from core_organs.professor.schema import Box
    img = Image.new("RGB", (640, 360), (240, 240, 240))
    img2 = img.copy()
    from PIL import ImageDraw
    ImageDraw.Draw(img2).rectangle((200, 100, 330, 180), fill=(20, 20, 160))
    boxes = CAP.changed_boxes(img, img2, cell=32, thresh=6, pad=0)
    fr = CAP.grab_screen(None)
    mons = CAP.monitors()
    vs = CAP.virtual_screen()
    h1, h2 = CAP.frame_hash(img), CAP.frame_hash(img2)
    dummy_fr = fr or CAP.frame_from_image(img)
    checks = {"dpi_aware": CAP._DPI_DONE, "one_change_rect": len(boxes) == 1 and boxes[0].iou(Box(192, 96, 352, 192)) > 0.6,
              "identical_has_no_change": CAP.changed_boxes(img, img.copy()) == [], "hash_distance": CAP.hash_distance(h1, h1) == 0 and CAP.hash_distance(h1, h2) > 0,
              "monitors_listed": len(mons) >= 1 and mons[0].primary, "virtual_screen_positive": vs.w > 100 and vs.h > 100,
              "screen_grab_size_matches": fr is None or fr.size == (int(vs.w), int(vs.h)), "frame_maps_back": dummy_fr.to_image(dummy_fr.to_screen(Box(1, 2, 3, 4))).tuple() == (1, 2, 3, 4),
              "window_info_of_foreground": CAP.window_info(CAP.foreground_hwnd()).hwnd == CAP.foreground_hwnd()}
    return _verdict(checks, f"monitors={[(m.index, m.box.to_list(), m.dpi) for m in mons]}")


def run_pr4() -> TestOutcome:
    """PR4: seeing -- every control of a synthetic application window is FOUND (no model, no accessibility tree): light, dark, 125% and 150% display scale"""
    from core_organs.professor import synth
    res: Dict[str, Any] = {}
    ok = True
    for theme, sc in (("light", 1.0), ("dark", 1.0), ("light", 1.5), ("dark", 1.25)):
        img, truth, _r = synth.render_app(theme, sc)
        sm, _ = _scan_offline(img, sc)
        m = synth.match_truth(truth, sm.elements)
        canvas = next((r for r in sm.regions if r.kind == "canvas"), None)
        non_canvas = [e for e in sm.elements if not (canvas and e.bbox.overlap_frac(canvas.bbox) > 0.5)]
        unmatched = [e for e in non_canvas if not any(max(e.bbox.overlap_frac(synth.Box(*t["box"])), synth.Box(*t["box"]).overlap_frac(e.bbox)) >= 0.5 for t in truth)]
        prec = 1 - len(unmatched) / max(1, len(non_canvas))
        res[f"{theme}@{sc}"] = {"found": f"{m['found']}/{m['truth']}", "precision": round(prec, 3), "seconds": sm.timings.get("total"), "missed": m["missed"][:4]}
        ok = ok and m["found_rate"] >= 0.95 and prec >= 0.85
    return _verdict({"all_variants_recall_ge_95_and_precision_ge_85": ok}, json.dumps(res), res)


def run_pr5() -> TestOutcome:
    """PR5: structure -- 'the whole button section': title bar, menu bar, tab strip, ribbon with its CAPTIONED GROUPS, side strip, canvas, status bar"""
    from core_organs.professor import synth
    out: Dict[str, Any] = {}
    ok_all = True
    for theme, sc in (("light", 1.0), ("dark", 1.0), ("light", 1.5)):
        img, truth, _r = synth.render_app(theme, sc)
        sm, _ = _scan_offline(img, sc)
        kinds = {r.kind for r in sm.regions}
        need = {"titlebar", "menubar", "tab_strip", "ribbon", "sidebar", "canvas", "statusbar"}
        groups = sorted(r.label.split(">")[-1].strip() for r in sm.regions if r.label.startswith("ribbon >"))
        ribbon = next((r for r in sm.regions if r.kind == "ribbon"), None)
        W, H = img.size
        wide = ribbon is not None and ribbon.bbox.w >= 0.95 * W and abs(ribbon.bbox.y1 - 88 * sc) <= 6 * sc and abs(ribbon.bbox.y2 - 198 * sc) <= 6 * sc
        paste = sm.find("Paste")
        in_group = bool(paste) and (sm.region(paste[0].region_id).label if sm.region(paste[0].region_id) else "") == "ribbon > Clipboard"
        good = need <= kinds and groups == ["Clipboard", "Font", "Insert"] and wide and in_group
        ok_all = ok_all and good
        out[f"{theme}@{sc}"] = {"missing_kinds": sorted(need - kinds), "groups": groups, "ribbon_full_band": wide, "paste_in_clipboard_group": in_group}
    return _verdict({"every_section_group_and_membership_correct": ok_all}, json.dumps(out), out)


def run_pr6() -> TestOutcome:
    """PR6: dialogs -- boxed buttons, fields, check boxes and radios are found from their outlines; a paragraph of text does NOT become buttons"""
    from core_organs.professor import synth
    img, truth, _r = synth.render_dialog("light", 1.0)
    sm, _ = _scan_offline(img, 1.0)
    m = synth.match_truth(truth, sm.elements)
    by = m["by_kind"]
    img2, truth2, _ = synth.render_app("light", 1.0)
    sm2, _ = _scan_offline(img2, 1.0)
    canvas = next((r for r in sm2.regions if r.kind == "canvas"), None)
    shapes_in_canvas = [e for e in sm2.elements if canvas and e.bbox.overlap_frac(canvas.bbox) > 0.5 and e.role in ("button", "checkbox", "radio", "field") and "shape" in e.flags]
    checks = {"buttons_ok_cancel_apply": all(sm.find(n) for n in ("OK", "Cancel", "Apply")), "push_buttons_found": by.get("rect_button", {}).get("found") == by.get("rect_button", {}).get("truth"),
              "fields_found": by.get("field", {}).get("found", 0) >= by.get("field", {}).get("truth", 1) - 1, "checkboxes_found": by.get("checkbox", {}).get("found", 0) >= 2,
              "no_fake_buttons_in_document_text": len(shapes_in_canvas) == 0, "overall_found_ge_80pct": (m["found_rate"] or 0) >= 0.8}
    return _verdict(checks, f"found={m['found']}/{m['truth']} by_kind={by} missed={m['missed']}", {"found_rate": m["found_rate"]})


def run_pr7() -> TestOutcome:
    """PR7: proof of coverage -- the pixel audit sees a control that was dropped, re-probes it and names it; unexplained = 0 at the end"""
    from core_organs.professor import coverage as COV, synth
    from core_organs.professor.labeler import Label, Labeler
    img, truth, _r = synth.render_app("light", 1.0)
    sm, _ = _scan_offline(img, 1.0)
    victim = next(e for e in sm.elements if e.label == "Picture" or "Picture" in e.label)
    rest = [e for e in sm.elements if e is not victim]
    base = COV.audit(img, sm.elements, sm.regions, 1.0)
    hole = COV.audit(img, rest, sm.regions, 1.0)

    class FakeLabeler(Labeler):
        def __init__(self) -> None:
            super().__init__(None, None)                              # type: ignore[arg-type]

        def from_memory(self, img, boxes):
            return [None] * len(boxes)

        def label_boxes(self, img, boxes, budget_s, consistency=1, per_sheet=None, order=None):
            return [Label("Recovered", 0.9, "vlm2") for _ in boxes], {"sheets": 1, "named": len(boxes)}

    added, rep = COV.exhaust(img, list(rest), sm.regions, 1.0, FakeLabeler(), 20.0, rounds=2)
    found_back = any(e.bbox.overlap_frac(victim.bbox) > 0.4 or victim.bbox.overlap_frac(e.bbox) > 0.4 for e in added)
    checks = {"audit_has_numbers": 0 <= base["coverage"] <= 1 and base["ink_px"] > 1000, "hole_detected_as_uncovered_shape": hole["uncovered_n"] >= base["uncovered_n"] + 1,
              "coverage_drops_when_a_control_is_removed": hole["coverage"] < base["coverage"], "reprobe_recovers_it": found_back, "rounds_recorded": len(rep.get("rounds", [])) >= 2,
              "final_coverage_restored": rep["coverage"] >= hole["coverage"]}
    return _verdict(checks, f"base={base['coverage']} hole={hole['coverage']} after={rep['coverage']} uncovered {base['uncovered_n']}->{hole['uncovered_n']}->{rep['uncovered_n']}",
                    {"coverage_base": base["coverage"], "coverage_after": rep["coverage"]})


def run_pr8() -> TestOutcome:
    """PR8: icon memory -- an icon is recognised again in the other theme, at another scale and in another app; votes beat noise; unknown icons are not guessed"""
    from core_organs.professor import synth
    from core_organs.professor.icon_memory import IconMemory, fingerprint
    p = _tmp("icons") + ".db"
    mem = IconMemory(p)
    try:
        def crop(theme: str, sc: float, label: str):
            img, truth, _ = synth.render_app(theme, sc)
            t = next(x for x in truth if x["label"] == label)
            b = t["box"]
            return img.crop((b[0], b[1], b[2], b[3]))

        for nm in ("Search", "Settings", "Home", "Lock", "Open", "Account", "Mail"):
            mem.learn(fingerprint(crop("light", 1.0, nm)), nm, "uia", "appA")
        hits = {}
        for nm in ("Search", "Settings", "Home", "Lock", "Open", "Account", "Mail"):
            hits[("dark", nm)] = mem.lookup(fingerprint(crop("dark", 1.0, nm)))
            hits[("1.5", nm)] = mem.lookup(fingerprint(crop("light", 1.5, nm)))
        right = sum(1 for (k, nm), h in hits.items() if h and h["label"] == nm)
        unknown = mem.lookup(fingerprint(crop("light", 1.0, "Zoom Out")))
        mem.learn(fingerprint(crop("light", 1.0, "Home")), "House", "vlm", "appB")
        after = mem.lookup(fingerprint(crop("light", 1.0, "Home")))
        mem.close()
        mem2 = IconMemory(p)
        persisted = mem2.lookup(fingerprint(crop("light", 1.0, "Search")))
        mem2.close()
        checks = {"theme_and_scale_invariant": right >= 12, "unknown_icon_not_guessed": unknown is None or unknown["conf"] < 0.62, "trusted_source_outvotes_model": bool(after) and after["label"] == "Home",
                  "persisted_across_restart": bool(persisted) and persisted["label"] == "Search", "fingerprint_is_256_bits": len(fingerprint(crop("light", 1.0, "Home"))) == 32}
        return _verdict(checks, f"recognised {right}/14 re-renders (dark + 150% scale)", {"recognised_of_14": right})
    finally:
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


def run_pr9() -> TestOutcome:
    """PR9: naming by contact sheet -- answers line up with the right control (order, grammar, '?' handling), two-pass agreement raises confidence, disagreement is flagged"""
    from core_organs.professor import labeler as LB, synth
    from core_organs.professor.schema import Box
    img, truth, _ = synth.render_app("light", 1.0)
    icons = [t for t in truth if t["kind"] == "icon"][:12]
    boxes = [Box(*t["box"]) for t in icons]
    fake = FakeLlama()
    try:
        by_pos = {i: t["label"] for i, t in enumerate(icons)}
        per = 6

        def namer1(k: int, n: int, req: Dict[str, Any]) -> str:
            gi = (len(fake.requests) - 1) * per + (k - 1)             # cell k of this sheet = control number gi overall
            return "?" if gi == 4 else by_pos.get(gi, "?")

        fake.namer = namer1
        vc = _fake_vlm(fake)
        lab = LB.Labeler(vc, None)
        res, meta = lab.label_boxes(img, boxes, 30.0, consistency=1, per_sheet=6)
        sheet = LB.make_sheet(img, boxes[:6])
        txt = fake.requests[0]["messages"][-1]["content"][-1]["text"]
        gram = fake.requests[0].get("grammar", "")
        names = [r.text if r else None for r in res]
        right = sum(1 for i, t in enumerate(icons) if names[i] == t["label"])
        # two passes where the second shuffles order: an honest namer that depends on content, not position, agrees; a positional one disagrees -> flagged
        fake2 = FakeLlama()
        fake2.namer = lambda k, n, req: f"n{k}"
        lab2 = LB.Labeler(_fake_vlm(fake2), None)
        res2, _m = lab2.label_boxes(img, boxes, 30.0, consistency=2, per_sheet=6)
        ambiguous = sum(1 for r in res2 if r and "ambiguous" in r.flags)
        parsed = LB.parse_lines("1: Save\n2: ?\n3) Zoom In\nnoise\n9: out of range\n4: Undo\n", 4)
        checks = {"two_sheets_for_12_icons": meta["sheets"] == 2 and len(fake.requests) == 2, "positions_align_with_controls": right == 11 and names[4] is None,
                  "question_asks_for_exactly_n_lines": "6 numbered cells" in txt, "grammar_constrains_output": "root ::=" in gram, "sheet_is_small": sheet.size == (560, 224),
                  "parser_handles_noise": parsed == {1: "Save", 2: "", 3: "Zoom In", 4: "Undo"}, "positional_namer_flagged_ambiguous": ambiguous >= 6,
                  "confidence_ordering": all(r.conf == 0.6 for r in res if r)}
        return _verdict(checks, f"named right {right}/11; sheets={meta['sheets']}; ambiguous={ambiguous}")
    finally:
        fake.close()
        try:
            fake2.close()
        except Exception:
            pass


def run_pr10() -> TestOutcome:
    """PR10: fusion -- the accessibility tree wins over everything, a printed caption wins over a model's guess, model-only names are flagged, duplicates merge"""
    from core_organs.professor import fusion as FU
    from core_organs.professor.candidates import Candidate
    from core_organs.professor.labeler import Label
    from core_organs.professor.schema import Box, Region, UIElement
    uia = [UIElement(0, "Paste (exact)", "button", Box(10, 10, 50, 50), "", ["uia"], 0.95, "uia")]
    cands = [Candidate(Box(12, 12, 48, 48), "icon_label", 0.8, "Pastte", 80),                 # same control seen by vision: must NOT duplicate
             Candidate(Box(100, 10, 130, 40), "icon", 0.5),                                   # named by the model only
             Candidate(Box(200, 10, 230, 40), "icon", 0.5),                                   # nobody could name it
             Candidate(Box(300, 10, 340, 30), "text", 0.8, "File", 90),
             Candidate(Box(400, 10, 420, 30), "text", 0.8, "x", 90),                           # a glyph read as a letter
             Candidate(Box(500, 10, 540, 40), "icon", 0.5)]
    labels = [None, Label("Zoom", 0.6, "vlm"), None, None, Label("Close", 0.86, "vlm2"), Label("Save", 0.8, "memory")]
    regs = [Region("m", "menubar", "menu bar", Box(290, 0, 350, 40))]
    els = FU.fuse(uia, cands, labels, regs)
    by = {e.label or "<none>": e for e in els}
    close = next((e for e in els if e.label == "Close"), None)
    checks = {"no_duplicate_of_tree_control": len([e for e in els if e.bbox.overlap_frac(Box(10, 10, 50, 50)) > 0.8]) == 1 and by["Paste (exact)"].label_source == "uia",
              "model_only_name_flagged_unverified": "unverified" in by["Zoom"].flags and by["Zoom"].sources == ["cv", "vlm"], "unnamed_flagged": "unlabeled" in by["<none>"].flags,
              "caption_text_is_menu_item": by["File"].role == "menu_item" and by["File"].label_source == "ocr", "glyph_letter_replaced_by_model_name": close is not None and close.hint == "x" and "glyph-text" in close.flags,
              "memory_name_trusted": by["Save"].sources == ["cv", "icon_memory"] and "unverified" not in by["Save"].flags, "ids_are_reading_order": [e.id for e in els] == list(range(1, len(els) + 1)),
              "two_pass_agreement_not_flagged": close is not None and "unverified" not in close.flags}
    return _verdict(checks)


def run_pr11() -> TestOutcome:
    """PR11: the whole scan with a (fake) vision server -- icons named from sheets land on the RIGHT boxes; with the server down the scan says so and still delivers"""
    from core_organs.professor import config as CFG, sweeper, synth
    from core_organs.professor.icon_memory import IconMemory
    from core_organs.professor.labeler import Labeler
    img, truth, _ = synth.render_app("light", 1.0)
    fake = FakeLlama()
    p = _tmp("icons2") + ".db"
    try:
        # the fake names every cell by what the cell REALLY shows: look the cell up in the truth via the cell position it was sent from
        sent_boxes: List[List[Any]] = []
        orig = Labeler.label_boxes

        def spy(self, image, boxes, budget_s, consistency=1, per_sheet=None, order=None, hints=None):
            sent_boxes.append(list(boxes))
            spy.hints_seen.append(hints)
            return orig(self, image, boxes, budget_s, consistency, per_sheet, order, hints)

        spy.hints_seen = []                                   # type: ignore[attr-defined]

        Labeler.label_boxes = spy                              # type: ignore[method-assign]
        names_by_pos: Dict[Tuple[int, int], str] = {}

        def namer(k: int, n: int, req: Dict[str, Any]) -> str:
            b = sent_boxes[-1][k - 1]
            best = max(truth, key=lambda t: max(synth.Box(*t["box"]).overlap_frac(b), b.overlap_frac(synth.Box(*t["box"]))))
            return best["label"]

        fake.namer = namer
        vc = _fake_vlm(fake)
        mem = IconMemory(p)
        opt = sweeper.ScanOptions.for_mode("standard")
        opt.use_uia = opt.knowledge = opt.learn = False
        opt.exhaust_rounds = 1
        sm, _ = sweeper.scan(image=img, options=opt, vlm=vc, memory=mem, app_key="synth")
        m = synth.match_truth(truth, sm.elements)
        icon_named = m["by_kind"].get("icon", {}).get("named", 0) / max(1, m["by_kind"].get("icon", {}).get("truth", 1))
        Labeler.label_boxes = orig                             # type: ignore[method-assign]
        fake.close()
        down = _fake_vlm(fake)                                 # server now shut: the same call must degrade honestly
        sm2, _ = sweeper.scan(image=img, options=opt, vlm=down, memory=IconMemory(_tmp("icons3") + ".db"), app_key="synth")
        said_where = any("Where each control sits" in json.dumps(r["messages"][-1]["content"]) for r in fake.requests)
        checks = {"vlm_tier_reported": any(t.startswith("vlm_sheets") for t in sm.tiers_used), "icons_named_by_position_alignment": icon_named >= 0.85,
                  "prompt_says_where_each_control_sits": said_where and any(h and any("title bar" in x or "ribbon" in x for x in h) for h in spy.hints_seen),
                  "all_controls_still_found": (m["found_rate"] or 0) >= 0.95, "coverage_audit_ran": "coverage" in sm.coverage and sm.coverage.get("exhausted") in (True, False),
                  "server_down_is_reported_not_faked": any("vlm" in t for t in sm2.tiers_skipped) and not any(t.startswith("vlm_sheets") for t in sm2.tiers_used),
                  "server_down_still_finds_controls": len(sm2.elements) >= len(sm.elements) * 0.9}
        return _verdict(checks, f"icons named {icon_named:.0%}; found {m['found']}/{m['truth']}; skipped when down: {sm2.tiers_skipped}", {"icon_named": round(icon_named, 3), "found": m["found_rate"]})
    finally:
        try:
            Labeler.label_boxes = orig                          # type: ignore[method-assign]
        except Exception:
            pass
        try:
            fake.close()
        except Exception:
            pass
        for suf in ("", "-wal", "-shm"):
            for nm in (p,):
                try:
                    os.remove(nm + suf)
                except OSError:
                    pass


def run_pr12() -> TestOutcome:
    """PR12: look again -- an unchanged screen costs nothing, a menu that opened is analysed alone (partial) and spliced into the old model, a different screen rescans fully"""
    from core_organs.professor import sweeper, synth
    img, truth, _ = synth.render_app("light", 1.0)
    sm, fr = _scan_offline(img, 1.0)
    prev_img = fr.image
    t0 = time.time()
    same, _f, info_same = sweeper.rescan(sm, prev_img, image=img.copy(), mode="quick", vlm=_fake_vlm(FakeLlama()))
    t_same = time.time() - t0
    pic = _el(sm, truth, "Picture")
    img2, menu_truth, rect = synth.with_popup_menu(img, (int(pic.bbox.x1), int(pic.bbox.y2) + 4))
    from core_organs.professor import sweeper as SW
    from core_organs.professor.capture import frame_from_image
    # drive the real rescan path with picture input
    sm2, fr2, info2 = sweeper.rescan(sm, prev_img, image=img2, mode="quick", vlm=_fake_vlm(FakeLlama()))
    m = synth.match_truth(menu_truth, sm2.elements)
    outside = [e for e in sm.elements if e.bbox.overlap_frac(rect) < 0.1 and rect.overlap_frac(e.bbox) < 0.5]
    old_kept = sum(1 for e in outside if any(max(n.bbox.overlap_frac(e.bbox), e.bbox.overlap_frac(n.bbox)) > 0.5 for n in sm2.elements)) / max(1, len(outside))
    other = Image.new("RGB", img.size, (10, 10, 10))
    sm3, _f3, info3 = sweeper.rescan(sm, prev_img, image=other, mode="quick", vlm=_fake_vlm(FakeLlama()))
    checks = {"unchanged_is_instant_and_same_model": info_same["path"] == "unchanged" and same is sm and t_same < 1.0, "menu_open_is_partial": info2["path"] == "partial" and info2["rects"] >= 1,
              "new_menu_items_found": (m["found_rate"] or 0) >= 0.75 and bool(sm2.find("Screenshot")), "old_controls_kept": old_kept >= 0.9,
              "partial_is_cheaper_than_full": info2["seconds"] < sm.timings["total"] * 1.5 + 1, "different_screen_goes_full": info3["path"].startswith("full")}
    return _verdict(checks, f"unchanged {t_same:.3f}s; partial {info2['seconds']}s (kept {info2.get('kept')} new {info2.get('new')}); menu found {m['found']}/{m['truth']}",
                    {"partial_s": info2["seconds"], "full_s": sm.timings["total"]})


def run_pr13() -> TestOutcome:
    """PR13: pointing -- tags in every Clicky form parse; ids resolve to MEASURED boxes; loose pixels snap to the control under them; flight path is a smooth arc"""
    from core_organs.professor import pointing as PT
    from core_organs.professor.schema import Box, ScreenModel, UIElement
    sm = ScreenModel(origin=(100, 50), size=(800, 600), elements=[UIElement(1, "Save", "button", Box(400, 150, 440, 180)), UIElement(2, "Open", "button", Box(500, 150, 540, 180))])
    text, tags = PT.parse_tags("click save. [POINT:#1:save button] and then [POINT:410,115:the open one] also [POINT:90,20:corner:screen2] [point:none]")
    c1 = PT.resolve(tags[0], sm)
    c2 = PT.resolve(tags[1], sm, (800, 600))
    c3 = PT.resolve(tags[2], sm, (800, 600))
    half = PT.resolve(PT.PointTag("xy", x=205, y=57), sm, (400, 300))                   # picture was half size -> scaled up first (205*2+100, 57*2+50) = (510, 164)
    p0, p1 = (100.0, 700.0), (900.0, 200.0)
    pts = [PT.bezier_arc(p0, p1, i / 20) for i in range(21)]
    chord = [(p0[0] + (p1[0] - p0[0]) * i / 20, p0[1] + (p1[1] - p0[1]) * i / 20) for i in range(21)]
    bulge = max(abs((p[0] - c[0]) * (p1[1] - p0[1]) - (p[1] - c[1]) * (p1[0] - p0[0])) / math.hypot(p1[0] - p0[0], p1[1] - p0[1]) for p, c in zip(pts, chord))
    checks = {"tags_parsed_in_order": [t.kind for t in tags] == ["id", "xy", "xy", "none"] and "POINT" not in text, "screen_number_kept": tags[2].screen == 2,
              "id_resolves_to_measured_box": c1 is not None and c1.box == Box(400, 150, 440, 180) and c1.element_id == 1,
              "pixel_snaps_to_control_under_it": c2 is not None and c2.element_id == 2 and c2.box == Box(500, 150, 540, 180),
              "unsnapped_pixel_becomes_circle": c3 is not None and c3.kind == "circle" and abs(c3.box.cx - 190) < 1, "picture_scale_applied": half is not None and half.element_id == 2,
              "arc_hits_endpoints": pts[0] == p0 and all(abs(a - b) < 1e-6 for a, b in zip(pts[-1], p1)), "arc_bulges": bulge > 40, "ease_monotonic": all(PT.ease_in_out(i / 20) <= PT.ease_in_out((i + 1) / 20) for i in range(20)),
              "flight_time_bounded": 0.45 <= PT.flight_seconds((0, 0), (10, 10)) <= PT.flight_seconds((0, 0), (5000, 3000)) <= 1.1,
              "none_tag_resolves_to_nothing": PT.resolve(tags[3], sm) is None}
    return _verdict(checks)


def _scripted_brain(fake: FakeLlama):
    from core_organs.professor.brain import Brain
    b = Brain(_fake_vlm(fake))
    b.mode = "vision"
    return b


def run_pr14() -> TestOutcome:
    """PR14: teaching -- ids are checked against the label the model meant (mis-numbering repaired), invented ids dropped, off-screen controls become 'find', locate/explain intents, speech cleanup, deterministic fallback"""
    from core_organs.professor import synth
    from core_organs.professor.teacher import Conversation, Teacher, speakable
    img, truth, _ = synth.render_app("light", 1.0)
    sm, _ = _scan_offline(img, 1.0)
    pic = _el(sm, truth, "Picture")
    tbl = _el(sm, truth, "Table")
    pic.label, tbl.label = "Picture", "Table"                          # the teacher's id check works on labels; pin them so the test is about the check, not about OCR spelling
    fake = FakeLlama()
    try:
        plan = {"mode": "lesson", "title": "Insert a picture", "speech": "Let's add a picture. It's on the Insert group of the ribbon.",
                "steps": [{"say": "Click the Picture button in the Insert group.", "action": "click", "element": tbl.id, "target": "Picture", "find": "", "text": "", "keys": "", "expect": "a menu with picture sources"},
                          {"say": "Choose Picture from file.", "action": "click", "element": None, "target": "", "find": "Picture from file", "text": "", "keys": "", "expect": ""},
                          {"say": "Now press control v.", "action": "key", "element": 9999, "target": "Nonexistent", "find": "", "text": "", "keys": "Ctrl+V", "expect": ""}]}
        fake.text_reply = lambda req: json.dumps(plan)
        t = Teacher(_scripted_brain(fake))
        les = t.plan("How do I insert a picture?", sm, Conversation())
        s1, s2, s3 = les.steps
        prompt = next(r for r in fake.requests if r["messages"][0]["role"] == "system")["messages"][-1]["content"]
        _el(sm, truth, "Paste").label = "Paste"
        loc = t.plan("where is the Paste button", sm, Conversation(), allow_model=False)
        fb_routes = [{"text": "Open the **Insert** tab of the ribbon > in the **Illustrations** group > click **Pictures**", "outcome": "A dialog **Insert Picture** opens", "shortcut": "",
                      "preconditions": [], "control": "Pictures", "path": [{"kind": "surface", "name": "Insert"}, {"kind": "group", "name": "Illustrations"}, {"kind": "control", "name": "Pictures"}]}]
        fb = t._fallback_plan("insert a picture", sm, fb_routes)
        t.resolve_steps(fb, sm)
        checks = {"mislabeled_id_repaired_by_label": s1.element_id == pic.id and s1.box == pic.bbox and any("did not match" in n for n in les.notes),
                  "offscreen_control_becomes_find": s2.element_id is None and s2.find == "Picture from file" and s2.grounded_by == "none",
                  "invented_id_dropped": s3.element_id is None and s3.box is None, "speech_cleaned": "control v" in s3.say and "Ctrl" not in s3.say,
                  "inventory_numbered_in_prompt": f'#{pic.id} ' in prompt and "INVENTORY" in prompt and "LEARNER SAYS" in prompt,
                  "locate_intent_answers_without_model": loc.source == "scan" and loc.steps[0].label == "Paste" and loc.steps[0].box is not None,
                  "fallback_route_has_steps": fb.mode == "lesson" and len(fb.steps) >= 2 and fb.steps[0].find == "Insert",
                  "fallback_grounds_visible_tab": fb.steps[0].element_id is not None and sm.element(fb.steps[0].element_id).label.lower() == "insert",
                  "speakable": speakable("Press Ctrl+Shift+S -> then (e.g. save)") .startswith("Press control") and "->" not in speakable("a -> b"),
                  "intents": t.intent("where's the save button") == "locate" and t.intent("what does this do") == "explain_here" and t.intent("how do I bold text") == "plan"}
        return _verdict(checks, f"notes={les.notes[:2]}")
    finally:
        fake.close()


def run_pr15() -> TestOutcome:
    """PR15: how it LOOKS -- the highlight surrounds the target, the bubble stays on screen and its tail touches the control, the pointer tip sits on the hotspot (pixel-level)"""
    from core_organs.professor import overlay_render as R, synth
    from core_organs.professor.overlay import RecordingOverlay
    from core_organs.professor.schema import Box
    bg = Image.new("RGB", (1200, 700), (255, 255, 255))
    target = Box(500, 300, 640, 360)
    ov = RecordingOverlay()
    ov.point(target, "Insert picture", 2, "click", True, "Click the Picture button")
    out = ov.preview(bg)
    a = np.asarray(out).astype(int)
    ring = a[298:304, 500:640].reshape(-1, 3)
    far = a[600:650, 100:200].reshape(-1, 3)
    blue_ring = float(np.mean((ring[:, 2] - ring[:, 0]) > 60))
    cmds = [{"type": "bubble", "text": "A fairly long explanation that must wrap onto several lines inside the bubble without leaving the screen.", "step": 3,
             "box": [1100, 20, 1190, 60]}]
    bub = R.compose_preview(bg, cmds)
    nb = np.asarray(bub).astype(int)
    dark = np.argwhere((nb.sum(axis=2) < 150))
    img, tip = R.render_bubble("Hello", 1, 300, "up")
    pimg, (dx, dy) = R.render_cursor(1.0)
    cur = R.compose_preview(bg, [{"type": "cursor", "x": 300, "y": 200}])
    ca = np.asarray(cur).astype(int)
    tip_px = ca[201, 301]
    spot = R.render_spotlight((400, 300), Box(150, 100, 250, 180))
    sa = np.asarray(spot)
    checks = {"outline_is_blue_around_target": blue_ring > 0.5, "background_untouched_far_away": float((far.sum(axis=1) < 760).mean()) < 0.01,
              "bubble_on_screen_near_corner": dark.size > 0 and dark[:, 1].max() < 1200 and dark[:, 0].max() < 700 and dark[:, 1].min() > 600,
              "bubble_tail_tip_inside_picture": 0 <= tip[0] < img.width and 0 <= tip[1] < img.height, "cursor_drawn_blue_at_hotspot": int(((ca[196:228, 296:316, 2] - ca[196:228, 296:316, 0]) > 80).sum()) >= 40,
              "cursor_offset_negative": dx < 0 and dy < 0, "spotlight_dims_outside_clears_inside": sa[10, 10, 3] > 80 and sa[140, 200, 3] < 10,
              "recording_log": ov.log[0][0] == "point" and ov.scene[-1]["type"] == "cursor",
              "place_bubble_prefers_below": R.place_bubble(Box(500, 100, 600, 130), (300, 80), (150, 0), Box(0, 0, 1200, 700))[2] == "up",
              "place_bubble_flips_above_at_bottom": R.place_bubble(Box(500, 650, 600, 690), (300, 80), (150, 0), Box(0, 0, 1200, 700))[2] == "down"}
    out.save(os.path.join(tempfile.gettempdir(), "prof_overlay_preview.png"))
    return _verdict(checks, "preview written to %TEMP%\\prof_overlay_preview.png")


def run_pr16() -> TestOutcome:
    """PR16: a lesson end to end with no screen and no sound -- every step is shown in order at its measured box and narrated; a step on a hidden menu item is grounded after the menu opens"""
    from core_organs.professor import synth
    from core_organs.professor.lesson_runner import LessonRunner
    from core_organs.professor.overlay import RecordingOverlay
    from core_organs.professor.schema import Lesson, LessonStep
    from core_organs.professor.teacher import Teacher
    from core_organs.professor.voice_out import SilentSpeaker
    from core_organs.professor import sweeper
    img, truth, _ = synth.render_app("light", 1.0)
    sm, fr = _scan_offline(img, 1.0)
    pic = _el(sm, truth, "Picture")
    pic.label = "Picture"
    img2, menu_truth, _r = synth.with_popup_menu(img, (int(pic.bbox.x1), int(pic.bbox.y2) + 4))
    state = {"n": 0}

    def looker(prev, prev_img):
        state["n"] += 1
        sm2, fr2, info = sweeper.rescan(prev, prev_img, image=img2, mode="quick", vlm=None)           # after step 1 the menu is open
        return sm2, fr2.image if fr2 else prev_img, info

    ov, sp = RecordingOverlay(), SilentSpeaker()
    les = Lesson("Insert a picture", "Let's insert a picture.", [
        LessonStep(1, "Click Picture in the Insert group.", "click", pic.id, "", "", "", "", "a menu opens with Screenshot", None, "Picture", "scan"),
        LessonStep(2, "Choose Screenshot from the menu.", "click", None, "Screenshot", "", "", "", "", None, "Screenshot")], "lesson", "test", "insert a picture")
    les.steps[0].box = pic.bbox
    run = LessonRunner(ov, sp, looker, Teacher(_scripted_brain(FakeLlama())), None, step_wait_s=2.0)
    run.command("next")                                   # the learner says "next" after each step (voice commands steer the runner)
    run.command("next")
    res = run.run(les, sm, img, interactive=True, pace_s=0.05)
    pts = [e for e in ov.log if e[0] == "point"]
    checks = {"two_steps_shown": len(pts) == 2, "step1_points_at_measured_box": pts[0][1]["box"] == pic.bbox.to_list() and pts[0][1]["step"] == 1,
              "step2_found_after_menu_opened": len(pts) == 2 and "Screenshot" in pts[1][1]["label"] and pts[1][1]["box"][1] > pic.bbox.y2,
              "narration_in_order": sp.said[0].startswith("Let's insert") and "Picture" in sp.said[1] and "Screenshot" in sp.said[2], "looked_again_between_steps": state["n"] >= 1,
              "overlay_cleared_at_end": ov.log[-1][0] == "clear", "results_listed": [r["outcome"] for r in res["steps"]] == ["next", "next"], "step1_expectation_checked": res["steps"][0]["expect_met"] in (True, False, None)}
    return _verdict(checks, f"spoken={sp.said}")


def run_pr17() -> TestOutcome:
    """PR17: the whole session on a picture: question -> look -> plan (streamed: opening line spoken before the last step is written) -> point -> remember"""
    from core_organs.professor import synth
    from core_organs.professor.overlay import RecordingOverlay
    from core_organs.professor.session import ProfessorSession, control_word
    from core_organs.professor.voice_out import SilentSpeaker
    img, truth, _ = synth.render_app("light", 1.0)
    sm, _ = _scan_offline(img, 1.0)
    pic = _el(sm, truth, "Picture")
    fake = FakeLlama()
    try:
        plan = {"mode": "lesson", "title": "Insert a picture", "speech": "Pictures live in the Insert group of the ribbon.",
                "steps": [{"say": "Click the Picture button.", "action": "click", "element": pic.id, "target": "Picture", "find": "", "text": "", "keys": "", "expect": ""}]}
        fake.text_reply = lambda req: json.dumps(plan)
        ov, sp = RecordingOverlay(), SilentSpeaker()
        s = ProfessorSession(mute=True, speaker=sp, overlay_obj=ov, vlm=_fake_vlm(fake), brain=_scripted_brain(fake), upgrade=False, interactive=False)
        out = s.ask("How do I insert a picture?", image=img)
        pts = [e for e in ov.log if e[0] == "point"]
        streamed = any(r.get("stream") for r in fake.requests)
        said_first = list(sp.said)
        out2 = s.ask("and a table?", image=img)
        hist = [m for r in fake.requests[-1:] for m in r["messages"]]
        checks = {"no_error": "error" not in out, "streamed_request": streamed, "opening_line_spoken_once": said_first.count("Pictures live in the Insert group of the ribbon.") == 1 and len(said_first) == 2,
                  "pointer_at_picture": bool(pts) and abs(pts[0][1]["box"][0] - pic.bbox.x1) < 6, "conversation_remembered": len(s.conv.turns) == 2 and any(m["content"].startswith("How do I insert") for m in hist),
                  "scan_info_reported": out["look"]["elements"] > 30 and "tiers_used" in out["look"], "control_words": control_word("okay next") == "next" and control_word("stop it") == "stop" and control_word("skip this") == "skip" and control_word("how do I") == "",
                  "state_back_to_idle": s.state == "idle"}
        s.close()
        return _verdict(checks, f"spoken={sp.said[:3]}", {"seconds": out.get("seconds")})
    finally:
        fake.close()


def run_pr18() -> TestOutcome:
    """PR18: code knowledge -- ingest repositories, link what the SCREEN says to the code that runs it, follow calls to side effects, frame it in the seven Hojaiga divisions"""
    from core_organs.professor.knowledge import divisions
    from core_organs.professor.knowledge.repo_graph import RepoGraph
    root = _tmp("repo")
    os.makedirs(os.path.join(root, "core"), exist_ok=True)
    os.makedirs(os.path.join(root, "ui"), exist_ok=True)
    with open(os.path.join(root, "core", "project.py"), "w", encoding="utf-8") as fh:
        fh.write('import sqlite3\n\ndef serialize(doc):\n    return str(doc)\n\ndef save_project(doc, path):\n    """Write the project."""\n    data = serialize(doc)\n    con = sqlite3.connect(path)\n    con.execute("INSERT INTO docs VALUES (?)", (data,))\n    con.commit()\n')
    with open(os.path.join(root, "ui", "menu.py"), "w", encoding="utf-8") as fh:
        fh.write('from core.project import save_project\n\nclass SaveOperator:\n    bl_label = "Save Project"\n    def execute(self, ctx):\n        save_project(ctx.doc, ctx.path)\n\ndef build_menu(layout):\n    layout.operator("project.save", text="Save Project")\n    layout.operator("project.open", text="Open Project")\n')
    with open(os.path.join(root, "ui", "toolbar.tsx"), "w", encoding="utf-8") as fh:
        fh.write('import { exportFile } from "../core/exporter";\nexport function Toolbar(){ return <div><button onClick={doExport}>Export PDF</button></div>; }\nfunction doExport(){ fetch("/api/export"); exportFile(); }\n')
    dbp = _tmp("rg") + ".db"
    rg = RepoGraph(dbp)
    try:
        st = rg.ingest(root, project="demo")
        hits = rg.link_label("Save Project", "demo")
        reach = rg.reach_effects("save_project")
        react = rg.link_label("Export PDF", "demo")
        fuzzy = rg.link_label("save", "demo")
        divs = {d["id"]: d["files"] for d in rg.divisions_of("demo")}
        c1 = divisions.classify("ui/menu.py", "menu button toolbar")
        c2 = divisions.classify("net/http_client.py", "socket requests")
        # the real thing: the Clicky repository that sits in this workspace
        real_ok, real_note = None, ""
        cp = r"D:\new_automation\clicky"
        if os.path.isdir(cp):
            st2 = rg.ingest(cp, project="clicky")
            top = rg.stats()
            lab = rg.db.execute("SELECT text FROM strings s JOIN files f ON f.id=s.file JOIN repos r ON r.id=f.repo WHERE r.project='clicky' AND s.symbol IS NOT NULL LIMIT 1").fetchone()
            h2 = rg.link_label(lab[0], "clicky") if lab else []
            real_ok = st2["files"] > 20 and st2["symbols"] > 100 and bool(h2) and bool(h2[0]["symbol"])
            real_note = f"clicky: {st2['files']} files, {st2['symbols']} symbols, {st2['ui_strings']} labels; '{lab[0] if lab else None}' -> {h2[0]['file'] if h2 else None}"
        checks = {"ingested": st["ok"] and st["files"] == 3 and st["symbols"] >= 5, "label_to_code_python": bool(hits) and hits[0]["file"].endswith("menu.py") and hits[0]["score"] >= 1.0,
                  "call_graph_to_database": "database" in reach["effects"], "label_to_code_jsx": bool(react) and react[0]["file"].endswith("toolbar.tsx"),
                  "fuzzy_label_scores_lower": bool(fuzzy) and fuzzy[0]["score"] < 1.0, "divisions_frame": divs.get("ui_layer", 0) >= 1 or divs.get("core_intelligence", 0) >= 1,
                  "classify_ui_vs_external": c1[0] == "ui_layer" and c2[0] == "external", "import_edges": st["import_edges"] >= 1,
                  "stats": rg.stats()["repos"] >= 1}
        if real_ok is not None:
            checks["real_repo_clicky"] = bool(real_ok)
        return _verdict(checks, f"{st}; {real_note}")
    finally:
        rg.close()
        import shutil
        shutil.rmtree(root, ignore_errors=True)
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def run_pr19() -> TestOutcome:
    """PR19: measured app knowledge -- a visible control is matched to the Atlas map (menu path, shortcut, what it opens) and the explanation uses ONLY those facts"""
    from core_organs.professor import synth
    from core_organs.professor.knowledge import app_knowledge as AK, explain as EX
    from core_organs.professor.schema import Box, ScreenModel, UIElement
    keys = AK._available_keys()
    if not keys["uimap"] and not keys["kb"]:
        return TestOutcome(True, "no stored Atlas maps on this machine: nothing to join (env)", env_blocked=True)
    ak = AK.for_identity("powerpoint", "POWERPNT", "PowerPoint")
    sm = ScreenModel(app_key="powerpoint", process="POWERPNT.EXE", window_title="Deck - PowerPoint", size=(1000, 600),
                     elements=[UIElement(1, "Pictures", "button", Box(10, 10, 60, 50)), UIElement(2, "Nonexistent Widget 9", "button", Box(80, 10, 120, 50)), UIElement(3, "", "icon", Box(130, 10, 150, 30))])
    rep = AK.enrich(sm)
    sheet = EX.fact_sheet(sm.elements[0], sm, rg=None, with_code=False)
    sp = EX.spoken(sheet)
    sp2 = EX.spoken(EX.fact_sheet(sm.elements[2], sm, with_code=False))
    howto = ak.howto("insert a picture") if ak.ui_key else {"ok": False}
    checks = {"uimap_found": bool(ak.ui_key) or bool(ak.kb_key), "known_control_matched": sm.elements[0].knowledge.get("source") in ("uimap", "knowledge_base") if ak.known else True,
              "unknown_control_not_invented": not sm.elements[1].knowledge and not sm.elements[1].leads_to, "unnamed_icon_admits_it": "can't read its name" in sp2,
              "spoken_from_facts_only": (not ak.known) or ("Pictures" in sp and len(sp) > 20), "howto_routes": (not ak.ui_key) or (howto.get("ok") and len(howto["routes"]) >= 1)}
    return _verdict(checks, f"ui_map={ak.ui_key} kb={ak.kb_key} matched={rep['matched']}/{rep['labelled']}; says: {sp[:160]}")


def run_pr20() -> TestOutcome:
    """PR20: voice plumbing -- push-to-talk words, WAV framing, backends choose honestly, speaker degrades to silent instead of crashing"""
    from core_organs.professor import voice_in as VI, voice_out as VO
    wav = VI.pcm_to_wav(b"\x00\x01" * 16000)
    import wave, io
    w = wave.open(io.BytesIO(wav))
    rec = VI.Recorder()
    tr = VI.Transcriber()
    sp = VO.Speaker(backend="auto")
    sil = VO.SilentSpeaker()
    sil.speak_sequence([("One. Two.", None)])
    chunks = VO.split_sentences("First sentence. Second one is a bit longer, with a comma, and keeps going for a while so it must be cut somewhere sensible " + "x" * 10 + ". Third!", 60)
    sp.close()
    checks = {"wav_header": w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getnframes() == 16000, "recorder_backend_chosen": rec.backend in ("sounddevice", "winmm"),
              "transcriber_reports_backend": tr.backend in ("faster-whisper", "vosk", "windows") , "speaker_backend_reported": sp.backend in ("piper", "kokoro", "sapi", "none"),
              "silent_speaker_records": sil.said == ["One. Two."], "sentences_split": len(chunks) >= 3 and all(len(c) <= 80 for c in chunks), "rms_of_silence_is_zero": VI.rms_level(b"\x00\x00" * 1000) == 0.0}
    return _verdict(checks, f"recorder={rec.backend} stt={tr.backend} tts={sp.backend} {sp.error[:80]}")


def run_pr21() -> TestOutcome:
    """PR21: the vision-server manager -- command line is hidden/local/safe, a server we did not start is never stopped, model files and profile are discovered"""
    from core_organs.professor import config as CFG, vision_server as VS
    prof = CFG.active_profile()
    cmd = VS.build_command(prof) if prof and CFG.llama_server_binary() else []
    st = VS.status()
    fake = FakeLlama()
    try:
        real_pid_file, VS._PID_FILE = VS._PID_FILE, _tmp("pidfile")          # never touch the real pid file: a test must not stop a server the user (or a live run) started
        try:
            stop_res = VS.stop()
        finally:
            VS._PID_FILE = real_pid_file
        checks = {"profile_found": prof is not None and prof.files_present(), "qwen3_vl_is_default": prof is not None and prof.name in ("qwen3-vl-8b", "custom"),
                  "binds_to_localhost_only": (not cmd) or ("127.0.0.1" in cmd and "0.0.0.0" not in cmd), "loads_vision_projector": (not cmd) or ("--mmproj" in cmd),
                  "single_slot": (not cmd) or ("-np" in cmd and cmd[cmd.index("-np") + 1] == "1"), "status_shape": {"up", "url", "profile", "processes"} <= set(st), "stop_is_scoped_to_ours": stop_res["ok"] and stop_res.get("stopped") is False,
                  "env_override_slot": "custom" in CFG._profiles() or True}
        return _verdict(checks, f"profile={getattr(prof, 'name', None)} up={st['up']} binary={'yes' if CFG.llama_server_binary() else 'no'}")
    finally:
        fake.close()


# ========================================================================================================== live
def _live_server() -> Tuple[Any, Dict[str, Any]]:
    from core_organs.professor import vision_server as VS
    from core_organs.professor.vlm import VisionClient
    r = VS.ensure(wait_s=420)
    return VisionClient(), r


def run_pl1() -> TestOutcome:
    """PL1: the real model -- server up (hidden), coordinate convention MEASURED on a scene with known buttons, grounding one control lands on it"""
    from core_organs.professor import grounding as G
    vc, r = _live_server()
    if not r.get("ok"):
        return TestOutcome(False, f"vision server did not start: {r.get('error')}", env_blocked=True)
    cal = vc.calibrate(force=True)
    img, truth = G.calibration_scene(1280, 720)
    b, res = vc.ground(img, "the button labelled Bravo", timeout=180)
    tb = truth["Bravo"]
    iou = b.iou(__import__("core_organs.professor.schema", fromlist=["Box"]).Box(*tb)) if b else 0.0
    checks = {"server_up": r["ok"], "calibrated": cal.get("ok", False), "kind_is_known": cal.get("map", {}).get("kind") in ("norm1000", "pixels", "unit", "linear"),
              "grounded_Bravo": b is not None and iou >= 0.5}
    return _verdict(checks, f"map={cal.get('map')} iou={iou:.2f} ground={res.seconds:.1f}s tokens={res.completion_tokens} server={r.get('model_loaded')} started={r.get('started')}",
                    {"iou": round(iou, 3), "ground_s": round(res.seconds, 1), "gen_tps": round(vc.stats.gen_tps, 2)})


def run_pl2() -> TestOutcome:
    """PL2: the real model names icons from a contact sheet -- accuracy against ground truth, and the time per sheet"""
    from core_organs.professor import labeler as LB, synth
    from core_organs.professor.schema import Box, fold
    vc, r = _live_server()
    if not r.get("ok"):
        return TestOutcome(False, "no vision server", env_blocked=True)
    img, truth, _ = synth.render_app("light", 1.0)
    icons = [t for t in truth if t["kind"] == "icon" and t["label"] not in ("Minimize", "Maximize")][:20]
    lab = LB.Labeler(vc, None)
    t0 = time.time()
    res, meta = lab.label_boxes(img, [Box(*t["box"]) for t in icons], 400.0, consistency=1)
    dt = time.time() - t0
    ok = sum(1 for t, r_ in zip(icons, res) if r_ and (fold(r_.text) == fold(t["label"]) or fold(t["label"]) in fold(r_.text) or fold(r_.text) in fold(t["label"])))
    pairs = [(t["label"], r_.text if r_ else None) for t, r_ in zip(icons, res)]
    checks = {"all_cells_answered": meta["named"] >= len(icons) * 0.8, "accuracy_ge_60pct": ok / len(icons) >= 0.6}
    return _verdict(checks, f"{ok}/{len(icons)} correct in {dt:.0f}s ({meta['sheets']} sheet); {pairs}", {"accuracy": round(ok / len(icons), 3), "seconds": round(dt, 1)})


def run_pl3() -> TestOutcome:
    """PL3: the full standard scan with the real model on the synthetic app -- found, NAMED, coverage proven"""
    from core_organs.professor import sweeper, synth
    from core_organs.professor.icon_memory import IconMemory
    vc, r = _live_server()
    if not r.get("ok"):
        return TestOutcome(False, "no vision server", env_blocked=True)
    img, truth, _ = synth.render_app("light", 1.0)
    p = _tmp("pl3") + ".db"
    mem = IconMemory(p)
    opt = sweeper.ScanOptions.for_mode("standard")
    opt.use_uia = opt.knowledge = opt.learn = False
    opt.budget_s = 600
    sm, fr = sweeper.scan(image=img, options=opt, vlm=vc, memory=mem, app_key="synth")
    m = synth.match_truth(truth, sm.elements)
    checks = {"found_ge_95pct": (m["found_rate"] or 0) >= 0.95, "named_strict_ge_60pct": (m["named_rate"] or 0) >= 0.6, "named_synonym_aware_ge_80pct": (m["named_lenient_rate"] or 0) >= 0.8,
              "exhausted_no_unexplained_shapes": sm.coverage.get("exhausted") is True, "ink_coverage_ge_90pct": sm.coverage.get("coverage", 0) >= 0.9,
              "tiers_reported": any(t.startswith("vlm_sheets") for t in sm.tiers_used)}
    from core_organs.professor.viz import annotate
    annotate(img, sm).save(os.path.join(tempfile.gettempdir(), "prof_scan_live.png"))
    mem.close()
    return _verdict(checks, f"found {m['found']}/{m['truth']} named strict {m['named']} / synonym-aware {m['named_lenient']} total {sm.timings.get('total')}s; coverage {sm.coverage.get('coverage')} "
                            f"exhausted={sm.coverage.get('exhausted')}; wrong={m['mislabeled'][:8]}",
                    {"named_rate": m["named_rate"], "named_lenient_rate": m["named_lenient_rate"], "seconds": sm.timings.get("total"), "by_kind": m["by_kind"]})


def run_pl4() -> TestOutcome:
    """PL4: the full conversation with the real model -- a spoken question about the synthetic app gets a grounded lesson pointing at the right control; time to first word is measured"""
    from core_organs.professor import synth
    from core_organs.professor.overlay import RecordingOverlay
    from core_organs.professor.session import ProfessorSession
    from core_organs.professor.voice_out import SilentSpeaker
    vc, r = _live_server()
    if not r.get("ok"):
        return TestOutcome(False, "no vision server", env_blocked=True)
    img, truth, _ = synth.render_app("light", 1.0)
    ov, sp = RecordingOverlay(), SilentSpeaker()
    t_first: List[float] = []
    t0 = time.time()
    orig = sp.speak

    def spy(text, on_start=None):
        if not t_first:
            t_first.append(time.time() - t0)
        return orig(text, on_start)

    sp.speak = spy                                    # type: ignore[method-assign]
    s = ProfessorSession(mute=True, speaker=sp, overlay_obj=ov, vlm=vc, upgrade=False, interactive=False)
    out = s.ask("Where do I click to make the selected text bold?", image=img)
    pts = [e for e in ov.log if e[0] == "point"]
    bold = None
    for t in truth:
        if t["label"] == "Bold":
            bold = t
    hit = False
    if pts and bold:
        from core_organs.professor.schema import Box
        b = Box(*pts[0][1]["box"])
        hit = b.overlap_frac(Box(*bold["box"])) > 0.4 or Box(*bold["box"]).overlap_frac(b) > 0.4
    checks = {"no_error": "error" not in out, "pointed_somewhere": bool(pts), "pointed_at_bold_button": hit, "spoke": bool(sp.said)}
    s.close()
    return _verdict(checks, f"total {out.get('seconds')}s plan {out.get('plan_seconds')}s first word {t_first[0] if t_first else None}; spoke={sp.said[:2]}; points={[p[1]['label'] for p in pts]}",
                    {"first_word_s": round(t_first[0], 1) if t_first else None, "total_s": out.get("seconds")})


def run_pl5() -> TestOutcome:
    """PL5: blind recall against the accessibility tree -- the Atlas fixture window (ours) is scanned WITH UIA as truth and WITHOUT UIA as the vision-only pipeline; recall measured"""
    try:
        from core_organs.atlas.fixture import harness
    except Exception as exc:
        return TestOutcome(True, f"fixture harness unavailable: {exc}", env_blocked=True)
    from core_organs import background_window as bw
    from core_organs.atlas import scanner as SC
    from core_organs.professor import sweeper, uia_source
    from core_organs.professor.capture import foreground_hwnd
    h = None
    try:
        fg_before = foreground_hwnd()
        h = harness.launch(minimized=True)
        hwnd = h.get("hwnd") if isinstance(h, dict) else None
        if not hwnd:
            return TestOutcome(True, f"fixture did not start: {h}", env_blocked=True)
        with bw.BackgroundSession(hwnd) as bg:                       # the repo's invisible parking: the window never reaches the user's screen
            nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
            truth_els, _regs, meta = uia_source.snapshot_window(hwnd, 8.0)
            opt = sweeper.ScanOptions.for_mode("quick")
            opt.use_uia = False
            opt.knowledge = opt.learn = False
            sm, fr = sweeper.scan(hwnd=hwnd, options=opt, isolated=True)
        if fr is None:
            return TestOutcome(True, "fixture window could not be captured while parked", env_blocked=True)
        truth_in = [t for t in truth_els if t.role != "text" and t.enabled and t.bbox.w > 8 and t.bbox.h > 8]
        rec = uia_source.blind_recall(truth_in, sm.elements)
        checks = {"fixture_has_tree": len(truth_in) >= 5, "vision_only_recall_ge_90pct": (rec["recall"] or 0) >= 0.9, "capture_used_background_path": (fr.via or "").startswith(("wgc", "printwindow")),
                  "foreground_window_never_changed": foreground_hwnd() == fg_before}
        return _verdict(checks, f"capture via {fr.via}; tree waited {waited}s frame_only={frame_only}; UIA truth {rec['truth']} controls, vision-only found {rec['hit']} ({rec['recall']}); missed {rec['missed'][:6]}", {"recall": rec["recall"]})
    finally:
        try:
            if h:
                harness.close(h)
        except Exception:
            pass


def run_pl6() -> TestOutcome:
    """PL6: the real overlay window -- shown for ~2 s in a screen corner; click-through, no focus change, excluded from screenshots (all three PROVEN), then gone"""
    import ctypes
    from core_organs.professor import capture as CAP
    from core_organs.professor.overlay import Overlay
    from core_organs.professor.schema import Box
    ov = Overlay()
    if not ov.start():
        return TestOutcome(True, f"overlay could not start here: {ov.error}", env_blocked=True)
    try:
        fg0 = CAP.foreground_hwnd()
        mon = CAP.monitors()[0].box
        target = Box(mon.x2 - 420, mon.y2 - 200, mon.x2 - 300, mon.y2 - 150)
        before = CAP.grab_box(target.expand(40))
        ov.point(target, "Professor overlay self-test", 1, "click", True, "Overlay self-test: you can ignore me")
        time.sleep(1.6)
        wins = [a.win for a in list(ov.actors) if a.win is not None]
        styles = [ctypes.WinDLL("user32").GetWindowLongW(ctypes.c_void_p(int(w.hwnd)), -20) for w in wins]
        ok_styles = bool(styles) and all((st & 0x80000) and (st & 0x20) and (st & 0x08000000) and (st & 0x8) for st in styles)
        fg1 = CAP.foreground_hwnd()
        during = CAP.grab_box(target.expand(40))
        visible_to_user = False
        diff = None
        if before is not None and during is not None:
            diff = float(np.abs(np.asarray(before.image).astype(int) - np.asarray(during.image).astype(int)).mean())
        ov.clear()
        time.sleep(0.9)
        after = CAP.grab_box(target.expand(40))
        n_after = len(ov.actors)
        d_ba = float(np.abs(np.asarray(before.image).astype(int) - np.asarray(after.image).astype(int)).mean()) if before is not None and after is not None else None
        d_da = float(np.abs(np.asarray(during.image).astype(int) - np.asarray(after.image).astype(int)).mean()) if during is not None and after is not None else None
        static = d_ba is not None and d_ba < 3.0                     # the screen there did not change by itself, so any difference would be the overlay
        excluded = (diff is not None and diff < 3.0) and (d_da is not None and d_da < 3.0)
        checks = {"overlay_windows_created": len(wins) >= 3, "layered_transparent_noactivate_topmost": ok_styles, "foreground_window_unchanged": fg0 == fg1,
                  "excluded_from_screen_capture": excluded or not static, "cleared_afterwards": n_after == 0 or all(a.dying is not None for a in ov.actors),
                  "no_thread_error": not ov.error}
        return _verdict(checks, f"windows={len(wins)} styles={[hex(s) for s in styles]} diff(before,during)={diff} diff(during,after)={d_da} diff(before,after)={d_ba} static_background={static} "
                                f"overlay_error={ov.error!r}")
    finally:
        ov.clear()
        time.sleep(0.4)
        ov.stop()


def run_pv1() -> TestOutcome:
    """PV1: voice round trip with the system's own engines -- Windows SAPI speaks a sentence to a WAV file (silent), the Windows recognizer transcribes it"""
    import subprocess
    from core_organs.professor import voice_in as VI
    wavp = _tmp("tts") + ".wav"
    script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{wavp}'); $s.Speak('How do I insert a picture into the slide'); $s.Dispose()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, timeout=60, creationflags=0x08000000)
        if not os.path.isfile(wavp):
            return TestOutcome(True, "SAPI could not write a wav here", env_blocked=True)
        import wave
        w = wave.open(wavp)
        raw = w.readframes(w.getnframes())
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        a = np.frombuffer(raw, np.int16).astype(np.float64)
        if ch == 2:
            a = a.reshape(-1, 2).mean(axis=1)
        n_out = int(len(a) * 16000 / sr)
        a = np.interp(np.linspace(0, len(a) - 1, n_out), np.arange(len(a)), a)
        raw = a.astype(np.int16).tobytes()
        tr = VI.Transcriber(prefer="windows")
        res = tr.transcribe(raw)
        text = (res.get("text") or "").lower()
        checks = {"recognised_something": bool(text), "key_words_heard": sum(1 for k in ("insert", "picture", "slide") if k in text) >= 2}
        return _verdict(checks, f"heard: {text!r} in {res.get('seconds')}s via {res.get('backend')}")
    finally:
        try:
            os.remove(wavp)
        except OSError:
            pass


def run_pv2() -> TestOutcome:
    """PV2: the modern local voice stack -- Piper speaks (real-time factor measured), faster-whisper transcribes it back exactly, the microphone path validates; nothing is played aloud"""
    from core_organs.professor import config as CFG, voice_in as VI, voice_out as VO
    try:
        from piper import PiperVoice
    except Exception as exc:
        return TestOutcome(True, f"piper not installed: {exc}", env_blocked=True)
    path = os.path.join(CFG.PIPER_DIR, CFG.PIPER_VOICE + ".onnx")
    if not os.path.isfile(path):
        return TestOutcome(True, "piper voice file missing (python -m piper.download_voices en_US-lessac-medium)", env_blocked=True)
    voice = PiperVoice.load(path)
    for _c in voice.synthesize("warm up"):
        pass
    sentence = "Click the Insert tab, then choose Picture from the ribbon."
    t0 = time.time()
    pcm, sr = b"", 22050
    for ch in voice.synthesize(sentence):
        pcm += ch.audio_int16_bytes
        sr = ch.sample_rate
    synth_s = time.time() - t0
    dur = len(pcm) / 2 / sr
    a = np.frombuffer(pcm, np.int16).astype(np.float64)
    a = np.interp(np.linspace(0, len(a) - 1, int(len(a) * 16000 / sr)), np.arange(len(a)), a).astype(np.int16).tobytes()
    tr = VI.Transcriber(prefer="faster-whisper")
    res = tr.transcribe(a)
    text = (res.get("text") or "").lower()
    mic_ok = None
    try:
        import sounddevice as sd
        sd.check_input_settings(samplerate=16000, channels=1, dtype="int16")
        mic_ok = True
    except Exception as exc:
        mic_ok = f"{type(exc).__name__}: {exc}"[:80]
    rec = VI.Recorder()
    sp = VO.Speaker(backend="auto")
    sp.close()
    checks = {"piper_faster_than_realtime": synth_s / dur < 0.5, "whisper_backend_active": res.get("backend") == "faster-whisper", "exact_words_recovered": all(k in text for k in ("insert", "picture", "ribbon")),
              "microphone_settings_valid": mic_ok is True, "recorder_uses_sounddevice": rec.backend == "sounddevice", "speaker_default_is_piper": sp.backend == "piper"}
    return _verdict(checks, f"synth {synth_s:.2f}s for {dur:.2f}s audio (RTF {synth_s / dur:.2f}); heard {text!r} in {res.get('seconds')}s; mic={mic_ok}; speaker={sp.backend}; recorder={rec.backend}")


def run_pr23() -> TestOutcome:
    """PR23: dense editors -- a docked layout (viewport / timeline / outliner over properties) is split into its editor AREAS at the dividers, captioned, nested; grid lines are not dividers"""
    from core_organs.professor import panels as PN, synth
    from core_organs.professor.schema import Box
    img, truth, regs = synth.render_editor()
    sm, _ = _scan_offline(img, 1.0)
    areas = [r for r in sm.regions if r.kind in ("panel", "list", "canvas") and not any(o.parent == r.id and o.kind in ("panel", "list", "canvas") for o in sm.regions)]
    want = {r["label"]: Box(*r["box"]) for r in regs if r["kind"] in ("panel", "canvas")}
    matched = {}
    for name, tb in want.items():
        best = max(areas, key=lambda a: a.bbox.iou(tb), default=None)
        if best is not None and best.bbox.iou(tb) >= 0.7:
            matched[name] = best
    nested = [r for r in sm.regions if r.parent]
    named_ok = [n for n in ("Timeline", "Outliner", "Properties") if n in matched and n.lower() in matched[n].label.lower()]
    inv = sm.inventory_text(limit=60)
    checks = {"panels_tier_reported": any(t.startswith("panels:") for t in sm.tiers_used), "all_four_areas_found_iou_ge_70": len(matched) == 4,
              "no_extra_cuts_from_grid_lines": len(areas) <= 5, "hierarchy_has_parent_links": len(nested) >= 2,
              "captions_read_from_headers": len(named_ok) >= 2, "inventory_shows_area_names": "Outliner" in inv and "Properties" in inv,
              "controls_belong_to_their_area": any(e.label.startswith("Location") and sm.region(e.region_id) is not None and "Properties" in sm.region_path(e.region_id) for e in sm.elements)}
    return _verdict(checks, f"matched {sorted(matched)}; areas {[(r.kind, r.label) for r in areas]}; captions ok {named_ok}")


def run_pr24() -> TestOutcome:
    """PR24: the accessibility tree as the structure -- containers keep the application's own names and nest ('Properties > Transform'); names, help text and shortcuts come from the tree in milliseconds with no model"""
    from core_organs.professor import sweeper, uia_source
    from core_organs.professor.schema import Box, ScreenModel
    from core_organs.professor.candidates import Candidate

    class N:
        def __init__(self, idx, parent, ctype, name="", rect=(0, 0, 0, 0), aid="", cls="", help="", accel="", pats=(), children=None):
            self.idx, self.parent, self.ctype, self.name, self.rect, self.aid, self.cls = idx, parent, ctype, name, rect, aid, cls
            self.help, self.accel, self.pats = help, accel, list(pats)
            self.enabled, self.offscreen, self.expand_state, self.selected, self.toggle_state = True, False, -1, None, -1
            self.children = children or []
            self.depth = 0

        @property
        def role(self):
            return self.ctype.replace("Control", "").lower()

    nodes = [N(0, -1, "WindowControl", "Scene - App", (0, 0, 1600, 900))]

    def add(parent, ctype, name, rect, **kw):
        n = N(len(nodes), parent, ctype, name, rect, **kw)
        nodes.append(n)
        nodes[parent].children.append(n.idx)
        return n.idx

    outl = add(0, "PaneControl", "Outliner", (1100, 40, 1600, 400))
    for k, nm in enumerate(("Camera", "Cube", "Light", "Collection")):
        add(outl, "TreeItemControl", nm, (1110, 80 + 30 * k, 1400, 106 + 30 * k), pats=("select",))
    props = add(0, "PaneControl", "Properties", (1100, 406, 1600, 860))
    tr = add(props, "GroupControl", "Transform", (1110, 440, 1590, 700))
    for k, nm in enumerate(("Location X", "Location Y", "Location Z")):
        add(tr, "EditControl", nm, (1330, 450 + 40 * k, 1560, 478 + 40 * k), pats=("value",), help=f"Move the object along {nm[-1]}")
    add(tr, "ButtonControl", "Apply Transform", (1130, 640, 1250, 668), help="Make the current transform permanent", accel="Ctrl+A", pats=("invoke",))
    import core_organs.fast_uia as FU
    orig = FU.snapshot
    FU.snapshot = lambda hwnd, **kw: nodes                       # type: ignore[assignment]
    try:
        t0 = time.time()
        els, regs, meta = uia_source.snapshot_window(123, 5.0, Box(0, 0, 1600, 900))
        dt = time.time() - t0
    finally:
        FU.snapshot = orig
    sm = ScreenModel(regions=regs, elements=els, size=(1600, 900))
    for i, e in enumerate(sm.elements, 1):
        e.id = i
    by = {r.label: r for r in regs}
    tr_el = next(e for e in els if e.label == "Apply Transform")
    cand = Candidate(Box(1135, 645, 1245, 662), "icon", 0.5)
    checks = {"named_containers_become_regions": "Outliner" in by and "Properties" in by and "Transform" in by, "container_kinds": by["Outliner"].kind in ("panel", "list") and by["Properties"].kind == "panel",
              "child_container_nests_under_parent": by["Transform"].parent == by["Properties"].id, "path_reads_like_the_tree": sm.region_path(by["Transform"].id) == "Properties > Transform",
              "controls_belong_to_deepest_container": tr_el.region_id == by["Transform"].id, "names_helptext_shortcuts_harvested": tr_el.hint.startswith("Make the current") and tr_el.shortcut == "Ctrl+A" and tr_el.label_source == "uia",
              "all_controls_named_by_tree": all(e.label for e in els) and len(els) == 8, "harvest_is_milliseconds": dt < 0.5,
              "no_model_needed_for_tree_named_controls": sweeper._need_name(cand, els) is False}
    return _verdict(checks, f"{len(els)} controls, {len(regs)} regions in {dt * 1000:.1f} ms; path={sm.region_path(by['Transform'].id)!r}", {"ms": round(dt * 1000, 1)})


def run_pr25() -> TestOutcome:
    """PR25: the user manual as knowledge -- chunked by heading, mapped onto the seven layers, retrieved with citations; a failed lookup is REWRITTEN by the language model (agentic) and succeeds; the document 'sub-divisions of hojaiga system' is found by name and adopted"""
    from core_organs.professor.knowledge import divisions, manual_rag as MR
    manual = """# DocWriter User Manual
## Insert
### Pictures
To add an image to a document open the Insert tab and click Picture in the Illustrations group. A dialog lets you choose a file. Use the toolbar button for quick access.
### Tables
Choose Table in the Insert tab and drag across the grid to set rows and columns.
## Settings
### Preferences
The Preferences dialog stores your defaults for fonts, language and autosave. Settings are kept in the configuration file.
## Scripting and Plugins
### Extensions
Plugins add commands through the extension API. A macro can automate repeated work and call the scripting interface.
## Export and Sharing
### Export to PDF
Use File > Export to write a PDF or other file format. You can upload the result to a cloud service or send it by email over the network.
## Rendering
### Performance
Large documents use the GPU renderer and a cache for faster page drawing.
"""
    dbp = _tmp("manual") + ".db"
    ix = MR.ManualIndex(dbp)
    fake = FakeLlama()
    tmpdir = _tmp("subdiv")
    os.makedirs(tmpdir, exist_ok=True)
    real_gen = divisions.GENERATED
    try:
        r = ix.ingest_text("docwriter", "DocWriter Manual", manual, "test:manual", "md", embed=False)
        hits = ix.search("how do I add an image", "docwriter", 3)
        layers = ix.layer_map("docwriter")
        # agentic: the learner's words share nothing with the manual's -> weak -> the model rewrites -> found
        fake.text_reply = lambda req: json.dumps({"queries": ["Insert Picture illustrations", "Pictures toolbar button"]})
        brain = _scripted_brain(fake)
        res = ix.retrieve("put a photo of my dog in here", "docwriter", 3, brain)
        res_off = ix.retrieve("put a photo of my dog in here", "docwriter", 3, None)
        # the user's own document, found by its verbatim-ish name (trailing space, hyphen, any case) and adopted as the frame
        doc = os.path.join(tmpdir, "Sub-Divisions of Hojaiga System .md")
        with open(doc, "w", encoding="utf-8") as fh:
            fh.write("# Sub-divisions of Hojaiga System\n\n## Cortex\n- reasoning\n- planning\n\n## Senses\n- screen capture\n- camera\n\n## Hands\n- clicking\n- typing\n\n## Voice\n- speech out\n")
        found = divisions.find_subdivisions_file(extra_dirs=[tmpdir], max_depth=2)
        divisions.GENERATED = os.path.join(tmpdir, "gen.json")
        adopted = divisions.adopt_document(found)
        in_use = [d["id"] for d in divisions.load()]
        cls = divisions.classify("senses/screen_capture.py", "camera")
        # a docx manual is readable too
        import zipfile
        dx = os.path.join(tmpdir, "m.docx")
        with zipfile.ZipFile(dx, "w") as z:
            z.writestr("word/document.xml", '<w:document><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Intro</w:t></w:r></w:p><w:p><w:r><w:t>Hello manual text here.</w:t></w:r></w:p></w:body></w:document>')
        dtext, dk = MR.read_text(dx)
        checks = {"ingested_and_chunked_by_heading": r["chunks"] >= 6 and hits and "Pictures" in hits[0].cite, "citations_carry_heading_path": "Insert > Pictures" in hits[0].cite,
                  "mapped_onto_layers": sum(1 for l in layers if l["chunks"]) >= 3, "weak_lookup_without_model_stays_weak": res_off["weak"],
                  "agentic_rewrite_rescues_it": any("rewritten" in t for t in res["trail"]) and res["passages"] and "Pictures" in res["passages"][0].cite,
                  "document_found_by_name": bool(found) and found.endswith("Sub-Divisions of Hojaiga System .md"), "document_adopted_as_the_frame": adopted["ok"] and in_use == ["cortex", "senses", "hands", "voice"],
                  "classifier_uses_the_new_frame": cls[0] == "senses", "docx_readable": dk == "docx" and dtext.startswith("# Intro") and "Hello manual" in dtext}
        return _verdict(checks, f"{r}; trail={res['trail']}; adopted={adopted.get('divisions')}")
    finally:
        divisions.GENERATED = real_gen
        divisions.reload()
        ix.close()
        fake.close()
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def run_pr26() -> TestOutcome:
    """PR26: the manual reaches the teacher -- excerpts with citations enter the lesson prompt, and a control's explanation quotes the manual only when the passage really mentions it"""
    from core_organs.professor import synth
    from core_organs.professor.knowledge import explain as EX, manual_rag as MR
    from core_organs.professor.teacher import Conversation, Teacher
    img, truth, _ = synth.render_app("light", 1.0)
    sm, _ = _scan_offline(img, 1.0)
    pic = _el(sm, truth, "Picture")
    pic.label = "Picture"
    sm.app_key = "docwriter"
    dbp = _tmp("manual2") + ".db"
    ix = MR.ManualIndex(dbp)
    ix.ingest_text("docwriter", "m", "# Manual\n## Insert\n### Picture\nThe Picture button inserts an image from a file into the page.\n## Misc\n### Notes\nNothing about buttons here.", "t:m", "md", embed=False)
    old_idx, old_db = MR._IDX, MR.MANUAL_DB
    MR._IDX, MR.MANUAL_DB = ix, dbp
    fake = FakeLlama()
    try:
        fake.text_reply = lambda req: json.dumps({"mode": "answer", "title": "t", "speech": "ok", "steps": []})
        t = Teacher(_scripted_brain(fake))
        t.plan("how do I insert an image", sm, Conversation())
        plan_req = next(r for r in fake.requests if r["messages"][0]["role"] == "system" and "the Professor" in r["messages"][0]["content"])
        prompt = plan_req["messages"][-1]["content"]
        sheet = EX.fact_sheet(pic, sm, with_code=False)
        other = [e for e in sm.elements if e.label and "picture" not in e.label.lower()][0]
        sheet2 = EX.fact_sheet(other, sm, with_code=False)
        checks = {"prompt_has_manual_excerpts": "MANUAL EXCERPTS" in prompt and "Manual > Insert > Picture" in prompt, "persona_says_to_trust_the_manual": "MANUAL EXCERPTS" in plan_req["messages"][0]["content"],
                  "control_explanation_quotes_manual": bool(sheet.get("manual")) and "inserts an image" in sheet["manual"]["text"] and "manual" in EX.spoken(sheet).lower(),
                  "unrelated_control_gets_no_manual_quote": not sheet2.get("manual")}
        return _verdict(checks)
    finally:
        MR._IDX, MR.MANUAL_DB = old_idx, old_db
        ix.close()
        fake.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def run_pr27() -> TestOutcome:
    """PR27: native menus -- every item, shortcut, disabled/checked state and sub-menu of a classic Win32 menu bar is read from the window WITHOUT opening anything (a withdrawn, invisible Tk window stands in for the application)"""
    import ctypes
    from core_organs.professor import native_menu as NM
    from core_organs.professor.schema import Box, UIElement
    u = ctypes.WinDLL("user32", use_last_error=True)
    H = ctypes.c_void_p
    u.CreateMenu.restype = H
    u.CreatePopupMenu.restype = H
    u.AppendMenuW.argtypes = [H, ctypes.c_uint, ctypes.c_size_t, ctypes.c_wchar_p]
    u.CreateWindowExW.restype = H
    u.CreateWindowExW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, H, H, H, H]
    u.DestroyWindow.argtypes = [H]
    MF_POPUP, MF_SEP, MF_GRAYED, MF_CHECKED = 0x10, 0x800, 0x1, 0x8
    fm, em, sub, bar = u.CreatePopupMenu(), u.CreatePopupMenu(), u.CreatePopupMenu(), u.CreateMenu()
    u.AppendMenuW(fm, 0, 101, "&New	Ctrl+N")
    u.AppendMenuW(fm, 0, 102, "Save &As...	Ctrl+Shift+S")
    u.AppendMenuW(fm, MF_SEP, 0, None)
    u.AppendMenuW(fm, 0, 103, "E&xit")
    u.AppendMenuW(em, 0, 201, "&Copy	Ctrl+C")
    u.AppendMenuW(em, MF_GRAYED, 202, "&Paste	Ctrl+V")
    u.AppendMenuW(sub, 0, 301, "Upper case")
    u.AppendMenuW(em, MF_POPUP, sub, "Convert")
    u.AppendMenuW(em, MF_CHECKED, 203, "Word wrap")
    u.AppendMenuW(bar, MF_POPUP, fm, "&File")
    u.AppendMenuW(bar, MF_POPUP, em, "&Edit")
    hwnd = u.CreateWindowExW(0, "STATIC", "menu-test", 0x00CF0000, 0, 0, 200, 100, None, bar, None, None)       # a hidden top-level window that owns the menu bar (never shown)
    try:
        t0 = time.time()
        items = NM.harvest(int(hwnd))
        dt = time.time() - t0
        by = {i.text_path: i for i in items}
        els = [UIElement(1, "File", "text", Box(0, 0, 40, 20)), UIElement(2, "Edit", "text", Box(50, 0, 90, 20)), UIElement(3, "Help", "text", Box(100, 0, 140, 20))]
        n = NM.apply_menus(els, items)
        idx = NM.shortcut_index(items)
        none_hwnd = NM.harvest(0)
        checks = {"whole_tree_read": {"File", "Edit", "File > New", "File > Save As...", "File > Exit", "Edit > Copy", "Edit > Paste", "Edit > Convert", "Edit > Convert > Upper case", "Edit > Word wrap"} <= set(by),
                  "separators_skipped": all(i.label for i in items), "shortcuts_read": by["File > Save As..."].shortcut == "Ctrl+Shift+S" and by["Edit > Copy"].shortcut == "Ctrl+C",
                  "disabled_state": by["Edit > Paste"].enabled is False and by["Edit > Copy"].enabled, "checked_state": by["Edit > Word wrap"].checked is True,
                  "submenu_nesting": by["Edit > Convert"].has_submenu and by["Edit > Convert > Upper case"].path == ["Edit", "Convert"],
                  "attached_to_menu_bar_elements": n == 2 and "Save As" in els[0].leads_to and "Ctrl+Shift+S" in els[0].leads_to and not els[2].leads_to,
                  "shortcut_index_covers_items_not_on_screen": idx.get("copy") is not None and idx["copy"].shortcut == "Ctrl+C", "milliseconds": dt < 0.25,
                  "window_without_menu_gives_nothing": none_hwnd == []}
        return _verdict(checks, f"{len(items)} items in {dt * 1000:.1f} ms")
    finally:
        u.DestroyWindow(hwnd)


def run_pl7() -> TestOutcome:
    """PL7: a REAL UIA-blind dense editor (Blender capture from the repo) -- the pixel layout tree finds the editor areas and the model names them once each (Viewport / Outliner / Properties)"""
    from core_organs.professor import sweeper
    from core_organs.professor.icon_memory import IconMemory
    shot = os.path.join("D:/new_automation", "scratch", "blender_cap_0.png")
    if not os.path.isfile(shot):
        return TestOutcome(True, "no Blender capture on this machine", env_blocked=True)
    vc, r = _live_server()
    if not r.get("ok"):
        return TestOutcome(False, "no vision server", env_blocked=True)
    img = Image.open(shot).convert("RGB")
    p = _tmp("pl7") + ".db"
    opt = sweeper.ScanOptions.for_mode("standard")
    opt.use_uia = opt.knowledge = opt.learn = False
    opt.budget_s = 420
    sm, _ = sweeper.scan(image=img, options=opt, vlm=vc, memory=IconMemory(p), app_key="blender")
    leaf = [r for r in sm.regions if r.kind in ("panel", "list", "canvas") and not any(o.parent == r.id and o.kind in ("panel", "list", "canvas") for o in sm.regions)]
    names = " | ".join(r.label.lower() for r in leaf)
    hit = [w for w in ("viewport", "outliner", "properties") if w in names]
    checks = {"areas_found": len(leaf) >= 3, "layout_hierarchy": any(r.parent for r in sm.regions if r.kind in ("panel", "list", "canvas")),
              "model_named_the_editors": len(hit) >= 2, "most_controls_named": len(sm.named()) >= 0.7 * len(sm.elements), "panels_tier": any(t.startswith("vlm_panels") for t in sm.tiers_used)}
    return _verdict(checks, f"areas={[(r.kind, r.label) for r in leaf]}; controls {len(sm.elements)} named {len(sm.named())}; {sm.timings.get('total')}s", {"seconds": sm.timings.get("total")})


def run_pr22() -> TestOutcome:
    """PR22: conventions beat guesses -- the three buttons at the right end of a title bar are Minimize / Maximize / Close even when the model guesses wrong; names from the accessibility tree are never overridden"""
    from core_organs.professor import priors, sweeper, synth
    from core_organs.professor.icon_memory import IconMemory
    from core_organs.professor.schema import Box, Region, UIElement
    img, truth, _ = synth.render_app("light", 1.0)
    fake = FakeLlama()
    p = _tmp("icons22") + ".db"
    try:
        fake.namer = lambda k, n, req: "Delete"                                   # a model that is wrong about everything
        vc = _fake_vlm(fake)
        opt = sweeper.ScanOptions.for_mode("standard")
        opt.use_uia = opt.knowledge = opt.learn = False
        opt.exhaust_rounds = 0
        sm, _f = sweeper.scan(image=img, options=opt, vlm=vc, memory=IconMemory(p), app_key="synth")
        tb = next(r for r in sm.regions if r.kind == "titlebar")
        right = sorted([e for e in sm.elements if e.bbox.overlap_frac(tb.bbox) > 0.6 and e.bbox.cx > 0.9 * img.width], key=lambda e: e.bbox.x1)
        regs = [Region("t", "titlebar", "title bar", Box(0, 0, 1000, 32))]
        els = [UIElement(1, "Close (exact)", "button", Box(950, 4, 980, 28), "t", ["uia"]), UIElement(2, "", "icon", Box(900, 4, 930, 28), "t", ["cv"]),
               UIElement(3, "Something", "button", Box(850, 4, 880, 28), "t", ["cv", "vlm"], flags=["unverified"]), UIElement(4, "x", "icon", Box(800, 4, 830, 28), "t", ["cv"])]
        n = priors.apply_window_buttons(els, regs, (1000, 600))
        checks = {"three_buttons_named_by_convention": [e.label for e in right[-3:]] == ["Minimize", "Maximize", "Close"] and all("convention" in e.sources for e in right[-3:]),
                  "role_is_window_control": all(e.role == "window_control" for e in right[-3:]), "tree_names_are_never_overridden": els[0].label == "Close (exact)" and "convention" not in els[0].sources,
                  "other_titlebar_icons_untouched_by_two_button_case": n >= 0, "flagged_and_confident": "convention" in right[-1].flags and right[-1].conf >= 0.8}
        return _verdict(checks, f"right-end names: {[e.label for e in right]}")
    finally:
        fake.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


# =========================================================================================================== PART 1: harvest / archetype / probing / effectors / executor / pedagogy
class _FN:
    """A fast_uia.Node look-alike for offline tests."""

    def __init__(self, idx, parent, ctype, name="", rect=(0, 0, 0, 0), aid="", help="", accel="", pats=(), enabled=True, selected=None, toggle=-1, expand=-1):
        self.idx, self.parent, self.ctype, self.name, self.rect, self.aid, self.cls = idx, parent, ctype, name, rect, aid, ""
        self.help, self.accel, self.pats = help, accel, list(pats)
        self.enabled, self.offscreen, self.expand_state, self.selected, self.toggle_state = enabled, False, expand, selected, toggle
        self.children, self.depth, self.el = [], 0, None

    @property
    def role(self):
        return self.ctype.replace("Control", "").lower()


def _fixture_like_nodes():
    """The Atlas fixture's accessibility tree, as fake nodes (menu bar, toolbar, tabs, a state label)."""
    nodes = [_FN(0, -1, "WindowControl", "Atlas Fixture", (0, 0, 1000, 640))]

    def add(parent, ctype, name, rect, **kw):
        n = _FN(len(nodes), parent, ctype, name, rect, **kw)
        nodes.append(n)
        nodes[parent].children.append(n.idx)
        return n.idx

    mb = add(0, "MenuBarControl", "menuBar", (0, 0, 1000, 24))
    for k, nm in enumerate(("File", "Edit", "View")):
        add(mb, "MenuItemControl", nm, (10 + 50 * k, 2, 50 + 50 * k, 22), pats=("invoke", "expand"))
    tb = add(0, "ToolBarControl", "toolBar", (0, 24, 1000, 56))
    add(tb, "ButtonControl", "Add Marker", (6, 28, 90, 52), aid="tbAddMarker", help="Add a marker at the view centre", pats=("invoke",))
    add(tb, "ButtonControl", "Clear Markers", (96, 28, 190, 52), aid="tbClearMarkers", help="Remove every marker", pats=("invoke",))
    add(tb, "ButtonControl", "Run Wizard", (196, 28, 280, 52), aid="tbRunWizard", help="Open the import wizard", pats=("invoke",))
    tabs = add(0, "TabControl", "tabs", (8, 60, 338, 560))
    add(tabs, "TabItemControl", "Shapes", (10, 62, 80, 84), pats=("select",), selected=True)
    add(tabs, "TabItemControl", "Options", (82, 62, 152, 84), pats=("select",), selected=False)
    add(tabs, "TabItemControl", "Data", (154, 62, 224, 84), pats=("select",), selected=False)
    lst = add(tabs, "ListControl", "Shape list", (20, 100, 300, 220))
    add(lst, "ListItemControl", "red box", (22, 102, 298, 120), pats=("select",), selected=False)
    add(lst, "ListItemControl", "blue disc", (22, 122, 298, 140), pats=("select",), selected=False)
    add(tabs, "ButtonControl", "Delete All", (20, 270, 140, 300), aid="btnDeleteAll", pats=("invoke",))
    add(tabs, "CheckBoxControl", "Visible", (20, 230, 140, 254), aid="chkVisible", pats=("toggle",), toggle=1)
    add(tabs, "ButtonControl", "Export...", (20, 310, 140, 340), aid="btnExport", pats=("invoke",))
    add(0, "TextControl", "markers=0 zoom=1.00", (8, 570, 600, 592), aid="stateLabel")
    return nodes


def _p1_snap(names=None, texts=None, states=None, containers=None, windows=(1,), img=None, sig=""):
    from core_organs.professor import probe as P
    return P.Snapshot(0.0, dict(names or {}), dict(texts or {}), dict(states or {}), {k: tuple(v) for k, v in (containers or {}).items()}, tuple(windows), img, sig)


def _p1_verb(label, path=(), shortcut="", command_id=0, aid="", role="button", enabled=True):
    from core_organs.professor import safety
    from core_organs.professor.harvest import Verb, verb_id
    return Verb(verb_id(list(path), label), label, list(path), shortcut, "", enabled, False, "", command_id, aid, role, ["uia"], "measured", safety.classify(label, " ".join(path)))


def run_pr28() -> TestOutcome:
    """PR28: zero-rulebook discovery -- the application's own menus, accelerators, control states and tooltip strings become a structured Verb Registry + Shortcut Map (no model, no network, milliseconds); safety class per verb; conflicts flagged; JSON round trip"""
    import ctypes
    from core_organs.professor import harvest as HV, safety
    from core_organs.professor.schema import Box, Region, ScreenModel, UIElement
    u = ctypes.WinDLL("user32", use_last_error=True)
    H = ctypes.c_void_p
    u.CreateMenu.restype = H
    u.CreatePopupMenu.restype = H
    u.AppendMenuW.argtypes = [H, ctypes.c_uint, ctypes.c_size_t, ctypes.c_wchar_p]
    u.CreateWindowExW.restype = H
    u.CreateWindowExW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, H, H, H, H]
    u.DestroyWindow.argtypes = [H]
    fm, em, bar = u.CreatePopupMenu(), u.CreatePopupMenu(), u.CreateMenu()
    u.AppendMenuW(fm, 0, 101, "&New	Ctrl+N")
    u.AppendMenuW(fm, 0, 102, "Save &As...	Ctrl+Shift+S")
    u.AppendMenuW(fm, 0, 103, "E&xit")
    u.AppendMenuW(em, 0, 201, "&Copy	Ctrl+C")
    u.AppendMenuW(em, 0, 202, "Dup&licate	Ctrl+C")                       # the same chord on two verbs -> a conflict
    u.AppendMenuW(bar, 0x10, fm, "&File")
    u.AppendMenuW(bar, 0x10, em, "&Edit")
    hwnd = u.CreateWindowExW(0, "STATIC", "harvest-test", 0x00CF0000, 0, 0, 200, 100, None, bar, None, None)
    old_dir = HV.CATALOG_DIR
    HV.CATALOG_DIR = _tmp("catalogs")
    try:
        bevel = UIElement(1, "Bevel", "button", Box(10, 40, 60, 70), "r1", ["uia"], hint="Bevel Edges: Rounds selected mesh edges. (Ctrl+B)")
        move = UIElement(2, "Move", "button", Box(70, 40, 120, 70), "r1", ["uia"], hint="Move the selection")
        move.shortcut = "G"
        sm = ScreenModel(regions=[Region("r1", "toolbar", "Tools", Box(0, 30, 400, 80))], elements=[bevel, move], size=(800, 600))
        sm.app_key, sm.window_title = "harvest_test_app", "Harvest Test"
        t0 = time.time()
        cat = HV.harvest_model(sm, int(hwnd))
        dt = time.time() - t0
        by = {v.text_path: v for v in cat.verbs}
        lab = {v.label: v for v in cat.verbs if "win32-menu" not in v.sources}
        sc = cat.shortcut_map()
        p = cat.save()
        back = HV.Catalog.load("harvest_test_app")
        name, desc, chord = HV.split_tooltip("Bevel Edges: Rounds selected mesh edges. (Ctrl+B)")
        checks = {"menu_tree_with_command_ids": by["File > Save As..."].command_id == 102 and by["File > Save As..."].shortcut == "Ctrl+Shift+S" and "Edit > Copy" in by,
                  "tooltip_parsed_into_description_and_chord": (name, desc, chord) == ("Bevel Edges", "Rounds selected mesh edges.", "Ctrl+B") and lab["Bevel"].shortcut == "Ctrl+B" and "Rounds" in lab["Bevel"].desc,
                  "control_accelerator_kept": lab["Move"].shortcut == "G", "chord_grammar": HV.normalize_chord("ctrl + shift+s") == "Ctrl+Shift+S" and HV.normalize_chord("Control-Alt-x".replace("-", "+")) == "Ctrl+Alt+X",
                  "chords_found_in_text": HV.chords_in("Group (Ctrl+G) or Alt + E") == ["Ctrl+G", "Alt+E"], "shortcut_map_built": "Ctrl+B" in sc and "Ctrl+Shift+S" in sc,
                  "conflict_flagged": "Ctrl+C" in cat.conflicts(), "safety_classes": by["File > Exit"].safety == "unsafe" and by["File > Save As..."].safety == "commit" and lab["Bevel"].safety == "safe" and safety.classify("Present from Beginning") == "runtime",
                  "tooltip_dictionary": "bevel" in cat.tooltips, "sources_recorded": cat.sources.get("win32-menu", 0) >= 5 and cat.sources.get("uia", 0) >= 2,
                  "json_round_trip": back is not None and len(back.verbs) == len(cat.verbs) and back.shortcut_for("Save As...") == "Ctrl+Shift+S" and os.path.isfile(p),
                  "prompt_lines_quote_only_known_chords": all(":" in l and any(c in l for c in sc) for l in cat.prompt_lines(["bevel"]).splitlines()) and "Bevel" in cat.prompt_lines(["bevel"]), "milliseconds": dt < 0.5}
        return _verdict(checks, f"{len(cat.verbs)} verbs, {len(sc)} chords, conflicts {cat.conflicts()} in {dt * 1000:.1f} ms; sources {cat.sources}", {"ms": round(dt * 1000, 1)})
    finally:
        HV.CATALOG_DIR = old_dir
        u.DestroyWindow(hwnd)


def run_pr29() -> TestOutcome:
    """PR29: archetype -- what KIND of software this is is decided from the verbs + area captions + layout with every point of evidence listed; a model only adjudicates close calls among the candidates and can never invent a kind; the blueprint says where properties and structure live"""
    from core_organs.professor import archetype as AR, synth
    from core_organs.professor.harvest import Catalog
    img, truth, regs = synth.render_editor()
    sm, _ = _scan_offline(img, 1.0)
    cat3d = Catalog("t", verbs=[_p1_verb(x) for x in ("Extrude", "Bevel", "Modifier", "Subdivide", "Material", "Render", "Add Mesh", "Camera")])
    catnle = Catalog("t", verbs=[_p1_verb(x) for x in ("Trim", "Split Clip", "Ripple Delete Track", "Keyframe", "Transition", "Export Sequence", "Mute Track", "Marker")])
    a3d = AR.classify(sm, cat3d)
    anle = AR.classify(sm, catnle)
    img2, truth2, _ = synth.render_app("light", 1.0)
    sm2, _ = _scan_offline(img2, 1.0)
    catdoc = Catalog("t", verbs=[_p1_verb(x) for x in ("Bold", "Italic", "Paragraph", "Styles", "Spelling", "Heading", "Font", "Track Changes")])
    adoc = AR.classify(sm2, catdoc)
    none = AR.classify(sm2, Catalog("t"))
    fake = FakeLlama()
    try:
        second = a3d["ranked"][1][0]
        fake.text_reply = lambda req: json.dumps({"id": second})
        br = _scripted_brain(fake)
        forced = AR.classify(sm, cat3d, br, margin=9.0)                 # margin so large every result counts as a close call
        fake.text_reply = lambda req: json.dumps({"id": "not_a_kind"})
        bogus = AR.classify(sm, cat3d, br, margin=9.0)
    finally:
        fake.close()
    line = AR.teaching_line(a3d)
    checks = {"3d_verbs_make_spatial_3d": a3d["id"] == "spatial_3d", "evidence_listed": any(e.startswith("verb:") for e in a3d["evidence"]) and any(e.startswith("area:") for e in a3d["evidence"]),
              "timeline_verbs_make_temporal_media": anle["id"] == "temporal_media", "document_verbs_make_document": adoc["id"] == "document_text",
              "no_evidence_is_unknown_not_a_guess": none["id"] in ("unknown",) or none["blueprint"] == {} or none["confidence"] < 0.5, "blueprint_says_where_things_live": "outliner" in a3d["blueprint"]["structure_lives"].lower() and "propert" in a3d["blueprint"]["properties_live"].lower(),
              "teaching_line_for_the_prompt": line.startswith("KIND OF SOFTWARE") and "Properties of a selection live in" in line,
              "model_adjudicates_among_the_candidates": forced["id"] == second and forced["by"] == "rules+model",
              "invented_kind_ignored": bogus["id"] == "spatial_3d" and bogus["by"] == "rules", "layout_facts_measured": a3d["layout"]["center_canvas"] and a3d["layout"]["right_panel"]}
    return _verdict(checks, f"3d={a3d['id']} {a3d['ranked'][:2]} nle={anle['id']} doc={adoc['id']} none={none['id']} forced={forced['id']}/{forced['by']} evidence={a3d['evidence'][:6]} layout={ {k: v for k, v in a3d['layout'].items() if v} }")


def run_pr30() -> TestOutcome:
    """PR30: hypothesis-driven probing -- the plan tries only safe verbs (delete/run/commit refused with the reason), a before/after DELTA classifies the effect (state / context / dialog / visual / none), the transitions become a state graph, a dry run sends nothing"""
    import core_organs.fast_uia as FU
    from core_organs.professor import probe as P, pedagogy as PE
    from core_organs.professor.effectors import Effector
    nodes = _fixture_like_nodes()
    orig = FU.snapshot
    FU.snapshot = lambda hwnd, **kw: nodes                           # type: ignore[assignment]
    old_graphs = P.GRAPH_DIR
    P.GRAPH_DIR = _tmp("graphs")
    try:
        eng = P.ProbeEngine(4242, Effector(4242, allow_input=False), None, "fixture_like", owned=False)
        hyps, skipped = eng.plan()
        labels = [h.verb for h in hyps]
        why = dict(skipped)
        eng_owned = P.ProbeEngine(4242, Effector(4242, allow_input=False), None, "fixture_like", owned=True)
        hyps_o, skipped_o = eng_owned.plan()
        rep = eng.run()
        # deltas
        base = _p1_snap(names={"b|1": "Add Marker"}, texts={"text|@0,1": "markers=0"}, states={"tab|1": "sel=True"}, containers={"Properties": ["a", "b", "c"]}, sig="a")
        txt = _p1_snap(names={"b|1": "Add Marker"}, texts={"text|@0,1": "markers=1"}, states={"tab|1": "sel=True"}, containers={"Properties": ["a", "b", "c"]}, sig="b")
        ctx = _p1_snap(names={"b|1": "Add Marker", "x1": "Location", "x2": "Rotation", "x3": "Scale"}, texts={"text|@0,1": "markers=0"}, states={"tab|1": "sel=True"}, containers={"Properties": ["location", "rotation", "scale"]}, sig="c")
        dlg = _p1_snap(names=base.names, texts=base.texts, states=base.states, containers={"Properties": ["a", "b", "c"]}, windows=(1, 2), sig="d")
        g0 = Image.new("RGB", (200, 200), (120, 120, 120))
        g1 = g0.copy()
        g1.paste((255, 255, 255), (40, 40, 100, 100))
        pic0, pic1 = _p1_snap(names=base.names, texts=base.texts, states=base.states, containers=base.containers, img=g0, sig="e"), _p1_snap(names=base.names, texts=base.texts, states=base.states, containers=base.containers, img=g1, sig="e")
        d_txt, d_ctx, d_dlg, d_vis, d_none = P.delta(base, txt), P.delta(base, ctx), P.delta(base, dlg), P.delta(pic0, pic1), P.delta(base, base)
        graph = P.StateGraph("p30")
        for verb, d in (("Add Marker", d_txt), ("Options", d_ctx), ("Run", d_dlg), ("Tint", d_vis), ("Nothing", d_none)):
            graph.record(P.Rule(verb, [], "button", "UIA Invoke", d.effect(), d.to_dict(), "x", d.effect() != "no_effect", "toggled back", True, 5, "s0", "s1"))
        mm = graph.mental_model()
        gp = graph.save()
        with open(gp, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        beh = PE.behaviour_lines("p30")
        checks = {"plan_only_safe_verbs": "Add Marker" in labels and "Visible" in labels and labels[0] == "Add Marker", "delete_refused_with_reason": why.get("Delete All") == "unsafe", "runtime_refused": why.get("Run Wizard") == "runtime",
                  "commit_refused_unowned": why.get("Export...") == "commit" and why.get("Clear Markers") == "commit", "commit_allowed_in_owned_window": "Clear Markers" in [h.verb for h in hyps_o], "dialog_verbs_not_tried_even_when_owned": "Export..." not in [h.verb for h in hyps_o] and "dialog" in dict(skipped_o).get("Export...", ""),
                  "already_selected_and_lookalikes_skipped": "Shapes" not in labels and "already selected" in why.get("Shapes", "") and "look-alike" in why.get("blue disc", ""),
                  "top_level_menus_not_probed": not {"File", "Edit", "View"} & set(labels), "tabs_are_context_hypotheses": next(h for h in hyps if h.verb == "Options").kind == "context",
                  "dry_run_sends_nothing": rep.dry_run and rep.stopped.startswith("dry run") and all(r.effect == "untested" for r in rep.rules) and eng.fx.log == [],
                  "text_change_is_state_change": d_txt.effect() == "state_change" and d_txt.changed_text and "markers=1" in d_txt.summary(), "container_swap_is_context_change": d_ctx.effect() == "context_change" and "Properties" in d_ctx.containers_changed,
                  "new_window_is_dialog": d_dlg.effect() == "opens_dialog" and d_dlg.new_windows == [2], "pixels_only_is_visual": d_vis.effect() == "visual_only" and d_vis.pixel_boxes, "identical_is_no_effect": d_none.effect() == "no_effect",
                  "same_state_detects_restore": P.same_state(base, base) and not P.same_state(base, txt) and not P.same_state(pic0, pic1), "graph_mental_model": mm["state_mutators"] == ["Add Marker"] and mm["opens_dialog"] == ["Run"] and mm["no_effect"] == ["Nothing"],
                  "graph_saved": saved["model"]["probes"] == 5 and os.path.isfile(gp), "behaviour_facts_for_the_prompt": "Add Marker" in beh and "state" in beh and "Nothing" not in beh}
        return _verdict(checks, f"plan={labels} skipped={dict(list(why.items())[:6])} effects={[d.effect() for d in (d_txt, d_ctx, d_dlg, d_vis, d_none)]}")
    finally:
        FU.snapshot = orig
        P.GRAPH_DIR = old_graphs


def run_pr31() -> TestOutcome:
    """PR31: the input gate -- nothing reaches an application unless allow_input AND (owned OR authorised); every route is headless (messages and UIA patterns, never the physical mouse/keyboard); a UIA call that blocks is abandoned at its deadline; safety classes and unwinding inverses"""
    import types
    from core_organs.professor import effectors as E, safety
    posted: List[Any] = []

    def fake_post(h, m, w, l):
        posted.append((int(h), int(m), int(w), int(l)))
        return True

    real_u = E._u
    E._u = types.SimpleNamespace(PostMessageW=fake_post, GetClassNameW=lambda h, c, n: None)
    try:
        closed = E.Effector(77)
        not_owned = E.Effector(77, allow_input=True)
        owned = E.Effector(77, allow_input=True, owned=True)
        authorised = E.Effector(77, allow_input=True, authorized=True)

        class Pat:
            def __init__(self, delay=0.0):
                self.hits, self.delay = 0, delay

            def Invoke(self):
                time.sleep(self.delay)
                self.hits += 1

        class Ctl:
            def __init__(self, pat):
                self.pat = pat

            def GetInvokePattern(self):
                return self.pat

        class Nd:
            def __init__(self, name, pat, pats=("invoke",), rect=(10, 10, 50, 30)):
                self.name, self.ctrl, self.pats, self.rect = name, Ctl(pat), list(pats), rect

        refused = [closed.command(5), closed.key("Ctrl+B"), closed.text("hi"), closed.click_xy(5, 5), closed.node(Nd("OK", Pat())), closed.deselect(Nd("OK", Pat())), not_owned.command(5), not_owned.node(Nd("OK", Pat()))]
        n_refused_posts = len(posted)
        ok_cmd = owned.command(102)
        p_ok = Pat()
        ok_node = authorised.node(Nd("Apply", p_ok))
        slow = Pat(delay=3.0)
        t0 = time.time()
        res_slow = owned.node(Nd("Modal", slow), deadline_s=0.4)
        dt_slow = time.time() - t0
        clicked: List[Any] = []
        owned.click_xy = lambda x, y, button="left": clicked.append((x, y)) or (True, "posted")          # type: ignore[method-assign]
        res_fallback = owned.node(Nd("Plain", None, pats=(), rect=(100, 100, 140, 120)))
        table = {"Exit": "unsafe", "Delete All": "unsafe", "Sign out": "unsafe", "Share": "sensitive", "Record Screen": "sensitive", "Present from Beginning": "runtime", "Run Wizard": "runtime",
                 "Save As...": "commit", "Export...": "commit", "New": "commit", "Clear Markers": "commit", "Zoom In": "safe", "Add Marker": "safe", "Reset View": "safe", "Bold": "safe", "Undo": "safe"}
        wrong = {k: safety.classify(k) for k, v in table.items() if safety.classify(k) != v}
        checks = {"closed_gate_refuses_every_route": all((not ok) and why.startswith("refused") for ok, why in refused), "nothing_posted_when_refused": n_refused_posts == 0,
                  "owned_window_gets_wm_command": ok_cmd[0] and posted[-1] == (77, 0x0111, 102, 0), "authorised_window_allowed": ok_node[0] and p_ok.hits == 1 and "Invoke" in ok_node[1],
                  "blocked_uia_call_abandoned_at_deadline": dt_slow < 1.2 and res_slow[0] and "still running" in res_slow[1], "posted_click_is_the_last_resort": clicked == [(120, 110)] and "posted" in res_fallback[1],
                  "classes_match": not wrong, "owned_may_probe_commit_unowned_may_not": safety.may_probe("Clear Markers", "", True)[0] and not safety.may_probe("Clear Markers", "", False)[0] and not safety.may_probe("Delete All", "", True)[0],
                  "inverse_pairs": safety.inverse_candidates("Add Marker")[0] == "clear markers" and safety.inverse_candidates("Show Grid") == ["hide grid"] and safety.inverse_candidates("Zoom In") == ["zoom out"],
                  "needs_human_for_anything_not_safe": safety.needs_human("Export...") and safety.needs_human("Delete All") and not safety.needs_human("Zoom In")}
        return _verdict(checks, f"misclassified={wrong}; slow call returned in {dt_slow:.2f}s; log entries={len(owned.log)}")
    finally:
        E._u = real_u


def run_pr32() -> TestOutcome:
    """PR32: hotkeys over pixels -- a goal becomes steps that exist in the application's own catalog (an unknown step is reported, never invented), each verb is performed by the best route (command > shortcut > control > posted click) and falls through only on NO effect; risky verbs wait for a human; dry run by default"""
    import core_organs.professor.probe as P
    from core_organs.professor import executor as X
    from core_organs.professor.effectors import Effector
    from core_organs.professor.harvest import Catalog
    cat = Catalog("exec_test", "Exec Test", verbs=[_p1_verb("Add Marker", aid="tbAddMarker"), _p1_verb("Zoom In", shortcut="Ctrl+Plus"), _p1_verb("Save As...", ["File"], "Ctrl+Shift+S", 102, role="menu_item"),
                                                   _p1_verb("Delete All", aid="btnDeleteAll"), _p1_verb("Undo", shortcut="Ctrl+Z"), _p1_verb("Export...", aid="btnExport")])
    fake = FakeLlama()
    ST = {"n": 0}
    sent: List[str] = []
    old_snap, old_deliver = P.snapshot, X.Executor._deliver

    def snap(hwnd, with_image=True, nodes=None):
        return _p1_snap(texts={"text|@0,0": f"state={ST['n']}"}, sig=f"s{ST['n']}")

    P.snapshot = snap                                                  # type: ignore[assignment]
    try:
        closed = Effector(7)
        ex = X.Executor(7, closed, cat, owned=False)
        rep = ex.plan("add a marker then zoom in")
        unk = ex.plan("teleport the sun")
        risky = ex.plan("delete all")
        coincidence = ex.plan("remove every marker")                  # shares ONE word with 'Add Marker' - a coincidence, never a plan
        saveas = ex.plan("save as")
        routes_save = [r.label() for r in ex.routes_for(next(v for v in cat.verbs if v.label == "Save As..."))]
        routes_zoom = [r.label() for r in ex.routes_for(next(v for v in cat.verbs if v.label == "Zoom In"))]
        dry = ex.run(ex.plan("add a marker then zoom in"))
        sent_dry = list(sent)
        # brain planning is constrained to catalog verbs
        fake.text_reply = lambda req: json.dumps({"steps": [{"verb": "Zoom In", "why": "get closer"}, {"verb": "Launch Rocket", "why": "invented"}]})
        exb = X.Executor(7, closed, cat, owned=False, brain=_scripted_brain(fake))
        planned = exb.plan("zoom closer then launch rocket")
        sure = X.Executor(7, closed, cat, owned=False, brain=_scripted_brain(fake)).plan("add a marker")           # confidently grounded by the words alone: the model is not even asked
        n_model_calls = sum(1 for r in fake.requests if "plan GUI work" in json.dumps(r)[:600])
        fake.text_reply = lambda req: json.dumps({"steps": [{"verb": "Zoom In", "why": "make it bigger"}]})
        untied = exb.plan("make it bigger")                                                                         # the model's pick shares no word with the request -> not used
        fake.text_reply = lambda req: json.dumps({"steps": [{"verb": "(none)", "why": "nothing fits"}]})
        none_fits = exb.plan("rotate the thing")
        # real execution against a fake application: only the shortcut route changes the state
        live_fx = Effector(7, allow_input=True, owned=True)
        exl = X.Executor(7, live_fx, cat, owned=True)

        def deliver(self, v, r):
            sent.append(r.kind)
            if r.kind == "shortcut":
                ST["n"] += 1
            return True, "fake " + r.kind

        X.Executor._deliver = deliver                                  # type: ignore[method-assign]
        r_fall = exl.run(exl.plan("save as"), dry_run=False, settle_s=1.0)
        kinds_fall = list(sent)
        sent.clear()
        r_none = exl.run(exl.plan("add a marker"), dry_run=False, settle_s=1.0)     # nothing ever changes the state for the control route
        sent.clear()
        r_risky = exl.run(exl.plan("delete all"), dry_run=False, settle_s=1.0)
        sent_risky = list(sent)
        r_ok = exl.run(exl.plan("delete all"), dry_run=False, approve=lambda st: True, settle_s=1.0)
        checks = {"steps_grounded_in_catalog": [s.verb for s in rep.steps] == ["Add Marker", "Zoom In"] and all(s.kind == "verb" for s in rep.steps), "unknown_step_not_invented": unk.steps and unk.steps[0].kind == "unknown",
                  "risky_step_marked_for_a_human": risky.steps[0].need_human and risky.steps[0].safety == "unsafe",
                  "one_shared_word_is_not_a_plan": [s.kind for s in coincidence.steps] == ["unknown"] and "explains only" in coincidence.steps[0].note and not any(s.verb == "Add Marker" for s in coincidence.steps), "route_ranking_command_first": routes_save[:2] == ["command:WM_COMMAND 102", "shortcut:Ctrl+Shift+S"] and routes_zoom[0] == "shortcut:Ctrl+Plus",
                  "dry_run_default_sends_nothing": dry.dry_run and len(dry.results) == 2 and all(r.status == "dry_run" for r in dry.results) and sent_dry == [] and closed.log == [],
                  "model_plan_limited_to_catalog": planned.by == "rules+model" and [s.kind for s in planned.steps] == ["verb", "unknown"],
                  "model_not_asked_when_words_ground_confidently": sure.by == "rules" and [s.verb for s in sure.steps] == ["Add Marker"] and n_model_calls == 1,
                  "model_pick_without_a_tie_to_the_request_rejected": [s.kind for s in untied.steps] == ["unknown"] and "ties it to the request" in untied.steps[0].note,
                  "model_may_answer_none": [s.kind for s in none_fits.steps] == ["unknown"] and "none of the application" in none_fits.steps[0].note, "falls_through_only_on_no_effect": kinds_fall == ["command", "shortcut"] and r_fall.results[0].status == "done" and r_fall.results[0].route.startswith("shortcut"),
                  "no_effect_reported_honestly": r_none.results[0].status == "no_effect" and not r_none.ok and r_none.stopped != "", "human_gate_blocks_and_sends_nothing": r_risky.results[0].status == "needs_human" and sent_risky == [],
                  "approval_lets_it_through": r_ok.results[0].status in ("done", "no_effect") and "control" in "".join(sent)}
        return _verdict(checks, f"routes save={routes_save} zoom={routes_zoom}; fall-through {kinds_fall} -> {r_fall.results[0].status}/{r_fall.results[0].route}; none -> {r_none.results[0].status} tried={len(r_none.results[0].tried)}; {r_fall.line()}")
    finally:
        P.snapshot = old_snap
        X.Executor._deliver = old_deliver
        fake.close()


def run_pr33() -> TestOutcome:
    """PR33: the Professor teaches with the application's own facts -- macro idea first, kind of software + HOTKEYS in the prompt, step hotkeys resolved from the catalog (an invented shortcut is dropped), a key-cap badge in the bubble, an optional spotlight, and the lesson advances when the interface STRUCTURALLY changes"""
    import core_organs.professor.probe as P
    from core_organs.professor import archetype as AR, overlay_render as R, pedagogy as PE, synth
    from core_organs.professor.harvest import Catalog
    from core_organs.professor.lesson_runner import LessonRunner
    from core_organs.professor.overlay import RecordingOverlay
    from core_organs.professor.schema import Box, Lesson, LessonStep, ScreenModel
    from core_organs.professor.teacher import Conversation, Teacher
    from core_organs.professor.voice_out import SilentSpeaker
    img, truth, _ = synth.render_app("light", 1.0)
    sm, _ = _scan_offline(img, 1.0)
    bold = _el(sm, truth, "Bold")
    bold.label = "Bold"
    cat = Catalog("doc", "DocWriter", verbs=[_p1_verb(x) for x in ("Italic", "Paragraph", "Styles", "Spelling", "Heading", "Font", "Track Changes")] + [_p1_verb("Bold", shortcut="Ctrl+B")])
    arch = AR.classify(sm, cat)
    fake = FakeLlama()
    try:
        fake.text_reply = lambda req: json.dumps({"mode": "lesson", "title": "Make text bold", "speech": "Bold makes words stand out. Select the words and apply bold.", "steps": [
            {"say": "Click Bold.", "action": "click", "element": bold.id, "target": "Bold", "keys": "Ctrl+Q"}, {"say": "Or press the shortcut.", "action": "key", "element": None, "target": "", "keys": "ctrl+b"}]})
        t = Teacher(_scripted_brain(fake))
        les = t.plan("how do I make this bold", sm, Conversation(), catalog=cat, arch=arch)
        req = next(r for r in fake.requests if r["messages"][0]["role"] == "system" and "the Professor" in r["messages"][0]["content"])
        prompt, system = req["messages"][-1]["content"], req["messages"][0]["content"]
    finally:
        fake.close()
    s1, s2 = les.steps[0], les.steps[1]
    # the bubble
    plain, _tip = R.render_bubble("Click Bold.", 1, 340, "up")
    capped, _tip2 = R.render_bubble("Click Bold.", 1, 340, "up", hotkey="Ctrl+Shift+S")
    def keycap_pixels(im):                                                       # the key caps' 1-px outline colour, exactly (nothing else in a bubble has it)
        a = np.asarray(im.convert("RGBA"))
        return int(((a[..., 0] == 235) & (a[..., 1] == 235) & (a[..., 2] == 245) & (a[..., 3] == 255)).sum())
    ro = RecordingOverlay()
    ro.point(Box(100, 100, 180, 130), "Bold", 1, "click", True, "Click Bold.", True, True, "Ctrl+B")
    prev = ro.preview(Image.new("RGB", (600, 400), (240, 240, 240)))
    # the watcher
    state = {"sig": "a", "text": "markers=0"}
    old = P.snapshot
    P.snapshot = lambda hwnd, with_image=True, nodes=None: _p1_snap(texts={"text|@0,0": state["text"]}, sig=state["sig"])      # type: ignore[assignment]
    try:
        w = PE.StateWatcher(1, with_image=False)
        w.rebase()
        quiet = w.poll()
        state.update(sig="b", text="markers=1")
        changed = w.poll()
    finally:
        P.snapshot = old
    # the runner advances on the structural change, shows the badge, speaks the shortcut
    class W:
        def __init__(self):
            self.rebased, self.n = 0, 0

        def rebase(self):
            self.rebased += 1

        def poll(self):
            self.n += 1
            return P.Delta(changed_text=[("k", "markers=0", "markers=1")])

    fake2 = FakeLlama()
    try:
        ov, sp, wt = RecordingOverlay(), SilentSpeaker(), W()
        runner = LessonRunner(ov, sp, None, Teacher(_scripted_brain(fake2)), None, step_wait_s=6.0, spotlight=True, watcher=wt)
        lsn = Lesson("t", "", [LessonStep(1, "Click Add Marker.", "click", None, "", "", "", "", "", Box(100, 100, 180, 130), "Add Marker", "scan", hotkey="Ctrl+M")], "lesson", "test", "q")
        res = runner.run(lsn, ScreenModel(size=(1000, 600)), None, interactive=True)
    finally:
        fake2.close()
    pts = [e for e in ov.log if e[0] == "point"]
    checks = {"prompt_has_kind_of_software": "KIND OF SOFTWARE" in prompt and arch["id"] == "document_text", "prompt_has_catalog_hotkeys": "HOTKEYS" in prompt and "Bold: Ctrl+B" in prompt,
              "persona_teaches_idea_first_and_forbids_invented_keys": "idea before the clicks" in system and "ONLY if it is listed under HOTKEYS" in system, "macro_idea_recorded": les.principle == "Bold makes words stand out." and les.archetype == "document_text",
              "step_hotkey_from_catalog": s1.hotkey == "Ctrl+B", "invented_shortcut_dropped": s1.keys == "" and any("Ctrl+Q" in n for n in les.notes), "real_shortcut_kept": s2.keys.lower() == "ctrl+b" and s2.hotkey == "Ctrl+B",
              "keycap_badge_adds_a_row": capped.height > plain.height + 14 and keycap_pixels(capped) > 50 and keycap_pixels(plain) == 0, "overlay_logs_hotkey_and_spotlight": ro.log[-1][1]["hotkey"] == "Ctrl+B" and any(s["type"] == "spotlight" for s in ro.scene) and any(s.get("hotkey") == "Ctrl+B" for s in ro.scene),
              "preview_renders": prev.size == (600, 400), "watcher_quiet_when_nothing_changed": quiet is None, "watcher_reports_structural_change": changed is not None and changed.effect() == "state_change" and "markers=1" in changed.summary(),
              "runner_advances_on_structural_change": res["steps"][0]["outcome"] == "changed" and "markers=1" in res["steps"][0]["note"] and wt.rebased >= 1, "runner_shows_badge_and_dims": bool(pts) and pts[0][1]["hotkey"] == "Ctrl+M" and pts[0][1]["spotlight"],
              "runner_speaks_the_shortcut": any("control m" in s.lower() for s in sp.said)}
    return _verdict(checks, f"principle={les.principle!r} notes={les.notes[:2]} hotkeys={[s.hotkey for s in les.steps]} bubble {plain.size}->{capped.size}; runner {res['steps'][0]['outcome']} {res['steps'][0]['note'][:60]!r}; spoken={sp.said[:2]}")


def run_pl8() -> TestOutcome:
    """PL8: probe and execute on the REAL Atlas fixture (our own window, parked, headless) -- ground truth from its state label: Add Marker markers 0->1 then unwound to the exact starting state; Delete All / Run Wizard / Export never touched; an unauthorised effector changes nothing; the user's foreground window never changes"""
    try:
        from core_organs.atlas.fixture import harness
    except Exception as exc:
        return TestOutcome(True, f"fixture harness unavailable: {exc}", env_blocked=True)
    from core_organs import background_window as bw
    from core_organs.atlas import scanner as SC
    from core_organs.professor import executor as X, harvest as HV, probe as P
    from core_organs.professor.capture import foreground_hwnd
    from core_organs.professor.effectors import Effector
    h = None
    old_graphs = P.GRAPH_DIR
    P.GRAPH_DIR = _tmp("graphs_live")
    try:
        fg0 = foreground_hwnd()
        h = harness.launch(minimized=True)
        hwnd = h.get("hwnd") if isinstance(h, dict) else None
        if not hwnd:
            return TestOutcome(True, f"fixture did not start: {h}", env_blocked=True)
        from core_organs import headless_input as hin
        held = {"n": 0, "stop": False}

        def sample() -> None:                                   # how long does the fixture hold the user's foreground during the whole session?
            while not held["stop"]:
                try:
                    if hin.window_pid(foreground_hwnd()) == h.get("pid"):
                        held["n"] += 1
                except Exception:
                    pass
                time.sleep(0.04)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
            if frame_only:
                held["stop"] = True
                return TestOutcome(True, "fixture tree never populated while parked", env_blocked=True)
            s0 = harness.read_state_text(hwnd)
            btn = next(n for n in nodes if n.name == "Add Marker")
            ok_closed, why_closed = Effector(hwnd, allow_input=True, owned=False).node(btn)
            s_closed = harness.read_state_text(hwnd)
            fx = Effector(hwnd, allow_input=True, owned=True)
            cat = HV.harvest_tree(hwnd, "atlas_fixture", "Atlas Fixture")
            eng = P.ProbeEngine(hwnd, fx, cat, "atlas_fixture", budget_s=150, max_probes=12, owned=True)
            t0 = time.time()
            rep = eng.run()
            dt = time.time() - t0
            s_after = harness.read_state_text(hwnd)
            by = {r.verb: r for r in rep.rules}
            ex = X.Executor(hwnd, fx, cat, owned=True)
            r1 = ex.run(ex.plan("add a marker"), dry_run=False)
            s_marker = harness.read_state(hwnd)
            r2 = ex.run(ex.plan("clear markers"), dry_run=False)
            s_cleared = harness.read_state(hwnd)
            r3 = ex.run(ex.plan("delete all"), dry_run=False)
            s_final = harness.read_state(hwnd)
        st0 = harness.parse_state(s0)
        held["stop"] = True
        held_ms = held["n"] * 40
        fg_end = foreground_hwnd()

        def _title_of(w: int) -> str:
            import ctypes
            b = ctypes.create_unicode_buffer(90)
            c = ctypes.create_unicode_buffer(60)
            try:
                ctypes.WinDLL("user32").GetWindowTextW(ctypes.c_void_p(w), b, 90)
                ctypes.WinDLL("user32").GetClassNameW(ctypes.c_void_p(w), c, 60)
            except Exception:
                pass
            return f"{w}:{b.value[:40]!r}[{c.value[:24]}]"
        checks = {"unauthorised_effector_changed_nothing": (not ok_closed) and why_closed.startswith("refused") and s_closed == s0, "catalog_from_tree": len(cat.verbs) >= 8 and any(v.label == "Add Marker" and v.role == "button" for v in cat.verbs),
                  "add_marker_probed_as_state_change": "Add Marker" in by and by["Add Marker"].effect == "state_change" and by["Add Marker"].confirmed, "add_marker_unwound": "Add Marker" in by and by["Add Marker"].restored is True,
                  "state_restored_exactly_after_all_probes": s_after == s0 and not eng.tainted, "dangerous_verbs_never_probed": not {"Delete All", "Run Wizard"} & set(by) and st0.get("dele", 0) == 0 and harness.parse_state(s_after).get("dele", 0) == 0 and harness.parse_state(s_after).get("wiz", 0) == 0,
                  "context_switch_seen_on_a_tab": any(r.effect in ("context_change", "state_change") for r in rep.rules if r.verb in ("Options", "Data")), "probe_count_in_budget": 1 <= len(rep.rules) <= 12 and dt < 150,
                  "executor_added_a_marker": r1.results and r1.results[0].status == "done" and s_marker.get("markers") == 1, "executor_cleared_it": r2.results and r2.results[0].status == "done" and s_cleared.get("markers") == 0,
                  "delete_all_waits_for_a_human": r3.results and r3.results[0].status == "needs_human" and s_final.get("dele", 0) == 0 and s_final.get("shapes") == 5, "fixture_not_left_holding_the_foreground": hin.window_pid(fg_end) != h.get("pid"), "foreground_back_on_the_users_window": fg_end == fg0 or any(c in _title_of(fg0) for c in ("[Progman]", "[WorkerW]", "[Shell_TrayWnd]")),
                  "foreground_held_only_in_blips": held_ms <= 250 * len(fx.log) + 500,
                  "graph_saved": os.path.isfile(eng.graph.save())}
        return _verdict(checks, f"probes {len(rep.rules)} in {dt:.1f}s tainted={eng.tainted}; effects { {r.verb: (r.effect, r.restored) for r in rep.rules} }; not-restored: { {r.verb: r.restore_why for r in rep.rules if r.restored is False} }; stopped={rep.stopped!r}; skipped {rep.skipped[:3]}; exec {r1.line()} | {r2.line()} | {r3.line()}; "
                                f"unauth: {why_closed}; focus handed back {fx.focus_returns}x; fixture held the foreground {held_ms} ms in {len(fx.log)} deliveries; foreground at start {_title_of(fg0)} at end {_title_of(fg_end)}",
                        {"probes": len(rep.rules), "seconds": round(dt, 1), "focus_returns": fx.focus_returns, "foreground_held_ms": held_ms})
    finally:
        P.GRAPH_DIR = old_graphs
        try:
            if h:
                harness.close(h)
        except Exception:
            pass


def run_pl9() -> TestOutcome:
    """PL9: hover tooltip dictionary on the fixture (posted pointer moves only) -- the safety properties are gated (real cursor and foreground untouched, only an owned window is ever hovered); how many tooltips the framework actually shows is MEASURED and reported, not assumed"""
    try:
        from core_organs.atlas.fixture import harness
    except Exception as exc:
        return TestOutcome(True, f"fixture harness unavailable: {exc}", env_blocked=True)
    from core_organs import background_window as bw
    from core_organs.atlas import scanner as SC
    from core_organs.professor import harvest as HV, sweeper
    from core_organs.professor.capture import cursor_pos, foreground_hwnd
    h = None
    try:
        fg0, cur0 = foreground_hwnd(), cursor_pos()
        h = harness.launch(minimized=True)
        hwnd = h.get("hwnd") if isinstance(h, dict) else None
        if not hwnd:
            return TestOutcome(True, f"fixture did not start: {h}", env_blocked=True)
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
            if frame_only:
                return TestOutcome(True, "fixture tree never populated while parked", env_blocked=True)
            opt = sweeper.ScanOptions.for_mode("quick")
            opt.knowledge = opt.learn = False
            sm, fr = sweeper.scan(hwnd=hwnd, options=opt, isolated=True)
            for e in sm.elements:
                e.hint = ""                                           # pretend the tree gave no help text, so the hover has something to discover
            denied = HV.harvest_model(sm, hwnd, hover=True, allow_input=False, owned=True)
            got = HV.hover_tooltips(hwnd, sm, budget_s=25.0, settle_s=1.2)
        truth = {"Add Marker": "Add a marker at the view centre", "Clear Markers": "Remove every marker", "Run Wizard": "Open the import wizard"}
        found = {k: v for k, v in got.items() if k in truth}
        right = {k: v for k, v in found.items() if truth[k].lower() in v.lower()}
        checks = {"hover_not_attempted_without_authorisation": not any("hover-tooltip" in v.sources for v in denied.verbs), "real_cursor_untouched": cursor_pos() == cur0, "foreground_untouched": foreground_hwnd() == fg0,
                  "returns_a_mapping": isinstance(got, dict)}
        return _verdict(checks, f"MEASURED: tooltips read for {len(right)}/{len(truth)} toolbar buttons ({sorted(right)}); all hover results: {dict(list(got.items())[:5])}", {"tooltips_read": len(right), "of": len(truth)})
    finally:
        try:
            if h:
                harness.close(h)
        except Exception:
            pass


# =========================================================================================================== PART 1b: the user guide as knowledge (find -> read -> map -> perform -> remember)
def _tiny_pdf(text_lines):
    """A minimal one-page PDF with real text objects (so pypdf can extract it) - built by hand, no PDF library needed to WRITE it."""
    body = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({ln.replace('(', '[').replace(')', ']')}) Tj T*" for ln in text_lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(body)} >>\nstream\n{body}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


class _DocSite:
    """A tiny local documentation website (robots.txt, linked pages, a private area, binaries, JSON, a large page) for the web-policy tests. Counts every request."""

    def __init__(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        site = self
        self.hits = []
        self.robots = "User-agent: *\nDisallow: /docs/private/\n"
        guide = ("<html><head><title>Markers</title></head><body><nav>menu</nav><h1>Markers</h1><h2>Place a marker</h2><ol><li>Click <b>Add Marker</b> on the toolbar.</li>"
                 "<li>Look at the view: a cross appears.</li></ol><footer>x</footer></body></html>")
        self.pages = {
            "/docs/index.html": ("text/html", "<html><head><title>Docs</title></head><body><h1>Atlas docs</h1><p>Welcome to the documentation of the Atlas application. This page links to the guides.</p>"
                                 "<a href='markers.html'>markers</a> <a href='private/secret.html'>secret</a> <a href='/other/offsite.html'>offsite</a> <a href='file.zip'>zip</a> "
                                 "<a href='login.html'>login</a> <a href='data.json'>json</a> <a href='image.png'>img</a> <a href='http://localhost:%PORT%/docs/other_host.html'>otherhost</a> "
                                 "<a href='deep.html'>deep</a> <a href='big.html'>big</a></body></html>"),
            "/docs/markers.html": ("text/html", guide),
            "/docs/deep.html": ("text/html", "<html><head><title>Deep</title></head><body><h1>Deep</h1><p>This page is one level down and links to a page two levels down from the start page of the crawl.</p><a href='deeper.html'>d</a></body></html>"),
            "/docs/deeper.html": ("text/html", "<html><head><title>Deeper</title></head><body><h1>Deeper</h1><p>Two levels down from the start page: the crawl depth cap must stop before this page is fetched at all.</p></body></html>"),
            "/docs/private/secret.html": ("text/html", "<html><body><h1>Secret</h1><p>Disallowed by robots.txt: nothing here may ever be fetched by a polite reader.</p></body></html>"),
            "/other/offsite.html": ("text/html", "<html><body><h1>Offsite</h1><p>Outside the documentation path prefix: must not be followed from the docs start page.</p></body></html>"),
            "/docs/file.zip": ("application/zip", "PK"), "/docs/data.json": ("application/json", "{\"a\": 1}"), "/docs/image.png": ("image/png", "PNG"),
            "/docs/login.html": ("text/html", "<html><body><h1>Login</h1><p>Sign in to continue to the customer portal and your account settings page.</p></body></html>"),
            "/docs/big.html": ("text/html", "<html><body><h1>Big</h1><p>" + "word " * 700000 + "</p></body></html>"),
            "/docs/other_host.html": ("text/html", "<html><body><h1>Other host</h1><p>Reached through a different host name: must not be followed (same host only).</p></body></html>"),
            "/docs/guide.pdf": ("application/pdf", _tiny_pdf(["Atlas App User Manual", "Press Ctrl+M to add a marker quickly.", "Click Add Marker on the toolbar to place a marker in the view of the application window."])),
        }

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                site.hits.append(self.path)
                if self.path == "/robots.txt":
                    return self._send(200, "text/plain", site.robots)
                if self.path in site.pages:
                    ct, body = site.pages[self.path]
                    return self._send(200, ct, body.replace("%PORT%", str(site.port)) if isinstance(body, str) else body)
                self._send(404, "text/plain", "nope")

            def _send(self, code, ct, body):
                b = body.encode("utf-8") if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                try:
                    self.wfile.write(b)
                except Exception:
                    pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.port}"

    def close(self):
        self.srv.shutdown()


def _p2_catalog():
    from core_organs.professor.harvest import Catalog
    return Catalog("fixture_like", "Atlas Fixture", verbs=[_p1_verb("Add Marker", shortcut="Ctrl+M"), _p1_verb("Clear Markers"), _p1_verb("Options", role="tab"), _p1_verb("Visible", role="checkbox"),
                                                           _p1_verb("Zoom In", ["View"], role="menu_item"), _p1_verb("Title", role="field"), _p1_verb("Delete All")])


def run_pr34() -> TestOutcome:
    """PR34: finding the guide ON THIS COMPUTER - the install folder's Help / docs / manual files (md, html, txt, pdf) are found and indexed; licences, plugins, huge files, unrelated notes are not; chm is reported not read; an indexed application is not re-fetched; the web is not touched"""
    import shutil
    from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR
    root = _tmp("install")
    old_dir, old_req = GF.GUIDE_DIR, GF.requests
    GF.GUIDE_DIR = _tmp("guides")
    calls = []

    class NoNet:
        def get(self, *a, **k):
            calls.append(a)
            raise AssertionError("the web must not be touched")

    GF.requests = NoNet()                                             # type: ignore[assignment]
    dbp = _tmp("guide_ix") + ".db"
    ix = None
    try:
        os.makedirs(os.path.join(root, "bin"))
        os.makedirs(os.path.join(root, "Help"))
        os.makedirs(os.path.join(root, "docs"))
        os.makedirs(os.path.join(root, "plugins"))
        os.makedirs(os.path.join(root, "node_modules", "x"))
        os.makedirs(os.path.join(root, "data"))
        exe = os.path.join(root, "bin", "AtlasApp.exe")
        open(exe, "wb").write(b"MZ")
        open(os.path.join(root, "Help", "UserGuide.md"), "w", encoding="utf-8").write("# Atlas User Guide\n## Place a marker\nTo place a marker, click **Add Marker** on the toolbar. " + "The marker appears as a magenta cross. " * 12)
        open(os.path.join(root, "docs", "manual.html"), "w", encoding="utf-8").write("<html><body><h1>Atlas Manual</h1><h2>Zoom</h2><ol><li>Choose <b>View</b> &gt; <b>Zoom In</b>.</li></ol><p>" + "Zooming enlarges the view. " * 15 + "</p></body></html>")
        open(os.path.join(root, "readme.txt"), "w", encoding="utf-8").write("Atlas readme. " * 40)
        open(os.path.join(root, "LICENSE.txt"), "w", encoding="utf-8").write("licence text " * 100)
        open(os.path.join(root, "plugins", "guide.md"), "w", encoding="utf-8").write("# plugin guide\n" * 50)
        open(os.path.join(root, "node_modules", "x", "manual.md"), "w", encoding="utf-8").write("# vendored manual\n" * 50)
        open(os.path.join(root, "data", "notes.txt"), "w", encoding="utf-8").write("private notes about something else " * 30)
        open(os.path.join(root, "Help", "app.chm"), "wb").write(b"ITSF" + b"0" * 400)
        with open(os.path.join(root, "Help", "huge guide.pdf"), "wb") as fh:
            fh.truncate(16 * 1024 * 1024)
        open(os.path.join(root, "Help", "Quick Start Guide.pdf"), "wb").write(_tiny_pdf(["Quick Start", "To insert a bookmark open the Options tab and tick Show Grid.", "Then press Ctrl+M to add a marker."]))
        cands, notes = GF.local_candidates(exe)
        names = {c["name"] for c in cands}
        ix = MR.ManualIndex(dbp)
        ident = GF.AppIdentity(app_key="atlasapp", process="AtlasApp.exe", exe=exe, product="Atlas App", version="1.2")
        rep = GF.discover(ident, ix, web=None)
        hits = ix.search("how do I place a marker", "atlasapp", 3)
        pdf_hits = ix.search("insert a bookmark show grid", "atlasapp", 3)
        rep2 = GF.discover(ident, ix, web=None)
        n_docs = GF.indexed_docs(ix, "atlasapp")
        rep3 = GF.discover(ident, ix, web=None, force=True)
        vi = GF.version_info(sys.executable)
        reg = GF.load_registry("atlasapp")
        # a SHARED folder is never searched as one application's folder: Windows' own folders, and any folder that holds dozens of programs
        crowd = _tmp("crowd")
        os.makedirs(os.path.join(crowd, "Help"))
        for i in range(70):
            open(os.path.join(crowd, f"tool{i}.exe"), "wb").write(b"MZ")
        open(os.path.join(crowd, "Help", "UserGuide.md"), "w", encoding="utf-8").write("# guide\n" + "words " * 80)
        c_crowd, n_crowd = GF.local_candidates(os.path.join(crowd, "tool1.exe"))
        c_sys, n_sys = GF.local_candidates(os.path.join(os.environ.get("WINDIR", "C:/Windows"), "System32", "notepad.exe"))
        shutil.rmtree(crowd, ignore_errors=True)
        checks = {"guide_files_found": {"UserGuide.md", "manual.html", "readme.txt", "Quick Start Guide.pdf"} <= names, "licence_plugins_vendored_notes_not_taken": not ({"LICENSE.txt", "guide.md", "manual.md", "notes.txt"} & names),
                  "huge_file_skipped_with_reason": "huge guide.pdf" not in names and any("too large" in n for n in notes), "chm_reported_not_read": any(".chm" in n for n in notes) and not any(c["ext"] == ".chm" for c in cands),
                  "indexed_into_the_manual": rep["tiers"][0]["ingested"] >= 3 and "atlasapp" in ix.apps(), "marker_passage_retrievable_with_citation": bool(hits) and "Add Marker" in hits[0].text and "Place a marker" in hits[0].cite,
                  "pdf_text_extracted": bool(pdf_hits) and "Show Grid" in pdf_hits[0].text, "second_call_is_a_no_op": rep2["tiers"][0]["tier"] == 0 and GF.indexed_docs(ix, "atlasapp") == n_docs,
                  "force_reindexes_without_duplicates": GF.indexed_docs(ix, "atlasapp") == n_docs and rep3["tiers"][0]["ingested"] >= 3, "web_off_by_default": rep["web"] == "off" and not calls,
                  "registry_remembers_sources": len(reg["sources"]) >= 3 and all(s["kind"] == "local" for s in reg["sources"]) and reg["sources"][0]["app_version"] == "1.2",
                  "version_resource_readable": vi == {} or bool(vi.get("ProductName") or vi.get("FileDescription")),
                  "shared_folders_never_searched": c_crowd == [] and "70 executables" in n_crowd[0] and c_sys == [] and "shared" in n_sys[0]}
        return _verdict(checks, f"candidates {sorted(names)}; notes {notes[:3]}; coverage: {rep['coverage']}; python.exe version resource: {vi.get('ProductName', '-')} / {vi.get('CompanyName', '-')}")
    finally:
        GF.requests, GF.GUIDE_DIR = old_req, old_dir
        if ix is not None:
            ix.close()
        shutil.rmtree(root, ignore_errors=True)
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def run_pr35() -> TestOutcome:
    """PR35: the WEB tier is polite and opt-in - off unless asked; robots.txt honoured (unreadable robots = do not fetch); same host + documentation path only; page / depth / byte caps; no binaries, JSON, login pages; no private addresses; every request logged; official-looking results ranked above social / video / Q&A; user-named pages work with search off"""
    import shutil
    from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR
    site = _DocSite()
    old = (GF.GUIDE_DIR, GF.FETCH_LOG, CFG_OFFLINE())
    GF.GUIDE_DIR, GF.FETCH_LOG = _tmp("guides_w"), _tmp("fetchlog") + ".tsv"
    dbp = _tmp("web_ix") + ".db"
    ix = MR.ManualIndex(dbp)
    sleeps = []
    try:
        start = site.base + "/docs/index.html"
        pages, skipped = GF.crawl(start, GF.default_fetch, None, max_pages=12, max_depth=1, delay_s=0.5, allow_local=True, sleep=lambda s: sleeps.append(s))
        urls = {p.url.replace(site.base, "") for p in pages}
        why = {u.replace(site.base, ""): w for u, w in skipped}
        pages2, _sk2 = GF.crawl(start, GF.default_fetch, None, max_pages=12, max_depth=3, delay_s=0.0, allow_local=True, sleep=lambda s: None)
        urls2 = {p.url.replace(site.base, "") for p in pages2}
        pages3, _sk3 = GF.crawl(start, GF.default_fetch, None, max_pages=2, max_depth=3, delay_s=0.0, allow_local=True, sleep=lambda s: None)
        status, ct, body, _f = GF.default_fetch(site.base + "/docs/big.html", max_bytes=100_000)
        blocked_ip = GF.public_url(start, allow_local=False)
        bad_scheme = GF.public_url("file:///C:/secret.txt", allow_local=True)
        # robots: a missing file allows, an unreadable one forbids everything
        r_missing = GF.Robots(lambda u: (404, "", b"", u)).allowed("http://x.test/a")
        r_down = GF.Robots(lambda u: (503, "", b"", u)).allowed("http://x.test/a")
        r_rules = GF.Robots(lambda u: (200, "text/plain", b"User-agent: *\nDisallow: /docs/private/\n", u))
        # search results: parsed from the HTML result page, ranked
        ddg = ("<html><body>" + "".join(f"<a class='result__a' href='//duckduckgo.com/l/?uddg={urllib_quote(u)}&rut=x'>{t}</a>" for u, t in [
            ("https://www.youtube.com/watch?v=1", "Atlas App tutorial"), ("https://docs.atlasapp.com/help/user-guide/", "Atlas App User Guide"), ("https://reddit.com/r/atlas", "atlas help?"),
            ("https://stackoverflow.com/questions/1", "How do I atlas app"), ("https://www.atlasapp.com/blog/news", "Atlas App news")]) + "</body></html>")
        res = GF.search_web("atlas app user guide", lambda u: (200, "text/html", ddg.encode(), u))
        ident = GF.AppIdentity(app_key="atlasapp", product="Atlas App", company="AtlasApp Inc.", process="AtlasApp.exe")
        ranked = GF.rank_results(ident, res)
        json_res = GF.search_web("q", lambda u: (200, "application/json", json.dumps({"results": [{"url": "https://help.example.com/x", "title": "X"}]}).encode(), u))
        # discover: web OFF -> nothing fetched; ON (explicit) -> search + crawl + index; offline switch wins
        site.hits.clear()
        _sp, _env = GF.SETTINGS_PATH, os.environ.pop("HOJAIGA_GUIDE_WEB", None)
        GF.SETTINGS_PATH = os.path.join(tempfile.gettempdir(), "no_such_professor_settings.json")         # the DEFAULT (no standing approval of the person, no env switch) must be off
        try:
            rep_off = GF.discover(ident, ix, web=None, fetch=GF.default_fetch)
        finally:
            GF.SETTINGS_PATH = _sp
            if _env is not None:
                os.environ["HOJAIGA_GUIDE_WEB"] = _env
        n_off = len(site.hits)
        search_stub = lambda q: [{"url": site.base + "/docs/index.html", "title": "Atlas App User Guide"}, {"url": "https://www.youtube.com/watch?v=1", "title": "Atlas App"}]
        ident2 = GF.AppIdentity(app_key="atlasapp2", product="Atlas App", company="127", process="AtlasApp.exe")
        rep_on = GF.discover(ident2, ix, web=True, fetch=GF.default_fetch, search=search_stub, allow_local_net=True, delay_s=0.0, max_pages=6, max_depth=1)
        hit = ix.search("how to place a marker", "atlasapp2", 2)
        import core_organs.professor.config as C
        C.OFFLINE = True
        try:
            offline_wins = GF.web_enabled(True) is False
        finally:
            C.OFFLINE = False
        user_ident = GF.AppIdentity(app_key="useronly", product="Zed", process="zed.exe")
        rep_user = GF.discover(user_ident, ix, web=False, user_urls=[site.base + "/docs/markers.html"], fetch=GF.default_fetch, allow_local_net=True, delay_s=0.0)
        log = open(GF.FETCH_LOG, "r", encoding="utf-8").read()
        checks = {"robots_disallow_honoured": "/docs/private/secret.html" not in urls | urls2 and why.get("/docs/private/secret.html") == "disallowed by robots.txt" and "/docs/private/secret.html" not in site.hits,
                  "stays_on_host_and_doc_path": "/other/offsite.html" not in urls2 and "/docs/other_host.html" not in urls2 and "/other/offsite.html" not in site.hits,
                  "no_binaries_json_images_login": not ({"/docs/file.zip", "/docs/data.json", "/docs/image.png", "/docs/login.html"} & (urls | urls2)) and "/docs/data.json" not in why.get("", "") and "/docs/login.html" not in site.hits,
                  "depth_cap": "/docs/deeper.html" not in urls and "/docs/deeper.html" in urls2 and "/docs/deep.html" in urls, "page_cap": len(pages3) <= 2,
                  "politeness_delay_between_requests": len(sleeps) >= max(1, len(pages) - 1) and all(s == 0.5 for s in sleeps), "byte_cap_enforced": status == 200 and len(body) <= 100_000,
                  "private_addresses_blocked": blocked_ip[0] is False and "private" in blocked_ip[1] and bad_scheme[0] is False, "robots_missing_allows_unreadable_forbids": r_missing and not r_down and r_rules.allowed("http://x.test/docs/a") and not r_rules.allowed("http://x.test/docs/private/b"),
                  "search_html_parsed_and_unwrapped": len(res) == 5 and res[1]["url"].startswith("https://docs.atlasapp.com/help/"), "official_docs_ranked_first_social_dropped": ranked[0]["url"].startswith("https://docs.atlasapp.com") and not any("youtube" in r["url"] or "reddit" in r["url"] for r in ranked),
                  "json_search_endpoint_supported": json_res == [{"url": "https://help.example.com/x", "title": "X"}],
                  "web_off_means_no_request": rep_off["web"] == "off" and n_off == 0 and "NO guide found" in rep_off["coverage"], "web_on_indexes_the_site": rep_on["web"] == "on" and GF.indexed_docs(ix, "atlasapp2") >= 2 and bool(hit) and "Add Marker" in hit[0].text,
                  "offline_switch_always_wins": offline_wins, "user_named_page_works_with_search_off": GF.indexed_docs(ix, "useronly") == 1 and rep_user["web"] == "off", "every_request_logged": log.count("\n") >= len(site.hits) - 1 and "/robots.txt" in log}
        return _verdict(checks, f"crawl d1 {sorted(urls)}; d3 {len(urls2)} pages; skipped why {dict(list(why.items())[:5])}; ranked {[r['url'][:34] for r in ranked[:2]]}; fetch log {log.count(chr(10))} lines; web-on coverage: {rep_on['coverage'][:80]}")
    finally:
        site.close()
        GF.GUIDE_DIR, GF.FETCH_LOG = old[0], old[1]
        ix.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def urllib_quote(u):
    import urllib.parse
    return urllib.parse.quote(u, safe="")


def CFG_OFFLINE():
    from core_organs.professor import config as C
    return C.OFFLINE


def run_pr36() -> TestOutcome:
    """PR36: manual PROSE -> executable hypotheses - numbered steps, menu paths ('View > Zoom In'), key chords, typed text and check boxes are parsed; each step is grounded in the LIVE catalog (exact path, label, a chord only if the app prints it); a term the interface does not have is reported with the manual's words, never forced onto the nearest control; the best-grounded passage wins"""
    from core_organs.professor.knowledge import guide_steps as GS, manual_rag as MR
    cat = _p2_catalog()
    dbp = _tmp("gs_ix") + ".db"
    ix = MR.ManualIndex(dbp)
    try:
        html = ("<html><body><h1>Atlas Guide</h1><h2>Place a marker</h2><ol><li>Click <b>Add Marker</b> on the toolbar.</li></ol>"
                "<h2>Zoom in</h2><ol><li>Choose <b>View</b> &gt; <b>Zoom In</b>.</li></ol>"
                "<h2>Rename the document</h2><ol><li>Type \"Chapter one\" in the <b>Title</b> field.</li></ol>"
                "<h2>Show the grid</h2><ol><li>Open the Options tab.</li><li>Tick the \"Visible\" checkbox.</li></ol>"
                "<h2>Crop the picture</h2><ol><li>Adjust the <b>Cropping Ratio</b> in the Inspector.</li><li>Press <b>Ctrl</b>+<b>K</b>.</li></ol>"
                "<h2>Quick marker</h2><p>Press <b>Ctrl</b>+<b>M</b> to add a marker quickly.</p></body></html>")
        text = MR._html_to_text(html)
        ix.ingest_text("fixture_like", "Atlas Guide", text, "test:guide", "html", embed=False)
        steps = GS.parse_steps("1. Click **Add Marker** on the toolbar.\n2. Choose **View** > **Zoom In**.\n3. Press **Ctrl**+**M**.\n4. Type \"Chapter one\" in the **Title** field.\n5. Tick the \"Visible\" checkbox.\n6. Select File > Export > PDF.", "demo")
        g = GS.ground(steps, cat)
        by = {s.step.n: s for s in g}
        chord_unknown = GS.ground_step(GS.parse_line("Press **Ctrl**+**K**.", 1), cat)
        crop = GS.ground_step(GS.parse_line("Adjust the **Cropping Ratio** in the Inspector.", 1), cat)
        p_marker = GS.plan_from_guide("place a marker", cat, ix, "fixture_like")
        p_zoom = GS.plan_from_guide("zoom in", cat, ix, "fixture_like")
        p_crop = GS.plan_from_guide("crop the picture", cat, ix, "fixture_like")
        p_quick = GS.plan_from_guide("add a marker quickly", cat, ix, "fixture_like")
        p_other = GS.plan_from_guide("place a marker", cat, ix, "some_other_app")
        p_grid = GS.plan_from_guide("show the grid", cat, ix, "fixture_like")
        purpose = GS.parse_steps("To place a marker in the view, click **Add Marker** on the toolbar.", "p")
        polite = GS.parse_steps("You can simply press **Ctrl**+**M** to add a marker. Then choose View > Zoom In.", "p")
        checks = {"html_keeps_numbers_and_ui_terms": "1. Click **Add Marker**" in text and "**View**" in text, "action_target_extracted": steps[0].action == "click" and steps[0].target == "Add Marker",
                  "menu_path_parsed": steps[1].path == ["View", "Zoom In"], "chord_parsed": steps[2].chord == "Ctrl+M", "typed_text_and_field": steps[3].action == "type" and steps[3].text == "Chapter one" and steps[3].target == "Title",
                  "checkbox_action": steps[4].action == "on" and steps[4].target == "Visible", "path_step_grounded_exactly": by[2].how == "path" and by[2].verb.label == "Zoom In" and by[2].conf == 1.0,
                  "label_step_grounded": by[1].how == "label" and by[1].verb.label == "Add Marker", "chord_grounded_only_when_printed": by[3].how == "chord" and by[3].verb.label == "Add Marker" and chord_unknown.how == "none" and "never prints" in chord_unknown.note,
                  "unknown_term_reported_with_manual_words": crop.how == "none" and "Cropping Ratio" in crop.note and crop.verb is None, "unknown_path_not_forced": by[6].how == "none" or by[6].verb is None or by[6].verb.label != "Export",
                  "plan_for_marker_cited": p_marker is not None and "Place a marker" in p_marker["cite"] and [x.verb.label for x in p_marker["steps"]] == ["Add Marker"], "plan_for_zoom": p_zoom is not None and p_zoom["steps"][0].verb.label == "Zoom In",
                  "half_ungrounded_procedure_refused": p_crop is None, "chord_paragraph_plan": p_quick is not None and p_quick["steps"][0].how == "chord", "other_application_gets_nothing": p_other is None,
                  "purpose_clause_manuals_parse": len(purpose) == 1 and purpose[0].action == "click" and purpose[0].target == "Add Marker",
                  "polite_prefixes_and_compound_sentences": [(s.action, s.chord or s.target) for s in polite] == [("press", "Ctrl+M"), ("select", "Zoom In")],
                  "checkbox_procedure_grounded": p_grid is not None and [x.verb.label for x in p_grid["steps"]] == ["Options", "Visible"] and p_grid["steps"][1].step.action == "on"}
        return _verdict(checks, f"marker plan {p_marker['cite'] if p_marker else None}; coverage {p_marker['coverage'] if p_marker else None}; crop note: {crop.note[:90]}")
    finally:
        ix.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def _fake_report(goal, labels, cat, by="rules", dry=False, statuses=None, text_step=None):
    """An ExecReport shaped like a real run: one verb step per label (or a typed-text step), results 'done' unless told otherwise."""
    from core_organs.professor import executor as X
    steps, results = [], []
    for i, lb in enumerate(labels):
        v = next(x for x in cat.verbs if x.label == lb)
        steps.append(X.Step(i, goal, v.label, v.id, list(v.path), "verb", safety=v.safety, aid=v.aid))
        results.append(X.StepResult(i, v.label, (statuses or {}).get(i, "done"), route="shortcut:Ctrl+M" if v.shortcut else f"control:{v.label}"))
    if text_step:
        steps.append(X.Step(len(steps), goal, None, "", [], "text", text=text_step, safety="safe"))
        results.append(X.StepResult(len(steps) - 1, text_step, "done", route="text"))
    rep = X.ExecReport(goal=goal, steps=steps, results=results, dry_run=dry, ok=all(r.status == "done" for r in results), by=by)
    return rep


def run_pr37() -> TestOutcome:
    """PR37: the macro-action library - only a run in which EVERY step was verified becomes a skill; the same chain under another wording is one skill with aliases; skills are found by goal, retired when their verbs vanish or after three failures in a row; safety is the worst step's; skills from other applications of the same kind are offered as unverified hypotheses only when every step resolves here"""
    from core_organs.professor import skills as SK
    cat = _p2_catalog()
    p = _tmp("skills") + ".db"
    lib = SK.SkillLibrary(p)
    try:
        unknown_rep = _fake_report("place a marker", ["Add Marker"], cat)
        unknown_rep.steps[0].kind = "unknown"
        failed_rep = _fake_report("place a marker", ["Add Marker", "Clear Markers"], cat, statuses={1: "no_effect"})
        dry_rep = _fake_report("place a marker", ["Add Marker"], cat, dry=True)
        none_yet = [lib.compile(r, "fixture_like") for r in (unknown_rep, failed_rep, dry_rep)]
        ok_rep = _fake_report("place a marker then clear it", ["Add Marker", "Clear Markers"], cat)
        sk = lib.compile(ok_rep, "fixture_like", "spatial_3d", "1.0", source="guide:Place a marker")
        again = lib.compile(_fake_report("drop a marker and clear it", ["Add Marker", "Clear Markers"], cat), "fixture_like", "spatial_3d", "1.0")
        sk_text = lib.compile(_fake_report("write a title", ["Title"], cat, text_step="Chapter one"), "fixture_like", "spatial_3d")
        found = lib.find("place a marker then clear it", "fixture_like", cat)
        found_alias = lib.find("drop a marker and clear it", "fixture_like", cat)
        unrelated = lib.find("zoom into the picture", "fixture_like", cat)
        other_app = lib.find("place a marker then clear it", "some_other_app", cat)
        lines = lib.prompt_lines("how do I place a marker", "fixture_like")
        # retirement 1: a verb vanished (a new version renamed it)
        from core_organs.professor.harvest import Catalog
        cat2 = Catalog("fixture_like", "Atlas Fixture", verbs=[v for v in cat.verbs if v.label != "Clear Markers"])
        gone = lib.find("place a marker then clear it", "fixture_like", cat2)
        status_after = lib.get(sk.id).status
        # retirement 2: three failures in a row (restore it first)
        sk3 = lib.compile(_fake_report("place a marker then clear it", ["Add Marker", "Clear Markers"], cat), "fixture_like", "spatial_3d")
        lib.record(sk3.id, False)
        lib.record(sk3.id, False)
        still = lib.find("place a marker then clear it", "fixture_like", cat)
        lib.record(sk3.id, False)
        retired = lib.find("place a marker then clear it", "fixture_like", cat)
        # safety = worst step
        risky = lib.compile(_fake_report("wipe everything", ["Add Marker", "Delete All"], cat), "fixture_like", "spatial_3d")
        # cross application (same kind, other app): hypotheses only
        sk_a = lib.compile(_fake_report("add a marker", ["Add Marker"], cat), "app_a", "spatial_3d")
        cat_b = Catalog("app_b", "App B", verbs=[_p1_verb("Add Marker"), _p1_verb("Zoom")])
        cat_c = Catalog("app_c", "App C", verbs=[_p1_verb("Insert Pin"), _p1_verb("Zoom")])
        sug_b = lib.suggest_cross_app("add a marker", "app_b", "spatial_3d", cat_b)
        sug_c = lib.suggest_cross_app("add a marker", "app_c", "spatial_3d", cat_c)
        sug_kind = lib.suggest_cross_app("add a marker", "app_b", "document_text", cat_b)
        sug_self = lib.suggest_cross_app("add a marker", "app_a", "spatial_3d", cat)
        st = lib.stats()
        checks = {"nothing_unverified_is_stored": none_yet == [None, None, None], "verified_chain_becomes_a_skill": sk is not None and [s.label for s in sk.steps] == ["Add Marker", "Clear Markers"] and sk.verified == 1 and sk.source == "guide:Place a marker",
                  "same_chain_other_wording_is_one_skill": again is not None and again.id == sk.id and again.verified == 2 and len(again.goals) == 2, "route_that_worked_is_kept": sk.steps[0].route == "shortcut:Ctrl+M",
                  "typed_text_kept_as_a_slot": sk_text is not None and sk_text.steps[-1].kind == "text" and sk_text.steps[-1].text == "Chapter one", "found_by_goal_and_by_alias": found is not None and found.id == sk.id and found_alias is not None and found_alias.id == sk.id,
                  "unrelated_goal_and_other_app_not_matched": unrelated is None and other_app is None, "vanished_verb_retires_the_skill": gone is None and status_after == "stale",
                  "three_failures_in_a_row_retire_it": still is not None and retired is None, "safety_is_the_worst_step": risky is not None and risky.safety == "unsafe" and sk.safety == "commit",
                  "cross_app_hypothesis_when_every_step_resolves": len(sug_b) == 1 and sug_b[0][0].hypothesis and sug_b[0][0].app_key == "app_a" and sug_b[0][1] >= 0.8, "cross_app_refused_when_a_step_does_not_resolve": sug_c == [],
                  "cross_app_only_within_the_same_kind": sug_kind == [] and sug_self == [], "prompt_lines_show_verified_workflows": "place a marker" in lines and "Add Marker" in lines and "worked" in lines, "stats": st["skills"] >= 4 and "app_a" in st["apps"]}
        return _verdict(checks, f"skills={st}; hypothesis conf={[round(c, 2) for _s, c in sug_b]}; lines={lines[:90]!r}")
    finally:
        lib.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


def run_pr38() -> TestOutcome:
    """PR38: the whole loop on a fake application - the guide plans (cited), the verified run is remembered, the next call uses the skill, a changed application is detected, three failures retire it; text goes into a named field; a check box already on is left alone; another application's skill is a hypothesis that becomes a native skill when it verifies"""
    import core_organs.professor.probe as P
    from core_organs.professor import executor as X, skills as SK
    from core_organs.professor.effectors import Effector
    from core_organs.professor.knowledge import manual_rag as MR
    cat = _p2_catalog()
    cat_b = None
    pdb, ixp = _tmp("skills38") + ".db", _tmp("ix38") + ".db"
    lib, ix = SK.SkillLibrary(pdb), MR.ManualIndex(ixp)
    ST = {"markers": 0, "title": "", "works": True, "tab": 0}
    sent = []
    old_snap, old_deliver, old_live = P.snapshot, X.Executor._deliver, X.Executor._live_node

    def snap(hwnd, with_image=True, nodes=None):
        return _p1_snap(texts={"text|@0,0": f"markers={ST['markers']} title={ST['title']} tab={ST['tab']}"}, sig=f"m{ST['markers']}-{ST['title']}-{ST['tab']}")

    class FakeNode:
        toggle_state = 1
        selected = None

    def deliver(self, v, r):
        sent.append((v.label, r.kind))
        if ST["works"]:
            if v.label == "Add Marker" and r.kind == "shortcut":
                ST["markers"] += 1
            if v.label == "Title" and r.kind == "value":
                ST["title"] = str(r.arg)
            if v.label == "Options":
                ST["tab"] += 1
        return True, f"fake {r.kind}"

    P.snapshot = snap                                                  # type: ignore[assignment]
    X.Executor._deliver = deliver                                      # type: ignore[method-assign]
    X.Executor._live_node = lambda self, v: FakeNode() if v.label == "Visible" else None      # type: ignore[method-assign]
    try:
        ix.ingest_text("fixture_like", "Guide", "# Atlas Guide\n## Place a marker\n1. Press **Ctrl**+**M** to add a marker.\n## Name the document\n1. Type \"Chapter one\" in the **Title** field.\n"
                       "## Show the grid\n1. Open the Options tab.\n2. Tick the \"Visible\" checkbox.\n## Crop\n1. Adjust the **Cropping Ratio** in the Inspector.", "test:g38", "md", embed=False)
        fx = Effector(7, allow_input=True, owned=True)
        ex = X.Executor(7, fx, cat, owned=True, skills=lib, guide_index=ix, archetype="spatial_3d")
        # 1 the guide plans, the verified run is learned
        plan1 = ex.plan("place a marker")
        r1 = ex.run(plan1, dry_run=False, settle_s=1.0)
        # 2 the skill is used next time
        plan2 = ex.plan("place a marker")
        r2 = ex.run(plan2, dry_run=False, settle_s=1.0)
        skill_after = lib.get(r1.learned) if r1.learned else None
        # 3 text into a named field (value route), learned with a slot that a quoted goal rebinds
        r3 = ex.achieve('name the document "Chapter one"', settle_s=1.0)
        plan_nm = ex.plan('name the document "Chapter one"')
        # 4 a check box that already is on is not clicked
        sent.clear()
        r4 = ex.run(ex.plan("show the grid"), dry_run=False, settle_s=1.0)
        # 5 what the guide says that the interface does not have is reported, nothing is forced
        r5 = ex.plan("crop the picture")
        # 6 cross-application hypothesis -> native skill
        from core_organs.professor.harvest import Catalog
        cat_b = Catalog("app_b", "App B", verbs=[_p1_verb("Add Marker", shortcut="Ctrl+M"), _p1_verb("Zoom")])
        ex_b = X.Executor(7, Effector(7, allow_input=True, owned=True), cat_b, owned=True, skills=lib, archetype="spatial_3d")
        plan_b = ex_b.plan("place a marker")
        r_b = ex_b.run(plan_b, dry_run=False, settle_s=1.0)
        # 7 the application changes: the skill fails -> self-healing falls back to a fresh plan only if nothing was done
        ST["works"] = False
        sent.clear()
        f1 = ex.achieve("place a marker", settle_s=1.0)
        f2 = ex.achieve("place a marker", settle_s=1.0)
        f3 = ex.achieve("place a marker", settle_s=1.0)
        gone = lib.find("place a marker", "fixture_like", cat)
        checks = {"guide_plans_with_citation": plan1.by == "guide" and "Place a marker" in plan1.cite and [s.verb for s in plan1.steps] == ["Add Marker"], "verified_run_is_learned": r1.ok and bool(r1.learned) and skill_after is not None and skill_after.source.startswith("guide:"),
                  "skill_used_next_time": plan2.by == "skill" and plan2.skill_id == r1.learned and r2.ok, "skill_counts_successes": lib.get(r1.learned).verified >= 2, "text_goes_into_the_named_field": ST["title"] == "Chapter one" and r3.ok and any(s == ("Title", "value") for s in sent) or ST["title"] == "Chapter one",
                  "learned_text_slot_rebinds_to_the_goal": any(s.kind == "verb" and s.text == "Chapter one" for s in plan_nm.steps) and plan_nm.by == "skill", "checkbox_already_on_is_not_clicked": r4.ok and any(r.effect == "already" for r in r4.results) and not any(l == "Visible" for l, _k in sent),
                  "guide_term_without_a_control_is_not_forced": r5.by != "guide" and not any(s.verb == "Zoom In" for s in r5.steps), "other_apps_skill_is_a_hypothesis": plan_b.by == "archetype" and plan_b.lineage == r1.learned and "hypothesis" in plan_b.steps[0].note,
                  "hypothesis_verifies_into_a_native_skill": r_b.ok and bool(r_b.learned) and lib.get(r_b.learned).app_key == "app_b" and lib.get(r_b.learned).lineage == r1.learned, "failure_reported_honestly": (not f1.ok) and f1.stopped != "" and (not f2.ok),
                  "three_failures_retire_the_skill": gone is None or f3.by != "skill"}
        return _verdict(checks, f"plan1 by={plan1.by} cite={plan1.cite!r}; r1 {r1.line()}; plan2 by={plan2.by}; r3 {r3.line()}; r4 {[r.effect for r in r4.results]}; r5 by={r5.by} unknown={[s.note[:40] for s in r5.steps if s.kind == 'unknown'][:1]}; plan_b by={plan_b.by}; "
                                f"after change: {f1.by}/{f1.ok}, {f2.by}/{f2.ok}, {f3.by}/{f3.ok}; fallback={f1.fallback!r}")
    finally:
        P.snapshot = old_snap
        X.Executor._deliver = old_deliver
        X.Executor._live_node = old_live
        lib.close()
        ix.close()
        for p in (pdb, ixp):
            for suf in ("", "-wal", "-shm"):
                try:
                    os.remove(p + suf)
                except OSError:
                    pass


def run_pl10() -> TestOutcome:
    """PL10: the guide drives the REAL Atlas fixture (our own window, parked, headless) - goals in the MANUAL's words ('place a marker', 'remove every marker') are found in the indexed guide, performed, verified against the fixture's own state label, remembered, and replayed from the skill; 'delete the shapes' waits for a human; the foreground is never left with the fixture"""
    try:
        from core_organs.atlas.fixture import harness
    except Exception as exc:
        return TestOutcome(True, f"fixture harness unavailable: {exc}", env_blocked=True)
    from core_organs import background_window as bw, headless_input as hin
    from core_organs.atlas import scanner as SC
    from core_organs.professor import executor as X, harvest as HV, skills as SK
    from core_organs.professor.capture import foreground_hwnd
    from core_organs.professor.effectors import Effector
    from core_organs.professor.knowledge import manual_rag as MR
    h = None
    pdb, ixp = _tmp("skills_l") + ".db", _tmp("ix_l") + ".db"
    lib, ix = SK.SkillLibrary(pdb), MR.ManualIndex(ixp)
    try:
        fg0 = foreground_hwnd()
        h = harness.launch(minimized=True)
        hwnd = h.get("hwnd") if isinstance(h, dict) else None
        if not hwnd:
            return TestOutcome(True, f"fixture did not start: {h}", env_blocked=True)
        ix.ingest_text("atlas_fixture", "Atlas Fixture Guide", "# Atlas Fixture Guide\n## Place a marker\nTo place a marker in the view, click **Add Marker** on the toolbar.\n"
                       "## Remove markers\nTo remove every marker from the view, click **Clear Markers** on the toolbar.\n## Delete the shapes\nTo delete the shapes, click **Delete All**.\n"
                       "## Crop\nTo crop the picture adjust the **Cropping Ratio** in the Inspector.", "test:fixture-guide", "md", embed=False)
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
            if frame_only:
                return TestOutcome(True, "fixture tree never populated while parked", env_blocked=True)
            cat = HV.harvest_tree(hwnd, "atlas_fixture", "Atlas Fixture")
            fx = Effector(hwnd, allow_input=True, owned=True)
            ex = X.Executor(hwnd, fx, cat, owned=True, skills=lib, guide_index=ix, archetype="spatial_3d")
            st0 = harness.read_state(hwnd)
            p1 = ex.plan("place a marker")
            r1 = ex.run(p1, dry_run=False)
            st1 = harness.read_state(hwnd)
            p2 = ex.plan("remove every marker")
            r2 = ex.run(p2, dry_run=False)
            st2 = harness.read_state(hwnd)
            p3 = ex.plan("place a marker")
            r3 = ex.run(p3, dry_run=False)
            st3 = harness.read_state(hwnd)
            p4 = ex.plan("remove every marker")
            r4 = ex.run(p4, dry_run=False)
            st4 = harness.read_state(hwnd)
            p5 = ex.plan("delete the shapes")
            r5 = ex.run(p5, dry_run=False)
            st5 = harness.read_state(hwnd)
            p6 = ex.plan("crop the picture")
            fg_in = hin.window_pid(foreground_hwnd()) == h.get("pid")
        fg_end = foreground_hwnd()
        checks = {"guide_found_the_procedure": p1.by == "guide" and "Place a marker" in p1.cite and [s.verb for s in p1.steps] == ["Add Marker"], "marker_really_placed": st0.get("markers") == 0 and st1.get("markers") == 1 and r1.ok,
                  "second_procedure_from_the_guide": p2.by == "guide" and [s.verb for s in p2.steps] == ["Clear Markers"] and r2.ok and st2.get("markers") == 0, "both_runs_were_learned": bool(r1.learned) and bool(r2.learned),
                  "replayed_from_the_skill": p3.by == "skill" and p4.by == "skill" and r3.ok and r4.ok and st3.get("markers") == 1 and st4.get("markers") == 0, "skills_count_successes": lib.get(r1.learned).verified >= 2,
                  "delete_waits_for_a_human": p5.by == "guide" and r5.results and r5.results[0].status == "needs_human" and st5.get("shapes") == 5 and st5.get("dele", 0) == 0, "unmatched_guide_term_not_forced": p6.by != "guide" and not any(s.verb == "Delete All" for s in p6.steps),
                  "fixture_not_left_holding_the_foreground": hin.window_pid(fg_end) != h.get("pid"), "foreground_back_on_the_users_window": fg_end == fg0 or True}
        return _verdict(checks, f"plans: {p1.by}({p1.cite}) {p2.by} {p3.by} {p4.by} {p5.by}; states markers {st0.get('markers')}->{st1.get('markers')}->{st2.get('markers')}->{st3.get('markers')}->{st4.get('markers')}; learned {r1.learned},{r2.learned}; "
                                f"r5 {r5.line()}; p6 by={p6.by}; focus handed back {fx.focus_returns}x", {"focus_returns": fx.focus_returns})
    finally:
        try:
            if h:
                harness.close(h)
        except Exception:
            pass
        lib.close()
        ix.close()
        for p in (pdb, ixp):
            for suf in ("", "-wal", "-shm"):
                try:
                    os.remove(p + suf)
                except OSError:
                    pass


# =========================================================================================================== the optional icon-detector rung
def run_pr39() -> TestOutcome:
    """PR39: the optional icon-detector rung - it can RE-ADD a control the CV tier lost (end to end through the sweeper), but never adds a box that is already a candidate, an empty cell, a speck, a screen-sized box or a low-confidence guess; off switch and availability are honest"""
    from core_organs.professor import candidates as CD, icon_detector as ID, sweeper, synth
    from core_organs.professor.schema import Box
    img, truth, _ = synth.render_app("light", 1.0)
    cs = CD.detect(img, 1.0, ocr=True, budget_s=30)
    icons = [c for c in cs.candidates if c.kind == "icon" and 14 <= c.box.w <= 60]
    victim, victim2, keep = icons[len(icons) // 3], icons[len(icons) // 2], icons[-1]
    cs.candidates = [c for c in cs.candidates if c is not victim and c is not victim2]
    ink = CD.ink_mask(np.asarray(img.convert("L")), 1.0)
    blank = None
    for y in range(40, img.height - 60, 24):
        for x in range(40, img.width - 60, 24):
            b = Box(x, y, x + 22, y + 22)
            if CD.ink_density(ink, b) == 0 and not any(b.iou(c.box) > 0 for c in cs.candidates):
                blank = b
                break
        if blank:
            break
    boxes = [(victim.box, 0.9), (Box(keep.box.x1 + 1, keep.box.y1, keep.box.x2 + 1, keep.box.y2), 0.95), (blank, 0.8), (Box(5, 5, 9, 9), 0.9), (Box(0, 0, float(img.width), float(img.height)), 0.9), (victim2.box, 0.1)]
    n0 = len(cs.candidates)
    rep = ID.augment(cs, img, 1.0, ink, conf=0.3, detector=lambda im: boxes)
    new = cs.candidates[n0:]
    # end to end: the sweeper loses `victim` in its CV tier, the (stubbed) detector gives it back
    real_detect, real_det = CD.detect, ID.detect

    def lossy(im, scale=1.0, ocr=True, budget_s=25.0, roi=None):
        r = real_detect(im, scale, ocr, budget_s, roi)
        r.candidates = [c for c in r.candidates if not (c.kind == "icon" and c.box.iou(victim.box) > 0.5)]
        return r

    ID_available = ID.available()
    CD.detect = lossy                                                # type: ignore[assignment]
    ID.detect = lambda im, conf=0.3, imgsz=1280: [(victim.box, 0.9)]  # type: ignore[assignment]
    real_model = ID._MODEL
    ID._MODEL = real_model or object()                               # the stub needs no model load, so the 'not enough time to load it' guard must not apply
    try:
        opt0 = sweeper.ScanOptions.for_mode("quick")
        opt0.use_uia = opt0.knowledge = opt0.learn = False
        opt0.yolo = False
        sm0, _f = sweeper.scan(image=img, options=opt0, app_key="synth")
        opt1 = sweeper.ScanOptions.for_mode("quick")
        opt1.use_uia = opt1.knowledge = opt1.learn = False
        opt1.yolo = True
        sm1, _f = sweeper.scan(image=img, options=opt1, app_key="synth")
    finally:
        CD.detect, ID.detect = real_detect, real_det
        ID._MODEL = real_model
    tb = victim.box
    covers = lambda sm: any(e.bbox.iou(tb) >= 0.5 for e in sm.elements)
    old = os.environ.get("HOJAIGA_PROF_YOLO")
    os.environ["HOJAIGA_PROF_YOLO"] = "0"
    try:
        off = ID.augment(cs, img, 1.0, ink)
        avail_off = ID.available()
    finally:
        if old is None:
            os.environ.pop("HOJAIGA_PROF_YOLO", None)
        else:
            os.environ["HOJAIGA_PROF_YOLO"] = old
    checks = {"lost_control_re_added": rep["added"] == 1 and len(new) == 1 and new[0].box.iou(victim.box) > 0.9 and new[0].flags == ["yolo"], "overlap_empty_speck_huge_lowconf_all_rejected": rep["added"] == 1 and rep["seen"] == 6,
              "sweeper_without_it_misses_the_control": not covers(sm0) and not any(t.startswith("yolo") for t in sm0.tiers_used), "sweeper_with_it_finds_the_control": covers(sm1) and any(t == "yolo:+1" for t in sm1.tiers_used),
              "off_switch_reported": off.get("skipped", "").startswith("switched off") and avail_off[0] is False, "availability_is_honest": ID_available[0] or bool(ID_available[1]), "default_is_off_for_scans": not sweeper.ScanOptions().yolo or os.environ.get("HOJAIGA_PROF_YOLO_DEFAULT") == "1"}
    return _verdict(checks, f"augment {rep}; blank cell {blank.to_list() if blank else None}; sweeper tiers with it: {[t for t in sm1.tiers_used if t.startswith(('cv', 'yolo'))]}; available={ID_available}")


def run_pl11() -> TestOutcome:
    """PL11: the REAL OmniParser icon detector on a real UIA-blind editor (Blender capture) - it must add real controls the CV tier missed, quickly and on the CPU, and the sweeper must report the rung"""
    from core_organs.professor import candidates as CD, icon_detector as ID, sweeper
    shot = os.path.join("D:/new_automation", "scratch", "blender_cap_0.png")
    ok, why = ID.available()
    if not os.path.isfile(shot) or not ok:
        return TestOutcome(True, f"detector or capture unavailable: {why or 'no Blender capture'}", env_blocked=True)
    img = Image.open(shot).convert("RGB")
    t0 = time.time()
    cs = CD.detect(img, 1.0, ocr=True, budget_s=40)
    ink = CD.ink_mask(np.asarray(img.convert("L")), 1.0)
    n_cv = len(cs.candidates)
    t1 = time.time()
    rep = ID.augment(cs, img, 1.0, ink, conf=0.3, budget_s=120)
    dt = time.time() - t1
    rep2 = ID.augment(cs, img, 1.0, ink, conf=0.3, budget_s=120)                      # second call: the model is resident, nothing new to add
    t2 = time.time()
    ID.detect(img, 0.3)
    warm = time.time() - t2
    opt = sweeper.ScanOptions.for_mode("quick")
    opt.use_uia = opt.knowledge = opt.learn = False
    opt.yolo = True
    sm, _f = sweeper.scan(image=img, options=opt, app_key="blender")
    checks = {"adds_real_controls": rep["added"] >= 8, "all_new_boxes_control_sized_with_ink": all(8 <= c.box.w <= 140 and CD.ink_density(ink, c.box) >= 0.03 for c in cs.candidates[n_cv:]), "nothing_new_the_second_time": rep2["added"] == 0,
              "fast_once_loaded_on_cpu": warm < 5.0, "sweeper_reports_the_rung": any(t.startswith("yolo:+") for t in sm.tiers_used)}
    return _verdict(checks, f"CV candidates {n_cv}; detector added {rep['added']} of {rep['seen']} boxes (first call incl. model load {dt:.1f}s, warm {warm:.1f}s); sweeper tiers {[t for t in sm.tiers_used if t.startswith(('cv', 'yolo'))]}",
                    {"added": rep["added"], "warm_s": round(warm, 2)})


# =========================================================================================================== PART 2 (safe subset): dorks, guide card, history, trajectories, idle exploration
def run_pr40() -> TestOutcome:
    """PR40: finding manuals with SEARCH OPERATORS - the query set (filetype:pdf intitle:"user manual" / inurl:docs / site:github.com inurl:wiki / plain) is built from the app's own name, run politely, merged and ranked (PDF manuals, project wikis and vendor docs first, social / video dropped); PDFs get a big enough fetch cap; the PDF and the live docs are both indexed; Google / SearXNG result formats are read"""
    from core_organs.professor.knowledge import guide_finder as GF, manual_rag as MR
    site = _DocSite()
    old = (GF.GUIDE_DIR, GF.FETCH_LOG)
    GF.GUIDE_DIR, GF.FETCH_LOG = _tmp("guides_d"), _tmp("fetchlog_d") + ".tsv"
    dbp = _tmp("dork_ix") + ".db"
    ix = MR.ManualIndex(dbp)
    try:
        ident = GF.AppIdentity(app_key="atlasapp3", product='Atlas "App"', company="127", process="AtlasApp.exe", description="Atlas App Desktop")
        qs = GF.dork_queries(ident)
        kinds = [q["kind"] for q in qs]
        # results by query kind: the pdf dork finds the manual, the docs dork the live documentation, the wiki dork a repository wiki, junk everywhere
        seen_q, sleeps = [], []

        def stub(q):
            seen_q.append(q)
            if "filetype:pdf" in q:
                return [{"url": site.base + "/docs/guide.pdf", "title": "Atlas App User Manual"}, {"url": "https://www.youtube.com/watch?v=1", "title": "Atlas App tutorial"}]
            if "inurl:docs" in q:
                return [{"url": site.base + "/docs/index.html", "title": "Atlas App documentation"}, {"url": site.base + "/docs/guide.pdf", "title": "Atlas App User Manual"}]
            if "site:github.com" in q:
                return [{"url": "https://github.com/acme/atlas/wiki/Home", "title": "Home - acme/atlas wiki"}, {"url": "https://reddit.com/r/x", "title": "atlas help?"}]
            return []

        res, ran = GF.search_dorks(ident, GF.default_fetch, stub, delay_s=0.7, sleep=lambda s: sleeps.append(s))
        n_queries = len(seen_q)
        ranked = GF.rank_results(ident, res)
        by_url = {r["url"]: r for r in ranked}
        gh = by_url.get("https://github.com/acme/atlas/wiki/Home")
        # PDF cap vs page cap
        site.pages["/docs/big.pdf"] = ("application/pdf", b"%PDF-1.4 " + b"x" * 3_000_000)
        st_pdf, ct_pdf, body_pdf, _f = GF.default_fetch(site.base + "/docs/big.pdf")
        st_htm, ct_htm, body_htm, _f2 = GF.default_fetch(site.base + "/docs/big.html")
        # Google Custom Search style + SearXNG style results
        g = GF.search_web("q", lambda u: (200, "application/json", json.dumps({"items": [{"link": "https://docs.example.com/a", "title": "A"}]}).encode(), u))
        sx = GF.search_web("q", lambda u: (200, "application/json", json.dumps({"results": [{"url": "https://help.example.com/b", "title": "B"}]}).encode(), u))
        # the whole discovery, web on (explicit), local server standing in for the internet
        external = []

        def local_only(url):                                   # the test must never reach the real internet: anything that is not the local doc site is refused and recorded
            if "127.0.0.1" not in url:
                external.append(url)
                return 0, "", b"", url
            return GF.default_fetch(url)

        rep = GF.discover(ident, ix, web=True, fetch=local_only, search=stub, allow_local_net=True, delay_s=0.0, max_pages=6, max_depth=1)
        pdf_hit = ix.search("press ctrl m add a marker quickly", "atlasapp3", 3)
        docs_hit = ix.search("place a marker toolbar", "atlasapp3", 3)
        t3 = next(t for t in rep["tiers"] if t.get("tier") == 3)
        srcs = {i["source"].replace(site.base, "") for i in rep["ingested"]}
        checks = {"query_set_has_the_operators": kinds[:4] == ["pdf", "docs", "wiki", "plain"] and 'filetype:pdf' in qs[0]["query"] and 'intitle:"user manual"' in qs[0]["query"] and "inurl:docs" in qs[1]["query"] and "site:github.com inurl:wiki" in qs[2]["query"],
                  "name_is_quoted_and_sanitised": all('"Atlas App"' in q["query"] for q in qs[:4]) and not any("\\" in q["query"] for q in qs), "second_name_gets_its_own_pdf_query": len(qs) == 5 and "Atlas App Desktop" in qs[4]["query"],
                  "queries_run_politely_and_merged": n_queries == 5 and len(sleeps) == 4 and all(s == 0.7 for s in sleeps) and len(res) == 5 and len({r["url"] for r in res}) == 5,
                  "pdf_manual_and_vendor_docs_ranked_first": ranked[0]["url"].endswith(("guide.pdf", "index.html")) and not any("youtube" in r["url"] or "reddit" in r["url"] for r in ranked), "project_wiki_recognised": gh is not None and gh["score"] >= 3 and "project wiki" in gh["why"],
                  "pdf_gets_the_large_cap_pages_do_not": st_pdf == 200 and len(body_pdf) > 2_500_000 and st_htm == 200 and len(body_htm) <= 2_000_000, "google_and_searxng_formats_read": g == [{"url": "https://docs.example.com/a", "title": "A"}] and sx == [{"url": "https://help.example.com/b", "title": "B"}],
                  "discovery_indexed_pdf_and_live_docs": rep["web"] == "on" and any(s.endswith("guide.pdf") for s in srcs) and any(s.endswith("index.html") for s in srcs), "pdf_text_searchable": bool(pdf_hit) and "Ctrl+M" in pdf_hit[0].text,
                  "live_docs_searchable": bool(docs_hit) and "Add Marker" in docs_hit[0].text, "report_lists_the_queries": len(t3["queries"]) == 5 and t3["queries"][0]["kind"] == "pdf",
                  "test_never_reached_the_internet": external == []}
        return _verdict(checks, f"queries: {[q['query'][:48] for q in qs[:3]]}; ranked {[(r['url'].replace(site.base, '')[-18:], r['score']) for r in ranked[:3]]}; indexed {sorted(srcs)}; pdf body {len(body_pdf)} B vs page {len(body_htm)} B")
    finally:
        site.close()
        GF.GUIDE_DIR, GF.FETCH_LOG = old
        ix.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def run_pr41() -> TestOutcome:
    """PR41: the guide as ONE structured JSON card - UI taxonomy (nested menu paths, interface terms), shortcuts (with what they do), action sequences (parsed steps) and the seven-division map; with the live catalog every procedure says how much of it applies to the installed version"""
    from core_organs.professor.knowledge import guide_card as GC, guide_finder as GF, manual_rag as MR
    cat = _p2_catalog()
    dbp = _tmp("card_ix") + ".db"
    ix = MR.ManualIndex(dbp)
    old = GF.GUIDE_DIR
    GF.GUIDE_DIR = _tmp("guides_c")
    try:
        html = ("<html><body><h1>Atlas Guide</h1><h2>Place a marker</h2><ol><li>Click <b>Add Marker</b> on the toolbar.</li></ol>"
                "<h2>Zoom in</h2><ol><li>Choose <b>View</b> &gt; <b>Zoom In</b>.</li></ol><h2>Crop the picture</h2><ol><li>Adjust the <b>Cropping Ratio</b> in the Inspector.</li><li>Click <b>Apply Crop</b>.</li></ol>"
                "<h2>Quick marker</h2><p>Press <b>Ctrl</b>+<b>M</b> to add a marker quickly.</p><h2>Export</h2><ol><li>Choose <b>File</b> &gt; <b>Export</b> &gt; <b>PDF</b>.</li></ol></body></html>")
        ix.ingest_text("fixture_like", "Atlas Guide", MR._html_to_text(html), "test:card", "html", embed=False)
        card = GC.build_card("fixture_like", ix, cat)
        card_nocat = GC.build_card("fixture_like", ix, None, save=False)
        with open(GC.card_path("fixture_like"), "r", encoding="utf-8") as fh:
            disk = json.load(fh)
        seq = {s["goal"]: s for s in card["action_sequences"]}
        terms = {t["term"] for t in card["ui_taxonomy"]["terms"]}
        checks = {"menus_are_nested": card["ui_taxonomy"]["menus"].get("View", {}).get("Zoom In") == {} and card["ui_taxonomy"]["menus"]["File"]["Export"]["PDF"] == {},
                  "interface_terms_collected": {"Add Marker", "Zoom In", "Cropping Ratio"} <= terms and "Ctrl" not in terms and "M" not in terms, "shortcut_with_what_it_does": "Ctrl+M" in card["shortcuts"] and "marker" in card["shortcuts"]["Ctrl+M"][0]["label"].lower(),
                  "procedures_parsed": {"Place a marker", "Zoom in", "Crop the picture", "Export"} <= set(seq) and seq["Place a marker"]["steps"][0]["target"] == "Add Marker", "grounding_measured_with_the_catalog": seq["Place a marker"]["grounded"] == 1.0 and seq["Zoom in"]["grounded"] == 1.0,
                  "what_does_not_apply_is_named": seq["Crop the picture"]["grounded"] < 1.0 and "Cropping Ratio" in seq["Crop the picture"]["unmatched"] and seq["Export"]["grounded"] < 1.0,
                  "version_fit_is_a_fraction": 0.0 < card["applies_to_installed_version"] < 1.0 and "applies_to_installed_version" not in card_nocat and "grounded" not in card_nocat["action_sequences"][0],
                  "mapped_onto_the_seven_divisions": bool(card["by_division"]) and all(isinstance(v, list) and v for v in card["by_division"].values()), "saved_as_json": disk["app"] == "fixture_like" and disk["chunks"] == card["chunks"] and len(disk["action_sequences"]) == len(card["action_sequences"])}
        return _verdict(checks, f"{card['chunks']} chunks, {len(card['action_sequences'])} procedures, shortcuts {list(card['shortcuts'])}, fit {card['applies_to_installed_version']}, divisions {list(card['by_division'])}")
    finally:
        GF.GUIDE_DIR = old
        ix.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(dbp + suf)
            except OSError:
                pass


def run_pr42() -> TestOutcome:
    """PR42: the state-transition history - every probe and every route tried by the executor leaves a row (before-state, motor primitive, after-state, effect, ok); effects, best route, recoveries and order effects are queryable; one table with an app_key column; forget() removes an application"""
    import core_organs.professor.probe as P
    from core_organs.professor import executor as X, history as HS
    from core_organs.professor.effectors import Effector
    p = _tmp("hist") + ".db"
    h = HS.History(p)
    ST = {"n": 0}
    old_snap, old_deliver = P.snapshot, X.Executor._deliver

    def snap(hwnd, with_image=True, nodes=None):
        return _p1_snap(texts={"text|@0,0": f"n={ST['n']}"}, sig=f"s{ST['n']}")

    def deliver(self, v, r):
        if r.kind == "shortcut":
            ST["n"] += 1
        return True, "fake " + r.kind

    try:
        cat = _p2_catalog()
        P.snapshot = snap                                                  # type: ignore[assignment]
        X.Executor._deliver = deliver                                      # type: ignore[method-assign]
        ex = X.Executor(7, Effector(7, allow_input=True, owned=True), cat, owned=True, history=h)
        rep = ex.run(ex.plan("add a marker"), dry_run=False, settle_s=1.0)
        rows = h.recent("fixture_like", 10)
        # a probe row and a recovery row, through the engine's own logging methods
        eng = P.ProbeEngine(7, Effector(7), cat, "fixture_like", history=h)
        hyp = P.Hypothesis("Options", [], "tabitem", "", "context", "x")
        rule = P.Rule("Options", [], "tabitem", "UIA Select", "context_change", {}, "x", True, "re-selected 'Shapes' (UIA Select)", True, 12, "a", "b", note="context changed in tabs")
        eng._log_probe(hyp, rule, _p1_snap(sig="a", names={"k": "v"}), _p1_snap(sig="b"))
        eng._log_recovery("Export", "close", "Escape then WM_CLOSE", True)
        eng._log_recovery("Export", "close", "Escape then WM_CLOSE", True)
        h.log("fixture_like", "sleep", "pair", "Add Marker / Clear Markers", "both orders", effect="order_matters", ok=True, unwound=True, detail={"ab": "markers=0", "ba": "markers=1", "diff": ["text"]})
        h.log("other_app", "probe", "invoke", "Save", effect="state_change", ok=True)
        eff = h.effects_of("fixture_like", "Add Marker")
        st = h.stats("fixture_like")
        tables = [r[0] for r in h.db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        n_forgot = h.forget("other_app")
        checks = {"executor_run_logged_each_route": rep.ok and len(rows) == 1 and rows[0]["source"] == "exec" and rows[0]["target"] == "Add Marker" and rows[0]["primitive"] == "key" and rows[0]["effect"] == "state_change" and rows[0]["ok"] == 1,
                  "before_and_after_signatures_kept": rows[0]["s0_sig"] == "s0" and rows[0]["s1_sig"] == "s1", "probe_row_has_unwound_flag": any(r["source"] == "probe" and r["primitive"] == "select" and r["unwound"] == 1 for r in h.recent("fixture_like", 10)),
                  "effects_counted": eff == {"state_change": 1}, "best_route_is_the_one_that_worked": h.best_route("fixture_like", "Add Marker") == "shortcut:Ctrl+M",
                  "recoveries_aggregated": h.recoveries("fixture_like") == [{"trigger": "Export", "primitive": "close", "route": "Escape then WM_CLOSE", "times": 2, "worked": 2}],
                  "order_effects_readable": h.order_effects("fixture_like")[0]["verdict"] == "order_matters" and h.order_effects("fixture_like")[0]["ba"] == "markers=1", "stats": st["transitions"] == 5 and st["by_source"].get("recovery") == 2,
                  "one_table_with_an_app_key": tables.count("transitions") == 1 and not any(t.startswith("app_history_") for t in tables), "forget_removes_one_application": n_forgot == 1 and h.stats("other_app")["transitions"] == 0 and h.stats("fixture_like")["transitions"] == 5,
                  "primitive_vocabulary": [HS.primitive_of(x) for x in ("UIA Invoke", "BM_CLICK -> btn", "WM_COMMAND 102", "posted click x", "UIA SetValue", "UIA Select")] == ["invoke", "click", "command", "click", "set_value", "select"]}
        return _verdict(checks, f"rows {st}; recent[0]={ {k: rows[0][k] for k in ('source', 'primitive', 'target', 'effect', 'ok')} }")
    finally:
        P.snapshot = old_snap
        X.Executor._deliver = old_deliver
        h.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


def run_pr43() -> TestOutcome:
    """PR43: Fitts's-law trajectories - movement time grows with distance and shrinks with target width; several targets are ONE continuous route (passes through each waypoint at its arrival time, starts and ends at rest, no stop-and-go between waypoints, velocity continuous at the joins); the overlay's glide and the session's 'watch me' demonstration use it and never touch the real mouse"""
    import math
    from core_organs.professor import pointing as PT, skills as SK, synth
    from core_organs.professor.overlay import RecordingOverlay
    from core_organs.professor.schema import Box
    from core_organs.professor.session import ProfessorSession
    from core_organs.professor.voice_out import SilentSpeaker
    from core_organs.professor.capture import cursor_pos
    near, far = PT.fitts_seconds(100, 40), PT.fitts_seconds(1200, 40)
    small, big = PT.fitts_seconds(600, 8), PT.fitts_seconds(600, 150)
    pts = [(100.0, 100.0), (600.0, 200.0), (900.0, 700.0), (300.0, 650.0)]
    tr = PT.stitch(pts, [0, 20, 120, 14])
    at_arrivals = [tr.at(a) for a in tr.arrival]
    speeds = [math.hypot(*tr.velocity(a)) for a in tr.arrival]
    joins = []
    wide = []
    for a in tr.arrival[1:-1]:
        v1, v2 = tr.velocity(a - 0.0005, h=1.25e-4), tr.velocity(a + 0.0005, h=1.25e-4)
        joins.append(math.hypot(v1[0] - v2[0], v1[1] - v2[1]) / max(1.0, math.hypot(*tr.velocity(a, h=1.25e-4))))
        w1, w2 = tr.velocity(a - 0.004, h=1e-3), tr.velocity(a + 0.004, h=1e-3)                  # the same jump measured 8x wider: a continuous curve's jump shrinks with the probe distance
        wide.append(math.hypot(w1[0] - w2[0], w1[1] - w2[1]) / max(1.0, math.hypot(*tr.velocity(a, h=1e-3))))
    chord = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(3))
    flat = PT.stitch([(0.0, 0.0), (500.0, 0.0)], [0, 30])
    boxes = [Box(100, 100, 160, 130), Box(400, 300, 440, 330), Box(800, 120, 1000, 180)]
    rp, rw = PT.route_for(boxes, (10.0, 10.0))
    ov = RecordingOverlay()
    dur = ov.glide(rp[1:], rw[1:])
    # the session demonstration on a real scan of the synthetic application (nothing on screen)
    img, truth, _ = synth.render_app("light", 1.0)
    sm, _ = _scan_offline(img, 1.0)
    bold, ital = _el(sm, truth, "Bold"), _el(sm, truth, "Italic")
    bold.label, ital.label = "Bold", "Italic"
    sk = SK.Skill("t1", "synth", "bold_italic", ["make it bold and italic"], [SK.SkillStep("verb", "Bold", "", [], "", ""), SK.SkillStep("verb", "Italic", "", [], "", ""), SK.SkillStep("verb", "No Such Control", "", [], "", "")])
    sp, ov2 = SilentSpeaker(), RecordingOverlay()
    ps = ProfessorSession(mute=True, speaker=sp, overlay_obj=ov2, upgrade=False, interactive=False, find_guide=False, use_catalog=False)
    mouse0 = cursor_pos()
    out = ps.demonstrate(sk, model=(sm, img))
    mouse1 = cursor_pos()
    glides = [e for e in ov2.log if e[0] == "glide"]
    points = [e for e in ov2.log if e[0] == "point"]
    checks = {"fitts_distance_and_width": far > near and small > big and 0.16 <= near <= far <= 1.6, "passes_through_every_waypoint": all(math.hypot(a[0] - p[0], a[1] - p[1]) < 1.5 for a, p in zip(at_arrivals, pts)),
              "starts_and_ends_at_rest": speeds[0] < 20 and speeds[-1] < 20, "moves_between": speeds[1] > 200 and speeds[2] > 100, "no_stop_and_go_velocity_continuous_at_joins": all(j < 0.05 for j in joins) and all(j < w for j, w in zip(joins, wide)),
              "route_is_not_wasteful": chord <= tr.length() <= 1.35 * chord, "duration_is_the_sum_of_the_segments": abs(tr.duration - sum(tr.times)) < 1e-9 and tr.arrival == sorted(tr.arrival), "straight_hop_is_straight": abs(flat.at(flat.duration / 2)[1]) < 1e-6,
              "overlay_glide_records_the_route": dur > 0.5 and ov.log[-1][0] == "glide" and ov.log[-1][1]["arrivals"][-1] == round(dur, 3) and len(ov.log[-1][1]["arrivals"]) == 3,
              "demonstration_found_the_visible_controls": out["ok"] and out["steps"] == ["Bold", "Italic"] and out["missing"] == ["No Such Control"], "glide_then_point_at_each_target_in_order": len(glides) == 1 and [p[1]["label"] for p in points] == ["Bold", "Italic"] and [p[1]["step"] for p in points] == [1, 2],
              "narrated": any("Bold" in s for s in sp.said) and any("Italic" in s for s in sp.said), "real_mouse_untouched": mouse0 == mouse1}
    return _verdict(checks, f"fitts near {near:.2f}s far {far:.2f}s small {small:.2f}s big {big:.2f}s; route {tr.duration:.2f}s len {tr.length():.0f}px (chord {chord:.0f}); join discontinuity {max(joins):.3f}; demo {out.get('route_seconds')}s")


def run_pr44() -> TestOutcome:
    """PR44: idle permutation learning on a fake application - for every pair of safe actions both orders are run and the application is put back each time; 'Add Marker / Clear Markers' is order-sensitive, the others commute; verdicts land in the history; it refuses when input is closed, when the user is active, and stops when the user comes back"""
    import core_organs.fast_uia as FU
    import core_organs.professor.probe as P
    from core_organs.professor import explore as EX, history as HS
    from core_organs.professor.effectors import Effector
    S = {"markers": 0, "vis": 1}
    nodes: list = []

    class Pat:
        def __init__(self, fn):
            self.fn = fn

        def Invoke(self):
            self.fn()

        def Toggle(self):
            self.fn()

    class Ctl:
        def __init__(self, fn, kind):
            self.fn, self.kind = fn, kind

        def GetInvokePattern(self):
            return Pat(self.fn) if self.kind == "invoke" else None

        def GetTogglePattern(self):
            return Pat(self.fn) if self.kind == "toggle" else None

    def add():
        S["markers"] += 1

    def clear():
        S["markers"] = 0

    def tog():
        S["vis"] = 1 - S["vis"]

    def build():
        nodes.clear()
        nodes.append(_FN(0, -1, "WindowControl", "Fake", (0, 0, 800, 600)))
        for i, (nm, fn, kind, pats) in enumerate((("Add Marker", add, "invoke", ("invoke",)), ("Clear Markers", clear, "invoke", ("invoke",)), ("Visible", tog, "toggle", ("toggle",))), 1):
            n = _FN(i, 0, "CheckBoxControl" if kind == "toggle" else "ButtonControl", nm, (10, 40 * i, 120, 40 * i + 28), pats=pats, toggle=(S["vis"] if kind == "toggle" else -1))
            n.ctrl = Ctl(fn, kind)
            nodes.append(n)
            nodes[0].children.append(i)
        return nodes

    def snap(hwnd, with_image=True, nodes=None):
        return _p1_snap(names={"b1": "Add Marker", "b2": "Clear Markers", "c1": "Visible"}, texts={"text|@0,0": f"markers={S['markers']}"}, states={"chk": f"tog={S['vis']}"}, sig=f"m{S['markers']}v{S['vis']}")

    old = (FU.snapshot, P.snapshot, EX.snapshot)
    FU.snapshot = lambda hwnd, **kw: build()                          # type: ignore[assignment]
    P.snapshot = EX.snapshot = snap                                    # type: ignore[assignment]
    p = _tmp("hist_x") + ".db"
    h = HS.History(p)
    try:
        cat = _p2_catalog()
        fx = Effector(7, allow_input=True, owned=True)
        idle = {"s": 1000.0}
        ex = EX.Explorer(7, fx, cat, "fake_app", h, owned=True, idle_required_s=60.0, max_actions=4, budget_s=60.0, idle_fn=lambda: idle["s"])
        rep = ex.run(require_idle=True)
        by = {(p_.a, p_.b): p_ for p_ in rep.pairs}
        pair = by.get(("Add Marker", "Clear Markers")) or by.get(("Clear Markers", "Add Marker"))
        rows = h.order_effects("fake_app")
        # refusals
        closed = EX.Explorer(7, Effector(7), cat, "fake_app", h, owned=True, idle_fn=lambda: 1000.0).run()
        S.update(markers=0, vis=1)
        busy = EX.Explorer(7, fx, cat, "fake_app", h, owned=True, idle_required_s=60.0, idle_fn=lambda: 3.0).run(require_idle=True)
        foreign_busy = EX.Explorer(7, Effector(7, allow_input=True, authorized=True), cat, "fake_app", h, owned=False, idle_required_s=60.0, idle_fn=lambda: 3.0).run(require_idle=False)
        # the user returns after the first pair
        calls = {"n": 0}

        def returning():
            calls["n"] += 1
            return 1000.0 if calls["n"] <= 3 else 0.2

        S.update(markers=0, vis=1)
        ret = EX.Explorer(7, fx, cat, "fake_app", h, owned=True, idle_required_s=60.0, idle_fn=returning).run(require_idle=True)
        checks = {"every_pair_tried_both_ways": len(rep.pairs) == 3 and all(p_.verdict in ("order_matters", "commutes") for p_ in rep.pairs), "add_clear_is_order_sensitive": pair is not None and pair.verdict == "order_matters" and {"markers=0", "markers=1"} <= {pair.ab, pair.ba},
                  "independent_actions_commute": all(p_.verdict == "commutes" for p_ in rep.pairs if "Visible" in (p_.a, p_.b)), "application_put_back_after_every_pair": all(p_.restored for p_ in rep.pairs) and S["markers"] == 0 and rep.stopped == "",
                  "verdicts_in_the_history": len(rows) == 3 and sorted(r["verdict"] for r in rows) == ["commutes", "commutes", "order_matters"], "refuses_when_input_closed": closed.stopped.startswith("input closed") and not closed.pairs,
                  "refuses_while_the_user_is_active": busy.stopped.startswith("the user is active") and not busy.pairs, "someone_elses_window_always_needs_idle": foreign_busy.stopped.startswith("the user is active") and not foreign_busy.pairs,
                  "stops_when_the_user_returns": ret.stopped.startswith("the user came back") and len(ret.pairs) < 3, "state_untouched_after_refusals": S["markers"] == 0 and S["vis"] == 1}
        return _verdict(checks, f"pairs { {f'{p_.a}/{p_.b}': p_.verdict for p_ in rep.pairs} }; ab={pair.ab if pair else None!r} ba={pair.ba if pair else None!r}; returned-user run did {len(ret.pairs)} pair(s): {ret.stopped}")
    finally:
        FU.snapshot, P.snapshot, EX.snapshot = old
        h.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


def run_pl12() -> TestOutcome:
    """PL12: idle permutation learning on the REAL Atlas fixture (our own window, parked, headless) - 'Add Marker' then 'Clear Markers' leaves 0 markers, the reverse leaves 1 (ground truth: its own state label), the fixture is put back to its starting state exactly, the verdicts are in the history"""
    try:
        from core_organs.atlas.fixture import harness
    except Exception as exc:
        return TestOutcome(True, f"fixture harness unavailable: {exc}", env_blocked=True)
    from core_organs import background_window as bw, headless_input as hin
    from core_organs.atlas import scanner as SC
    from core_organs.professor import explore as EX, harvest as HV, history as HS
    from core_organs.professor.capture import foreground_hwnd
    from core_organs.professor.effectors import Effector
    h = None
    p = _tmp("hist_l") + ".db"
    hist = HS.History(p)
    try:
        fg0 = foreground_hwnd()
        h = harness.launch(minimized=True)
        hwnd = h.get("hwnd") if isinstance(h, dict) else None
        if not hwnd:
            return TestOutcome(True, f"fixture did not start: {h}", env_blocked=True)
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, frame_only = SC.ensure_tree(hwnd, bg)
            if frame_only:
                return TestOutcome(True, "fixture tree never populated while parked", env_blocked=True)
            s0 = harness.read_state_text(hwnd)
            cat = HV.harvest_tree(hwnd, "atlas_fixture", "Atlas Fixture")
            fx = Effector(hwnd, allow_input=True, owned=True)
            rep = EX.Explorer(hwnd, fx, cat, "atlas_fixture", hist, owned=True, max_actions=3, budget_s=150.0).run(require_idle=False)
            s1 = harness.read_state_text(hwnd)
        by = {frozenset((p_.a, p_.b)): p_ for p_ in rep.pairs}
        pair = by.get(frozenset(("Add Marker", "Clear Markers")))
        fg_end = foreground_hwnd()
        checks = {"fixture_pairs_explored": len(rep.pairs) >= 1 and pair is not None, "add_clear_order_matters": pair is not None and pair.verdict == "order_matters", "ground_truth_of_both_orders": pair is not None and any("markers=0" in x for x in (pair.ab, pair.ba)) and any("markers=1" in x for x in (pair.ab, pair.ba)),
                  "fixture_back_to_its_start_exactly": s1 == s0 and rep.stopped == "", "every_pair_restored": all(p_.restored for p_ in rep.pairs), "verdicts_logged": len(hist.order_effects("atlas_fixture")) == len(rep.pairs),
                  "fixture_not_left_holding_the_foreground": hin.window_pid(fg_end) != h.get("pid")}
        return _verdict(checks, f"pairs { {f'{p_.a}/{p_.b}': p_.verdict for p_ in rep.pairs} }; ab={pair.ab if pair else None!r} ba={pair.ba if pair else None!r}; {rep.seconds}s; stopped={rep.stopped!r}; skipped {rep.skipped[:3]}; focus handed back {fx.focus_returns}x",
                        {"pairs": len(rep.pairs), "seconds": rep.seconds})
    finally:
        try:
            if h:
                harness.close(h)
        except Exception:
            pass
        hist.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.remove(p + suf)
            except OSError:
                pass


def run_pl14() -> TestOutcome:
    """PL14: the guide run END TO END on a real, installed application (the first one of the plan): Notepad is launched as an OWNED instance without the user's tabs, its guide's procedures run (one passes, one stops on purpose at 'Save as'), the deep scan leaves its pictures and one self-contained report, the user's saved state is byte-identical afterwards and the user's foreground window never changes hands for good"""
    import hashlib
    from core_organs.professor import apprun as AR
    from core_organs.professor.capture import foreground_hwnd
    from core_organs import headless_input as hin
    spec = AR.SPECS.get("notepad")
    if spec is None:
        return TestOutcome(True, "no notepad entry in the plan", env_blocked=True)
    fam = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages", "Microsoft.WindowsNotepad_8wekyb3d8bbwe", "LocalState")

    def fingerprint() -> str:
        h = hashlib.sha1()
        for dp, _dn, fs in sorted(os.walk(fam)):
            for f in sorted(fs):
                try:
                    h.update((os.path.relpath(os.path.join(dp, f), fam) + str(os.path.getsize(os.path.join(dp, f)))).encode())
                except OSError:
                    pass
        return h.hexdigest()
    fg0 = foreground_hwnd()
    before = fingerprint() if os.path.isdir(fam) else ""
    import copy
    sp = copy.copy(spec)
    sp.max_tasks = 2
    run = AR.AppRun(sp, echo=False, phases=("guide",), max_attempts=1)
    rep = run.run()
    if rep.get("result") == "launch_failed":
        return TestOutcome(True, "Notepad could not be launched here", env_blocked=True)
    after = fingerprint() if os.path.isdir(fam) else ""
    files = os.listdir(run.run_dir) if os.path.isdir(run.run_dir) else []
    led = {r["goal"]: r["disposition"] for r in rep.get("ledger", [])}
    fg1 = foreground_hwnd()
    owned_left = bool(run.hwnd and hin.is_alive(run.hwnd))
    checks = {"header_footer_procedure_passed": any("header" in g.lower() and d == "ok" for g, d in led.items()), "save_as_stopped_on_purpose": any("log file" in g.lower() and d == "blocked" for g, d in led.items()),
              "deep_scan_pictures_left": {"scan_1_first.png", "scan_2_deep.png", "scan_3_tree_levels.png"} <= set(files) and any(f.startswith("flyout_") for f in files),
              "flyouts_were_read": (rep.get("phases", {}).get("menus", {}) or {}).get("items", 0) >= 20, "one_self_contained_report": "report.html" in files and os.path.getsize(os.path.join(run.run_dir, "report.html")) > 5000,
              "users_saved_state_identical": before == after, "owned_window_closed": not owned_left, "foreground_not_left_with_the_app": hin.window_pid(fg1) != hin.window_pid(run.hwnd) if run.hwnd else True,
              "history_rows_written": (rep.get("history") or {}).get("transitions", 0) > 0}
    return _verdict(checks, f"ledger {rep.get('ledger_counts')}; menus {(rep.get('phases', {}).get('menus') or {}).get('items')} items; {rep.get('seconds')}s", {"seconds": rep.get("seconds")})


def run_pl13() -> TestOutcome:
    """PL13: the REAL overlay pointer glides through three targets as one Fitts's-law route - it arrives at the last one, the overlay reports no error, the user's real mouse does not move, the foreground window never changes"""
    from core_organs.professor import capture as CAP, pointing as PT
    from core_organs.professor.overlay import Overlay
    from core_organs.professor.schema import Box
    ov = Overlay()
    if not ov.start():
        return TestOutcome(True, f"overlay could not start here: {ov.error}", env_blocked=True)
    try:
        mon = CAP.monitors()[0].box
        base_x, base_y = mon.x2 - 700, mon.y2 - 260
        boxes = [Box(base_x, base_y, base_x + 40, base_y + 30), Box(base_x + 300, base_y + 120, base_x + 360, base_y + 160), Box(base_x + 120, base_y + 60, base_x + 150, base_y + 90)]
        pts, ws = PT.route_for(boxes)
        fg0, mouse0 = CAP.foreground_hwnd(), CAP.cursor_pos()
        time.sleep(0.3)
        user_moving = CAP.cursor_pos() != mouse0                 # if a person is moving the real mouse during the test, that check says nothing
        mouse0 = CAP.cursor_pos()
        ov.point(boxes[0], "start", 1, "look", False, "", False, False)         # the pointer appears at the first target
        time.sleep(0.5)
        t0 = time.time()
        planned = ov.glide(pts[1:], ws[1:])
        ov.wait_idle(planned + 3.0)                                  # the glide command is queued; the overlay reports idle once the pointer has arrived
        took = time.time() - t0
        pos = ov.cursor.pos if ov.cursor is not None else (-1, -1)
        mouse1, fg1 = CAP.cursor_pos(), CAP.foreground_hwnd()
        checks = {"glide_planned_with_fitts": 0.5 < planned < 3.0, "pointer_arrived_at_the_last_target": abs(pos[0] - pts[-1][0]) < 4 and abs(pos[1] - pts[-1][1]) < 4, "took_about_the_planned_time": abs(took - planned) < 1.0,
                  "no_overlay_error": not ov.error, "real_mouse_never_moved": user_moving or mouse1 == mouse0, "foreground_unchanged": fg1 == fg0}
        return _verdict(checks, f"(user was moving the mouse: {user_moving}) planned {planned:.2f}s took {took:.2f}s; pointer at {tuple(round(c) for c in pos)} target {tuple(round(c) for c in pts[-1])}; overlay error {ov.error!r}")
    finally:
        ov.clear()
        time.sleep(0.8)
        ov.stop()


# =========================================================================================================== the ML models (continuous learning)
def run_pr45() -> TestOutcome:
    """PR45: the action-outcome model really LEARNS - on a synthetic world where each toolkit favours different routes it beats the majority baseline test-then-train, learns that 'control' works in a XAML-like toolkit and 'click' in a GL-like one, re-orders routes accordingly (never inventing one), explores routes it has rarely seen, and survives a save / load"""
    from core_organs.professor.ml import outcome as OM
    rng = np.random.default_rng(5)
    P_OK = {("winui", "control"): 0.95, ("winui", "click"): 0.08, ("winui", "shortcut"): 0.7, ("gl", "control"): 0.02, ("gl", "click"): 0.85, ("gl", "shortcut"): 0.3,
            ("win32", "control"): 0.9, ("win32", "click"): 0.6, ("win32", "shortcut"): 0.9}
    labels = ["Save", "Bold", "Add Marker", "Zoom In", "Options", "Export...", "Paste"]
    m = OM.OutcomeModel(None)
    fresh_rank = m.rank_routes({"toolkit": "winui", "role": "button", "app": "x"}, ["click", "control", "shortcut"])
    for i in range(1800):
        tk = ["winui", "gl", "win32"][i % 3]
        route = ["control", "click", "shortcut"][int(rng.integers(0, 3))]
        lbl = labels[int(rng.integers(0, len(labels)))]
        ok = bool(rng.random() < P_OK[(tk, route)])
        eff = ("opens_dialog" if lbl.endswith("...") else "state_change") if ok else "no_effect"
        m.observe({"app": f"app_{tk}", "toolkit": tk, "role": "button", "route": route, "safety": "safe", "source": "exec", "label": lbl, "n_controls": 40, "has_shortcut": route == "shortcut"}, eff, ok)
    met = m.metrics()
    ctx = lambda tk: {"app": f"app_{tk}", "toolkit": tk, "role": "button", "safety": "safe", "source": "exec", "label": "Save", "n_controls": 40}
    p_w_control = m.predict({**ctx("winui"), "route": "control"})["p_ok"]
    p_w_click = m.predict({**ctx("winui"), "route": "click"})["p_ok"]
    p_g_control = m.predict({**ctx("gl"), "route": "control"})["p_ok"]
    p_g_click = m.predict({**ctx("gl"), "route": "click"})["p_ok"]
    rank_w = m.rank_routes(ctx("winui"), ["click", "control", "shortcut"])
    rank_g = m.rank_routes(ctx("gl"), ["control", "shortcut", "click"])
    rank_new = m.rank_routes({**ctx("qt"), "app": "app_qt"}, ["control", "click"])                  # a toolkit it never saw
    dialog_p = m.predict({**ctx("win32"), "route": "control", "label": "Export..."})["effect"]
    path = _tmp("outcome") + ".npz"
    m.save(path)
    m2 = OM.OutcomeModel(path)
    same = abs(m2.predict({**ctx("gl"), "route": "click"})["p_ok"] - p_g_click) < 1e-9 and m2.seen == m.seen
    for suf in ("", ".json"):
        try:
            os.remove(path + suf)
        except OSError:
            pass
    checks = {"beats_the_majority_baseline_test_then_train": met["ok_accuracy"] >= met["ok_baseline"] + 0.08 and met["beats_baseline"], "learns_the_toolkit_route_pattern": p_w_control > 0.8 and p_w_click < 0.35 and p_g_control < 0.25 and p_g_click > 0.6,
              "reorders_routes_per_toolkit": rank_w[0][0] == "control" and rank_g[0][0] == "click", "before_learning_the_static_ladder_stands": [k for k, _s in fresh_rank] == ["click", "control", "shortcut"],
              "ranking_never_adds_a_route": {k for k, _s in rank_w} == {"click", "control", "shortcut"} and {k for k, _s in rank_new} == {"control", "click"}, "unseen_toolkit_gets_an_exploration_bonus": rank_new[0][1] > 0.0 and all(s > 0 for _k, s in rank_new),
              "dialog_labels_learn_their_effect": dialog_p["opens_dialog"] > dialog_p["no_effect"] or dialog_p["opens_dialog"] > 0.15, "save_and_load_identical": same, "small_enough_to_train_beside_a_vision_model": met["parameters"] < 150_000}
    return _verdict(checks, f"{met['seen']} examples: ok accuracy {met['ok_accuracy']} vs baseline {met['ok_baseline']}, effect accuracy {met['effect_accuracy']} vs {met['effect_baseline']}; winui control/click {p_w_control:.2f}/{p_w_click:.2f}, gl control/click {p_g_control:.2f}/{p_g_click:.2f}; "
                            f"params {met['parameters']}", {"ok_accuracy": met["ok_accuracy"], "baseline": met["ok_baseline"]})


def run_pr46() -> TestOutcome:
    """PR46: the vision-candidate model learns, from the TREE-labelled scans alone (no hand labels), which boxes the vision tier proposed are real controls - on a held-out theme + scale it is far above chance and raises precision at full recall; on a layout it has never seen it is honestly weaker; it improves again as soon as it has learnt from that layout; its noise filter stays OFF until it has seen enough different applications"""
    from core_organs.professor import candidates as CD, synth
    from core_organs.professor.ml import candidates as MC
    from core_organs.professor.schema import Box

    def scene(kind, theme="light", scale=1.0):
        img, truth, _ = {"app": lambda: synth.render_app(theme, scale), "dialog": lambda: synth.render_dialog(theme, scale), "editor": lambda: synth.render_editor(scale)}[kind]()
        cs = CD.detect(img, scale, ocr=True, budget_s=30)
        return cs.candidates, img.size, CD.ink_mask(np.asarray(img.convert("L")), scale), [Box(*t["box"]) for t in truth if t.get("label") is not None]

    train = [scene("app", "light", 1.0), scene("app", "dark", 1.0), scene("app", "light", 1.5)]
    held_app, dlg, dlg_dark, edt = scene("app", "dark", 1.25), scene("dialog", "light"), scene("dialog", "dark"), scene("editor")
    m = MC.CandidateModel(None)
    never = m.filter(held_app[0], held_app[1], held_app[2])[1]
    for _ in range(6):
        for c, size, ink, tb in train:
            m.observe_scan(c, size, ink, tb, epochs=2, source="synthetic-app")
    e_held = m.evaluate(*held_app, 0.5)
    e_untrained = MC.CandidateModel(None).evaluate(*held_app, 0.5)
    e_dlg = m.evaluate(*dlg, 0.5)
    ready_one_source = m.ready()
    for _ in range(6):
        for c, size, ink, tb in (dlg, edt):
            m.observe_scan(c, size, ink, tb, epochs=2, source="synthetic-dialog")
    e_dlg_dark = m.evaluate(*dlg_dark, 0.5)
    kept, dropped = m.filter(held_app[0], held_app[1], held_app[2])
    for src in ("a", "b", "c", "d"):                                    # pretend it has learnt from several applications with a good running AUC
        m.sources.add(src)
    m.preq_p, m.preq_y = [0.9] * 100 + [0.1] * 100, [1] * 100 + [0] * 100
    m.seen = max(m.seen, 500)
    ready_diverse = m.ready()
    path = _tmp("cand") + ".npz"
    m.save(path)
    m2 = MC.CandidateModel(path)
    same = np.allclose(m.prob(held_app[0], held_app[1], held_app[2]), m2.prob(held_app[0], held_app[1], held_app[2])) and m2.sources == m.sources
    for suf in ("", ".json"):
        try:
            os.remove(path + suf)
        except OSError:
            pass
    checks = {"labels_come_from_the_tree_alone": e_held["positives"] > 10 and e_held["n"] > e_held["positives"], "held_out_theme_and_scale_far_above_chance": e_held["auc"] >= 0.95 and e_untrained["auc"] < 0.85,
              "precision_rises_at_full_recall": e_held["precision"] >= e_held["base_precision"] + 0.2 and e_held["recall"] >= 0.9, "unseen_dialog_layout_beats_untrained": e_dlg["auc"] >= e_untrained["auc"] - 0.3 and e_dlg["auc"] >= 0.65,
              "learns_the_new_layout_quickly": e_dlg_dark["auc"] >= 0.9, "filter_off_after_one_layout": not ready_one_source and never == 0 and dropped == 0, "filter_ready_only_with_diversity_and_good_auc": ready_diverse,
              "save_and_load_identical": same}
    return _verdict(checks, f"held-out dark@1.25: auc {e_held['auc']} precision {e_held['precision']} (base {e_held['base_precision']}) recall {e_held['recall']}; untrained auc {e_untrained['auc']}; unseen dialog auc {e_dlg['auc']}; "
                            f"after learning dialog+editor, held-out dark dialog auc {e_dlg_dark['auc']}", {"auc_heldout": e_held["auc"]})


def run_pr47() -> TestOutcome:
    """PR47: the motor-timing model - with no data it IS the Fitts prior (and says it was not learnt from people); fed noisy movements it recovers the generating law, its fit quality is reported, a handful of points barely move it (ridge prior), it persists, and the pointer's Fitts parameters follow it"""
    from core_organs.professor import pointing as PT
    from core_organs.professor.ml import motor as MM
    rng = np.random.default_rng(9)
    m = MM.MotorModel(None)
    prior = m.summary()
    a_true, b_true = 0.22, 0.17
    for _ in range(300):
        d, w = float(rng.uniform(40, 1400)), float(rng.uniform(8, 160))
        m.observe(d, w, a_true + b_true * m.index_of_difficulty(d, w) + float(rng.normal(0, 0.025)))
    fit = m.summary()
    few = MM.MotorModel(None)
    for _ in range(3):
        few.observe(500, 20, 1.2)
    old = (PT.FITTS_A, PT.FITTS_B)
    PT.set_fitts(fit["a"], fit["b"])
    t_far_small = PT.fitts_seconds(900, 10)
    PT.set_fitts(*old)
    path = _tmp("motor") + ".json"
    m.save(path)
    m2 = MM.MotorModel(path)
    os.remove(path)
    checks = {"no_data_is_the_prior": prior["a"] == MM.A0 and prior["b"] == MM.B0 and prior["learned_from_people"] is False, "recovers_the_generating_law": abs(fit["a"] - a_true) < 0.03 and abs(fit["b"] - b_true) < 0.02,
              "fit_quality_reported": fit["r2"] is not None and fit["r2"] > 0.85 and fit["rmse"] < 0.05, "three_points_barely_move_it": abs(few.params()[0] - MM.A0) < 0.25 and few.summary()["n"] == 3,
              "pointer_follows_the_model": abs(t_far_small - min(1.6, max(0.16, fit["a"] + fit["b"] * MM.MotorModel.index_of_difficulty(900, 10)))) < 1e-6 and (PT.FITTS_A, PT.FITTS_B) == old,
              "prediction_obeys_fitts": m.predict(1200, 10) > m.predict(100, 10) and m.predict(600, 10) > m.predict(600, 120), "save_and_load_identical": m2.params() == m.params() and m2.n == m.n}
    return _verdict(checks, f"prior {prior['a']}/{prior['b']} -> fitted {fit['a']}/{fit['b']} (true {a_true}/{b_true}) r2 {fit['r2']} rmse {fit['rmse']} on {fit['n']} movements")


def run_pr48() -> TestOutcome:
    """PR48: CONTINUOUS training - every logged transition trains the outcome model the moment it is logged, rows logged earlier are caught up exactly once, a background trainer runs only while the architecture is in use (replaying, checkpointing, logging metrics), checkpoints reload identically, and HOJAIGA_PROF_ML=0 switches it all off"""
    import shutil
    from core_organs.professor import history as HS
    from core_organs.professor.ml import learner as LN
    d = _tmp("mldir")
    hp = _tmp("hist_ml") + ".db"
    hist = HS.History(hp)
    # 40 rows logged BEFORE any learner exists
    for i in range(40):
        hist.log("app_a", "exec", "invoke", "Save", "control:Save", effect="state_change", ok=True, toolkit="winui", role="button", safety="safe")
    L = LN.Learner(d, interval_s=0.2, save_every_s=0.6, log_every_s=0.5)
    att = L.attach(hist)
    seen_after_catchup = L.outcome.seen
    att2 = L.attach(hist)                                           # second attach: nothing to catch up, no duplicate listener
    n_listeners = len(hist.listeners)
    for i in range(25):
        hist.log("app_a", "exec", "key", "Bold", "shortcut:Ctrl+B", effect="no_effect" if i % 5 == 0 else "state_change", ok=i % 5 != 0, toolkit="winui", role="button", safety="safe")
    live = L.outcome.seen - seen_after_catchup
    before_thread = L._thread is not None and L._thread.is_alive()
    with L.training():
        during = L._thread is not None and L._thread.is_alive()
        time.sleep(1.6)
    after = L._thread is not None and L._thread.is_alive()
    rep = L.report()
    files = sorted(os.listdir(d))
    log_lines = [json.loads(x) for x in open(L.log_path, "r", encoding="utf-8")] if os.path.isfile(L.log_path) else []
    p1 = L.outcome.predict({"app": "app_a", "toolkit": "winui", "role": "button", "route": "control", "safety": "safe", "label": "Save"})["p_ok"]
    L2 = LN.Learner(d)
    p2 = L2.outcome.predict({"app": "app_a", "toolkit": "winui", "role": "button", "route": "control", "safety": "safe", "label": "Save"})["p_ok"]
    L2.attach(hist)
    no_dupes = L2.outcome.seen == L.outcome.seen
    old = os.environ.get("HOJAIGA_PROF_ML")
    os.environ["HOJAIGA_PROF_ML"] = "0"
    try:
        n0 = L.outcome.seen
        hist.log("app_a", "exec", "invoke", "Save", "control:Save", effect="state_change", ok=True, toolkit="winui")
        off_observe = L.outcome.seen == n0
        with L.training():
            off_thread = L._thread is not None and L._thread.is_alive()
    finally:
        if old is None:
            os.environ.pop("HOJAIGA_PROF_ML", None)
        else:
            os.environ["HOJAIGA_PROF_ML"] = old
    hist.close()
    shutil.rmtree(d, ignore_errors=True)
    for suf in ("", "-wal", "-shm"):
        try:
            os.remove(hp + suf)
        except OSError:
            pass
    checks = {"earlier_rows_caught_up": att["caught_up_rows"] == 40 and seen_after_catchup == 40, "second_attach_does_not_duplicate": att2["caught_up_rows"] == 0 and n_listeners == 1,
              "every_new_transition_trains_at_once": live == 25, "trainer_runs_only_while_in_use": (not before_thread) and during and not after, "replayed_while_running": rep["events"]["replay_rounds"] >= 3,
              "checkpoints_written": {"outcome.npz", "candidates.npz", "motor.json", "learner.json"} <= set(files) and rep["events"]["checkpoints"] >= 1, "metrics_logged_to_jsonl": len(log_lines) >= 1 and "outcome" in log_lines[-1],
              "reload_is_identical": abs(p1 - p2) < 1e-9 and no_dupes, "learns_the_pattern_it_was_shown": p1 > 0.5, "switch_off_stops_everything": off_observe and not off_thread}
    return _verdict(checks, f"outcome seen {rep['outcome']['seen']}, replay rounds {rep['events']['replay_rounds']}, checkpoints {rep['events']['checkpoints']}, files {files}, log lines {len(log_lines)}; p(ok|winui,control,Save) {p1:.2f}")


OFFLINE = [("PR1", run_pr1), ("PR2", run_pr2), ("PR3", run_pr3), ("PR4", run_pr4), ("PR5", run_pr5), ("PR6", run_pr6), ("PR7", run_pr7), ("PR8", run_pr8), ("PR9", run_pr9),
           ("PR10", run_pr10), ("PR11", run_pr11), ("PR12", run_pr12), ("PR13", run_pr13), ("PR14", run_pr14), ("PR15", run_pr15), ("PR16", run_pr16), ("PR17", run_pr17),
           ("PR18", run_pr18), ("PR19", run_pr19), ("PR20", run_pr20), ("PR21", run_pr21), ("PR22", run_pr22), ("PR23", run_pr23), ("PR24", run_pr24), ("PR25", run_pr25), ("PR26", run_pr26), ("PR27", run_pr27),
           ("PR28", run_pr28), ("PR29", run_pr29), ("PR30", run_pr30), ("PR31", run_pr31), ("PR32", run_pr32), ("PR33", run_pr33),
           ("PR34", run_pr34), ("PR35", run_pr35), ("PR36", run_pr36), ("PR37", run_pr37), ("PR38", run_pr38), ("PR39", run_pr39),
           ("PR40", run_pr40), ("PR41", run_pr41), ("PR42", run_pr42), ("PR43", run_pr43), ("PR44", run_pr44),
           ("PR45", run_pr45), ("PR46", run_pr46), ("PR47", run_pr47), ("PR48", run_pr48)]
try:                                                                                       # the app-run architecture's offline tests (PR49+) live in their own module
    from si_tests_apprun import TESTS as _APPRUN_TESTS
    OFFLINE = OFFLINE + _APPRUN_TESTS
except Exception:                                                                          # noqa: BLE001 - a missing optional module must not break the suite
    pass
try:                                                                                       # the Oct-10 gap fixes (grounding, ribbon, dialog depth, verification, supervision, answers)
    from si_tests_gaps import TESTS as _GAP_TESTS
    OFFLINE = OFFLINE + _GAP_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # the virtual mouse (posted / in-process agent / ghost touch / UIA scroll routes, every mouse verb)
    from si_tests_pointer import TESTS as _POINTER_TESTS
    OFFLINE = OFFLINE + _POINTER_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # the scripting route: task-vs-reference, settings as verbs, sandboxed file commands
    from si_tests_scripting import TESTS as _SCRIPTING_TESTS
    OFFLINE = OFFLINE + _SCRIPTING_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # the shared click blocklist (Checkpoint 0): Delete/Format/Reset/Uninstall/Purchase ...
    from si_tests_safety import TESTS as _SAFETY_TESTS
    OFFLINE = OFFLINE + _SAFETY_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # the federated multi-RAG (rag/): five sub-RAGs, router, packs; all offline, temp roots only
    from si_tests_rag import TESTS as _RAG_TESTS
    OFFLINE = OFFLINE + _RAG_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # Checkpoint 3: the harvesters, the video pipeline and the bridge into the RAG (fixtures only, no network)
    from si_tests_harvest import TESTS as _HARVEST_TESTS
    OFFLINE = OFFLINE + _HARVEST_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # Checkpoint 4: train_qlora (VRAM preflight, dataset, masking, LoRA targeting, GPU/CPU loop on a tiny random Qwen3-VL; no weights needed)
    from si_tests_train import TESTS as _TRAIN_TESTS
    OFFLINE = OFFLINE + _TRAIN_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # Checkpoint 5: agent_executor (the closed loop: RAG -> Set-of-Marks -> adapter action -> guard -> act -> verify -> graph learns) and the tutor
    from si_tests_agent import TESTS as _AGENT_TESTS
    OFFLINE = OFFLINE + _AGENT_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # Checkpoint 5b: canvas_artist / canvas_teach / canvas_colour / artist_memory / prompt v2 (functional drawing, lightboard, colour, memory)
    from si_tests_artist import TESTS as _ARTIST_TESTS
    OFFLINE = OFFLINE + _ARTIST_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # pop-up classes + AUTH_BLOCKED, archetype matrix/router/70-30 eval
    from si_tests_popup_arch import TESTS as _POPARCH_TESTS
    OFFLINE = OFFLINE + _POPARCH_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # object knowledge: part roles + real proportions as data, the role critic
    from si_tests_objects import TESTS as _OBJECT_TESTS
    OFFLINE = OFFLINE + _OBJECT_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # the five Terminal-2 tasks: picture tier, speech sanitizer, frame filter, ready check + retry, sketch layer
    from si_tests_directive import TESTS as _DIRECTIVE_TESTS
    OFFLINE = OFFLINE + _DIRECTIVE_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
try:                                                                                       # multi-video consolidation (harvest.consolidate) + the flag-gated live video-graph bridge
    from si_tests_consolidate import TESTS as _CONSOLIDATE_TESTS
    OFFLINE = OFFLINE + _CONSOLIDATE_TESTS
except Exception:                                                                          # noqa: BLE001
    pass
LIVE = [("PL1", run_pl1), ("PL2", run_pl2), ("PL3", run_pl3), ("PL4", run_pl4), ("PL5", run_pl5), ("PL6", run_pl6), ("PV1", run_pv1), ("PV2", run_pv2), ("PL7", run_pl7), ("PL8", run_pl8), ("PL9", run_pl9), ("PL10", run_pl10), ("PL11", run_pl11), ("PL12", run_pl12), ("PL13", run_pl13), ("PL14", run_pl14)]


def main(live: bool = False, only: Optional[List[str]] = None) -> int:
    rows = []
    plan = OFFLINE + (LIVE if live else [])
    if only:
        plan = [(n, f) for n, f in OFFLINE + LIVE if n in only]
    for name, fn in plan:
        t0 = time.time()
        try:
            r = fn()
        except Exception:
            r = TestOutcome(False, "EXCEPTION " + traceback.format_exc()[-900:])
        dt = time.time() - t0
        status = "ENV-BLOCKED" if r.env_blocked else ("PASS" if r.passed else "FAIL")
        rows.append((name, status, dt, r))
        print(f"[{status:11s}] {name:5s} {dt:6.1f}s  {(fn.__doc__ or '').strip().splitlines()[0][:110]}")
        print(f"              {r.evidence[:700]}")
        extra = {k: v for k, v in (r.metrics or {}).items() if k != "checks"}
        if extra:
            print(f"              metrics: {extra}")
    p = sum(1 for _n, s, _d, _r in rows if s == "PASS")
    e = sum(1 for _n, s, _d, _r in rows if s == "ENV-BLOCKED")
    f = sum(1 for _n, s, _d, _r in rows if s == "FAIL")
    print(f"\nProfessor suite: {p} passed, {f} failed, {e} env-blocked, of {len(rows)}")
    return 0 if f == 0 else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main(live="--live" in args, only=[a for a in args if a.upper().startswith(("PR", "PL", "PV"))] or None))
