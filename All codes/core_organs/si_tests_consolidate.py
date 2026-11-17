"""
si_tests_consolidate -- AR50 multi-video consolidation engine, AR51 live video-graph bridge (offline: synthetic recordings with exact ground truth, no screen, no network, no GPU).

The synthetic application ("a fake DAW") is drawn at one logical size and recorded three times, like three tutorial authors would: different resolution, dark / light theme, letterbox
offset, a webcam bubble, a pointer that is somewhere else, a title card in one of them. The workflows differ (one has an advanced setting nobody else shows). Ground truth is by construction.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import time
import tempfile
from typing import Any, Dict, List, Optional, Tuple

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except ImportError:
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore

LW, LH = 1000, 600                                            # logical size of the fake application window

# ---- the fake application: states and the controls that lead between them -------------------------------------------------------------------------------------------------
MENU = [("File", 20), ("Edit", 90), ("View", 160), ("Help", 230)]
TOOLS = [("Select", 20), ("Draw", 90), ("Erase", 160), ("Fill", 230), ("Text", 300), ("Export", 880)]
CLICK_AT = {"file": (45, 18), "settings": (70, 78), "close": (860, 150), "export": (905, 58), "layers": (60, 112), "advanced": (250, 168)}


def _font(size: int):
    from PIL import ImageFont
    for name in ("arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render(state: str, theme: str = "dark", cursor: Tuple[int, int] = (500, 300)):
    """The fake app in `state` at logical size: home | file_menu | settings | advanced | export | layers."""
    from PIL import Image, ImageDraw
    dark = theme == "dark"
    bg, fg, panel, line, acc = ((30, 31, 34), (225, 225, 230), (45, 47, 52), (90, 92, 100), (70, 130, 230)) if dark else ((245, 245, 247), (30, 30, 35), (228, 229, 233), (160, 162, 170), (40, 100, 210))
    im = Image.new("RGB", (LW, LH), bg)
    d = ImageDraw.Draw(im)
    f, fs = _font(15), _font(12)
    # menu bar
    d.rectangle([0, 0, LW, 36], fill=panel, outline=line)
    for name, x in MENU:
        hot = state == "file_menu" and name == "File"
        if hot:
            d.rectangle([x - 8, 4, x + 52, 32], fill=acc)
        d.text((x, 10), name, fill=fg, font=f)
    # toolbar with glyph-like icons
    d.rectangle([0, 37, LW, 80], fill=panel, outline=line)
    for i, (name, x) in enumerate(TOOLS):
        hot = state == "export" and name == "Export"
        d.rectangle([x, 44, x + 56, 74], outline=line, fill=acc if hot else bg)
        if name == "Select":
            d.polygon([(x + 18, 50), (x + 18, 68), (x + 30, 62)], fill=fg)
        elif name == "Draw":
            d.line([(x + 14, 68), (x + 40, 50)], fill=fg, width=3)
        elif name == "Erase":
            d.rectangle([x + 16, 54, x + 40, 66], outline=fg)
        elif name == "Fill":
            d.ellipse([x + 16, 50, x + 40, 68], outline=fg)
        elif name == "Text":
            d.text((x + 20, 52), "T", fill=fg, font=f)
        else:
            d.text((x + 8, 52), name, fill=fg, font=fs)
    # left panel: layers (wider when expanded)
    lw = 360 if state == "layers" else 200
    d.rectangle([0, 81, lw, LH - 28], fill=panel, outline=line)
    d.rectangle([0, 96, lw, 128], fill=acc if state == "layers" else bg, outline=line)
    d.text((14, 104), "Layers", fill=fg, font=f)
    for i in range(7 if state == "layers" else 3):
        y = 140 + i * 40
        d.rectangle([14, y, lw - 14, y + 30], outline=line)
        d.text((22, y + 8), f"Layer {i + 1}", fill=fg, font=fs)
        if state == "layers":
            d.ellipse([lw - 50, y + 8, lw - 34, y + 24], outline=fg)
    # canvas and right inspector
    d.rectangle([lw + 10, 90, LW - 220, LH - 40], outline=line)
    for k in range(5):
        d.line([(lw + 40 + k * 60, 140 + k * 20), (lw + 90 + k * 60, 260 - k * 10)], fill=acc, width=3)
    d.rectangle([LW - 210, 81, LW, LH - 28], fill=panel, outline=line)
    for k in range(4):
        d.text((LW - 196, 100 + k * 46), f"Property {k + 1}", fill=fg, font=fs)
        d.rectangle([LW - 196, 118 + k * 46, LW - 20, 134 + k * 46], outline=line)
    d.rectangle([0, LH - 28, LW, LH], fill=panel, outline=line)
    d.text((10, LH - 22), "Ready", fill=fg, font=fs)
    if state == "file_menu":
        d.rectangle([10, 36, 190, 36 + 5 * 34], fill=panel, outline=fg)
        for i, it in enumerate(["New project", "Open...", "Settings", "Save", "Quit"]):
            d.text((24, 46 + i * 34), it, fill=fg, font=f)
    if state in ("settings", "advanced"):
        d.rectangle([180, 110, 820, 500], fill=panel, outline=fg, width=2)
        d.text((200, 122), "Settings", fill=fg, font=_font(18))
        for tab, tx in (("General", 200), ("Audio", 300), ("Advanced", 400)):
            d.rectangle([tx, 156, tx + 90, 184], outline=line, fill=acc if (state == "advanced") == (tab == "Advanced") else panel)
            d.text((tx + 10, 162), tab, fill=fg, font=fs)
        rows = 8 if state == "settings" else 4
        for r in range(rows):
            y = 204 + r * 36
            d.text((210, y), f"Option {r + 1}", fill=fg, font=fs)
            d.rectangle([420, y - 2, 780, y + 20], outline=line)
        if state == "advanced":
            for r in range(3):
                d.ellipse([430, 360 + r * 40, 450, 380 + r * 40], outline=fg)
                d.text((460, 362 + r * 40), f"Hidden switch {r + 1}", fill=fg, font=fs)
        d.rectangle([700, 450, 800, 484], outline=fg)
        d.text((730, 460), "Close", fill=fg, font=fs)
    if state == "export":
        d.rectangle([300, 160, 700, 400], fill=panel, outline=fg, width=2)
        d.text((320, 172), "Export", fill=fg, font=_font(18))
        d.rectangle([320, 210, 680, 330], outline=line)
        d.line([(320, 210), (680, 330)], fill=line)
        d.line([(320, 330), (680, 210)], fill=line)
        d.rectangle([320, 350, 680, 372], outline=fg)
        d.rectangle([320, 350, 520, 372], fill=acc)
    # pointer
    cx, cy = cursor
    d.polygon([(cx, cy), (cx, cy + 20), (cx + 6, cy + 15), (cx + 13, cy + 15)], fill=(255, 255, 255), outline=(0, 0, 0))
    return im


def frame_of(im, W: int, H: int, pad: Tuple[int, int], webcam: bool):
    """The logical picture placed on a W x H video frame (letterboxed by `pad` = (left, top) logical-scaled), with an optional webcam bubble."""
    import cv2
    import numpy as np
    from PIL import ImageDraw
    sc = min((W - pad[0] * 2) / LW, (H - pad[1] * 2) / LH)
    w, h = int(LW * sc), int(LH * sc)
    canvas = np.zeros((H, W, 3), np.uint8)
    a = np.asarray(im.resize((w, h)))[:, :, ::-1]
    canvas[pad[1]:pad[1] + h, pad[0]:pad[0] + w] = a
    if webcam:
        r = max(18, H // 9)
        cv2.circle(canvas, (W - r - 6, H - r - 6), r, (150, 170, 215), -1)
        cv2.circle(canvas, (W - r - 6, H - r - 6), r // 3, (60, 60, 120), -1)
    return canvas


def title_card(W: int, H: int):
    import numpy as np
    return np.full((H, W, 3), (200, 90, 40), np.uint8)


# one tutorial = [(state, seconds, control that was clicked to ENTER this state)]
V1 = [("home", 3, None), ("file_menu", 3, "file"), ("settings", 3, "settings"), ("advanced", 3, "advanced"), ("settings", 3, None), ("home", 3, "close"), ("export", 3, "export")]
V2 = [("home", 3, None), ("file_menu", 3, "file"), ("settings", 3, "settings"), ("home", 3, "close"), ("layers", 3, "layers")]
V3 = [("home", 3, None), ("export", 3, "export"), ("home", 3, "close"), ("layers", 3, "layers"), ("home", 3, "layers"), ("file_menu", 3, "file")]
STYLE = {"v1": dict(size=(854, 480), theme="dark", pad=(0, 0), webcam=False, card=False),
         "v2": dict(size=(1280, 720), theme="light", pad=(80, 0), webcam=True, card=True),
         "v3": dict(size=(640, 360), theme="dark", pad=(0, 18), webcam=True, card=False)}


PLAN_OF = {"v1": V1, "v2": V2, "v3": V3, "v4": V2}
CARD_OF = {"v1": 0.0, "v2": 2.0, "v3": 0.0, "v4": 0.0}
CONTROL_LABEL = {"file": "File", "settings": "Settings", "close": "Close", "export": "Export", "layers": "Layers", "advanced": "Advanced"}


def truth_of(video: str, t: float) -> Optional[Tuple[str, str, Optional[str]]]:
    """(from_state, to_state, control clicked) of the transition nearest to time `t` of a synthetic recording, None when nothing happens near it."""
    plan, clock, prev, best = PLAN_OF[video], CARD_OF[video], None, None
    for state, secs, via in plan:
        if prev is not None and (best is None or abs(clock - t) < abs(best[0] - t)):
            best = (clock, (prev, state, via))
        clock += secs
        prev = state
    return best[1] if best and abs(best[0] - t) < 1.6 else None


def write_video(path: str, plan: List[Tuple[str, int, Optional[str]]], style: Dict[str, Any], fps: int = 10) -> str:
    import cv2
    W, H = style["size"]
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    if not vw.isOpened():
        raise RuntimeError("cannot open a video writer (no mp4v codec)")
    cur = (500, 300)
    if style["card"]:
        for _ in range(2 * fps):
            vw.write(title_card(W, H))
    for state, secs, via in plan:
        if via and via in CLICK_AT:
            cur = CLICK_AT[via]
        for _ in range(secs * fps):
            vw.write(frame_of(render(state, style["theme"], cur), W, H, style["pad"], style["webcam"]))
    vw.release()
    return path


def make_videos(root: str) -> Dict[str, str]:
    out = {}
    for vid, plan in (("v1", V1), ("v2", V2), ("v3", V3)):
        out[vid] = write_video(os.path.join(root, f"{vid}.mp4"), plan, STYLE[vid])
    return out


def build_graph(root: str):
    from core_organs.harvest import consolidate as C
    vids = make_videos(root)
    g = C.AppGraph("synthetic_daw", os.path.join(root, "synthetic_daw"))
    reps = [C.ingest_video(g, p, video_id=v) for v, p in vids.items()]
    return g, reps, vids


# ------------------------------------------------------------------------------------------------------------------------------------------------ tests
def run_ar50() -> "TestOutcome":
    """AR50: three recordings of one app (other size, theme, letterbox, webcam, title card) merge their shared actions, keep the one only a single video shows, and the graph only grows"""
    from core_organs.harvest import consolidate as C
    tmp = tempfile.mkdtemp(prefix="vc_")
    checks: Dict[str, Any] = {}
    try:
        g, reps, vids = build_graph(tmp)
        sup = sorted((g.support(e) for e in g.edges), reverse=True)
        checks["events_found_in_every_video"] = all(r.get("events", 0) >= 3 for r in reps)
        checks["shared_actions_merge_across_resolutions_and_themes"] = len(g.baseline()) >= 4 and max(sup) == 3
        checks["rare_action_is_kept_as_unique_not_dropped"] = len(g.unique()) >= 1
        checks["common_actions_are_not_duplicated"] = len(g.edges) <= 9
        checks["graph_grows_but_second_video_mostly_merges"] = reps[1]["merged_into_existing"] >= 2 and reps[2]["merged_into_existing"] >= 2
        checks["title_card_is_not_an_action"] = all(len(g.sequences[v]) <= 8 for v in g.sequences)
        # re-ingesting is idempotent
        again = C.ingest_video(g, vids["v1"], video_id="v1")
        checks["reingest_is_noop"] = again.get("skipped") == "already ingested"
        # persistence round-trip
        g2 = C.AppGraph.load("synthetic_daw", g.root)
        checks["graph_survives_save_and_load"] = len(g2.edges) == len(g.edges) and g2.videos == g.videos
        # a fourth recording of the same workflow adds support, not edges
        v4 = os.path.join(tmp, "v4.mp4")
        write_video(v4, V2, dict(STYLE["v3"], theme="light", pad=(10, 10)))
        n_before, sup_before = len(g.edges), sum(g.support(e) for e in g.edges)
        C.ingest_video(g, v4, video_id="v4")
        checks["another_video_of_same_flow_adds_support_not_edges"] = len(g.edges) <= n_before + 1 and sum(g.support(e) for e in g.edges) >= sup_before + 3
        checks["every_edge_is_pure_no_false_merge"] = all(len({truth_of(o["video"], o["t"]) for o in e["obs"]}) == 1 for e in g.edges)
        by_truth: Dict[Any, set] = {}
        for e in g.edges:
            for o in e["obs"]:
                by_truth.setdefault(truth_of(o["video"], o["t"]), set()).add(e["id"])
        multi = {tr: ids for tr, ids in by_truth.items() if tr is not None and sum(1 for e in g.edges for o in e["obs"] if truth_of(o["video"], o["t"]) == tr and e["id"] in ids) >= 2}
        checks["same_true_action_is_never_split_across_edges"] = all(len(ids) == 1 for ids in multi.values())
        checks["support_histogram_equals_ground_truth"] = g.summary()["support_histogram"] == {1: 4, 2: 1, 3: 3, 4: 1}
        checks["_support_histogram"] = str(g.summary()["support_histogram"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: v for k, v in checks.items() if not k.startswith("_")}, extra=str({k: v for k, v in checks.items() if k.startswith("_")}))


def run_ar51() -> "TestOutcome":
    """AR51: exporters + live bridge: labelled shared steps become one RAG workflow, rows only for matched controls, and the live hint relocalises on a differently sized screen (flag off = no change)"""
    from core_organs.harvest import consolidate as C
    from core_organs.harvest import video_graph_live as L
    tmp = tempfile.mkdtemp(prefix="vc_")
    checks: Dict[str, Any] = {}
    try:
        g, _reps, _vids = build_graph(tmp)
        # label the edges the way a transcript would: the control the author clicked, taken from the recording plan (ground truth), majority over the edge's observations
        for e in g.edges:
            votes: Dict[str, int] = {}
            for o in e["obs"]:
                tr = truth_of(o["video"], o["t"])
                if tr and tr[2] in CONTROL_LABEL and tr[1] != "home":
                    votes[CONTROL_LABEL[tr[2]].lower()] = votes.get(CONTROL_LABEL[tr[2]].lower(), 0) + 1
            if votes:
                e["labels"] = votes
                for o in e["obs"]:
                    tr = truth_of(o["video"], o["t"])
                    if tr and tr[2] in CONTROL_LABEL and tr[1] != "home":
                        o["label_keys"] = [CONTROL_LABEL[tr[2]].lower()]
        wrote: List[Any] = []

        class FakeRag:
            pass
        import core_organs.harvest.rag_feed as RF
        orig = RF.write_workflow
        RF.write_workflow = lambda rag, app_key, app_name, title, steps, source: (wrote.append((app_key, title, [st["text"] for st in steps], source)) or {"chains": len(steps)})   # type: ignore
        try:
            res = C.export_rag(g, FakeRag(), "Synthetic DAW", include_unique=True)
        finally:
            RF.write_workflow = orig
        checks["labelled_edges_become_one_workflow"] = bool(wrote) and len(wrote[0][2]) >= 3 and "video-consolidation" in wrote[0][3]
        checks["only_named_concepts_are_written"] = res["written"] == len([c for c in g.concepts() if len(c["key"]) >= 3])
        checks["shared_steps_come_before_unique_branches"] = True
        txts = wrote[0][2] if wrote else []
        uniq_idx = [i for i, t in enumerate(txts) if "alternate path" in t]
        checks["shared_steps_come_before_unique_branches"] = (not uniq_idx) or min(uniq_idx) >= len(txts) - len(uniq_idx)
        # training rows: only when the label is on the screen's Set-of-Marks
        def fake_som(img, region=None):
            return {"elements": [{"id": i + 1, "role": "button", "label": n, "box": [0, 0, 10, 10]} for i, n in enumerate(["File", "Settings", "Export", "Layers", "Draw"])], "seconds": 0.0}
        out = os.path.join(tmp, "rows.jsonl")
        rep = C.export_training(g, out, root=tmp, som_fn=fake_som)
        import json
        rows = [json.loads(l) for l in open(out, encoding="utf-8")] if os.path.isfile(out) else []
        checks["rows_only_for_labels_found_on_screen"] = len(rows) >= 2 and all(r["meta"]["source"] == "video-consolidation" for r in rows)
        checks["same_action_in_several_videos_gives_several_rows"] = len({r["meta"]["video_id"] for r in rows if r["meta"]["concept"] == rows[0]["meta"]["concept"]}) >= 2 if rows else False
        checks["a_label_not_on_screen_gives_no_row"] = rep.get("label_not_on_screen", 0) >= 1
        # live bridge: flag off changes nothing
        os.environ.pop("HOJAIGA_VIDEO_GRAPH", None)
        checks["flag_off_hint_is_unchanged"] = L.augment("base hint", None, "synthetic_daw", "open settings") == "base hint"
        # live bridge. Evidence 1: the edge's label is among the live screen's own control labels (what the grounder already holds)
        g.save()
        L.CACHE.clear()
        os.environ["HOJAIGA_VIDEO_GRAPH"] = "1"
        os.environ["HOJAIGA_VIDEO_GRAPH_DIR"] = os.path.dirname(g.root)
        try:
            live = frame_of(render("home", "light", (600, 400)), 1100, 620, (0, 0), False)
            som_home = {"elements": [{"id": i + 1, "role": "button", "label": n, "box": [0, 0, 1, 1]} for i, n in enumerate(["File", "Edit", "View", "Help", "Export", "Layers", "Draw"])]}
            h_file = L.augment("base hint", live, "synthetic_daw", "open the file menu", som=som_home)
            checks["hint_keeps_the_existing_hint_and_adds_the_video_one"] = h_file.startswith("base hint\n") and "'file'" in h_file and "tutorial video" in h_file
            som_other = {"elements": [{"id": 1, "role": "button", "label": "Print", "box": [0, 0, 1, 1]}, {"id": 2, "role": "button", "label": "Zoom", "box": [0, 0, 1, 1]}]}
            checks["no_hint_when_no_known_control_is_on_screen"] = L.augment("base hint", live, "synthetic_daw", "open the file menu", som=som_other) == "base hint"
            checks["goal_relevant_and_best_supported_come_first"] = L.augment("", live, "synthetic_daw", "open the file menu", som=som_home).split("'")[1] == "file"
            # Evidence 2: the control is FOUND again in a differently sized, differently themed live picture, in live pixels
            els = L.elements("synthetic_daw", live, "export the project", root=g.root)
            checks["elements_use_the_6_field_contract"] = bool(els) and all(set(e) >= {"id", "name", "role", "bbox", "provider_tier", "confidence"} for e in els)
            checks["tier_name"] = bool(els) and all(e["provider_tier"] == "tier4_offline_video_grounding" for e in els)
            ex = [e for e in els if e["name"] == "export"]
            if ex:
                x0, y0, x1, y1 = ex[0]["bbox"]
                checks["export_button_found_in_live_pixels"] = x0 > 0.75 * 1100 and y0 < 0.2 * 620 and (x1 - x0) < 0.25 * 1100
            else:
                checks["export_button_found_in_live_pixels"] = False
            fl = [e for e in L.elements("synthetic_daw", live, "open the file menu", root=g.root) if e["name"] == "file"]
            if fl:
                x0, y0, x1, y1 = fl[0]["bbox"]
                checks["file_title_found_in_live_pixels_on_the_menu_bar"] = y0 < 0.1 * 620 and x0 < 0.15 * 1100
            else:
                checks["file_title_found_in_live_pixels_on_the_menu_bar"] = False
            allfound = L.candidates(L.graph("synthetic_daw", g.root), live, "", limit=50)
            labelled = [e for e in g.edges if g.best_label(e) and e.get("opener_crops")]
            checks["_localize_recall"] = f"{len(allfound)} found of {len(labelled)} labelled edges that have a stored control crop (of {len([e for e in g.edges if g.best_label(e)])} labelled)"
            blank = frame_of(render("home", "dark", (0, 0)), 400, 300, (0, 0), False) * 0
            checks["unrelated_screen_finds_nothing"] = L.candidates(L.graph("synthetic_daw", g.root), blank, "open the file menu") == []
        finally:
            os.environ.pop("HOJAIGA_VIDEO_GRAPH", None)
            os.environ.pop("HOJAIGA_VIDEO_GRAPH_DIR", None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: v for k, v in checks.items() if not k.startswith('_')}, extra=str({k: v for k, v in checks.items() if k.startswith('_')}))


# what each author SAYS when clicking the same control: different words, same control
PHRASES = {
    "v1": {"file": "Now click the File menu.", "settings": "Then select Settings.", "advanced": "Go to the Advanced tab.", "close": "Click Close.", "export": "Click the Export button."},
    "v2": {"file": "Open the file menu here.", "settings": "Choose the Settings option.", "close": "Click on Close.", "layers": "Click the Layers panel."},
    "v3": {"export": "First click Export.", "close": "Now click the close button.", "layers": "Click on layers.", "file": "Then select File."},
    "v4": {"file": "Select the File menu.", "settings": "Click Settings.", "close": "Press Close.", "layers": "Click Layers."},
}


def speech_for(video: str) -> List[Dict[str, Any]]:
    """Caption-style segments [{text, start, duration}]: each click is announced about a second before the screen changes."""
    plan, clock, prev, segs = PLAN_OF[video], CARD_OF[video], None, []
    for state, secs, via in plan:
        if prev is not None and via in PHRASES[video]:
            segs.append({"text": PHRASES[video][via], "start": max(0.0, clock - 1.0), "duration": 1.2})
        clock += secs
        prev = state
    return segs


def build_graph_with_speech(root: str):
    from core_organs.harvest import consolidate as C
    vids = make_videos(root)
    v4 = os.path.join(root, "v4.mp4")
    write_video(v4, V2, dict(STYLE["v3"], theme="light", pad=(10, 10)))
    vids["v4"] = v4
    g = C.AppGraph("synthetic_daw", os.path.join(root, "synthetic_daw"))
    reps = [C.ingest_video(g, p, video_id=v, segments=speech_for(v)) for v, p in vids.items()]
    return g, reps, vids


def run_ar52() -> "TestOutcome":
    """AR52: what authors SAY is the cross-author merge: four recordings with different wording for the same control give one concept per control, support = authors, and a control only one author uses stays unique"""
    from core_organs.harvest import consolidate as C
    tmp = tempfile.mkdtemp(prefix="vc_")
    checks: Dict[str, Any] = {}
    try:
        g, reps, _vids = build_graph_with_speech(tmp)
        cons = {c["key"]: c for c in g.concepts()}
        want = {"file": 4, "close": 4, "settings": 3, "layers": 3, "export": 2, "advanced": 1}
        got = {k: cons[k]["support"] for k in want if k in cons}
        checks["each_spoken_control_becomes_one_concept_with_the_right_support"] = got == want
        checks["different_wording_same_key"] = C.label_key("the Rectangle tool") == C.label_key("rectangle") == C.label_key("Rectangle button") == "rectangle"
        checks["chords_keep_their_identity"] = C.label_key("Ctrl + Shift + E") == "ctrl+shift+e" and C.label_key("control+s") == "ctrl+s"
        checks["a_concept_needs_a_visible_change_at_that_moment"] = all(c["n_obs"] >= c["support"] for c in cons.values()) and len(cons) <= 9
        checks["a_step_labels_only_the_first_event_after_it"] = all(len([o for o in c["obs"] if o["video"] == v]) <= 2 for c in cons.values() for v in c["videos"])
        s = g.summary()
        checks["summary_reports_shared_and_unique_concepts"] = s["concepts_shared(support>=2)"] >= 5 and s["concepts"] >= 6
        checks["agreed_order_follows_the_sessions"] = [c["key"] for c in g.concepts() if c["support"] >= 3][0] in ("file", "close")
        wrote: List[Any] = []
        import core_organs.harvest.rag_feed as RF
        orig = RF.write_workflow
        RF.write_workflow = lambda rag, app_key, app_name, title, steps, source: (wrote.append((app_key, title, steps, source)) or {"chains": len(steps)})   # type: ignore
        try:
            res = C.export_rag(g, object(), "Synthetic DAW")
        finally:
            RF.write_workflow = orig
        agreed = [c["key"] for c in g.concepts() if c["support"] >= 2]
        checks["rag_export_writes_only_the_agreed_concepts_by_default"] = bool(wrote) and [st["names"][0] for st in wrote[0][2]] == [c["key"] for c in sorted([c for c in g.concepts() if c["support"] >= 2], key=lambda c: c["order"])] and "advanced" not in agreed
        checks["_concepts"] = str({k: v["support"] for k, v in cons.items()})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: v for k, v in checks.items() if not k.startswith("_")}, extra=str({k: v for k, v in checks.items() if k.startswith("_")}))


def run_ar53() -> "TestOutcome":
    """AR53: text read off the screens: a shortcut counts only when >= 2 authors' screens show it, a Mac author's cmd chord and a Windows author's ctrl chord are one fact, one author's OCR slip is dropped"""
    from core_organs.harvest import consolidate as C
    checks: Dict[str, Any] = {}
    f = C.facts_from_text("Paste Cmd+V | Copy to clipboard as PNG Shift+Option+c | Save Ctrl+S | Cmdtv¥ garbage")
    checks["chords_with_their_action_are_read"] = {(x["chord"], x["action"].lower()) for x in f} >= {("cmd+v", "paste"), ("shift+option+c", "copy to clipboard as png"), ("ctrl+s", "save")}
    checks["a_garbled_chord_is_not_a_fact"] = len(f) == 3
    checks["mac_chords_become_windows_chords"] = C.windows_chord("cmd+v") == "ctrl+v" and C.windows_chord("shift+option+c") == "shift+alt+c" and C.windows_chord("ctrl+s") == "ctrl+s"
    tmp = tempfile.mkdtemp(prefix="vc_")
    try:
        g, _reps, _vids = build_graph(tmp)
        screens = {"v1": "New project\nSave Ctrl+S\nQuit Ctrl+Q\nOpen Ctrl+O",
                   "v2": "New project\nSave Cmd+S\nQuit Cmd+Q\nOpn Ctrl+X",
                   "v3": "New project\nSave Ctrl+S\nQuit Ctrl+Q"}

        def fake_ocr(post_path, primary, crop_px):
            for v, txt in screens.items():
                if os.sep + v + os.sep in post_path or "/" + v + "/" in post_path:
                    return txt
            return ""
        rep = C.ocr_edges(g, ocr=fake_ocr)
        facts = {x["windows"]: x for x in g.facts()}
        checks["ocr_ran_on_the_shared_edges_only"] = 0 < rep["ocr_calls"] <= sum(min(len(e["obs"]), 8) for e in g.edges if g.support(e) >= 2)
        checks["shortcut_shown_by_several_authors_is_a_fact"] = "ctrl+s" in facts and "ctrl+q" in facts and facts["ctrl+s"]["videos"] >= 3
        checks["mac_and_windows_author_agree_on_one_fact"] = facts.get("ctrl+s", {}).get("mac_style") is True
        checks["one_authors_ocr_slip_is_dropped"] = "ctrl+o" not in facts and "ctrl+x" not in facts
        lines = [l["text"] for e in g.edges for l in (e.get("ocr") or {}).get("lines", [])]
        checks["shared_menu_text_is_kept_and_a_typo_is_not"] = "New project" in lines and not any(t.startswith("Opn") for t in lines)
        class Rep:
            inserted, updated = 1, 0

        class FakeRag:
            def __init__(self):
                self.cmds, self.rows, self.procs = [], [], []
                outer = self

                class Lex:
                    def add_command(self, key, label, source="", trust=""):
                        outer.cmds.append((key, label, source, trust))
                        return f"{key}:{label.lower()}"

                class Fast:
                    def upsert(self, recs):
                        outer.rows += list(recs)
                        return Rep()

                class Proc:
                    def ingest_procedure(self, key, title, steps, source, trust=""):
                        outer.procs.append((key, title, steps, source, trust))
                        return Rep()
                self.lex, self.fast, self.proc = Lex(), Fast(), Proc()
        fr = FakeRag()
        res = C.export_facts_rag(g, fr, "Synthetic DAW")
        checks["facts_are_filed_under_the_graphs_own_app_key"] = res["written"] == len(fr.rows) >= 2 and all(r["app_key"] == "synthetic_daw" for r in fr.rows) and all(c[0] == "synthetic_daw" for c in fr.cmds)
        checks["hotkeys_are_leads_not_verified_shortcuts"] = all(r["verified"] is False and r["trust"] == "web" for r in fr.rows)
        checks["windows_form_is_what_is_stored"] = any(r["payload"] == "ctrl+s" for r in fr.rows) and not any("cmd" in str(r["payload"]) for r in fr.rows)
        checks["one_procedure_with_a_video_ocr_source"] = len(fr.procs) == 1 and fr.procs[0][3].startswith("video-ocr") and fr.procs[0][4] == "web"
        res2 = C.export_facts_rag(g, FakeRag(), "Synthetic DAW", write_procedure=False)
        checks["procedure_can_be_skipped"] = "procedure" not in res2 and res2["written"] == res["written"]
        from core_organs.harvest import video_graph_live as L
        os.environ.pop("HOJAIGA_VIDEO_GRAPH", None)
        checks["flag_off_shortcut_hint_changes_nothing"] = L.augment("base", None, "synthetic_daw", "save the project") == "base"
        os.environ["HOJAIGA_VIDEO_GRAPH"] = "1"
        os.environ["HOJAIGA_VIDEO_GRAPH_DIR"] = tmp
        L.CACHE.clear()
        try:
            h = L.augment("base", None, "synthetic_daw", "please save the project")
            checks["a_goal_that_names_a_known_shortcut_gets_it_as_a_hint"] = h.startswith("base\n") and "CTRL+S" in h and "unverified" in h and "Save" in h
            checks["an_unrelated_goal_gets_no_shortcut"] = L.augment("base", None, "synthetic_daw", "rotate the canvas") == "base"
        finally:
            os.environ.pop("HOJAIGA_VIDEO_GRAPH", None)
            os.environ.pop("HOJAIGA_VIDEO_GRAPH_DIR", None)
        checks["_facts"] = str([(k, v["videos"]) for k, v in facts.items()])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: v for k, v in checks.items() if not k.startswith("_")}, extra=str({k: v for k, v in checks.items() if k.startswith("_")}))


class FakePage:
    """A stand-in for the page, with a few REAL behaviours bound to chords (key-code form). The verifier is never told them: it has to reach the right verdicts from pictures, the accessibility
    text, the saved scene and the clipboard alone. `noisy` makes the picture move by itself (an animation), `broken` makes the page unloadable."""

    def __init__(self, noisy: bool = False, broken: bool = False, stale_clipboard: bool = False, empty_copy: bool = False):
        self.noisy, self.broken, self.empty_copy = noisy, broken, empty_copy
        self.zz = False
        self.tick = 0
        self.els: List[Dict[str, Any]] = []
        self.sel: List[str] = []
        self.clip: List[Dict[str, Any]] = [{"id": "left_over_from_an_earlier_attempt"}] if stale_clipboard else []
        self.zen = self.view = self.snap = False
        self.closed = False
        self.b = {
            "Alt+KeyZ": self._zen, "Alt+KeyR": self._view, "Alt+KeyS": self._snap, "Control+KeyA": self._all, "Control+KeyG": self._group, "Control+KeyD": self._dup,
            "Control+Shift+KeyL": self._lock, "Control+KeyC": self._copy, "Control+KeyX": self._cut, "Control+KeyV": self._paste, "Shift+KeyH": self._flip,
            "Control+BracketRight": self._fwd, "Control+Alt+BracketRight": self._fwd, "Control+Shift+BracketRight": self._front, "Alt+KeyB": self._delete_instead, "Alt+KeyP": self._zz}

    # --- the driver interface
    def load(self, elements):
        if self.broken:
            raise RuntimeError("net::ERR_INTERNET_DISCONNECTED")
        import copy
        self.els, self.sel, self.zen, self.view, self.snap = copy.deepcopy(list(elements)), [], False, False, False

    def click(self, x, y, shift=False):
        for e in reversed(self.els):
            if not e["isDeleted"] and e["x"] <= x <= e["x"] + e["width"] and e["y"] <= y <= e["y"] + e["height"]:
                if shift:
                    self.sel = self.sel + [e["id"]] if e["id"] not in self.sel else self.sel
                else:
                    self.sel = [e["id"]]
                return

    def press(self, chord):
        fn = self.b.get(playwright_chord_of(chord))
        if fn:
            fn()

    def wait(self, s):
        self.tick += 1

    def screenshot(self):
        import numpy as np
        import cv2
        im = np.full((800, 1280, 3), 255, np.uint8)
        if not (self.zen or self.view):
            cv2.rectangle(im, (0, 0), (1280, 60), (200, 200, 200), -1)
            cv2.rectangle(im, (0, 60), (90, 800), (220, 220, 220), -1)
        for e in self.els:
            if not e["isDeleted"]:
                cv2.rectangle(im, (int(e["x"]), int(e["y"])), (int(e["x"] + e["width"]), int(e["y"] + e["height"])), (120, 160, 240), -1)
                if e["id"] in self.sel:
                    cv2.rectangle(im, (int(e["x"]) - 4, int(e["y"]) - 4), (int(e["x"] + e["width"]) + 4, int(e["y"] + e["height"]) + 4), (200, 60, 0), 3)
        if self.noisy:
            self.tick += 1
            cv2.circle(im, (600 + 40 * (self.tick % 7), 120 + 15 * (self.tick % 5)), 70, (0, 0, 0), -1)        # something moves by itself
        return im

    def aria(self):
        lines = [] if (self.zen or self.view) else [f"- button 'Tool {i}'" for i in range(12)]
        if self.sel:
            lines += ["- heading 'Stroke'", "- heading 'Background'"]
        return "\n".join(lines)

    def scene(self):
        import json as _j
        from core_organs.harvest.shortcut_verify import scene_summary
        return scene_summary(_j.dumps(self.els), _j.dumps({"objectsSnapModeEnabled": self.snap, "zzFlag": self.zz}))

    def clipboard(self):
        return {"any": bool(self.clip), "image": False, "types": ["text/plain"] if self.clip else [], "sig": f"text/plain:{len(self.clip)}:{sum(len(str(c)) for c in self.clip)}"}

    def clear_clipboard(self):
        self.clip = []

    def close(self):
        self.closed = True

    # --- behaviours
    def _zen(self): self.zen = not self.zen
    def _view(self): self.view = not self.view
    def _snap(self): self.snap = not self.snap
    def _all(self): self.sel = [e["id"] for e in self.els if not e["isDeleted"]]

    def _group(self):
        if len(self.sel) >= 2:
            for e in self.els:
                if e["id"] in self.sel:
                    e["groupIds"] = ["g1"]
                    e["version"] += 1

    def _dup(self):
        import copy
        for e in [x for x in self.els if x["id"] in self.sel]:
            n = copy.deepcopy(e)
            n["id"], n["x"], n["y"] = e["id"] + "d", e["x"] + 10, e["y"] + 10
            self.els.append(n)

    def _lock(self):
        for e in self.els:
            e["locked"] = True
            e["version"] += 1

    def _copy(self):
        self.clip = [dict(e) for e in self.els if e["id"] in self.sel] or ([{"type": "empty-payload"}] if self.empty_copy else [])

    def _cut(self):
        self.clip = [dict(e) for e in self.els if e["id"] in self.sel]
        for e in self.els:
            if e["id"] in self.sel:
                e["isDeleted"] = True

    def _paste(self):
        for e in list(self.clip):
            n = dict(e)
            n["id"], n["x"] = e["id"] + "p", e["x"] + 20
            n["isDeleted"] = False
            self.els.append(n)

    def _flip(self):
        for e in self.els:
            if e["id"] in self.sel:
                e["version"] += 1

    def _fwd(self):                                   # ONE place up
        if self.sel:
            i = next(k for k, x in enumerate(self.els) if x["id"] == self.sel[0])
            if i < len(self.els) - 1:
                self.els[i], self.els[i + 1] = self.els[i + 1], self.els[i]

    def _front(self):                                 # all the way up
        if self.sel:
            e = next(x for x in self.els if x["id"] == self.sel[0])
            self.els.remove(e)
            self.els.append(e)

    def _zz(self): self.zz = not self.zz

    def _delete_instead(self):
        for e in self.els:
            if e["id"] in self.sel:
                e["isDeleted"] = True


def playwright_chord_of(c):
    from core_organs.harvest.shortcut_verify import playwright_chord
    return playwright_chord(c) if "+Key" not in c and "Bracket" not in c else c


def run_ar54() -> "TestOutcome":
    """AR54: the shortcut verifier reaches the right verdict from evidence alone: a working shortcut is VERIFIED only when its effect beats the control's noise AND matches its name; a decoy that does nothing is NO_EFFECT even on a page that moves by itself; one that does the wrong thing is MISMATCH; proofs are saved and promotion touches only VERIFIED"""
    from core_organs.harvest import shortcut_verify as SV, consolidate as C
    checks: Dict[str, Any] = {}
    checks["chords_become_key_codes"] = (SV.playwright_chord("ctrl+alt+]") == "Control+Alt+BracketRight" and SV.playwright_chord("shift+h") == "Shift+KeyH" and SV.playwright_chord("alt+/") == "Alt+Slash"
                                         and SV.playwright_chord("ctrl+1") == "Control+Digit1")
    facts = [{"action": a, "windows": w, "chord": w, "videos": 3, "mac_style": a == "Bring to front"} for a, w in [
        ("Zen mode", "alt+z"), ("View mode", "alt+r"), ("Snap to objects", "alt+s"), ("Select all", "ctrl+a"), ("Group selection", "ctrl+g"), ("Duplicate", "ctrl+d"),
        ("Lock all", "ctrl+shift+l"), ("Copy", "ctrl+c"), ("Cut", "ctrl+x"), ("Paste", "ctrl+v"), ("Flip horizontal", "shift+h"), ("Bring forward", "ctrl+]"),
        ("Bring to front", "ctrl+alt+]"), ("Frobnicate", "alt+q"), ("Bring to back", "alt+b"), ("Pixie dust", "alt+p")]]
    tmp = tempfile.mkdtemp(prefix="sv_")
    try:
        drv = FakePage()
        res = {f["action"]: SV.verify_fact(drv, f, facts, tmp, log=lambda s: None) for f in facts}
        v = {k: r["verdict"] for k, r in res.items()}
        checks["working_shortcuts_with_a_checkable_name_are_verified"] = all(v[k] == "VERIFIED" for k in ("Zen mode", "View mode", "Select all", "Group selection", "Duplicate", "Lock all", "Copy", "Cut", "Paste", "Flip horizontal", "Bring forward"))
        checks["a_setting_that_flips_under_a_matching_name_is_verified"] = v["Snap to objects"] == "VERIFIED"
        checks["a_flip_of_an_unrelated_setting_is_effect_only"] = v["Pixie dust"] == "EFFECT_ONLY"
        checks["wrong_effect_is_a_mismatch"] = v["Bring to back"] == "MISMATCH"
        checks["forward_is_not_mistaken_for_front_and_the_windows_variant_is_found"] = (v["Bring to front"] == "VERIFIED" and res["Bring to front"].get("variant_of") == "ctrl+alt+]" and res["Bring to front"]["chord"] == "ctrl+shift+]"
                                                                                       and res["Bring to front"]["first_try"]["verdict"] == "MISMATCH")
        rc = SV.verify_fact(FakePage(empty_copy=True), facts[7], facts, os.path.join(tmp, "emptycopy"), log=lambda s: None)
        checks["copying_nothing_is_not_proof_that_copy_works"] = rc["verdict"] == "VERIFIED" and rc["rung"].startswith("P1")
        checks["a_stale_clipboard_does_not_hide_a_copy"] = SV.verify_fact(FakePage(stale_clipboard=True), facts[7], facts, os.path.join(tmp, "stale"), log=lambda s: None)["verdict"] == "VERIFIED"
        checks["no_effect_is_no_effect"] = v["Frobnicate"] == "NO_EFFECT"
        checks["the_ladder_climbs_until_the_effect_appears"] = res["Duplicate"]["rung"].startswith("P1") and res["Group selection"]["rung"].startswith("P2") and res["Zen mode"]["rung"].startswith("P0")
        checks["the_proof_records_that_the_selection_was_seen"] = all(a.get("selection_seen") is True for a in res["Duplicate"]["attempts"] if "rung" in a and "error" not in a)
        checks["paste_runs_its_copy_sibling_first"] = res["Paste"]["prerequisite"] == "ctrl+c" and SV.prerequisite_for(facts[0], facts) is None
        noisy = FakePage(noisy=True)
        extra = os.path.join(tmp, "extra")
        rn = SV.verify_fact(noisy, next(f for f in facts if f["action"] == "Frobnicate"), facts, extra, log=lambda s: None)
        checks["a_page_that_moves_by_itself_does_not_fake_an_effect"] = rn["verdict"] == "NO_EFFECT"
        rz = SV.verify_fact(FakePage(noisy=True), facts[0], facts, extra, log=lambda s: None)
        checks["real_effect_is_still_seen_on_a_noisy_page_via_the_other_tiers"] = rz["verdict"] == "VERIFIED"
        rb = SV.verify_fact(FakePage(broken=True), facts[0], facts, extra, log=lambda s: None)
        checks["an_unloadable_page_is_env_blocked_not_a_verdict"] = rb["verdict"] == "ENV_BLOCKED"
        # proofs: every attempt's pictures exist and the manifest hashes match
        att = [a for r in res.values() for a in r["attempts"] if "files" in a]
        checks["every_attempt_saved_before_control_and_after_pictures"] = bool(att) and all(os.path.isfile(os.path.join(tmp, f)) for a in att for f in a["files"].values())
        checks["manifest_hashes_match_the_files"] = all(SV._sha(os.path.join(tmp, a["files"][k])) == a["hashes"][k] for a in att[:12] for k in a["files"])
        # a whole run from a graph's facts, with the report and results files
        g = C.AppGraph("fake_app", os.path.join(tmp, "g"))
        g.edges = [{"id": 0, "videos": ["a", "b"], "obs": [], "ocr": {"lines": [], "facts": [dict(chord=f["chord"], windows=f["windows"], action=f["action"], videos=f["videos"], mac_style=False) for f in facts[:3]]}}]
        g.videos = ["a", "b"]
        g.save()
        orig_load = C.AppGraph.load
        C.AppGraph.load = classmethod(lambda cls, app_key, root="": orig_load.__func__(cls, app_key, os.path.join(tmp, "g")))   # type: ignore
        try:
            out = SV.run("fake_app", "http://fake", driver_factory=lambda: FakePage(), out_root=os.path.join(tmp, "out"), log=lambda s: None)
            pl = SV.plan("fake_app")
        finally:
            C.AppGraph.load = orig_load                                         # type: ignore
        checks["run_writes_results_and_a_markdown_report_with_pictures"] = os.path.isfile(os.path.join(out["out_dir"], "results.json")) and "![after]" in open(os.path.join(out["out_dir"], "report.md"), encoding="utf-8").read()
        checks["plan_touches_nothing_and_lists_every_shortcut"] = pl["shortcuts"] == 3 and all("press" in r for r in pl["rows"])
        # promotion: only VERIFIED rows, as verified=True with the proof folder
        rows = []

        class FR:
            class lex:
                @staticmethod
                def best(app, action):
                    class H: command_id = f"{app}:{action.lower()}"
                    return H()

            class fast:
                @staticmethod
                def find(app, action, payload):
                    return None

                @staticmethod
                def upsert(recs):
                    rows.extend(recs)

                    class R: inserted, updated = len(recs), 0
                    return R()
        rp = SV.promote(os.path.join(out["out_dir"], "results.json"), FR)
        n_ver = sum(1 for r in out["results"] if r["verdict"] == "VERIFIED")
        checks["promotion_touches_only_verified_rows"] = rp["promoted"] == n_ver == len(rows) and all(r["verified"] is True and "proof" in r["context"] for r in rows)
        res_path = os.path.join(tmp, "variant_results.json")
        json_ = __import__("json")
        json_.dump({"app_key": "fake_app", "when": "t", "results": [{"action": "Bring to front", "chord": "ctrl+shift+]", "variant_of": "ctrl+alt+]", "verdict": "VERIFIED", "rung": "P1", "attempts": []},
                                                                  {"action": "Frobnicate", "chord": "alt+q", "verdict": "NO_EFFECT", "attempts": []}]}, open(res_path, "w"))
        calls: List[Any] = []

        class FR2:
            lex = FR.lex

            class fast:
                @staticmethod
                def find(app, action, payload):
                    return {"fast_id": "old1"} if payload == "ctrl+alt+]" else None

                @staticmethod
                def upsert(recs):
                    calls.append(("upsert", recs[0]["payload"], recs[0]["verified"]))

                @staticmethod
                def annotate(fid, ctx):
                    calls.append(("annotate", fid, ctx))

                @staticmethod
                def set_verified(fid, v, run=""):
                    calls.append(("set_verified", fid, v))
        rp2 = SV.promote(res_path, FR2)
        checks["a_refuted_video_chord_is_annotated_and_left_unverified_the_proven_one_is_added"] = (
            rp2["promoted"] == 1 and rp2["refuted_rows_annotated"] == 1 and ("upsert", "ctrl+shift+]", True) in calls and any(c[0] == "annotate" and c[1] == "old1" and "REFUTED" in c[2] for c in calls)
            and ("set_verified", "old1", False) in calls)
        fsom = lambda img, **k: {"elements": [{"id": 1, "role": "button", "label": "Zen", "box": [0, 0, 5, 5]}], "seconds": 0.0}
        res_json = os.path.join(out["out_dir"], "results.json")
        tr1 = SV.export_training_rows(res_json, os.path.join(tmp, "rows.jsonl"), som_fn=fsom, root=tmp)
        n_ok = sum(1 for r in out["results"] if r["verdict"] == "VERIFIED")
        rows_v = [json_.loads(l) for l in open(os.path.join(tmp, "rows.jsonl"), encoding="utf-8")] if tr1["rows"] else []
        checks["verified_shortcuts_become_training_rows_with_their_proof_picture"] = tr1["rows"] == n_ok > 0 and all(r["meta"]["verified"] is True and r["meta"]["source"] == "live-verified-shortcut" for r in rows_v)
        checks["the_answer_is_the_proven_hotkey_and_the_prompt_is_the_usual_shape"] = all(json_.loads(r["messages"][2]["content"][0]["text"])[0]["action"] == "hotkey" and "Goal:" in r["messages"][1]["content"][1]["text"] for r in rows_v)
        tr2 = SV.export_training_rows(res_json, os.path.join(tmp, "rows.jsonl"), som_fn=fsom, root=tmp)
        checks["running_it_again_adds_nothing"] = tr2["rows"] == 0 and tr2["skipped"]["duplicate"] == n_ok
        checks["_verdicts"] = str(v)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: x for k, x in checks.items() if not k.startswith("_")}, extra=str({k: x for k, x in checks.items() if k.startswith("_")}))


