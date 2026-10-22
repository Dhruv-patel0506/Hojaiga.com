"""
si_tests_directive -- AR49: the five Terminal-2 tasks, checked offline (no window, no GPU): picture tier in the live scan, speech sanitizer, window-frame filter, ready-check + re-measure + retry before an action, the live-teacher sketch layer.
"""
from __future__ import annotations

import math
import os

try:
    from si_tests_apprun import _verdict, TestOutcome  # type: ignore
except ImportError:
    from core_organs.si_tests_apprun import _verdict, TestOutcome  # type: ignore

PHOTOS = os.path.join("D:" + os.sep, "new_automation", "photo_examples")
CALC = os.path.join(PHOTOS, "proof_before_after", "before_after_calculator_warm.png")


def _keypad_picture():
    """The real Calculator window picture saved by the timed batch (cropped from its proof sheet); a drawn keypad when that file is not there."""
    from PIL import Image, ImageDraw, ImageFont
    if os.path.isfile(CALC):
        return Image.open(CALC).convert("RGB").crop((14, 68, 763, 588)), "real calculator picture"
    im = Image.new("RGB", (480, 360), (32, 32, 32))
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("arial.ttf", 26)
    except Exception:
        f = ImageFont.load_default()
    for i, ch in enumerate("789456123"):
        x, y = 20 + (i % 3) * 110, 20 + (i // 3) * 90
        d.rectangle([x, y, x + 100, y + 80], fill=(60, 60, 60))
        d.text((x + 40, y + 24), ch, fill=(255, 255, 255), font=f)
    return im, "drawn keypad"


def _bow(points) -> float:
    """The largest distance of a path's points from the straight chord between its ends (0 = a straight line)."""
    (x0, y0), (x1, y1) = points[0], points[-1]
    d = math.hypot(x1 - x0, y1 - y0) or 1.0
    return max(abs((x1 - x0) * (y0 - py) - (x0 - px) * (y1 - y0)) / d for px, py in points)


def run_ar49() -> "TestOutcome":
    """AR49: picture tier fills a thin accessibility tree, the voice never reads prompt machinery, window frame buttons are never queued or operated, a not-delivered action is re-checked / re-measured / sent again, the teacher's sketch layer groups, loops and points without taking a click"""
    import types
    import numpy as np
    from core_organs import agent_executor as AE, chrome_filter as CF, picture_tier as PT, sketch_overlay as SK, tutor_overlay as TO
    from core_organs.speech_sanitize import clean_for_speech
    from core_organs.professor import voice_out as VO
    img, src = _keypad_picture()
    W, H = img.size
    frame = [{"name": "Minimize", "type": "ButtonControl", "box": (W - 140, 2, 45, 30)}, {"name": "Maximize", "type": "ButtonControl", "box": (W - 95, 2, 45, 30)}, {"name": "Close", "type": "ButtonControl", "box": (W - 50, 2, 45, 30)}]
    # ---- Task 1: picture tier
    reason = PT.needs_picture_tier(frame, (W, H))
    extra = PT.picture_controls(img, frame)
    digits = {c["name"] for c in extra if c["name"] in set("0123456789")}
    merged, info = PT.augment(img, frame)
    big_tree = [{"name": f"c{i}", "type": "ButtonControl", "box": (5 + 40 * (i % 8), 5 + 30 * (i // 8), 36, 26)} for i in range(24)]            # 24 controls, all in the top strip: the work area is empty
    centred = big_tree + [{"name": "Work area", "type": "ButtonControl", "box": (int(W * 0.3), int(H * 0.35), int(W * 0.4), int(H * 0.4))}]
    t1 = {"thin_tree_triggers_picture_tier": reason == "few_controls", "keypad_digits_found_by_picture": len(digits) >= 6, "no_frame_button_in_picture_controls": not any(CF.is_window_chrome(c["name"], "", c["box"], (W, H)) for c in extra),
          "added_controls_are_tagged": info["added"] > 0 and all(c["source"] in ("ocr", "icon", "tile") and c["ctl"] is None for c in merged[len(frame):]),
          "empty_work_area_triggers_it": PT.needs_picture_tier(big_tree, (W, H)) == "empty_viewport", "covered_work_area_does_not": PT.needs_picture_tier(centred, (W, H)) == ""}
    # ---- Task 2: speech
    leak = "user: You are HoJaiga Tutor, a friendly teacher. Explain Bold. assistant: Click the **Bold** button [12] to make text heavier."
    sp = VO.SilentSpeaker()
    sp.speak(leak)
    sp.speak_sequence([("<|im_start|>assistant\nSelect the text first.<|im_end|>", None)])
    t2 = {"echoed_prompt_removed": clean_for_speech(leak) == "Click the Bold button to make text heavier.", "template_tokens_removed": clean_for_speech("<|im_start|>assistant\nSelect the text first.<|im_end|>") == "Select the text first.",
          "plain_text_untouched": clean_for_speech("Press Ctrl+B to make it bold.") == "Press Ctrl+B to make it bold.", "speaker_hears_only_the_answer": sp.said[0] == "Click the Bold button to make text heavier." and not any("assistant" in s or "HoJaiga Tutor" in s for s in sp.said)}
    # ---- Task 3: window frame
    ses = object.__new__(AE.LiveSession)
    clicked = []
    ses.eff = types.SimpleNamespace(click_xy=lambda x, y: (clicked.append((x, y)) or (True, "posted click")))
    ses.app = types.SimpleNamespace(controls=lambda o, s: [], act=lambda ctl: "")
    ses.origin, ses.size, ses.uia_first = (0, 0), (W, H), False
    som = {"elements": [{"id": 1, "label": "Restore", "box": [W - 95, 2, 45, 30], "role": "button"}, {"id": 2, "label": "Close", "box": [int(W * 0.4), int(H * 0.7), 90, 30], "role": "button"}]}
    r_chrome = ses._act({"action": "click", "target_id": 1}, som)
    n_after_chrome = len(clicked)
    r_dialog = ses._act({"action": "click", "target_id": 2}, som)
    t3 = {"caption_buttons_are_chrome": all(CF.is_window_chrome(c["name"], c["type"], c["box"], (W, H)) for c in frame), "a_dialogs_own_Close_is_not": not CF.is_window_chrome("Close", "ButtonControl", (int(W * 0.4), int(H * 0.7), 90, 30), (W, H)),
          "system_menu_at_top_left_is_chrome": CF.is_window_chrome("System", "MenuItemControl", (2, 2, 30, 30), (W, H)), "drop_chrome_keeps_the_app": [c["name"] for c in CF.drop_chrome(frame + [{"name": "Bold", "type": "ButtonControl", "box": (10, 80, 30, 30)}], (W, H))] == ["Bold"],
          "restore_is_refused_not_clicked": r_chrome[0] is False and "chrome" in r_chrome[1] and n_after_chrome == 0, "dialog_close_is_clicked": r_dialog[0] is True and len(clicked) == 1}
    # ---- Task 4: ready check, re-measure, retry
    calls = []
    win = types.SimpleNamespace(IsIconic=lambda h: True, ShowNoActivate=lambda h: calls.append("show_no_activate"), Foreground=lambda: 99, SetForeground=lambda h: calls.append("foreground"), cloaked=lambda h: False)
    ses2 = object.__new__(AE.LiveSession)
    ses2.app = types.SimpleNamespace(hwnd=5)
    ses2.foreground_ok = False
    rd = ses2.ensure_ready(win=win)
    no_fg = "foreground" not in calls
    ses2.foreground_ok = True
    ses2.ensure_ready(win=win)
    cl = types.SimpleNamespace(IsIconic=lambda h: False, ShowNoActivate=lambda h: None, Foreground=lambda: 5, SetForeground=lambda h: None, cloaked=lambda h: True)
    rc = ses2.ensure_ready(win=cl)
    ses3 = object.__new__(AE.LiveSession)
    ses3.app = types.SimpleNamespace(hwnd=5, controls=lambda o, s: [{"name": "Plus", "box": (120, 240, 50, 40)}])
    ses3.origin, ses3.size = (0, 0), (W, H)
    fb, why = ses3.fresh_box({"label": "Plus", "box": [100, 200, 50, 40]})
    seq = [(False, "not delivered"), (True, "posted click")]
    ses3.ensure_ready = lambda force=False, win=None: {"ready": True, "notes": ["checked"]}
    ses3._act = lambda a, s: seq.pop(0)
    ses3._repark = lambda: None
    ra = ses3.act({"action": "click", "target_id": 1}, {"elements": []})
    t4 = {"minimised_window_restored_without_activation": "show_no_activate" in calls and any("not activated" in n for n in rd["notes"]), "foreground_only_when_allowed": no_fg and calls.count("foreground") == 1,
          "cloaked_frame_reported_not_ready": rc["ready"] is False, "box_is_re_measured": fb == (120, 240, 50, 40) and "moved" in why, "not_delivered_is_sent_again": ra[0] is True and "after re-check" in ra[1]}
    # ---- Task 5: the sketch layer
    rec = TO.RecordingRedOverlay()
    sk = SK.Sketcher(rec)
    keys = [c for c in extra if c["source"] in ("tile", "ocr") and c["name"] in set("0123456789")]
    clusters = SK.cluster_controls(keys, min_members=4, gap_factor=3.5)
    target = next((c for c in extra if c["name"] == "5"), extra[0])
    trig = (20, H - 40, 90, 30)
    done = sk.group_then_focus([c for c in extra if c["source"] in ("tile", "ocr")], target["box"], "the keypad", trigger=trig)
    kinds = [c.get("kind") or c["cmd"] for c in rec.commands]
    arrow = next((c for c in rec.commands if c.get("kind") == "arrow"), None)
    tb = SK._box(target["box"])
    tip = arrow["points"][-1] if arrow else (0, 0)
    drag = sk.drag([(50, 50), (120, 90), (200, 80), (260, 160)], "drag the stroke")
    prev = rec.preview(img)
    try:
        os.makedirs(PHOTOS, exist_ok=True)
        prev.save(os.path.join(PHOTOS, "sketch_overlay_preview.png"))
    except Exception:
        pass
    a = np.asarray(prev.convert("RGB")).astype(int)
    red = int(((a[..., 0] > 200) & (a[..., 1] < 90) & (a[..., 2] < 90)).sum())
    flags = SK.click_through()
    t5 = {"keypad_cluster_found_from_geometry": bool(clusters) and clusters[0]["n"] >= 6, "loop_then_box_then_arrow_in_order": "polygon" in kinds and "box" in kinds and "arrow" in kinds and kinds.index("polygon") < kinds.index("box") < kinds.index("arrow"),
          "arrow_stops_short_of_the_target": bool(arrow) and not (tb.x1 <= tip[0] <= tb.x2 and tb.y1 <= tip[1] <= tb.y2), "arrow_is_curved": bool(arrow) and _bow(arrow["points"]) > 3.0,
          "drag_path_is_smoothed": len(drag) > 4, "marks_really_drawn_red": red > 400, "overlay_is_click_through_never_activates_topmost": all(flags.values())}
    checks = {}
    for tag, d in (("t1", t1), ("t2", t2), ("t3", t3), ("t4", t4), ("t5", t5)):
        checks.update({f"{tag}_{k}": v for k, v in d.items()})
    return _verdict(checks, f"{src}; picture tier added {info['added']} (tiles {info.get('tiles')}, ocr {info.get('ocr')}, icons {info.get('icons')}), digits {sorted(digits)}; {done}; red px {red}")


TESTS = [("AR49", run_ar49)]
