"""
gauntlet -- the proof run: every case saves PICTURES, and a case passes only when its own check on the result passes.

    python -m core_organs.gauntlet --only notepad calculator          run named cases
    python -m core_organs.gauntlet --list

Per case, in D:/new_automation/data/mvp_proof_gallery/:
    before_after_<case>.png     the window before the job and after it, side by side, with the check written on the picture
    overlay_teach_<case>.png    the red teaching marks (box, pill, pointer) over the same window for the case's "how do I ..." question (rendered headless from the same beats the live overlay draws)
    results/<case>.json         the section's report (steps, sources, timings), the check, the verdict

A case is DESKTOP (an installed program, operated UIA-first through the engine), WEB (a site through the CDP loop), or SCRIPTED (a scripting engine: Blender). The harness decides nothing about the job;
it hands the sentence to AppTeachingAutomationSection.handle exactly as a person's request would be, then reads the result back.

Privacy: pictures are the application's own window (cropped to its rectangle), never the whole desktop; a case that touches a personal account (mail, chat) is masked by `mask_regions` before saving.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.join("D:" + os.sep, "new_automation", "All codes"))

GALLERY = os.path.join("D:" + os.sep, "new_automation", "data", "mvp_proof_gallery")


def _font(size: int = 16):
    from PIL import ImageFont
    for f in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        with contextlib.suppress(Exception):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def fit(img: Any, w: int = 760, h: int = 520) -> Any:
    img = img.convert("RGB")
    r = min(w / img.width, h / img.height, 1.0)
    return img.resize((max(1, int(img.width * r)), max(1, int(img.height * r))))


def compose_before_after(before: Any, after: Any, title: str, verdict: str, ok: bool, out_path: str, note: str = "", status: str = "") -> str:
    """Two pictures side by side; the verdict (and what was checked) written on the picture so the proof cannot be read as anything else."""
    from PIL import Image, ImageDraw
    b = fit(before) if before is not None else Image.new("RGB", (400, 200), (230, 230, 230))
    a = fit(after) if after is not None else Image.new("RGB", (400, 200), (230, 230, 230))
    pad, head, foot = 14, 54, 58
    W = b.width + a.width + pad * 3
    H = max(b.height, a.height) + head + foot + pad
    im = Image.new("RGB", (W, H), (248, 248, 250))
    d = ImageDraw.Draw(im)
    d.text((pad, 10), title, fill=(20, 20, 30), font=_font(20))
    d.text((pad, head - 4), "BEFORE", fill=(90, 90, 100), font=_font(13))
    d.text((b.width + pad * 2, head - 4), "AFTER", fill=(90, 90, 100), font=_font(13))
    im.paste(b, (pad, head + 14))
    im.paste(a, (b.width + pad * 2, head + 14))
    status = status or ("PASS" if ok else "FAIL")
    col = (20, 140, 60) if status == "PASS" else ((200, 130, 20) if status in ("AUTH_BLOCKED", "DEMO") else (200, 40, 40))
    y = head + 14 + max(b.height, a.height) + 8
    d.rectangle([pad, y, pad + 150, y + 24], fill=col)
    d.text((pad + 8, y + 3), status, fill=(255, 255, 255), font=_font(15))
    d.text((pad + 162, y + 3), (verdict or "")[:140], fill=(30, 30, 40), font=_font(14))
    if note:
        d.text((pad, y + 28), note[:190], fill=(90, 90, 100), font=_font(12))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    im.save(out_path)
    return out_path


def mask_regions(img: Any, boxes: Sequence[Tuple[int, int, int, int]]) -> Any:
    """Blur-and-fill rectangles (private content: message bodies, names, addresses) before a picture is saved."""
    from PIL import ImageDraw
    img = img.convert("RGB").copy()
    d = ImageDraw.Draw(img)
    for x0, y0, x1, y1 in boxes:
        d.rectangle([x0, y0, x1, y1], fill=(60, 60, 70))
        d.text((x0 + 6, y0 + 4), "masked (private)", fill=(230, 230, 235), font=_font(12))
    return img


def contact_sheet(paths: Sequence[str], out_path: str, cols: int = 3, cell: Tuple[int, int] = (520, 340)) -> str:
    from PIL import Image, ImageDraw
    paths = [p for p in paths if p and os.path.isfile(p)]
    if not paths:
        return ""
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell[0] + 12) + 12, rows * (cell[1] + 34) + 12), (240, 240, 244))
    d = ImageDraw.Draw(sheet)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        r = min(cell[0] / im.width, cell[1] / im.height)
        im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
        x, y = 12 + (i % cols) * (cell[0] + 12), 12 + (i // cols) * (cell[1] + 34)
        sheet.paste(im, (x, y + 22))
        d.text((x, y), os.path.basename(p)[:70], fill=(30, 30, 40), font=_font(13))
    sheet.save(out_path)
    return out_path


# ---------------------------------------------------------------------------------------------------------------------------------------------- cases
CASES: List[Dict[str, Any]] = [
    {"id": "blender_table", "kind": "scripted", "app": "Blender", "task": "build a wooden dining table in Blender", "label": "blender_table"},
    {"id": "blender_lamp", "kind": "scripted", "app": "Blender", "task": "build a simple desk lamp in Blender", "file": "@saved:blender_table", "label": "blender_lamp"},
    {"id": "blender_chair", "kind": "scripted", "app": "Blender", "task": "build a four legged wooden chair with a backrest in Blender", "label": "blender_chair"},
    {"id": "blender_bookshelf", "kind": "scripted", "app": "Blender", "task": "build a bookshelf with three shelves in Blender", "label": "blender_bookshelf"},
    {"id": "blender_house", "kind": "scripted", "app": "Blender", "task": "build a very big two storey luxury house with 12 rooms in Blender", "house": True, "label": "blender_house"},
    {"id": "notepad", "kind": "desktop", "app": "Notepad", "task": "in Notepad type the words Quarterly report sales are up twelve percent", "expect_words": ["quarterly", "report", "twelve"],
     "teach": "how do I find and replace text in Notepad?"},
    {"id": "notepad_replace", "kind": "desktop", "app": "Notepad", "task": "in Notepad type the words cat sat on the cat mat, then use Edit Replace to change cat to bird", "expect_words": ["bird sat on the bird mat"]},
    {"id": "calculator", "kind": "desktop", "app": "Calculator", "task": "use Calculator to add 21 and 21", "expect_words": ["42"], "teach": "how do I clear the Calculator?"},
    {"id": "calculator_chain", "kind": "desktop", "app": "Calculator", "task": "use Calculator to multiply 6 by 7", "expect_words": ["42"], "teach": "how do I switch Calculator to scientific mode?"},
    {"id": "word", "kind": "desktop", "app": "Word", "task": "in Word type the words Quarterly Summary Sales rose twelve percent this quarter", "expect_words": ["quarterly", "summary", "twelve"],
     "teach": "how do I make text bold in Word?"},
    {"id": "powerpoint", "kind": "desktop", "app": "PowerPoint", "task": "in PowerPoint add a title Roadmap 2027 and a subtitle Q1 plan", "expect_words": ["roadmap", "plan"], "teach": "how do I add a new slide in PowerPoint?"},
    {"id": "clock", "kind": "desktop", "app": "Clock", "task": "learn Clock", "mode": "understand", "teach": "how do I start a timer in Clock?"},
    {"id": "wikipedia", "kind": "web", "host": "en.wikipedia.org", "task": "search for Ada Lovelace and open her article", "check_url_end": "Ada_Lovelace", "check_text": ["lovelace", "mathematician"]},
    {"id": "youtube", "kind": "web", "host": "www.youtube.com", "task": "search for lofi coding music and open the first video", "check_url": "/watch"},
    {"id": "excalidraw", "kind": "web", "host": "excalidraw.com", "task": "draw a rectangle on the canvas",
     "pre_js": "localStorage.removeItem('excalidraw');localStorage.removeItem('excalidraw-state');1",
     "check_js": "(function(){try{var a=JSON.parse(localStorage.getItem('excalidraw')||'[]');return a.filter(function(e){return !e.isDeleted}).length}catch(x){return 0}})()"},
    {"id": "vscode_web", "kind": "web", "host": "vscode.dev", "task": "open the command palette",
     "check_js": "(function(){var q=document.querySelector('.quick-input-widget');return q&&q.style.display!=='none'&&q.offsetHeight>0?1:0})()"},
    {"id": "linkedin_guest", "kind": "web", "host": "www.linkedin.com", "task": "look for python developer jobs", "check_text": ["python"], "guest": True},
    {"id": "gmail_wall", "kind": "web", "host": "mail.google.com", "task": "open my inbox and read the newest subject", "wall": True, "steps": 3},
    {"id": "discord_wall", "kind": "web", "host": "discord.com/app", "task": "open the server list", "wall": True, "steps": 3},
    {"id": "whatsapp_wall", "kind": "web", "host": "web.whatsapp.com", "task": "open the newest chat", "wall": True, "steps": 3, "mask": [(0.40, 0.25, 0.95, 0.75)]},
    {"id": "selfheal_calculator", "kind": "selfheal"},
    {"id": "paint_trace", "kind": "desktop", "app": "Paint", "task": "trace the Ganapati1 image in Paint", "trace": (900, 0.97), "check": "trace", "teach": "how do I draw a rectangle in Paint?"},
    {"id": "paint_trace_unseen", "kind": "desktop", "app": "Paint", "task": "trace the Zorbmark image in Paint", "trace": (900, 0.97), "check": "trace", "make_image": "Zorbmark"},
    {"id": "paint_lightboard", "kind": "desktop", "app": "Paint", "task": "make a lightboard of the Ganapati1 image in Paint", "check": "lightboard"},
    {"id": "sticky_notes", "kind": "desktop", "app": "Sticky Notes", "task": "in Sticky Notes type the words buy milk and call mom", "expect_words": ["milk"], "teach": "how do I add a new note in Sticky Notes?"},
]


def window_png(session: Any) -> Any:
    with contextlib.suppress(Exception):
        img, _o = session.app.grab(popups=True)
        return img
    return None


def run_desktop(case: Dict[str, Any], section: Any, log: Callable[[str], None]) -> Dict[str, Any]:
    from core_organs import field_test as FT
    cid = case["id"]
    pdir = os.path.join(GALLERY, "raw", cid)
    section.proof_dir = pdir
    if case.get("make_image"):                                           # an image that did not exist before this run (drawn now, with a name no stored file has): the trace must work from the picture itself
        from PIL import Image, ImageDraw
        from core_organs import agent_artist as _AAx
        import random as _r
        rr = _r.Random(int(time.time()) % 10007)
        im = Image.new("RGB", (640, 480), (245, 245, 240))
        d = ImageDraw.Draw(im)
        bx, by = rr.randint(160, 240), rr.randint(220, 260)
        d.rectangle([bx, by, bx + 220, by + 170], outline=(30, 30, 30), width=5)
        d.polygon([(bx - 20, by), (bx + 110, by - rr.randint(90, 130)), (bx + 240, by)], outline=(30, 30, 30), width=5)
        d.rectangle([bx + 90, by + 70, bx + 140, by + 170], outline=(30, 30, 30), width=4)
        d.ellipse([bx + 270, by - 150, bx + 340, by - 80], outline=(30, 30, 30), width=5)
        for k in range(rr.randint(3, 6)):
            x = rr.randint(30, 600)
            d.line([x, 420, x + rr.randint(-20, 20), 380], fill=(30, 30, 30), width=4)
        im.save(os.path.join(_AAx.REF_DIR, case["make_image"] + ".png"))
    if case.get("trace"):
        from core_organs import agent_artist as _AA
        _AA.ArtistTools.DEFAULT_TRACE = tuple(case["trace"])
    t0 = time.time()
    rep = section.handle(case["task"], app=case.get("app", ""), mode=case.get("mode", "auto"), learn="auto", recall=True, live=False, vlm=True)
    section.proof_dir = ""
    rep["wall_s"] = round(time.time() - t0, 1)
    exp = FT.check_expectations(rep, case)
    proof = rep.get("proof") or {}
    words = (exp.get("words") or {})
    if case.get("check") == "trace":
        eff = " ".join(str(x.get("effect", "")) for x in (rep.get("steps") or []))
        m = re.search(r"(\d+) strokes, completion ([\d.]+)%.*edge pixels inked on the canvas ([\d.]+)%", eff)
        ok = bool(m) and float(m.group(2)) >= 97.0 and float(m.group(3)) >= 90.0 and not rep.get("error")
        verdict = (f"{m.group(1)} strokes, plan completion {m.group(2)}%, reference edge pixels inked {m.group(3)}%" if m else "no trace result: " + (eff[:100] or str(rep.get("error"))))
    elif case.get("check") == "lightboard":
        eff = " ".join(str(x.get("effect", "")) for x in (rep.get("steps") or []))
        m = re.search(r"(\d+) strokes, completion ([\d.]+)%, containment ([\d.]+)%, overlapping pairs (\d+)", eff)
        ok = bool(m) and float(m.group(2)) >= 97.0 and float(m.group(3)) == 100.0 and not rep.get("error")
        verdict = (f"{m.group(1)} strokes, completion {m.group(2)}%, containment {m.group(3)}%, overlapping pairs {m.group(4)}" if m else "no lightboard result: " + (eff[:100] or str(rep.get("error"))))
    elif case.get("mode") == "understand":
        ok = not rep.get("error") and bool(rep.get("learned") or rep.get("say") or rep.get("route"))
        verdict = "learned/recalled the program: " + str(rep.get("route", ""))
    else:
        v = rep.get("verification") or {}
        all_found = bool(words) and all(words.values())
        # strict: EVERY expected word must be read back from the window afterwards (the document's own object model lists all text; OCR / UI Automation for the rest) and every goal must have been done
        ok = not rep.get("error") and all_found and v.get("total", 0) >= 1 and v.get("done") == v.get("total")
        verdict = ("found " + ", ".join(w for w, v in words.items() if v) + (" | missing " + ", ".join(w for w, v in words.items() if not v) if not all(words.values()) else "")) if words else (rep.get("error") or "no expectation")
    from PIL import Image
    b = Image.open(proof["before"]) if proof.get("before") and os.path.isfile(proof["before"]) else None
    a = Image.open(proof["after"]) if proof.get("after") and os.path.isfile(proof["after"]) else None
    out_png = os.path.join(GALLERY, f"before_after_{cid}.png")
    compose_before_after(b, a, f"{case['app']}: {case['task']}", verdict, ok, out_png, note=f"{rep['wall_s']}s | steps: " + "; ".join(f"{s['goal'][:40]}={s['status']}" for s in (rep.get('steps') or [])[:4]))
    res = {"case": cid, "kind": "desktop", "ok": ok, "verdict": verdict, "wall_s": rep["wall_s"], "png": out_png, "report": {k: rep.get(k) for k in ("route", "steps", "verification", "error", "learned", "plan_source")}}
    return res


_SAVED: Dict[str, str] = {}


def compose_sheet(paths: Sequence[str], title: str, verdict: str, ok: bool, out_path: str, cols: int = 2, cell: Tuple[int, int] = (640, 400)) -> str:
    from PIL import Image, ImageDraw
    ims = [Image.open(p).convert("RGB") for p in paths if p and os.path.isfile(p)]
    if not ims:
        return ""
    rows = (len(ims) + cols - 1) // cols
    pad, head, foot = 12, 44, 44
    sheet = Image.new("RGB", (cols * (cell[0] + pad) + pad, head + rows * (cell[1] + pad) + foot), (248, 248, 250))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 10), title, fill=(20, 20, 30), font=_font(18))
    for i, im in enumerate(ims):
        r = min(cell[0] / im.width, cell[1] / im.height)
        im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
        sheet.paste(im, (pad + (i % cols) * (cell[0] + pad), head + (i // cols) * (cell[1] + pad)))
    y = head + rows * (cell[1] + pad) + 8
    d.rectangle([pad, y, pad + 92, y + 24], fill=(20, 140, 60) if ok else (200, 40, 40))
    d.text((pad + 8, y + 3), "PASS" if ok else "FAIL", fill=(255, 255, 255), font=_font(15))
    d.text((pad + 104, y + 3), (verdict or "")[:170], fill=(30, 30, 40), font=_font(14))
    sheet.save(out_path)
    return out_path


def run_scripted(case: Dict[str, Any], section: Any, log: Callable[[str], None]) -> Dict[str, Any]:
    """A scripting-engine program (Blender): the build is checked by the section's own measured quality (parts built, connected, nothing floating, standing on the ground plane z=0, earlier objects untouched) and the
    pictures it rendered are the proof."""
    cid = case["id"]
    t0 = time.time()
    file = _SAVED.get(case["file"][7:], "") if str(case.get("file", "")).startswith("@saved:") else ""
    rep = section.handle(case["task"], app=case.get("app", ""), mode="delegate", file=file, learn="auto", recall=False, live=False, vlm=not case.get("house"), keep_open=False)       # recall=False: every build is planned live; vlm = the three-view critique by the picture reader, no stored recipe / plan is replayed
    sv = rep.get("saved") or {}
    if sv.get("ok"):
        _SAVED[cid] = sv["path"]
    q = rep.get("quality") or {}
    pics: List[str] = []
    if case.get("house"):
        d = os.path.dirname(sv.get("copy", "")) if sv.get("copy") else ""
        order = ["01_outside.png", "02_plan_floor0_roof_off.png", "02_plan_floor1_roof_off.png"]
        pics = [os.path.join(d, n) for n in order if d and os.path.isfile(os.path.join(d, n))]
        pics += sorted(x for x in (os.path.join(d, n) for n in os.listdir(d)) if os.path.basename(x).startswith("1") and x.endswith(".png"))[:1] if d and os.path.isdir(d) else []
        h = rep.get("house") or {}
        ok = not rep.get("error") and h.get("rooms", 0) >= 12 and h.get("floors", 0) >= 2 and q.get("score", 0) >= 90 and q.get("failed", 1) == 0 and bool(pics)
        verdict = f"{h.get('rooms')} rooms on {h.get('floors')} floors, {q.get('parts_built')}/{q.get('parts_planned')} parts, connected groups {q.get('connected_groups')}, score {q.get('score')}"
    else:
        if rep.get("picture") and os.path.isfile(rep["picture"]):
            pics = [rep["picture"]]
        look = rep.get("vlm") or {}
        if look.get("sheet") and os.path.isfile(look["sheet"]):
            pics.append(look["sheet"])
        look_score = look.get("score") if look.get("ok") else None
        lowest = q.get("lowest_z")
        ok = (not rep.get("error") and q.get("score", 0) >= 90 and q.get("connected") is True and not q.get("floating_parts") and not q.get("piercing") and not q.get("quantity_problems") and q.get("on_ground") is True and lowest is not None and abs(lowest) <= 0.005
              and q.get("earlier_objects_untouched") is True and q.get("parts_built") == q.get("parts_wanted") and bool(pics) and look_score is not None and look_score >= 4)       # a PASS needs the picture reader's 3-view score >= 4/5, not only measurements
        ext = q.get("extent_m") or [0, 0, 0]
        verdict = f"{q.get('parts_built')}/{q.get('parts_wanted')} parts, connected={q.get('connected')}, floating={q.get('floating_parts')}, piercing={q.get('piercing')}, order-counts={q.get('quantity_problems') or 'ok'}, lowest z {lowest} (rule: 0), earlier objects untouched={q.get('earlier_objects_untouched')} ({q.get('earlier_objects')}), extent {ext}, score {q.get('score')}, planner {(rep.get('planner') or {}).get('source')}, picture reader {look_score} ('{look.get('wrong', '')[:90]}')"
    out_png = os.path.join(GALLERY, f"before_after_{cid}.png")
    compose_sheet(pics, f"Blender: {case['task']}", verdict, ok, out_png, cols=2 if len(pics) > 1 else 1)
    return {"case": cid, "kind": "scripted", "ok": ok, "verdict": verdict, "wall_s": round(time.time() - t0, 1), "png": out_png, "blend": sv.get("path", ""), "pictures": pics, "report": {"quality": q, "error": rep.get("error"), "tier": (rep.get("planner") or {}).get("source"), "model_calls": len((rep.get("planner") or {}).get("attempts") or []) + (1 if (rep.get("vlm") or {}).get("ok") else 0)}}


def run_selfheal_live(case: Dict[str, Any], section: Any, log: Callable[[str], None]) -> Dict[str, Any]:
    """The self-healing memory on a REAL application (Calculator): the key 'Seven' is learned from a checked press, its stored coordinate AND name are corrupted in the database, and the next request must fail the
    check, roll back (Clear), repair through UI Automation, write the repair to disk, and the process after that must use the repaired path with no fallback."""
    import tempfile
    from PIL import Image
    from core_organs import headless_input as hin
    from core_organs.harvest import local_recorder as LR
    from core_organs.rag import self_growth as SG
    t0 = time.time()
    LR.OwnedApp.READY_S = 25.0
    LR.OwnedApp.VISIBLE_FALLBACK = True
    tmp = tempfile.mkdtemp(prefix="selfheal_")
    db, rp = os.path.join(tmp, "sg.sqlite"), os.path.join(tmp, "replay.jsonl")
    res: Dict[str, Any] = {"case": case["id"], "kind": "selfheal", "ok": False}
    before = after = None
    with LR.OwnedApp("Calculator") as app:
        def snap():
            img, origin = app.grab(popups=True)
            return img, origin, app.controls(origin, img.size)

        def display() -> str:
            import uiautomation as auto
            with contextlib.suppress(Exception):
                for c, _d in auto.WalkControl(auto.ControlFromHandle(app.hwnd), maxDepth=12):
                    if (c.AutomationId or "") == "CalculatorResults":
                        return (c.Name or "").strip()
            return ""

        def labels() -> List[str]:
            return [c["name"] for c in snap()[2]][:60]

        def find(name: str):
            img, origin, cs = snap()
            for c in cs:
                if c["name"].lower() == name.lower():
                    x, y, w, h = c["box"]
                    return {"name": c["name"], "type": c["type"], "center": (int(origin[0] + x + w / 2), int(origin[1] + y + h / 2)), "box": (int(x), int(y), int(w), int(h))}
            return None

        def click(loc: Dict[str, Any]) -> None:
            """Act on whatever UI Automation finds at the stored screen point (a posted click does not reach a packaged app's XAML window); a point with nothing invokable does nothing."""
            import uiautomation as auto
            with contextlib.suppress(Exception):
                c = auto.ControlFromPoint(int(loc["center"][0]), int(loc["center"][1]))
                if c is not None:
                    c.GetInvokePattern().Invoke()
            time.sleep(0.8)

        def clear() -> None:
            loc = find("Clear") or find("Clear entry")
            if loc:
                click(loc)
        clear()
        with contextlib.suppress(Exception):
            before = snap()[0].convert("RGB")
        g = SG.SelfGrowth(db, rp, os.path.join(tmp, "crops"))
        parent = labels()
        good = find("Seven")
        d1 = ""
        for _try in range(3):                                                   # a slow XAML window may need a second press before the display shows the digit
            click(good)
            for _w in range(6):
                d1 = display()
                if "7" in d1:
                    break
                time.sleep(0.5)
            if "7" in d1:
                break
            clear()
        ok1 = "7" in d1
        crop = None
        with contextlib.suppress(Exception):
            im, o, _c = snap()
            x, y, w, h = good["box"]
            crop = im.crop((x, y, x + w, y + h))
        key = g.learn("calculator", parent, good, "click", labels(), crop, verified=ok1)
        clear()
        g.db.execute("UPDATE ui_fast SET locator=? WHERE key=?", (json.dumps({"name": "Sevn", "type": "button", "center": (good["center"][0] + 400, good["center"][1] + 400), "box": [0, 0, 10, 10]}), key))
        g.db.commit()
        parent2 = labels()
        before_disp = display()
        r1 = g.run("calculator", "Seven", parent2, perform=click, verify=labels, rollback=clear, fallbacks=[("uia", find)], check=lambda: "7" in display())
        d2 = display()
        row = g.row(key)
        g.close()
        clear()
        g2 = SG.SelfGrowth(db, rp, os.path.join(tmp, "crops"))
        parent3 = labels()
        r2 = g2.run("calculator", "Seven", parent3, perform=click, verify=labels, rollback=clear, fallbacks=[("uia", lambda n: (_ for _ in ()).throw(AssertionError("fallback used")))], check=lambda: "7" in display())
        lines = [json.loads(l) for l in open(rp, encoding="utf-8") if l.strip()]
        g2.close()
        with contextlib.suppress(Exception):
            after = snap()[0].convert("RGB")
    checks = {"the_press_was_checked_and_learned": bool(key) and ok1, "the_corrupted_path_failed_the_check_and_was_rolled_back": r1.get("tried", [""])[0] == "fast_path" and r1.get("healed") is True,
              "uia_repaired_it": r1.get("route") == "uia" and "7" in d2, "the_repair_is_on_disk": bool(row) and row["locator"]["name"] == "Seven" and bool(row.get("healed_from")),
              "the_next_process_used_the_repaired_path_with_no_fallback": r2.get("ok") and r2.get("route") == "fast_path" and not r2.get("healed"), "replay_has_learn_and_healed": {l["event"] for l in lines} >= {"learn", "healed"}}
    ok = all(checks.values())
    verdict = ", ".join(f"{k}={'yes' if v else 'NO'}" for k, v in checks.items())
    out_png = os.path.join(GALLERY, f"before_after_{case['id']}.png")
    compose_before_after(before, after, "Self-healing on Calculator: corrupt the stored key, repair via UI Automation, persist, reuse", verdict, ok, out_png,
                         note=f"display after the corrupted press: '{before_disp}' -> after repair: '{d2}' | route {r1.get('route')} then {r2.get('route')} | replay lines {len(lines)}")
    res.update({"ok": ok, "verdict": verdict, "wall_s": round(time.time() - t0, 1), "png": out_png, "r1": r1, "r2": r2})
    return res


def run_web(case: Dict[str, Any], section: Any, log: Callable[[str], None]) -> Dict[str, Any]:
    """A site through the CDP loop in a browser of our own: before / after pictures of the page, a check on the page itself (URL, words, or a JavaScript probe), send / post / pay always staged."""
    from PIL import Image
    from core_organs import web_delegate as WD
    cid, host = case["id"], case["host"]
    pdir = os.path.join(GALLERY, "raw", cid)
    os.makedirs(pdir, exist_ok=True)
    t0 = time.time()
    rep: Dict[str, Any] = {}
    before = after = None
    ok, verdict = False, ""
    with WD.OwnedBrowser(visible=True) as br:
        drv = br.driver()
        drv.navigate("https://" + host)
        time.sleep(3.0)
        if case.get("pre_js"):                                              # the harness (not the agent) puts the page into a known empty state: the owned profile keeps earlier drawings
            with contextlib.suppress(Exception):
                drv.p.call("Runtime.evaluate", {"expression": case["pre_js"], "returnByValue": True})
                drv.navigate("https://" + host)
                time.sleep(3.0)
        probe0 = None
        if case.get("check_js"):
            with contextlib.suppress(Exception):
                probe0 = drv.p.call("Runtime.evaluate", {"expression": case["check_js"], "returnByValue": True}).get("result", {}).get("value")
        with contextlib.suppress(Exception):
            before = drv.screenshot().convert("RGB")
        agent = WD.WebAgent(section.engine.get_brain(), drv, log=log, confirm=None, max_steps=case.get("steps", 12), growth=section.growth())
        rep = agent.run(case["task"], "")
        time.sleep(1.0)
        with contextlib.suppress(Exception):
            after = drv.screenshot().convert("RGB")
        url = ""
        text = ""
        probe = None
        with contextlib.suppress(Exception):
            url = drv.url()
        with contextlib.suppress(Exception):
            text = (rep.get("final") or {}).get("text", "") + " " + agent.body_text(3000)
        if case.get("check_js"):
            with contextlib.suppress(Exception):
                probe = drv.p.call("Runtime.evaluate", {"expression": case["check_js"], "returnByValue": True}).get("result", {}).get("value")
        checks = {}
        if case.get("check_url_end"):
            checks["url ends with " + case["check_url_end"]] = url.split("?")[0].split("#")[0].rstrip("/").lower().endswith(case["check_url_end"].lower())
        if case.get("check_url"):
            checks["url has " + case["check_url"]] = case["check_url"].lower() in url.lower()
        for w in case.get("check_text", []):
            checks["page says " + w] = w.lower() in (text or "").lower()
        if case.get("check_js"):
            checks["page probe rose (%s -> %s)" % (probe0, probe)] = isinstance(probe, (int, float)) and probe > (probe0 or 0)
        ok = bool(checks) and all(checks.values())
        if rep.get("status") == "needs_login":
            ok = False
        if case.get("wall"):                                                  # a site that needs a signed-in session: the honest result is 'stopped at the sign-in wall, nothing typed'
            typed = [x for x in (rep.get("steps") or []) if x.get("action") == "type"]
            blocked = rep.get("status") == "needs_login" and not typed
            ok = False                                                          # a sign-in wall is a BLOCK, never a pass: nothing of the task was done
            case["_status"] = "AUTH_BLOCKED" if blocked else "FAIL"
            checks = {"stopped at the sign-in wall (task NOT done)": blocked, "nothing typed": not typed}
        for img_name in ("before", "after"):
            im = before if img_name == "before" else after
            leaked = bool(case.get("wall")) and rep.get("status") != "needs_login"      # a personal page that did load (a signed-in session): everything below the title bar is masked, whatever the case says
            if im is not None and (case.get("mask") or leaked):
                W, H = im.size
                boxes = [(0, int(H * 0.1), W, H)] if leaked else [(int(W * a), int(H * b), int(W * c), int(H * d)) for a, b, c, d in case["mask"]]
                if img_name == "before":
                    before = mask_regions(im, boxes)
                else:
                    after = mask_regions(im, boxes)
        verdict = ", ".join(f"{k}={'yes' if v else 'NO'}" for k, v in checks.items()) + f" | agent: {rep.get('status')}, url {url[:60]}"
    for nm, im in (("before", before), ("after", after)):
        with contextlib.suppress(Exception):
            if im is not None:
                im.save(os.path.join(pdir, f"{nm}.png"))
    out_png = os.path.join(GALLERY, f"before_after_{cid}.png")
    compose_before_after(before, after, f"{host}: {case['task']}", verdict, ok, out_png, status=case.get("_status", ""), note=f"{round(time.time() - t0, 1)}s | steps: " + "; ".join(f"{s_['action']} {s_['target'][:25]}={'ok' if s_['ok'] else 'no'}" for s_ in (rep.get('steps') or [])[:5]))
    return {"case": cid, "kind": "web", "ok": ok, "status": case.get("_status") or ("PASS" if ok else "FAIL"), "verdict": verdict, "wall_s": round(time.time() - t0, 1), "png": out_png, "report": {k: rep.get(k) for k in ("status", "steps", "done_steps", "model_seconds", "summary")}}


CONCEPTS = [
    {"id": "pythagoras", "request": "explain the Pythagorean theorem by drawing it"},
    {"id": "water_cycle", "request": "draw the water cycle and explain it"},
    {"id": "binary_tree", "request": "draw a binary search tree with 7 nodes and explain it"},
]


def concept_proof(case: Dict[str, Any], brain: Any) -> Dict[str, Any]:
    """HeyClicky-style concept drawing: the brain plans the diagram, each part is drawn by the red overlay's own commands (shape + label + the sentence spoken with it). Rendered headless over a plain slate so the
    picture holds only the drawing (the live overlay draws the same commands over the real desktop: `python hojaiga_tutor.py --explain "..."`)."""
    from PIL import Image, ImageDraw
    from core_organs import diagram_teach as DT, tutor_overlay as TO
    t0 = time.time()
    plan = DT.plan_diagram(brain, case["request"])
    res: Dict[str, Any] = {"case": "concept_" + case["id"], "request": case["request"], "parts": len(plan["parts"]), "problems": plan["problems"], "plan_s": round(time.time() - t0, 1), "ok": False}
    if not plan["parts"]:
        return res
    W, H = 1280, 720
    parts = DT.to_screen(plan["parts"], (W * 0.08, H * 0.12, W * 0.92, H * 0.88))
    rec = TO.RecordingRedOverlay()
    slate = Image.new("RGB", (W, H), (250, 250, 252))
    d = ImageDraw.Draw(slate)
    for gx in range(0, W, 80):
        d.line([(gx, 0), (gx, H)], fill=(238, 238, 244))
    for gy in range(0, H, 80):
        d.line([(0, gy), (W, gy)], fill=(238, 238, 244))
    frames, says = [], []
    marks = sorted({max(0, len(parts) // 3 - 1), max(0, 2 * len(parts) // 3 - 1), len(parts) - 1})
    for k, part in enumerate(parts):
        rec.shape(part["kind"], part["points"], part["label"], seconds=1.0)
        says.append(part["say"])
        if k in marks:
            frames.append(rec.preview(slate).convert("RGB"))
    sheet = Image.new("RGB", (W // 2 * len(frames) + 8 * (len(frames) + 1), H // 2 + 120), (240, 240, 244))
    sd = ImageDraw.Draw(sheet)
    sd.text((8, 6), f"\"{case['request']}\"  |  {len(parts)} parts planned in {res['plan_s']}s, drawn part by part with the sentence spoken for each", fill=(20, 20, 30), font=_font(15))
    for i, f in enumerate(frames):
        sheet.paste(f.resize((W // 2, H // 2)), (8 + i * (W // 2 + 8), 30))
    for i, t in enumerate([x for x in says if x][:4]):
        sd.text((8, H // 2 + 36 + i * 20), f"say {i + 1}: {t[:150]}", fill=(60, 60, 80), font=_font(13))
    out = os.path.join(GALLERY, f"overlay_teach_concept_{case['id']}.png")
    sheet.save(out)
    res.update({"ok": len(parts) >= 4 and not plan["problems"], "png": out, "verdict": f"{len(parts)} parts; geometry/plan problems left: {plan['problems'] or 'none'}", "plan": plan["parts"]})
    return res


def concept_over_page(page_case: str, request: str, target: str = "") -> Dict[str, Any]:
    """A concept drawn FOR a real page (HeyClicky-style), after the vision model has LOOKED at it: (1) what is on the screen, (2) is a diagram of the concept already visible (then it is pointed at, not redrawn), else (3) the
    figure is planned (exact geometry when the concept is geometric) and drawn on an opaque card in the quietest part of the screen. With `target`, the vision model also finds that thing on the page and a red box + label is
    anchored to it. Rendered from the same overlay commands the live click-through overlay draws."""
    from PIL import Image
    from core_organs import diagram_teach as DT, tutor_overlay as TO, vision_ground as VG, brain_planner as BP
    from core_organs.professor.schema import Box
    res: Dict[str, Any] = {"case": f"screen_{page_case}", "ok": False, "status": "FAIL"}
    try:
        page = Image.open(os.path.join(GALLERY, "raw", page_case, "after.png")).convert("RGB")
        W, H = page.size
        rec = TO.RecordingRedOverlay()
        notes = []
        look = VG.look_at(page, request)
        notes.append(f"VLM sees: {look.get('description') or look.get('error')} | diagram of the concept visible: {look.get('diagram_visible')}")
        n_marks = 0
        f: Dict[str, Any] = {}
        if target:
            f = VG.find_on_screen(page, target)
            if f["found"]:
                x0, y0, x1, y1 = f["bbox"][0] * W, f["bbox"][1] * H, f["bbox"][2] * W, f["bbox"][3] * H
                rec.commands = [c for c in rec.commands if c["cmd"] != "box"]
                rec.box(Box(x0, y0, x1, y1), target, pointer=True)
                n_marks += 1
                notes.append(f"VLM found '{target}' at {[round(v, 2) for v in f['bbox']]} ({f['description']})")
            else:
                notes.append(f"VLM did not find '{target}' ({f.get('error') or 'not found'})")
        base_img = rec.preview(page).convert("RGB")
        avoid = [(f["bbox"][0] * W, f["bbox"][1] * H, f["bbox"][2] * W, f["bbox"][3] * H)] if (target and f.get("found")) else []
        sp = DT.plan_on_screen(BP.Brain(), request, page, look, avoid) if request else {"mode": "none"}
        img = base_img
        if sp["mode"] == "draw":
            rec2 = TO.RecordingRedOverlay()
            rec2.shape("card", sp["card"], "")
            for p in sp["parts"]:
                rec2.shape(p["kind"], p["points"], p["label"])
            img = rec2.preview(base_img).convert("RGB")
            n_marks += len(sp["parts"])
            notes.append(f"figure: {len(sp['parts'])} parts ({sp['plan'].get('mode', 'freeform')}), critic problems left: {sp['plan']['problems'] or 'none'}")
        elif sp["mode"] == "annotate":
            x0, y0, x1, y1 = sp["box"]
            rec3 = TO.RecordingRedOverlay()
            rec3.box(Box(x0, y0, x1, y1), "the diagram", pointer=True)
            img = rec3.preview(base_img).convert("RGB")
            n_marks += 1
        ok = n_marks >= 1 and not (sp["mode"] == "draw" and sp["plan"]["problems"]) and not look.get("error")
        out = os.path.join(GALLERY, f"overlay_teach_{page_case}_screen_concept.png")
        compose_before_after(page, img, f"Screen-grounded overlay on {page_case}: \"{request}\"" + (f" + point at {target}" if target else ""), " | ".join(notes)[:150], ok, out, note=" | ".join(notes)[:230])
        res.update({"ok": ok, "status": "PASS" if ok else "FAIL", "png": out, "verdict": " | ".join(notes), "look": look, "mode": sp["mode"]})
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"[:200]
        res["verdict"] = res["error"]
    return res


def teach_proof(case: Dict[str, Any], log: Callable[[str], None], max_beats: int = 3) -> Dict[str, Any]:
    """The red teaching marks for the case's question over the real window (cropped to it): what the live overlay would draw, rendered without opening a click-through window."""
    from PIL import Image
    from core_organs import micro_beats as MB, micro_tutor as MT, tutor_overlay as TO, tutor_voice as TV
    from core_organs.professor.schema import Box
    rec = TO.RecordingRedOverlay()
    mt = MT.MicroTutor(overlay=rec, voice=TV.Voice(enabled=False), watcher=TV.Watcher(None), bar=False, mic=False, log=lambda s: None, vision=False)
    res: Dict[str, Any] = {"case": case["id"], "question": case.get("teach", ""), "ok": False}
    try:
        mt.open(case["app"])
        time.sleep(1.0)
        mt.refresh()
        steps, src = mt.steps_for(case["teach"])
        beats = MB.plan_beats(steps, mt.controls, image=mt.screenshot(), app=mt.app, ground=None)
        live = mt.ts.live if (mt.ts and mt.ts.live) else None
        crop, origin = live.app.grab(popups=True)                         # the window's own picture (never the desktop around it), with its screen position for the marks
        frames = []
        for b in [x for x in beats if x.primitive == "box_pointer" and x.box][:max_beats]:
            rec.commands = []
            rec.box(Box(*b.box), b.pill, pointer=True)
            frames.append((b, rec.preview(crop, origin).convert("RGB")))
        res.update({"steps": len(steps), "source": src, "beats": len(beats), "marked": len(frames), "ok": len(frames) >= 1})
        if frames:
            out = os.path.join(GALLERY, f"overlay_teach_{case['id']}.png")
            fr = [(b, fit(f, 900, 420)) for b, f in frames]
            stack = Image.new("RGB", (max(f.width for _b, f in fr), 36 + sum(f.height + 30 for _b, f in fr)), (248, 248, 250))
            from PIL import ImageDraw
            d = ImageDraw.Draw(stack)
            d.text((8, 6), f"{case['app']}: \"{case['teach']}\"  [steps from {src}]", fill=(20, 20, 30), font=_font(16))
            y = 36
            for b, ff in fr:
                d.text((8, y + 4), f"{b.pill[:50]}  |  {b.speech[:110]}", fill=(60, 60, 80), font=_font(13))
                stack.paste(ff, (0, y + 26))
                y += ff.height + 30
            stack.save(out)
            res["png"] = out
    except Exception as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"[:200]
    finally:
        with contextlib.suppress(Exception):
            mt.close()
    return res


def live_guard() -> None:
    """Live runs open real windows on the person's own screen. They never start unless the person has said so: HOJAIGA_ALLOW_LIVE=1 is set by them (or by an assistant they told to run it), never by default."""
    if os.environ.get("HOJAIGA_ALLOW_LIVE") != "1":
        print("REFUSED: this run opens real windows on the screen. Set HOJAIGA_ALLOW_LIVE=1 only when the person has asked for a live run and is not working on the machine.", flush=True)
        raise SystemExit(3)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-teach", action="store_true")
    ap.add_argument("--concepts", action="store_true", help="draw the concept diagrams (the brain plans them; CPU)")
    ap.add_argument("--over", nargs="+", metavar=("PAGE_CASE", "REQUEST"), help="PAGE_CASE 'request' [target]: look at a saved page picture with the vision model, then draw the concept for it / point at the target")
    a = ap.parse_args(argv)
    if a.list:
        for c in CASES:
            print(c["id"], "|", c["kind"], "|", c.get("task", ""))
        return 0
    live_guard()
    from core_organs import app_teaching_automation as ATA
    section = ATA.AppTeachingAutomationSection(log=lambda s: print(s, flush=True))
    os.makedirs(os.path.join(GALLERY, "results"), exist_ok=True)
    if a.over:
        r = concept_over_page(*a.over)
        json.dump(r, open(os.path.join(GALLERY, "results", f"screen_{a.over[0]}.json"), "w", encoding="utf-8"), indent=1, default=str)
        print(json.dumps({k: r.get(k) for k in ("case", "ok", "status", "verdict", "png")}))
        return 0
    if a.concepts:
        outc = []
        for c in CONCEPTS:
            if a.only and c["id"] not in a.only:
                continue
            r = concept_proof(c, section.engine.get_brain())
            json.dump(r, open(os.path.join(GALLERY, "results", "concept_" + c["id"] + ".json"), "w", encoding="utf-8"), indent=1, default=str)
            print(f"##### concept_{c['id']}: {'PASS' if r.get('ok') else 'FAIL'} - {r.get('parts')} parts, problems {r.get('problems')}", flush=True)
            outc.append(r)
        print(json.dumps({"passed": sum(1 for r in outc if r.get("ok")), "total": len(outc)}))
        return 0
    results = []
    for c in CASES:
        if a.only and c["id"] not in a.only:
            continue
        print(f"\n##### {c['id']}: {c.get('task', c['kind'])}", flush=True)
        try:
            r = (run_desktop(c, section, print) if c["kind"] == "desktop" else run_web(c, section, print) if c["kind"] == "web" else run_scripted(c, section, print) if c["kind"] == "scripted" else run_selfheal_live(c, section, print) if c["kind"] == "selfheal"
                 else {"case": c["id"], "ok": False, "verdict": "kind not handled here"})
        except Exception as exc:
            r = {"case": c["id"], "ok": False, "verdict": f"crash: {type(exc).__name__}: {exc}"[:200]}
        if c.get("teach") and not a.no_teach:
            r["teach"] = teach_proof(c, print)
        json.dump(r, open(os.path.join(GALLERY, "results", c["id"] + ".json"), "w", encoding="utf-8"), indent=1, default=str)
        r["status"] = r.get("status") or ("PASS" if r.get("ok") else "FAIL")
        print(f"##### {c['id']}: {r['status']} - {r.get('verdict')}", flush=True)
        results.append(r)
    print(json.dumps({"passed": sum(1 for r in results if r.get("ok")), "total": len(results)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