def run_ar55() -> "TestOutcome":
    """AR55: promotion on a REAL (temporary) fast-path store works in place: the harvested row becomes verified with the same id (no duplicate), the video's refuted chord is annotated and unverified, the proven variant is added once, and an ingest that made duplicates can be undone row by row"""
    from si_tests_rag import _Env
    from core_organs.harvest import shortcut_verify as SV
    checks: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="sv55_")
    try:
        with _Env() as rag:
            key = "webapp:fake.test"
            rows = [{"app_key": key, "kind": "hotkey", "command_id": "", "task_pattern": a, "payload": p, "source": "web_table", "trust": "web", "verified": False,
                     "context": f"video-ocr: shown by 3 of 8 authors", "params_schema_json": {}} for a, p in [("Zen mode", "alt+z"), ("Bring to front", "ctrl+alt+]"), ("Copy", "ctrl+c")]]
            rag.fast.upsert(rows)
            checks["three_leads_start_unverified"] = rag.fast.count(key) == 3 and not any(rag.fast.find(key, r["task_pattern"], r["payload"])["verified"] for r in rows)
            zen_id = rag.fast.find(key, "Zen mode", "alt+z")["fast_id"]
            res = {"app_key": key, "when": "20261026_000000", "results": [
                {"action": "Zen mode", "chord": "alt+z", "verdict": "VERIFIED", "rung": "P0", "attempts": [{"effect": True, "name_check": True, "files": {"after": "z_after.png"}}]},
                {"action": "Bring to front", "chord": "ctrl+shift+]", "variant_of": "ctrl+alt+]", "verdict": "VERIFIED", "rung": "P1", "attempts": []},
                {"action": "Copy", "chord": "ctrl+c", "verdict": "NO_EFFECT", "attempts": []}]}
            rp = os.path.join(tmp, "results.json")
            __import__("json").dump(res, open(rp, "w"))
            out = SV.promote(rp, rag)
            zen = rag.fast.find(key, "Zen mode", "alt+z")
            checks["verified_in_place_same_id_no_duplicate"] = zen["fast_id"] == zen_id and zen["verified"] is True and zen["trust"] == "verified" and out["in_place"] == 1
            checks["row_count_grows_only_by_the_new_proven_variant"] = rag.fast.count(key) == 4 and out["inserted_new"] == 1
            checks["unproven_lead_is_untouched"] = rag.fast.find(key, "Copy", "ctrl+c")["verified"] is False
            old = rag.fast.find(key, "Bring to front", "ctrl+alt+]")
            checks["refuted_video_chord_is_annotated_and_unverified"] = old["verified"] is False and old["context"].startswith("REFUTED live") and "ctrl+shift+]" in old["context"]
            new = rag.fast.find(key, "Bring to front", "ctrl+shift+]")
            checks["proven_variant_is_verified"] = bool(new) and new["verified"] is True and new["trust"] == "verified"
            checks["a_proof_file_is_written"] = os.path.isfile(os.path.join(tmp, "promoted.json"))
            # undo an ingest that made duplicates, row by row
            dup = dict(rows[0], context="verified live DUPLICATE", verified=True)
            rag.fast.upsert([dup])
            checks["a_duplicate_row_exists_before_the_cleanup"] = rag.fast.count(key) == 5
            dup_id = [e.payload["fast_id"] for e in rag.fast.by_goal(key, "Zen mode", limit=10) if "DUPLICATE" in (e.payload.get("context") or "")]
            n = rag.fast.forget_rows(dup_id)
            checks["cleanup_removes_exactly_the_duplicate"] = n == 1 and rag.fast.count(key) == 4 and rag.fast.find(key, "Zen mode", "alt+z")["fast_id"] == zen_id
            checks["the_text_index_forgot_it_too"] = all("DUPLICATE" not in (e.payload.get("context") or "") for e in rag.fast.by_goal(key, "Zen mode", limit=10))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict(checks)


def run_ar56() -> "TestOutcome":
    """AR56: the unattended curriculum is safe to leave alone: easy->complex with categories taking turns, finished apps are skipped on resume, a time budget / STOP file / disk guard / three failures in a row end it cleanly, one failing app does not stop the rest, a rate limit waits and never retries in a loop, and RAG writes are conservative (new facts only; known = corroborated, different = conflict) and can be rolled back row by row"""
    from si_tests_rag import _Env
    from core_organs.harvest import video_curriculum as VC, consolidate as C
    checks: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="vc56_")
    saved = (VC.CURRICULUM_PATH, VC.STATE_PATH, VC.STOP_PATH, VC.OUT_ROOT, VC.free_gb)
    VC.CURRICULUM_PATH, VC.STATE_PATH, VC.STOP_PATH, VC.OUT_ROOT = (os.path.join(tmp, "curriculum.json"), os.path.join(tmp, "state.json"), os.path.join(tmp, "STOP"), os.path.join(tmp, "out"))
    quiet = lambda s: None
    try:
        rows = [dict(name=n, search=n, kind="desktop", host="", category=c, tier=t, videos=3, min_min=3, max_min=10) for n, c, t in [
            ("E1", "doc", 1), ("E2", "doc", 1), ("E3", "paint", 1), ("M1", "doc", 2), ("M2", "ide", 2), ("H1", "3d", 3)]]
        order = [e["name"] for e in VC.ordered(rows)]
        checks["easy_before_complex_and_categories_take_turns"] = order == ["E1", "E2", "E3", "M1", "M2", "H1"]
        lad = [dict(name=f"{c}{k}", search="", kind="desktop", host="", category=c, tier=1 + k // 3, rung=k, videos=3, min_min=3, max_min=9) for c in ("w", "d") for k in range(3)]
        checks["the_simplest_app_of_every_category_comes_before_the_second_of_any"] = [e["name"] for e in VC.ordered(lad)] == ["w0", "d0", "w1", "d1", "w2", "d2"]
        checks["a_tier_filter_and_an_only_filter_work"] = [e["name"] for e in VC.ordered(rows, tiers=[3])] == ["H1"] and [e["name"] for e in VC.ordered(rows, only=["m2"])] == ["M2"]
        dflt = VC.load_curriculum()
        checks["the_default_curriculum_is_written_as_an_editable_file_of_ladders"] = (os.path.isfile(VC.CURRICULUM_PATH) and {1, 2, 3} <= {e["tier"] for e in dflt} and len(dflt) >= 60
                                                                                      and len({e["category"] for e in dflt}) >= 12 and all("rung" in e for e in dflt))
        checks["each_ladder_starts_simple_and_the_names_are_unique_app_keys"] = (len({VC.app_key(e) for e in dflt}) == len(dflt) and VC.app_key({"name": "Notepad++", "kind": "desktop", "host": ""}) != VC.app_key({"name": "Notepad", "kind": "desktop", "host": ""}))
        checks["keys_follow_the_projects_own_conventions"] = VC.app_key({"name": "Figma", "kind": "web", "host": "figma.com"}) == "webapp:figma.com" and VC.app_key({"name": "Blender", "kind": "desktop", "host": ""}) == "blender"
        checks["relevance_words_ignore_generic_ones"] = VC.required_words("Windows 11 Notepad") == ["notepad"] and "visual" in VC.required_words("Visual Studio Code")
        # --- a run with a fake per-app function
        calls: List[str] = []
        script = {"E1": {"status": "ok", "shortcut_facts": 3, "rag": {"written": 2, "rows": [["Zen mode", "alt+z"], ["Save", "ctrl+s"]]}, "videos_ingested": 3, "edges": 40, "shared_edges": 5},
                  "E3": {"status": "too_few_videos", "videos_downloaded": 1}, "E2": {"status": "ok", "shortcut_facts": 0, "videos_ingested": 3}, "M1": RuntimeError("boom"),
                  "M2": {"status": "ok", "shortcut_facts": 1, "videos_ingested": 2, "rag": {"written": 0}}, "H1": {"status": "ok", "shortcut_facts": 4, "videos_ingested": 6, "rag": {"written": 1, "rows": [["Orbit", "alt+o"]]}, "rate_limited": True}}

        def fake(entry, rag, log, **kw):
            calls.append(entry["name"])
            r = script[entry["name"]]
            if isinstance(r, Exception):
                raise r
            return dict(r, name=entry["name"], tier=entry["tier"], category=entry["category"], key=entry["name"].lower())
        sleeps: List[float] = []
        out = VC.run_curriculum(hours=5, rows=rows, app_runner=fake, log=quiet, sleep=sleeps.append)
        st = VC.load_state()["apps"]
        checks["every_app_ran_in_order_and_one_failure_did_not_stop_the_rest"] = calls == ["E1", "E2", "E3", "M1", "M2", "H1"] and st["M1"]["status"] == "error" and st["H1"]["status"] == "ok"
        checks["an_app_with_nothing_two_authors_agree_on_is_marked_so"] = st["E2"]["status"] == "no_new_knowledge" and st["M2"]["status"] == "no_new_knowledge"
        checks["progress_summary_and_rag_write_logs_exist"] = all(os.path.isfile(os.path.join(VC.OUT_ROOT, f)) for f in ("progress.jsonl", "SUMMARY.md", "rag_writes.jsonl")) and "| E1 |" in open(os.path.join(VC.OUT_ROOT, "SUMMARY.md"), encoding="utf-8").read()
        checks["a_rate_limit_waits_instead_of_retrying"] = sleeps == [VC.RATE_LIMIT_WAIT_S]
        # --- resume: finished apps are skipped, failed / too-few ones are retried
        calls.clear()
        script["E3"], script["M1"] = {"status": "ok", "shortcut_facts": 2, "videos_ingested": 3, "rag": {"written": 1, "rows": [["Fill", "f"]]}}, {"status": "ok", "shortcut_facts": 1, "videos_ingested": 2, "rag": {"written": 0}}
        VC.run_curriculum(hours=5, rows=rows, app_runner=fake, log=quiet, sleep=lambda s: None)
        checks["resume_skips_finished_apps_and_retries_the_others"] = sorted(calls) == ["E3", "M1"]
        # --- stop conditions
        for n in list(VC.load_state()["apps"]):
            pass
        json.dump({"apps": {}}, open(VC.STATE_PATH, "w"))
        calls.clear()
        VC.run_curriculum(hours=0.0, rows=rows, app_runner=fake, log=quiet)
        checks["a_spent_time_budget_ends_the_run_before_the_next_app"] = calls == []
        open(VC.STOP_PATH, "w").write("x")
        VC.run_curriculum(hours=5, rows=rows, app_runner=fake, log=quiet)
        checks["the_STOP_file_ends_the_run"] = calls == []
        os.remove(VC.STOP_PATH)
        VC.free_gb = lambda path=None: 5.0
        VC.run_curriculum(hours=5, rows=rows, app_runner=fake, log=quiet)
        checks["low_disk_ends_the_run"] = calls == []
        VC.free_gb = saved[4]
        bad = {e["name"]: RuntimeError("x") for e in rows}
        script.update(bad)
        calls.clear()
        VC.run_curriculum(hours=5, rows=rows, app_runner=fake, log=quiet)
        checks["three_failures_in_a_row_end_the_run"] = len(calls) == VC.MAX_CONSECUTIVE_FAILURES
        # --- the pipeline: app k+1 is ACQUIRED while app k is being LEARNED
        json.dump({"apps": {}}, open(VC.STATE_PATH, "w"))
        import threading as _th
        events: List[str] = []
        lock = _th.Lock()

        def acq(entry, log, stop):
            with lock:
                events.append(f"acq_start:{entry['name']}")
            time.sleep(0.15)
            with lock:
                events.append(f"acq_end:{entry['name']}")
            if entry["name"] == "E2":
                raise RuntimeError("download exploded")
            return {"paths": ["a.mp4", "b.mp4"], "transcribed": 2, "seconds": 0.15}

        def lrn(entry, a, rag, log, write_rag, stop):
            with lock:
                events.append(f"learn_start:{entry['name']}")
            time.sleep(0.4)
            with lock:
                events.append(f"learn_end:{entry['name']}")
            return {"name": entry["name"], "tier": entry["tier"], "category": entry["category"], "status": "ok", "shortcut_facts": 1, "rag": {"written": 1, "rows": []}, "videos_ingested": 2, "edges": 9}
        VC.run_curriculum(hours=5, rows=rows[:3], log=quiet, acquire_fn=acq, learn_fn=lrn, sleep=lambda s: None)
        checks["the_next_app_is_acquired_while_the_current_one_is_learned"] = events.index("acq_start:E3") < events.index("learn_end:E1") if "acq_start:E3" in events else False
        stp = VC.load_state()["apps"]
        checks["a_failed_download_is_an_error_row_and_the_pipeline_goes_on"] = stp["E2"]["status"] == "error" and stp["E3"]["status"] == "ok" and stp["E1"]["status"] == "ok"
        # --- the growth ledger and its chart
        class FakeRag:
            class st:
                @staticmethod
                def count(t):
                    return 100 if t == "fast_paths" else 20
        VC.growth_snapshot(FakeRag, VC.load_state(), "T1")
        VC.growth_snapshot(FakeRag, VC.load_state(), "T2")
        gl = [json.loads(l) for l in open(os.path.join(VC.OUT_ROOT, "growth.jsonl"), encoding="utf-8")]
        checks["the_growth_ledger_records_the_pool_volume_and_draws_a_chart"] = len(gl) >= 2 and gl[-1]["rag"].get("fast_paths") == 100 and gl[-1]["apps_done"] >= 2 and os.path.isfile(os.path.join(VC.OUT_ROOT, "growth.png"))
        # --- run_app gating with the heavy steps replaced by stand-ins (no network, no video)
        class G:
            def __init__(self, n, facts):
                self.videos, self.edges, self._f = [f"v{i}" for i in range(n)], [1, 2, 3], facts

            def baseline(self, min_support=2): return [1]
            def facts(self, min_videos=2): return self._f
        fl = {"fetch": 0, "export": [], "ocr": 0}
        o = (C.fetch_videos, C.AppGraph.load, C.ingest_video, C.ocr_edges, C.understanding_report, C.export_facts_rag)
        entry = dict(name="Zed", search="Zed editor", kind="desktop", host="", category="ide", tier=2, videos=3, min_min=3, max_min=10)
        try:
            C.fetch_videos = lambda *a, **k: fl.__setitem__("fetch", fl["fetch"] + 1) or []
            C.ocr_edges = lambda g, **k: fl.__setitem__("ocr", fl["ocr"] + 1) or {"ocr_calls": 3}
            C.understanding_report = lambda *a, **k: {}
            C.export_facts_rag = lambda g, rag, name, **k: fl["export"].append(k) or {"written": 1, "corroborated": [], "conflicts": [], "rows": [("A", "ctrl+a")]}
            C.ingest_video = lambda g, p, **k: {}
            dl = os.path.join(C.GRAPH_DIR, "_downloads", VC.slug("Zed"))
            r0 = VC.run_app(entry, object(), quiet)
            checks["fewer_than_two_videos_is_not_an_app_and_writes_nothing"] = r0["status"] == "too_few_videos" and fl["export"] == []
            os.makedirs(dl, exist_ok=True)
            for i in range(3):
                open(os.path.join(dl, f"x{i}.mp4"), "wb").write(b"0")
            C.AppGraph.load = classmethod(lambda cls, k, root="": G(3, [{"action": "A", "windows": "ctrl+a", "videos": 2}]))
            r1 = VC.run_app(entry, object(), quiet)
            checks["with_videos_and_facts_it_ocrs_and_exports_only_new_rows"] = r1["status"] == "ok" and fl["ocr"] == 1 and fl["export"] == [{"min_videos": 2, "only_new": True, "accept_single": None}] and r1["rag"]["written"] == 1
            fl["export"].clear()
            VC.run_app(entry, object(), quiet, write_rag=False)
            checks["no_rag_flag_writes_nothing"] = fl["export"] == []
        finally:
            C.fetch_videos, C.AppGraph.load, C.ingest_video, C.ocr_edges, C.understanding_report, C.export_facts_rag = o
            shutil.rmtree(os.path.join(C.GRAPH_DIR, "_downloads", VC.slug("Zed")), ignore_errors=True)
        # --- conservative RAG export + rollback on a REAL temporary store
        with _Env() as rag:
            key = "notepad"
            rag.fast.upsert([{"app_key": key, "kind": "hotkey", "command_id": "", "task_pattern": "Save", "payload": "ctrl+s", "source": "web_table", "trust": "catalog", "verified": False, "context": "catalog", "params_schema_json": {}},
                             {"app_key": key, "kind": "hotkey", "command_id": "", "task_pattern": "Open", "payload": "ctrl+o", "source": "web_table", "trust": "catalog", "verified": False, "context": "catalog", "params_schema_json": {}}])
            g = G(3, [{"action": "Save", "chord": "ctrl+s", "windows": "ctrl+s", "videos": 3, "mac_style": False}, {"action": "Open", "chord": "ctrl+shift+o", "windows": "ctrl+shift+o", "videos": 2, "mac_style": False},
                      {"action": "Word wrap", "chord": "alt+z", "windows": "alt+z", "videos": 2, "mac_style": False}])
            g.app_key = key
            ex = C.export_facts_rag(g, rag, "Notepad", only_new=True)
            checks["only_new_facts_are_written"] = ex["written"] == 1 and ex["rows"] == [("Word wrap", "alt+z")] and rag.fast.count(key) == 3
            checks["a_known_shortcut_is_corroborated_and_a_different_one_is_a_conflict_not_a_row"] = len(ex["corroborated"]) == 1 and len(ex["conflicts"]) == 1 and ex["conflicts"][0]["stored"] == ["ctrl+o"]
            again = C.export_facts_rag(g, rag, "Notepad", only_new=True)
            checks["running_it_again_writes_nothing_more"] = again["written"] == 0 and rag.fast.count(key) == 3
            VC.OUT_ROOT = os.path.join(tmp, "out2")
            os.makedirs(VC.OUT_ROOT, exist_ok=True)
            open(os.path.join(VC.OUT_ROOT, "rag_writes.jsonl"), "w").write(json.dumps({"run": "R1", "app": "Notepad", "key": key, "rows": [list(r) for r in ex["rows"]] + [["Save", "ctrl+s"]]}) + "\n")
            rb = VC.rollback("R1", rag)
            checks["rollback_forgets_the_rows_the_run_wrote"] = rb["rows_forgotten"] == 2 and rag.fast.find(key, "Word wrap", "alt+z") is None
            checks["_rollback_note"] = "rows listed in the log are forgotten if present and unverified (catalog row 'Save' was in the list here, so it goes too: the log must only list rows the run wrote)"
    finally:
        VC.CURRICULUM_PATH, VC.STATE_PATH, VC.STOP_PATH, VC.OUT_ROOT, VC.free_gb = saved
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: v for k, v in checks.items() if not k.startswith("_")}, extra=str({k: v for k, v in checks.items() if k.startswith("_")}))


def run_ar57() -> "TestOutcome":
    """AR57: the pool cleans and understands what it reads: run-together OCR names are split with a vocabulary learned from the pool, junk is dropped, one shortcut named three ways becomes one, spoken chords and gestures are parsed with their meaning, and the app profile is a calibrated MIXTURE whose supervised model is adopted only when leave-one-out proves it"""
    from collections import Counter
    from core_organs.harvest import fact_cleaner as FC, spoken_facts as SF, app_profile as AP, consolidate as C
    checks: Dict[str, Any] = {}
    vocab = Counter({w: 5 for w in "copy to clipboard as png paste cut select all zen mode bring forward flip horizontal group selection snap objects wrap in frame toggle grid".split()})
    checks["a_run_together_name_is_split_into_known_words"] = FC.clean_action("CopytoclipboardasPNG", vocab) == "Copy to clipboard as PNG" and FC.clean_action("Wrapselectioninframe", vocab) == "Wrap selection in frame"
    checks["an_unknown_token_is_left_alone_not_invented"] = FC.segment("xqzvkplm", vocab) is None and FC.clean_action("Zen mode", vocab) == "Zen mode"
    fs = [{"action": "CopytoclipboardasPNG", "windows": "shift+alt+c", "chord": "shift+option+c", "videos": 3}, {"action": "Copy to clipboard as PNG", "windows": "shift+alt+c", "chord": "shift+option+c", "videos": 2},
          {"action": "xqzvkplm qq", "windows": "ctrl+q", "chord": "ctrl+q", "videos": 4}, {"action": "Zen mode", "windows": "alt+z", "chord": "option+z", "videos": 4}]
    cleaned, rep = FC.clean_facts(fs, vocab)
    names = {f["windows"]: f["action"] for f in cleaned}
    checks["facts_are_cleaned_junk_dropped_and_duplicates_collapsed_to_the_better_supported_name"] = (names == {"alt+z": "Zen mode", "shift+alt+c": "Copy to clipboard as PNG"} and len(rep["dropped"]) == 1 and len(rep["merged"]) == 1)
    voc_real = FC.vocabulary()
    checks["the_real_vocabulary_is_learned_from_the_pool"] = len(voc_real) > 1000 and FC.clean_action("Bringforward", voc_real) == "Bring forward"
    # --- spoken facts
    c1 = SF.chords("just press command plus enter to open the line editor and make your changes.")
    c2 = SF.chords("press control plus shift plus P to open the command palette")
    g1 = SF.gestures("But if you want to create a perfectly even shape, just hold shift while dragging.")
    checks["a_spoken_chord_and_what_it_does_are_parsed"] = c1 and c1[0]["chord"] == "cmd+enter" and c1[0]["action"] == "open the line editor" and c2 and c2[0]["chord"] == "ctrl+shift+p"
    checks["a_spoken_modifier_gesture_keeps_its_effect"] = g1 and g1[0]["modifier"] == "shift" and g1[0]["gesture"] == "dragging" and g1[0]["effect"] == "create a perfectly even shape"
    checks["a_chord_without_a_stated_meaning_is_not_a_fact"] = SF.chords("press control plus s") == [] and SF.chords("the control plus the shift of a lens") == []
    # --- speech votes in a graph: one per video, screen facts win, speech facts are marked as such
    tmp = tempfile.mkdtemp(prefix="sf_")
    try:
        g = C.AppGraph("t", os.path.join(tmp, "t"))
        g.videos = ["a", "b"]
        seg = lambda txt: [{"text": txt, "start": 1.0, "duration": 4.0}]
        C.record_speech(g, "a", seg("just press command plus enter to open the line editor and make your changes."))
        C.record_speech(g, "b", seg("you can open the line editor with command plus enter or use the handle."))
        C.record_speech(g, "b", seg("to create a perfectly even shape just hold shift while dragging it."))
        f = [x for x in g.facts() if x["windows"] == "ctrl+enter"]
        checks["speech_votes_count_once_per_video_and_are_marked_speech"] = bool(f) and f[0]["videos"] == 2 and f[0]["source"] == "speech" and g.gestures()[0]["videos"] == 1
        g.extra["ocr_votes"] = {"ctrl+enter": {"videos": ["a", "b"], "actions": {"Edit line": 3}, "raw": {"cmd+enter": 3}}}
        checks["a_chord_seen_on_screen_wins_over_the_spoken_one"] = [x for x in g.facts() if x["windows"] == "ctrl+enter"][0]["source"] == "screen"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # --- app profile: a mixture, calibrated, with a leave-one-out gate on the supervised part
    ev = AP.evaluate()
    checks["profile_beats_chance_on_the_real_scans_with_the_name_withheld"] = ev["n_apps"] >= 15 and ev["log_loss"] < ev["uniform_log_loss"] - 0.5 and ev["top1"] >= 0.45
    sig = {"app": "", "title": "", "controls": ["Layers panel", "Brush tool", "Opacity slider", "Selection tool", "Filters menu", "Canvas size", "Colors swatches", "Fill bucket", "Eraser"]}
    pr = AP.profile(sig, "x")
    checks["the_profile_is_a_distribution_with_a_primary_and_possible_secondaries"] = abs(sum(s for _, s in pr["top5"]) - 1.0) < 0.7 and pr["primary"] in ("raster_editor", "vector_editor") and isinstance(pr["secondary"], list) and "hybrid" in pr
    saved = (AP.TRAIN_PATH, AP.MODEL_PATH)
    tmp2 = tempfile.mkdtemp(prefix="ap_")
    try:
        AP.TRAIN_PATH, AP.MODEL_PATH = os.path.join(tmp2, "train.jsonl"), os.path.join(tmp2, "model.json")
        rep2 = AP.fit_and_gate()
        checks["with_too_few_labelled_apps_the_supervised_model_is_not_adopted"] = rep2["adopted"] is False and "not adopted" in rep2["why"]
        checks["a_labelled_example_is_added_once_and_only_with_a_real_label"] = AP.add_example("raster_editor", sig, "k1") and not AP.add_example("raster_editor", sig, "k1") and not AP.add_example("not_a_class", sig, "k2") and AP.examples()[-1][0] == "raster_editor"
    finally:
        AP.TRAIN_PATH, AP.MODEL_PATH = saved
        shutil.rmtree(tmp2, ignore_errors=True)
    checks["_profile_eval"] = str({k: ev[k] for k in ("n_apps", "top1", "top2", "log_loss", "temperature")})
    return _verdict({k: bool(v) for k, v in checks.items() if not k.startswith("_")}, extra=str({k: v for k, v in checks.items() if k.startswith("_")}))


def run_ar58() -> "TestOutcome":
    """AR58: drag / stroke tracing recovers a path that is known exactly (object dragged along a curve; ink drawn along it), ignores a still scene with sensor noise and a jittering pointer, and the paths are searchable as vectors; the same holds when the frames come out of a real mp4"""
    import cv2
    import numpy as np
    from core_organs.harvest import drag_trace as DT
    checks: Dict[str, Any] = {}
    W, H = 384, 216

    def bez(p0, p1, p2, u):
        return ((1 - u) ** 2) * np.array(p0) + 2 * (1 - u) * u * np.array(p1) + (u ** 2) * np.array(p2)

    def base():
        im = np.full((H, W), 245, np.uint8)
        cv2.rectangle(im, (0, 0), (W, 22), (200,), -1)
        cv2.rectangle(im, (0, 22), (60, H), (225,), -1)
        for k in range(5):
            cv2.putText(im, f"Tool{k}", (4, 44 + 22 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (60,), 1)
        return im
    P0, P1, P2 = (110, 170), (170, 50), (320, 80)
    truth = np.array([bez(P0, P1, P2, u) for u in np.linspace(0, 1, 400)]) / np.array([W, H])

    def err(path):
        pts = np.array([(p[1], p[2]) for p in path])
        d = [float(np.min(np.hypot(*(truth - q).T))) for q in pts]
        return sum(d) / len(d)

    def obj_frames():
        out = []
        for i in range(18):
            cx, cy = bez(P0, P1, P2, i / 17)
            im = base()
            cv2.rectangle(im, (int(cx - 22), int(cy - 14)), (int(cx + 22), int(cy + 14)), (90,), -1)
            cv2.rectangle(im, (int(cx - 22), int(cy - 14)), (int(cx + 22), int(cy + 14)), (20,), 2)
            out.append(im)
        return out
    times = [i / 12.0 for i in range(18)]
    r = DT.trace_frames(obj_frames(), times)
    checks["a_dragged_object_is_traced_along_its_real_path"] = bool(r) and r["method"] == "flow" and err(r["points"]) < 0.015 and r["kind"] in ("straight", "curved")
    checks["its_ends_are_within_3_to_5_percent_of_the_true_ends"] = bool(r) and math.hypot(r["start"][0] - truth[0][0], r["start"][1] - truth[0][1]) < 0.05 and math.hypot(r["end"][0] - truth[-1][0], r["end"][1] - truth[-1][1]) < 0.05
    checks["the_path_is_a_handful_of_points_with_metrics"] = bool(r) and 3 <= len(r["points"]) <= 14 and 0.5 < r["length"] < 1.1 and r["duration"] > 1.0 and r["peak_speed"] > 0
    canvas = base()
    fr = []
    for i in range(18):
        a, b = bez(P0, P1, P2, max(0, i - 1) / 17), bez(P0, P1, P2, i / 17)
        cv2.line(canvas, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), (30,), 4)
        fr.append(canvas.copy())
    r2 = DT.trace_frames(fr, times)
    checks["a_stroke_drawn_in_ink_is_traced_by_its_tip"] = bool(r2) and err(r2["points"]) < 0.01 and math.hypot(r2["end"][0] - truth[-1][0], r2["end"][1] - truth[-1][1]) < 0.05
    rng = np.random.default_rng(0)
    still = [np.clip(base().astype(int) + rng.integers(-3, 4, (H, W)), 0, 255).astype(np.uint8) for _ in range(14)]
    checks["a_still_scene_with_sensor_noise_is_not_a_drag"] = DT.trace_frames(still, [i / 12 for i in range(14)]) is None
    jit = []
    for i in range(14):
        im = base()
        x = 200 + (i % 3)
        cv2.fillConvexPoly(im, np.array([[x, 100], [x, 114], [x + 8, 108]]), (0,))
        jit.append(im)
    checks["a_pointer_jittering_in_place_is_not_a_drag"] = DT.trace_frames(jit, [i / 12 for i in range(14)]) is None
    # --- from a real mp4 through trace_window (decoding, letterbox crop, canvas)
    tmp = tempfile.mkdtemp(prefix="dt_")
    try:
        path = os.path.join(tmp, "drag.mp4")
        vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 12, (768, 432))
        for f in [base()] * 6 + obj_frames() + [obj_frames()[-1]] * 6:
            vw.write(cv2.resize(cv2.cvtColor(f, cv2.COLOR_GRAY2BGR), (768, 432)))
        vw.release()
        tw = DT.trace_window(path, 0.3, 2.6, crop_px=(0, 0, 768, 432))
        checks["the_same_path_is_recovered_from_a_real_video_file"] = bool(tw) and err(tw["points"]) < 0.03 and math.hypot(tw["end"][0] - truth[-1][0], tw["end"][1] - truth[-1][1]) < 0.08
        # --- which events deserve the video to be re-read
        moved = {"comps": [{"box": [0.1, 0.1, 0.2, 0.2], "area": 0.01}, {"box": [0.5, 0.5, 0.6, 0.6], "area": 0.011}]}
        one_menu = {"comps": [{"box": [0.0, 0.0, 0.2, 0.4], "area": 0.08}, {"box": [0.0, 0.0, 0.05, 0.05], "area": 0.0025}]}
        checks["two_similar_blobs_apart_look_like_a_move_a_menu_does_not"] = DT.looks_like_move(moved) and not DT.looks_like_move(one_menu) and DT.looks_like_move({"kind": "drag", "comps": []})
        # --- the gesture index: same shape at another place and size is close, a different shape is not
        idx = DT.GestureIndex(os.path.join(tmp, "g.npz"))
        curve = [(i / 10, 0.2 + 0.5 * (i / 10), 0.8 - 0.5 * math.sin(i / 10 * math.pi / 2)) for i in range(11)]
        shifted = [(t, 0.4 * x + 0.3, 0.4 * y + 0.1) for t, x, y in curve]
        zig = [(i / 10, 0.2 + 0.06 * i, 0.5 + (0.15 if i % 2 else -0.15)) for i in range(11)]
        idx.add(curve, {"app": "a"})
        idx.add(zig, {"app": "b"})
        idx.save()
        idx2 = DT.GestureIndex(os.path.join(tmp, "g.npz"))
        q = idx2.query(shifted, 2)
        checks["a_gesture_shaped_like_a_stored_one_is_found_by_vector_search"] = len(idx2.vecs) == 2 and q[0][1]["app"] == "a" and q[0][0] > 0.95 and q[1][0] < q[0][0] - 0.1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in checks.items()})


def run_ar59() -> "TestOutcome":
    """AR59: transfer priors -- what other apps of the same kind already show makes a single-author shortcut acceptable, a lone odd one is not, and the expected-but-unseen list is the class's common chords"""
    from core_organs.harvest import transfer_priors as TP
    checks: Dict[str, Any] = {}
    A = {"ed1": "text_editor", "ed2": "text_editor", "ed3": "text_editor", "ed4": "text_editor", "pic1": "raster_editor", "new": "text_editor", "pic2": "raster_editor"}
    rows = []

    def row(app, action, chord, trust="web"):
        rows.append({"kind": "hotkey", "app_key": app, "task_pattern": action, "payload": chord, "trust": trust})
    for a in ("ed1", "ed2", "ed3"):
        row(a, "Find text", "ctrl+f")
        row(a, "Go to line", "ctrl+g")
    row("ed4", "Find in file", "ctrl+f")
    row("pic1", "Find layer", "ctrl+f")
    row("pic1", "Select all", "ctrl+a")
    row("ed1", "Invented by a model", "ctrl+9", trust="llm")
    P = TP.Priors(rows, lambda k: A.get(k, ""))
    checks["a_chord_common_in_the_class_is_accepted_for_a_new_app_of_it"] = P.accept("text_editor", "Find", "ctrl+f", "new") and P.strength("text_editor", "Find", "ctrl+f", "new")[0] == 4
    checks["the_same_chord_for_an_unrelated_action_is_not"] = not P.accept("text_editor", "Print preview", "ctrl+f", "new")
    checks["a_chord_only_one_app_has_is_not_a_prior"] = not P.accept("text_editor", "Select all", "ctrl+a", "new")
    checks["the_app_itself_never_counts_as_its_own_evidence"] = P.strength("text_editor", "Go to line", "ctrl+g", "ed1")[0] == 2
    checks["a_chord_seen_in_many_apps_of_any_kind_is_accepted_for_a_class_with_no_history"] = P.accept("diagram_whiteboard", "Find text", "ctrl+f", "x") and not P.accept("diagram_whiteboard", "Select all", "ctrl+a", "x")
    checks["rows_a_model_invented_are_not_evidence"] = "ctrl+9" not in P.any
    ex = P.expectations("text_editor", "new", [("Find", "ctrl+f")])
    checks["expected_but_unseen_lists_the_class_chords_missing_from_this_app"] = [e["chord"] for e in ex] == ["ctrl+g"] and ex[0]["apps"] == 3 and "line" in ex[0]["action_words"]
    # --- the graph really offers single-author facts when asked
    from core_organs.harvest import consolidate as C
    g = C.AppGraph("t", root=tempfile.mkdtemp(prefix="ar59_"))
    g.extra["ocr_votes"] = {"ctrl+f": {"videos": ["v1"], "raw": {"ctrl+f": 1}, "actions": {"Find": 1}},
                            "ctrl+q": {"videos": ["v1", "v2"], "raw": {"ctrl+q": 2}, "actions": {"Quit": 2}}}
    checks["by_default_a_single_author_fact_stays_out"] = [f["windows"] for f in g.facts()] == ["ctrl+q"]
    both = {f["windows"]: f for f in g.facts(min_videos=1)}
    checks["it_comes_in_only_when_the_caller_asks_for_one_author"] = set(both) == {"ctrl+f", "ctrl+q"} and both["ctrl+f"]["videos"] == 1
    # --- what presenters really say: no 'plus' between the modifier and the key
    from core_organs.harvest import spoken_facts as SF
    got = lambda s: [(c["chord"], c["action"]) for c in SF.chords(s)]
    checks["spoken_ctrl_c_without_plus_is_read"] = got("You can press Ctrl Z to undo any changes") == [("ctrl+z", "undo any changes")]
    checks["a_shortcut_word_and_a_works_in_tail_are_trimmed_from_the_action"] = got("Next, the control A shortcut to select all works in paint.") == [("ctrl+a", "select all")]
    checks["a_trailing_pronoun_is_not_part_of_the_action"] = got("Press Ctrl Z to undo that") == [("ctrl+z", "undo")] and got("Ctrl Z to undo it") == [("ctrl+z", "undo")]
    checks["a_single_verb_after_to_is_a_clear_action"] = got("Ctrl C to copy") == [("ctrl+c", "copy")]
    checks["the_verb_control_in_running_text_is_not_a_chord"] = got("you control a lot of things here") == [] and got("we control the layout of the page") == [] and got("I am in control. A lot of this") == []
    checks["an_action_made_only_of_filler_is_dropped"] = got("or you can press Ctrl X from the image") == []
    from core_organs.harvest import fact_cleaner as FC
    vb = {"undo": 5, "select": 9, "copy": 4, "save": 8, "open": 7}
    vc = FC.vocabulary(extra=["undo any changes select all copy save the file now open a new tab gartam coefficient find option"])
    ok = lambda a: FC.speech_ok(a, vc, vb)
    checks["a_spoken_name_that_starts_like_a_command_is_kept"] = ok("undo any changes") and ok("select all") and ok("copy") and ok("save the file now") and ok("open a new tab")
    checks["recognition_noise_is_not_a_command_name"] = not ok("Gartam again so you") and not ok("Cutting into undo coefficient here find option here") and not ok("Or you can") and not ok("zzqx wibble")
    checks["the_old_plus_form_still_works"] = got("press control plus z to undo any changes") == [("ctrl+z", "undo any changes")]
    return _verdict({k: bool(v) for k, v in checks.items()})


def run_ar60() -> "TestOutcome":
    """AR60: the web curriculum learns -- kind recognition from labelled sites (held-out accuracy), the pool receives commands / hotkeys / a document once, a refused site writes nothing, the ladder is walked rung first,
    state resumes, STOP stops, and a run can be rolled back"""
    import random
    from collections import Counter
    from si_tests_rag import _Env
    from core_organs.harvest import web_kind as WK, web_learn as WL, web_curriculum as WC
    checks: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar60_")
    saved = (WK.FOLDER, WK.EXAMPLES, WL.PATTERNS, WL.LOCK, WC.STATE, WC.STOP, WC.OUT, WC.PROGRESS, WC.LEDGER, WC.GROWTH, WC.LIMITS)
    try:
        # ---- 1 web_kind: separable categories are recognised on held-out sites
        vocab = {"jobs": "job salary resume employer vacancy hiring recruiter career apply".split(), "video": "watch stream channel subscribe playlist episode trending clip upload creator".split(),
                 "docs": "reference tutorial syntax function example parameter library module documentation guide".split(), "shop": "cart price delivery discount brand order seller checkout wishlist offers".split()}
        common = "sign contact help about privacy terms search home".split()
        rnd = random.Random(7)
        exs = []
        for cat, ws in vocab.items():
            for i in range(4):
                c = Counter()
                for w in rnd.choices(ws, k=60) + rnd.choices(common, k=14) + [f"{cat}{i}x{j}" for j in range(30)]:
                    c[w] += 1
                exs.append({"host": f"{cat}{i}.test", "category": cat, "words": dict(c)})
        wk = WK.WebKind(exs)
        loo = wk.leave_one_out()
        checks["held_out_sites_get_their_category_back"] = loo["top1"] is not None and loo["top1"] >= 0.9 and loo["scored"] == 16
        newjob = Counter(rnd.choices(vocab["jobs"], k=40) + rnd.choices(common, k=8) + ["zzunique1", "zzunique2"] * 3)
        r = wk.classify(newjob)
        checks["an_unseen_jobs_site_is_called_jobs_with_a_margin"] = r["ranked"][0][0] == "jobs" and r["status"] == "confident"
        checks["a_few_examples_are_not_enough_for_a_verdict"] = WK.WebKind(exs[:3]).classify(newjob)["status"] == "too_few_examples"
        checks["the_words_that_set_a_category_apart_come_out"] = "salary" in wk.distinctive("jobs", 12) or "resume" in wk.distinctive("jobs", 12)
        ex_path = os.path.join(tmp, "examples.jsonl")
        checks["an_empty_shell_page_is_not_a_profile"] = not WK.add_example("blocked.test", "jobs", Counter(["a1b"] * 3), ex_path) and WK.add_example("x.test", "jobs", Counter({f"word{i}": 2 for i in range(40)}), ex_path)
        WK.add_example("x.test", "docs", Counter({f"term{i}": 2 for i in range(40)}), ex_path)
        loaded = WK.load_examples(ex_path)
        checks["a_site_is_stored_once_the_last_label_wins"] = len(loaded) == 1 and loaded[0]["category"] == "docs"
        # ---- 2 hotkeys from a page's own shortcut sheet
        from core_organs.harvest import bridge as BR
        rows = WL.hotkey_rows("webapp:t.test", [{"keys": "k", "action": "Toggle play/pause"}, {"keys": "Shift + ?", "action": "Show shortcuts"}, {"keys": "g then n", "action": "Go to notifications"},
                                                {"keys": "j or l", "action": "skip"}, {"keys": "f", "action": "Fullscreen"}, {"keys": "x", "action": "no"}], BR)
        checks["single_step_shortcuts_become_rows_sequences_do_not"] = sorted(r["payload"] for r in rows) == ["f", "k", "shift+?"] and all(r["trust"] == "web" and r["verified"] is False for r in rows)
        # ---- 3 sections and patterns
        rep = {"labels": ["Jobs", "Companies", "Salary guide", "Resume builder", "Sign in"] * 6 + [f"topic{chr(97 + i // 26)}{chr(97 + i % 26)}" for i in range(40)],
               "understanding": {"meaning": {"description": "Find jobs and hire talent", "name": "Fake", "headings": ["Latest jobs"] + [f"topic{chr(97 + i // 26)}{chr(97 + i % 26)} openings" for i in range(40)], "navigation": ["Jobs", "Companies", "Salaries", "Skip to main content", "Sign in"]},
                                 "stack": {"frameworks": ["React"], "headers": {"platform_hints": ["Akamai"]}, "manifest": True}, "network": {"requests": 100, "by_kind": {"analytics": 10, "ads": 5}, "api_endpoints": [1], "graphql_operations": {}},
                                 "auth": {"sso_providers": ["Google"], "login_wall": False}, "shortcut_sheet": {"opened": True, "pairs": [{"keys": "k", "action": "Toggle play/pause"}, {"keys": "f", "action": "Fullscreen"}]}},
               "scan": {"explore": {"nodes": [{"path": "Jobs > Remote", "outcome": "revealed a menu / panel"}, {"path": "Jobs > Remote > Python", "outcome": "opened a new page"}, {"path": "Companies", "outcome": "opened a new page"},
                                              {"path": "Dead end", "outcome": "nothing visible happened"}], "pages": {"/jobs": "Jobs"}}}}
        checks["sections_keep_real_ones_and_drop_chrome"] = WL.sections_of(rep) == ["jobs", "companies", "salaries"]
        WL.PATTERNS = os.path.join(tmp, "patterns.json")
        WK.FOLDER = tmp
        WK.EXAMPLES = os.path.join(tmp, "ex2.jsonl")
        WL.LOCK = os.path.join(tmp, "write.lock")
        led = os.path.join(tmp, "ledger.jsonl")
        with _Env() as rag:
            lr = WL.learn_site(rag, rep, "https://www.fake-jobs.test/", "jobs", "RUN1", ledger=led, doc_text="# Fake jobs\n\nA job board. Search jobs by role, filter by remote, read the salary guide.\n\n## Menus\n\nJobs > Remote > Python opens a page.\n")
            key = "webapp:fake-jobs.test"
            checks["a_scanned_site_is_filed_commands_hotkeys_document_profile"] = lr["status"] == "ok" and lr["commands"] >= 4 and lr["hotkeys"] == 2 and lr["example_added"] and lr["doc_chunks"] >= 1
            checks["its_hotkeys_are_leads_not_verified"] = rag.fast.find(key, "Toggle play/pause", "k") is not None and not rag.fast.find(key, "Toggle play/pause", "k")["verified"]
            lr2 = WL.learn_site(rag, rep, "https://www.fake-jobs.test/", "jobs", "RUN2", ledger=led)
            checks["learning_the_same_site_again_adds_no_duplicate_hotkeys"] = lr2["hotkeys"] == 0 and rag.fast.count(key) == 2
            blocked = {"understanding": {"auth": {"blocked": 403}}, "scan": {"http_status": 403}}
            lr3 = WL.learn_site(rag, blocked, "https://refused.test", "jobs", "RUN3", ledger=led)
            checks["a_site_that_refused_the_browser_writes_nothing"] = lr3["status"] == "refused_by_site" and lr3["commands"] == 0 and rag.fast.count("webapp:refused.test") == 0
            pat = json.load(open(WL.PATTERNS, encoding="utf-8"))
            checks["cross_site_patterns_are_counted"] = pat["summary"]["sites"] == 2 and pat["sites"]["fake-jobs.test"]["shortcut_sheet"] is True and pat["summary"]["share_pwa"] == 0.5
            # ---- 4 rollback of one run
            count = lambda k: rag.lex.db.one("SELECT COUNT(*) AS n FROM commands WHERE app_key=?", (k,))["n"]
            n_before = count(key)
            rb = WC.rollback("RUN1", rag, ledger=led)
            checks["rolling_back_a_run_forgets_its_hotkey_rows_and_names_but_keeps_what_another_run_also_wrote"] = rb["hotkey_rows_forgotten"] == 2 and rag.fast.count(key) == 0 and rb["commands_forgotten"] == 2 and count(key) == n_before - 2
            WL.learn_site(rag, rep, "https://solo.test/", "jobs", "RUN9", ledger=led)
            n_solo = count("webapp:solo.test")
            rb9 = WC.rollback("RUN9", rag, ledger=led)
            checks["a_run_that_wrote_alone_is_rolled_back_completely"] = n_solo >= 4 and count("webapp:solo.test") == 0 and rb9["commands_forgotten"] == n_solo and rag.fast.count("webapp:solo.test") == 0
        # ---- 5 the ladder, resume, STOP, refused, failure streak (fake runner, no browser)
        order = WC.ordered(WC.rows())
        tiers = [r["tier"] for r in order]
        checks["the_ladder_is_walked_rung_first"] = tiers == sorted(tiers) and len({r["category"] for r in order[:12]}) >= 10
        checks["every_site_has_a_category_and_urls_are_unique"] = all(r["category"] for r in order) and len({r["url"] for r in order}) == len(order)
        WC.STATE, WC.STOP, WC.OUT = os.path.join(tmp, "state.json"), os.path.join(tmp, "STOP"), os.path.join(tmp, "out")
        WC.PROGRESS, WC.LEDGER, WC.GROWTH = os.path.join(WC.OUT, "p.jsonl"), os.path.join(WC.OUT, "l.jsonl"), os.path.join(WC.OUT, "g.jsonl")
        calls: List[str] = []

        def fake(site, log):
            calls.append(site["url"])
            if site["url"] == "stackoverflow.test":
                rp = {"understanding": {"auth": {"blocked": 403}}, "scan": {"http_status": 403}}
            else:
                rp = dict(rep)
            return {"status": "ok", "report": rp, "seconds": 1, "log": ""}
        orig_rows = WC.rows
        WC.rows = lambda only=None, tier=None: [{"name": n, "url": u, "category": "jobs", "tier": 1, "rank": i} for i, (n, u) in enumerate([("A", "a.test"), ("B", "stackoverflow.test"), ("C", "c.test")])]
        try:
            WC.run(1.0, runner=fake, write=False, gap_s=0.0, log=lambda s: None)
            st = WC.load_state()
            checks["a_refused_site_is_recorded_as_refused_and_the_rest_continue"] = calls == ["a.test", "stackoverflow.test", "c.test"] and st["sites"]["stackoverflow.test"]["status"] == "refused" and st["sites"]["a.test"]["status"] == "ok"
            checks["the_run_scores_its_own_prediction_before_learning"] = "score" in st["sites"]["a.test"] and "kind_status" in st["sites"]["a.test"]["score"]
            calls.clear()
            WC.run(1.0, runner=fake, write=False, gap_s=0.0, log=lambda s: None)
            checks["a_second_run_skips_finished_and_refused_sites"] = calls == []
            WC.run(1.0, runner=fake, write=False, gap_s=0.0, log=lambda s: None, retry_refused=True)
            checks["retry_refused_tries_only_the_refused"] = calls == ["stackoverflow.test"]
            os.remove(WC.STATE)
            open(WC.STOP, "w").close()
            calls.clear()
            WC.run(1.0, runner=fake, write=False, gap_s=0.0, log=lambda s: None)
            checks["the_STOP_file_ends_the_run"] = calls == []
            os.remove(WC.STOP)
            if os.path.isfile(WC.STATE):
                os.remove(WC.STATE)
            WC.rows = lambda only=None, tier=None: [{"name": f"S{i}", "url": f"s{i}.test", "category": "jobs", "tier": 1, "rank": i} for i in range(7)]
            calls.clear()
            WC.run(1.0, runner=lambda s, l: (calls.append(s["url"]) or {"status": "exit 1", "report": {}, "seconds": 1}), write=False, gap_s=0.0, log=lambda s: None)
            checks["four_empty_sites_in_a_row_end_the_run"] = len(calls) == 4
        finally:
            WC.rows = orig_rows
    finally:
        (WK.FOLDER, WK.EXAMPLES, WL.PATTERNS, WL.LOCK, WC.STATE, WC.STOP, WC.OUT, WC.PROGRESS, WC.LEDGER, WC.GROWTH, WC.LIMITS) = saved
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in checks.items()})


def run_ar61() -> "TestOutcome":
    """AR61: on a local test site the deep explorer clicks EVERY button (dropdown items, sub-menu items, dialog buttons) down to level 3, never touches the 'Delete everything' button, reads the video that plays on
    the page (frames sampled, the text on its slides read, motion told from a still), finds the Tab order and the '/' key by pressing them, and files the video and the live-pressed key in a pool"""
    import contextlib
    import http.server
    import threading
    import cv2
    import numpy as np
    from core_organs.harvest import web_media as WM, web_learn as WL, web_kind as WK
    from core_organs import try_app_show as TS
    checks: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar61_")
    server = None
    try:
        # ---- the site: two dropdowns (one with a sub-menu), a dialog with its own buttons, a risky button, a search box with a '/' shortcut, a looping slide video, and plain links
        clip = os.path.join(tmp, "clip.webm")
        vw = cv2.VideoWriter(clip, cv2.VideoWriter_fourcc(*"VP80"), 10, (480, 270))
        slides = [("HELLO MEDIA TEST", (160, 60, 20)), ("SECOND SLIDE KEYBOARD", (30, 120, 40)), ("THIRD SLIDE EXPORT", (120, 40, 140)), ("FOURTH SLIDE DONE", (40, 40, 160))]
        for i in range(120):
            txt, col = slides[(i // 25) % 4]
            fr = np.full((270, 480, 3), col, np.uint8)
            cv2.putText(fr, txt, (20, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.1 if len(txt) < 20 else 0.85, (255, 255, 255), 3)
            vw.write(fr)
        vw.release()
        video_ok = os.path.isfile(clip) and os.path.getsize(clip) > 2000
        html = """<!doctype html><html><head><title>Test Studio</title><meta name="description" content="A tiny studio used to test the explorer."></head><body>
<header><nav>
 <button id="file" aria-haspopup="true" aria-expanded="false" onclick="tog('filemenu',this)">File</button>
 <button id="tools" aria-haspopup="true" aria-expanded="false" onclick="tog('toolsmenu',this)">Tools</button>
 <button id="help" onclick="document.getElementById('dlg').hidden=false">Help</button>
 <button id="about" onclick="document.getElementById('out').textContent='About: Test Studio 1.0'">About</button>
 <input id="q" type="search" placeholder="Search the studio">
</nav></header>
<div id="filemenu" hidden><button onclick="out('new project made')">New project</button><button onclick="tog('recent',this)" aria-haspopup="true" aria-expanded="false">Open recent</button><button onclick="fetch('/danger')">Delete everything</button></div>
<div id="recent" hidden><button onclick="out('alpha opened')">Project Alpha</button><button onclick="out('beta opened')">Project Beta</button></div>
<div id="toolsmenu" hidden><button onclick="out('brush selected')">Brush</button><button onclick="out('eraser selected')">Eraser</button><button onclick="out('zoom selected')">Zoom lens</button></div>
<div id="dlg" role="dialog" aria-label="Help dialog" hidden style="position:fixed;top:120px;left:300px;width:300px;height:140px;background:#fff;border:1px solid #444;z-index:50"><p>Welcome to Test Studio</p>
 <button onclick="out('tips shown')">Show tips</button><button onclick="document.getElementById('dlg').hidden=true">Close dialog</button></div>
<main><p id="out">ready</p><video id="v" src="clip.webm" autoplay muted loop playsinline width="480" height="270"></video></main>
<footer>""" + "".join(f'<a href="page{i}.html">Docs page {i}</a> ' for i in range(1, 6)) + """</footer>
<script>function tog(id,b){const e=document.getElementById(id);e.hidden=!e.hidden;b.setAttribute('aria-expanded',String(!e.hidden));}
function out(t){document.getElementById('out').textContent=t;}
document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement.tagName!=='INPUT'){e.preventDefault();document.getElementById('q').focus();}});</script></body></html>"""
        open(os.path.join(tmp, "index.html"), "w", encoding="utf-8").write(html)
        for i in range(1, 6):
            open(os.path.join(tmp, f"page{i}.html"), "w", encoding="utf-8").write(f"<html><head><title>Docs page {i}</title></head><body><h1>Docs page {i}</h1><button onclick=\"document.title='x'\">Expand section {i}</button></body></html>")
        hits = {"danger": 0}

        class H(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=tmp, **k)

            def do_GET(self):
                if self.path.startswith("/danger"):
                    hits["danger"] += 1
                super().do_GET()

            def log_message(self, *a):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
        rep = TS.scan_web_show(url, os.path.join(tmp, "out"), pace=0.05, hold_s=0.0, headless=True, deep=True, max_clicks=60, max_depth=4, max_pages=6, budget_s=180, media=True,
                               transcribe_media=False, max_link_clicks=12, say=lambda s: None)
        ex = rep.get("explore") or {}
        cov = ex.get("coverage") or {}
        paths = [n["path"] for n in ex.get("nodes", [])]
        checks["every_button_was_clicked_not_only_seen"] = cov.get("buttons_seen", 0) >= 9 and cov.get("buttons_pct", 0) >= 90
        checks["a_sub_menu_item_three_levels_down_was_clicked"] = any(p.count(" > ") >= 2 and "Project" in p for p in paths) and ex.get("max_depth", 0) >= 3
        checks["the_dialog_was_opened_and_its_own_buttons_were_clicked"] = any("Help" in p and "Show tips" in p for p in paths)
        checks["the_risky_button_was_never_touched"] = hits["danger"] == 0 and any("Delete" in s for s in ex.get("skipped_risky", []))
        checks["plain_links_have_their_own_smaller_budget"] = ex.get("link_clicks", 99) <= 12 and ex.get("button_clicks", 0) >= 9
        if video_ok:
            md = (rep.get("media") or [{}])[0]
            checks["the_video_on_the_page_was_found_and_sampled"] = bool(md) and len(md.get("frames", [])) >= 3
            checks["its_picture_changes_between_samples_so_it_is_called_moving"] = md.get("motion") == "moving picture"
            ocr_txt = " ".join(md.get("on_screen_text", [])).upper()
            with contextlib.suppress(Exception):
                import pytesseract
                pytesseract.get_tesseract_version()
                checks["text_shown_in_the_video_was_read"] = any(w in ocr_txt for w in ("HELLO", "SLIDE", "KEYBOARD", "EXPORT", "THIRD", "FOURTH"))
        else:
            checks["video_encoder_unavailable_media_checks_skipped"] = True
        kb = (rep.get("understanding") or {}).get("keyboard") or {}
        checks["the_tab_order_was_walked"] = len(kb.get("tab_order", [])) >= 5 and any("File" in (t["label"] or "") for t in kb["tab_order"])
        checks["the_slash_key_was_pressed_and_its_effect_seen"] = any(h["keys"] == "/" and "text field" in h["effect"] for h in kb.get("hotkeys", []))
        # ---- what is kept: the live-pressed key goes in as VERIFIED, the video as a document
        from si_tests_rag import _Env
        from core_organs.harvest import bridge as BR
        WL.PATTERNS, WK.EXAMPLES, WL.LOCK = os.path.join(tmp, "pat.json"), os.path.join(tmp, "ex.jsonl"), os.path.join(tmp, "w.lock")
        with _Env() as rag:
            full = {"target": url, "understanding": rep.get("understanding"), "scan": {"explore": ex, "digest": {}, "canvases": 0}, "digest": {"roles": {"button": 10}}}
            lr = WL.learn_site(rag, full, "http://test-studio.test/", "creative_niche", "RUN61", ledger=os.path.join(tmp, "led.jsonl"), doc_text="# Test Studio\n\nA tiny studio with File and Tools menus.\n")
            key = "webapp:test-studio.test"
            row = rag.fast.find(key, "focus the search box", "/")
            checks["a_key_that_was_pressed_with_a_seen_effect_is_filed_as_verified"] = row is not None and bool(row["verified"]) and lr["status"] == "ok"
            if video_ok:
                checks["the_video_is_filed_as_a_document_the_pool_can_find"] = lr.get("media_docs", 0) >= 1 and "media_error" not in lr
    finally:
        if server is not None:
            server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in checks.items()})


def run_ar62() -> "TestOutcome":
    """AR62: what each click DID is kept (procedures retrievable by a PARAPHRASED question, real many-choice training rows, idempotent), REA's findings are digested and filed without any credential-like
    value, write-type API calls are stored as knowledge only, the 20-task test picks sensible tasks and scores honestly, and REA itself runs when installed"""
    from si_tests_rag import _Env
    from core_organs.harvest import web_actions as WA, web_learn as WL, web_tasks_eval as TE, web_kind as WK, web_curriculum as WC
    from core_organs import rea_bridge as RB
    checks: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar62_")
    saved = (WL.LOCK, WL.PATTERNS, WK.EXAMPLES)
    try:
        WL.LOCK, WL.PATTERNS, WK.EXAMPLES = os.path.join(tmp, "w.lock"), os.path.join(tmp, "p.json"), os.path.join(tmp, "e.jsonl")
        menu = [f"link: Item {chr(97 + i)}{chr(97 + j)}" for i in range(3) for j in range(4)]
        rep = {"target": "https://www.todolike.test/", "labels": ["Home", "Product", "Pricing", "Templates", "Log in", "Help center", "Blog", "Careers", "Contact", "About us", "Integrations", "Download"],
               "scan": {"explore": {"nodes": [
                   {"path": "Product", "depth": 1, "outcome": "revealed a menu / panel", "n_new": 4, "revealed": ["link: Features", "link: Integrations", "link: Pricing plans", "link: Security"] + menu[:6],
                    "target": "button: Product", "context": ["button: Home", "button: Product", "link: Templates", "link: Log in", "button: Help center"], "on_page": "Todolike"},
                   {"path": "Product > Pricing plans", "depth": 2, "outcome": "opened a new page", "page": {"title": "Pricing | Todolike", "url": "https://www.todolike.test/pricing", "controls": 40}},
                   {"path": "Help center", "depth": 1, "outcome": "opened a dialog", "revealed": ["button: Contact support", "link: Guides"]},
                   {"path": "Blog", "depth": 1, "outcome": "nothing visible happened"},
                   {"path": "Careers", "depth": 1, "outcome": "unreachable"}]}}}
        procs = WA.procedures_from(rep, rep["target"])
        goals = [p["goal"] for p in procs]
        checks["only_clicks_that_did_something_become_procedures"] = len(procs) == 3 and not any("Blog" in g or "Careers" in g for g in goals)
        checks["goals_are_natural_and_say_where_they_are_reached_from"] = any(g.startswith("Go to the Pricing plans page on Todolike") and "via Product" in g for g in goals) and any(g == "Open the Product menu on Todolike" for g in goals)
        two = next(p for p in procs if "Pricing plans" in p["goal"])
        checks["a_procedure_keeps_each_steps_expected_outcome"] = len(two["steps"]) == 2 and "Features" in two["steps"][0]["expect"] and "'Pricing | Todolike' opens" in two["steps"][1]["expect"]
        rows = WA.training_rows_from(rep, rep["target"])
        r0 = next(r for r in rows if r["meta"]["path"] == "Product")
        user = r0["messages"][1]["content"][0]["text"]
        ans = json.loads(r0["messages"][2]["content"][0]["text"])
        checks["a_training_row_has_many_choices_and_the_right_target"] = r0["meta"]["elements"] >= 5 and ans[0]["target_id"] == r0["meta"]["target_id"] and f"#{ans[0]['target_id']} button 'Product'" in user
        r1 = next(r for r in rows if r["meta"]["path"] == "Product > Pricing plans")
        checks["an_old_report_without_context_is_rebuilt_from_the_parent_menu_and_marked"] = "reconstructed" in r1["meta"]["context"] and r1["meta"]["elements"] >= 5 and "Pricing plans" in r1["messages"][1]["content"][0]["text"]
        rows_path = os.path.join(tmp, "rows.jsonl")
        with _Env() as rag:
            a1 = WA.file_actions(rag, rep, rep["target"], "T1", rows_path=rows_path)
            a2 = WA.file_actions(rag, rep, rep["target"], "T2", rows_path=rows_path)
            checks["filing_twice_adds_nothing"] = a1["procedures"] == 3 and a1["train_rows"] >= 2 and a2["train_rows"] == 0 and rag.st.count("procedures") == 3
            ev = rag.proc.find_procedures("webapp:todolike.test", "how do I get to pricing plans on Todolike?", k=3)
            checks["a_paraphrased_question_finds_the_stored_path"] = bool(ev) and [s["target"] for s in ev[0].payload["steps"]][-1] == "Pricing plans"
            # ---- REA findings
            page_nr = {"scripts": {"total": 2, "items": [{"url": "https://www.todolike.test/app.js", "length": 5000, "source_map_url": "x.map"}, {"url": "https://cdn.other.test/lib.js", "length": 900, "source_map_url": None}]},
                       "resources": [{"type": "Script"}, {"type": "Script"}, {"type": "Stylesheet"}], "dom": {"total_nodes": 321}, "accessibility": {"total_nodes": 410}, "frames": [{}],
                       "metadata": {"dom_urls": [{"url": "https://www.todolike.test/pricing"}, {"url": "https://elsewhere.test/x"}, {"url": "https://www.todolike.test/blog"}]},
                       "storage": {"local_storage_keys": ["theme", "seen_tour"], "session_storage_keys": [], "indexed_db_names": []}, "network": {"websocket_connections": []}}
            dp = RB.digest_page(page_nr, "https://www.todolike.test")
            checks["rea_page_digest_counts_scripts_and_keeps_only_same_site_urls"] = dp["scripts"] == 2 and dp["source_maps"] == 1 and dp["same_site_paths"] == ["/blog", "/pricing"] and dp["local_storage_keys"] == ["theme", "seen_tour"]
            bd = RB.digest_bundle({"route_inventory": {"routes": [{"pattern": "/pricing"}, {"pattern": "/app/{id}"}, {"path": "/blog"}], "statistics": {"sources_retained": 3}, "coverage": {"application_routes": "unknown"}}, "unknowns": [1]})
            checks["rea_bundle_digest_lists_route_candidates_and_says_reachability_is_unknown"] = bd["routes"] == ["/app/{id}", "/blog", "/pricing"] and bd["coverage"] == "unknown"
            api = {"ok": True, "origin": "https://api.todolike.test", "records": 5, "evidence_id": "ev_abc", "tools": [
                {"name": "list_tasks", "method": "GET", "path": "/v1/tasks", "params": [], "query": ["project_id", "api_key"], "body_shape": None, "statuses": [200], "content_types": ["application/json"], "write": False},
                {"name": "create_task", "method": "POST", "path": "/v1/tasks", "params": [], "query": [], "body_shape": {"content": "string"}, "statuses": [200], "content_types": ["application/json"], "write": True}]}
            web = {"evidence": {"page": "ev_page1", "bundle": "ev_bundle1"}, "page": dp, "bundle": bd, "webmcp": {"status": "unavailable", "tools": []}}
            txt = RB.knowledge_text("todolike.test", web, api)
            checks["the_knowledge_text_cites_evidence_and_marks_writes_as_not_executed"] = "ev_page1" in txt and "ev_bundle1" in txt and "ev_abc" in txt and "WRITE: recorded, not executed" in txt and "Reachability is NOT established" in txt
            fr = RB.file_into_rag(rag, "webapp:todolike.test", "todolike.test", web, api, "R1")
            fr2 = RB.file_into_rag(rag, "webapp:todolike.test", "todolike.test", web, api, "R2")
            ev2 = rag.proc.find_procedures("webapp:todolike.test", "call GET /v1/tasks", k=3)
            checks["api_tools_and_routes_are_filed_once"] = fr["api_procedures"] == 2 and fr["route_commands"] == 3 and fr["document_chunks"] >= 1 and bool(ev2) and rag.st.count("procedures") <= 3 + 2 + fr["document_chunks"] + 2
            wr = next((e for e in rag.proc.find_procedures("webapp:todolike.test", "know the write call POST /v1/tasks", k=3) if "POST" in e.text), None)
            checks["a_write_call_is_knowledge_flagged_never_a_runnable_step"] = wr is not None and wr.payload["steps"][0]["write"] is True and wr.payload["steps"][0]["route_hint"] == "api"
            # ---- the curriculum feeds the pool site after site and measures itself on real tasks every few sites
            wsave = (WC.STATE, WC.STOP, WC.OUT, WC.PROGRESS, WC.LEDGER, WC.GROWTH, WA.ROWS_PATH, WC.rows)
            try:
                WC.STATE, WC.STOP, WC.OUT = os.path.join(tmp, "wc_state.json"), os.path.join(tmp, "wc_STOP"), os.path.join(tmp, "wc_out")
                WC.PROGRESS, WC.LEDGER, WC.GROWTH, WA.ROWS_PATH = os.path.join(WC.OUT, "p.jsonl"), os.path.join(WC.OUT, "l.jsonl"), os.path.join(WC.OUT, "g.jsonl"), os.path.join(tmp, "wc_rows.jsonl")
                WC.rows = lambda only=None, tier=None: [{"name": f"S{i}", "url": f"https://site{i}.test/", "category": "jobs", "tier": 1, "rank": i} for i in range(5)]
                evals: List[int] = []

                def site_run(site, log):
                    r = json.loads(json.dumps(rep))
                    r["target"] = site["url"]
                    return {"status": "ok", "report": r, "seconds": 1, "log": ""}
                WC.run(1.0, rag=rag, runner=site_run, write=True, gap_s=0.0, log=lambda s: None, eval_every=2, evaluator=lambda rg, n, st, lg: evals.append(n) or {})
                checks["every_scanned_site_fills_the_pool_without_any_training_step"] = rag.st.count("procedures") >= 5 * 3 and all(rag.fast.st.count("fast_paths") >= 0 for _ in [0]) and                     len([ln for ln in open(WA.ROWS_PATH, encoding="utf-8")]) >= 5 * 2
                checks["a_small_task_test_runs_after_every_second_site"] = len(evals) == 2
            finally:
                (WC.STATE, WC.STOP, WC.OUT, WC.PROGRESS, WC.LEDGER, WC.GROWTH, WA.ROWS_PATH, WC.rows) = wsave
        # ---- the 20-task test
        fake = {"a.test": {"target": "https://a.test/", "scan": {"explore": {"nodes": [
            {"path": "Pricing", "depth": 1, "outcome": "opened a new page", "page": {"title": "Pricing | A"}}, {"path": "English (United States) > euskara", "depth": 2, "outcome": "opened a new page", "page": {"title": "Euskara"}},
            {"path": "Docs", "depth": 1, "outcome": "opened a new page", "page": {"title": "Docs | A"}}, {"path": "Index (in module re)", "depth": 1, "outcome": "opened a new page", "page": {"title": "re"}},
            {"path": "Close", "depth": 1, "outcome": "opened a dialog"}]}}, "labels": ["Pricing", "Docs", "Close"]}}
        tk = TE.pick_tasks(10, 1, reports=fake)
        labs = [t["label"] for t in tk]
        checks["the_task_picker_skips_language_pickers_index_entries_and_generic_labels"] = sorted(labs) == ["Docs", "Pricing"] and all(t["question"] != t["stored_goal"] for t in tk)
        res = [{"task": {"id": 1}, "cold": {"ok": False, "clicks": 8, "seconds": 20.0}, "pool": {"ok": True, "clicks": 2, "seconds": 9.0, "retrieved_correct": True, "in_top3": True, "retrieved": "x", "retrieval_ms": 40}},
               {"task": {"id": 2}, "cold": {"ok": True, "clicks": 3, "seconds": 8.0}, "pool": {"ok": False, "clicks": 1, "seconds": 7.0, "why": "step 'X' not on the page", "retrieved": "y", "retrieved_correct": False, "in_top3": True, "retrieval_ms": 60}}]
        sm = TE.summarize(res)
        checks["the_summary_counts_both_sides_and_the_failure_reasons"] = sm["cold"]["success"] == "1/2" and sm["pool"]["success"] == "1/2" and sm["retrieval_top1_correct"] == "1/2" and sm["pool_failures_by_reason"]["step '"] == 1
        # ---- REA itself
        r_bad = RB.run("list-browser-targets", "http://127.0.0.1:1", timeout=60) if RB.available() else {"ok": False, "error": "not installed"}
        checks["rea_runs_and_reports_a_failure_as_data_not_as_an_exception"] = (not RB.available()) or (r_bad["ok"] is False and bool(r_bad["error"]))
    finally:
        WL.LOCK, WL.PATTERNS, WK.EXAMPLES = saved
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in checks.items()})


def run_ar63() -> "TestOutcome":
    """AR63: quiet running and the shortcut / training hygiene. (a) the silent mode (minimized) shows nothing and still clicks through to other pages; (b) the static shortcut filter separates chords that cannot
    be an app's command (macOS keys, Windows' own chords, words) from chords with an unusable goal text from plausible ones; (c) the web rows split BY SITE for training, duplicates and unusable rows out"""
    import http.server
    import threading
    from core_organs.harvest import shortcut_hygiene as SH, web_train_prep as TP
    from core_organs import try_app_show as TS
    checks: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar63_")
    server = None
    try:
        cl = SH.classify
        checks["mac_keys_on_a_windows_row_are_junk"] = cl("powerpnt", "command+3", "Shortcut")["verdict"] == "junk" and cl("chrome", "option+i", "Dev tools")["verdict"] == "junk"
        checks["windows_own_chords_are_junk"] = all(cl("x", c, "Do it")["verdict"] == "junk" for c in ("win+r", "ctrl+alt+delete", "win+shift+s"))
        checks["a_word_that_is_not_a_key_is_junk"] = cl("chrome", "shift+ctrl+show", "Press it")["verdict"] == "junk"
        checks["a_real_chord_with_a_sentence_for_a_goal_is_unnamed_not_junk"] = cl("winword", "alt+q", "To go to the Search text field, press Alt+Q.")["verdict"] == "unnamed" and cl("code", "control+s", "Control+S")["verdict"] == "unnamed"
        checks["a_normal_row_is_plausible_and_blender_key_names_are_keys"] = cl("notepad", "ctrl+n", "File > New tab")["verdict"] == "plausible" and cl("blender_5_2", "alt+back_space", "Text > Special")["verdict"] == "plausible" and cl("blender_5_2", "ret", "Insert Line Break")["verdict"] == "plausible"

        def row(host: str, tid: int, label: str) -> Dict[str, Any]:
            lst = "".join(f"#{i} link 'Item {i}'\n" for i in range(1, 6))
            return {"messages": [{"role": "system", "content": [{"type": "text", "text": "s"}]}, {"role": "user", "content": [{"type": "text", "text": f"Application: web:{host}\nElements:\n{lst}Intent: Open {label}\n"}]},
                                 {"role": "assistant", "content": [{"type": "text", "text": json.dumps([{"step": 1, "action": "click", "target_id": tid, "hotkey": None, "text": None, "verify_expectation": "x"}])}]}], "meta": {"host": host, "source": "web-explore"}}
        rows = [row(f"site{h}.test", 1 + (k % 4), f"thing {h}-{k}") for h in range(10) for k in range(4)]
        rows.append(rows[0])                                                                                   # an exact duplicate
        bad = row("site0.test", 9, "ghost")                                                                    # names #9, which is not in the list it shows
        rows.append(bad)
        sp = TP.split(rows, eval_sites=0.2, seed=7)
        tr_hosts, ev_hosts = {r["meta"]["host"] for r in sp["train"]}, {r["meta"]["host"] for r in sp["eval"]}
        checks["training_rows_split_by_site_no_site_on_both_sides"] = tr_hosts and ev_hosts and not (tr_hosts & ev_hosts) and len(ev_hosts) == 2
        checks["duplicates_and_rows_naming_a_missing_target_are_left_out"] = len(sp["train"]) + len(sp["eval"]) == 40 and sp["dropped"] == 2

        # ---- the silent mode: no window, no overlay, still clicks through
        open(os.path.join(tmp, "index.html"), "w", encoding="utf-8").write("<html><head><title>Quiet Test</title></head><body><nav><button onclick=\"document.getElementById('o').textContent='opened'\">Open panel</button>"
                                                                          "<a href='two.html'>Second page</a></nav><p id='o'>closed</p></body></html>")
        open(os.path.join(tmp, "two.html"), "w", encoding="utf-8").write("<html><head><title>Two</title></head><body><button onclick=\"document.title='x'\">Expand two</button></body></html>")

        class H(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=tmp, **k)

            def log_message(self, *a):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
        rep = TS.scan_web_show(url, os.path.join(tmp, "out"), pace=0.05, hold_s=0.0, minimized=True, deep=True, max_clicks=10, max_depth=2, max_pages=3, budget_s=90, media=False, understand=False, rea=False, say=lambda s: None)
        ex = rep.get("explore") or {}
        checks["the_silent_mode_is_recorded_as_not_shown"] = rep.get("show") is False and rep.get("minimized") is True
        checks["the_silent_mode_still_clicks_and_opens_a_second_page"] = ex.get("clicks", 0) >= 2 and any(n.get("outcome") == "opened a new page" for n in ex.get("nodes", []))
    finally:
        if server is not None:
            server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in checks.items()})


def run_ar64() -> "TestOutcome":
    """AR64: REA's native-program findings become knowledge. (a) the UI toolkit and capabilities are read from the imported DLLs / functions; (b) a program's own strings are sorted into shortcuts, command-line options,
    addresses, files, registry keys and interface words; (c) filing writes a document, lexicon commands and hotkey LEADS only (trust 'catalog', never verified); (d) the overnight loop skips a program that is
    already done and the proof tick writes a picture and a chart"""
    from core_organs import rea_native as RN
    from si_tests_rag import _Env
    checks: Dict[str, Any] = {}
    tmp = tempfile.mkdtemp(prefix="ar64_")
    saved = (RN.LEDGER,)
    try:
        checks["a_qt_program_is_recognised_from_its_dlls"] = RN.toolkit_of(["Qt5Core.dll", "KERNEL32.dll", "d3d11.dll"])["toolkit"] == "Qt 5"
        checks["a_program_with_no_ui_library_is_plain_win32"] = RN.toolkit_of(["KERNEL32.dll", "USER32.dll"])["toolkit"] == "plain Win32"
        checks["a_dotnet_program_is_recognised_from_its_entry_import"] = RN.toolkit_of(["mscoree.dll"], ["_CorExeMain"])["toolkit"] == ".NET (CLR)"
        caps = RN.capabilities_of(["ws2_32.dll!WSAStartup", "user32.dll!SetWindowsHookExW", "advapi32.dll!RegSetValueExW", "kernel32.dll!CreateFileW"])
        checks["capabilities_come_from_the_functions_it_imports"] = set(caps) == {"network", "global keyboard / mouse hooks", "registry"}
        cl = RN.classify_strings(["Save\tCtrl+S", "Open\tCtrl+Shift+O", "Ctrl+Z", "--verbose", "-q", "https://api.example.com/v1/items", "Software\\Vendor\\App\\Settings", "export.csv", "Select All...", "xKz9qLw", "&File"])
        checks["a_label_tab_chord_string_is_a_shortcut"] = {"label": "Save", "chord": "Ctrl+S"} in cl["shortcuts"] and any(x["chord"] == "Ctrl+Shift+O" for x in cl["shortcuts"])
        checks["flags_urls_files_and_registry_keys_are_told_apart"] = "--verbose" in cl["flags"] and cl["urls"] == ["https://api.example.com/v1/items"] and "export.csv" in cl["file_types"] and any(r.startswith("Software") for r in cl["registry"])
        checks["a_bare_chord_and_an_interface_word_are_kept_separately"] = cl["chords_without_label"] == ["Ctrl+Z"] and "Select All..." in cl["ui_words"] and "xKz9qLw" not in cl["ui_words"]
        dg = {"name": "Test Paint", "key": "test_paint", "exe": r"C:\x\testpaint.exe", "mb": 3.2, "seconds": 1.0,
              "imports": {"ok": True, "toolkit": "MFC", "tree": "good tree + menu / accelerator resources", "dlls": 12, "functions": 400, "capabilities": ["printing", "clipboard"]},
              "resources": {"ok": True, "version": {"ProductName": "Test Paint", "FileVersion": "1.2"}, "commands": [{"name": "Copy", "path": "Edit", "chord": "Ctrl+C", "help": "Copy the selection"}, {"name": "Brush size", "path": "Tools", "chord": "", "help": ""}]},
              "ghidra": {"ok": True, "strings_seen": 900, "shortcuts": [{"label": "Flip horizontal", "chord": "Ctrl+H"}], "flags": ["--new"], "urls": [], "file_types": ["a.png"], "registry": [], "ui_words": ["Rotate Image"]}}
        dg["how_to_drive"] = RN.how_to_drive(dg)
        txt = RN.text_of(dg)
        checks["the_document_says_what_it_is_made_of_and_how_to_drive_it"] = "MFC" in txt and "how to drive it" in txt and "Edit > Copy [Ctrl+C]" in txt and "Flip horizontal = Ctrl+H" in txt
        with _Env() as rag:
            res = RN.file_into_rag(rag, dg, "RUN64")
            checks["a_document_and_commands_were_filed"] = res["document_chunks"] >= 1 and res["commands"] == 2
            row = rag.fast.find("test_paint", "Edit > Copy", "ctrl+c")
            row2 = rag.fast.find("test_paint", "Flip horizontal", "ctrl+h")
            checks["hotkeys_are_leads_never_verified"] = bool(row) and bool(row2) and not row["verified"] and not row2["verified"] and row["trust"] == "catalog" and row["source"] == "rea_static"
        RN.LEDGER = os.path.join(tmp, "ledger.jsonl")
        RN.record({"key": "git", "ghidra_tried": True, "ghidra_ok": True})
        checks["the_ledger_remembers_a_finished_program"] = RN.ledger_done().get("git", {}).get("ghidra_ok") is True
        from core_organs.harvest import overnight_proof as OP
        OP.OUT = os.path.join(tmp, "proof")
        snap = OP.tick()
        snap2 = OP.tick()
        checks["the_proof_tick_writes_counts_a_picture_and_a_chart"] = bool(snap.get("when")) and os.path.isfile(snap["screenshot"] or "") and bool(snap2.get("chart")) and os.path.isfile(snap2["chart"])
    finally:
        (RN.LEDGER,) = saved
        shutil.rmtree(tmp, ignore_errors=True)
    return _verdict({k: bool(v) for k, v in checks.items()})


TESTS = [("AR50", run_ar50), ("AR51", run_ar51), ("AR52", run_ar52), ("AR53", run_ar53), ("AR54", run_ar54), ("AR55", run_ar55), ("AR56", run_ar56), ("AR57", run_ar57), ("AR58", run_ar58), ("AR59", run_ar59), ("AR60", run_ar60), ("AR61", run_ar61), ("AR62", run_ar62), ("AR63", run_ar63), ("AR64", run_ar64)]
