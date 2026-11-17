"""
si_tests_atlas.py -- tests for the Atlas layer (atlas/*), in the suite's TestOutcome style.

OFFLINE tests need no desktop and no network (a temp database, canned documents, synthetic pictures).
LIVE tests drive the Atlas FIXTURE (a WinForms program with known menus, dialogs, wizard and a viewport whose gestures are known) that this module
launches minimized and closes itself; ground truth is read from the fixture's own state label and truth file. They never touch a window the user owns.

    python hojaiga_atlas.py selftest [--live]
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

for _p in (r"D:\new_automation", r"D:\new_automation\All codes"):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@dataclass
class TestOutcome:
    passed: bool
    evidence: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    env_blocked: bool = False


def _verdict(checks: Dict[str, bool], extra: str = "", metrics: Dict[str, Any] = None, env: bool = False) -> TestOutcome:
    ok = all(checks.values())
    ev = "; ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()) + (f" | {extra}" if extra else "")
    m = {"checks": f"{sum(1 for v in checks.values() if v)}/{len(checks)}"}
    m.update(metrics or {})
    return TestOutcome(passed=ok, evidence=ev, metrics=m, env_blocked=env)


def _tmp_store():
    from core_organs.atlas import common as C
    p = os.path.join(tempfile.gettempdir(), "atlas_t_" + uuid.uuid4().hex[:8] + ".db")
    return C.AtlasStore(p), p


def _rm(p: str) -> None:
    for suf in ("", "-wal", "-shm"):
        try:
            os.remove(p + suf)
        except Exception:
            pass


def _tmp_model(path: str):
    from core_organs import organ_48_app_behavior_model as bm
    return bm.BehaviorModel(path)


# ===================================================================================================== offline

def run_at1() -> TestOutcome:
    """AT1: knowledge needs evidence -- a claim without it is refused; merging keeps the strongest trust; evidence is deduplicated"""
    from core_organs.atlas import common as C
    st, p = _tmp_store()
    try:
        refused = False
        try:
            st.claim("x", "arch.t", "bare assertion", trust="static", evidence=[])
        except C.EvidenceRequired:
            refused = True
        bad_trust = False
        try:
            st.claim("x", "arch.t", "s", trust="gospel", evidence=[C.Evidence("file", "a")])
        except ValueError:
            bad_trust = True
        st.claim("x", "arch.t", "Has a plugin API", trust="published", evidence=[C.Evidence("url", "http://a", "q1")], confidence=0.6)
        st.claim("x", "arch.t", "has a plugin api", trust="measured", evidence=[C.Evidence("probe", "p1")], confidence=0.9)
        st.claim("x", "arch.t", "has a plugin api", trust="measured", evidence=[C.Evidence("probe", "p1")], confidence=0.5)
        rows = st.claims("x")
        return _verdict({"no-evidence refused": refused, "unknown trust class refused": bad_trust, "same statement merged into one row": len(rows) == 1,
                         "strongest trust kept": rows[0]["trust_name"] == "measured", "confidence not lowered": rows[0]["confidence"] >= 0.9,
                         "evidence from both sources kept, no duplicates": len(rows[0]["evidence"]) == 2, "observations counted": rows[0]["n_obs"] == 3})
    finally:
        st.close()
        _rm(p)


def run_at2() -> TestOutcome:
    """AT2: library signatures describe libraries (never apps) and do not over-match (msvcp140 is not 'older MSVC')"""
    from core_organs.atlas import devscan
    names = ["Qt6Core.dll", "avcodec-62.dll", "python312.dll", "vcruntime140.dll", "msvcp140.dll", "wxmsw32u_core_vc.dll", "libsndfile-1.dll", "openvdb.dll", "soundtouch.dll",
             "sqlite3.dll", "foo.dll", "d3d12.dll", "MSVCR100.dll", "mmdevapi.dll", "libcurl-x64.dll", "onnxruntime.dll"]
    got = devscan.match_libs(names)
    labels = {h["label"] for hits in got.values() for h in hits}
    api = devscan.match_api(["RegisterHotKey", "DragAcceptFiles", "midiInOpen", "CreateFileW", "WSAStartup"])
    api_labels = {a["label"] for a in api}
    return _verdict({"Qt": "Qt" in labels, "FFmpeg libavcodec": "FFmpeg libavcodec" in labels, "Python embedded": "Python" in labels, "MSVC 2015+": "MSVC C/C++ runtime" in labels,
                     "msvcp140 NOT 'older MSVC runtime'": not any(h["label"] == "older MSVC runtime" and any("140" in f for f in h["files"]) for hits in got.values() for h in hits),
                     "MSVCR100 IS older runtime": "older MSVC runtime" in labels, "wxWidgets": "wxWidgets" in labels, "audio libs": {"libsndfile", "SoundTouch", "WASAPI"} <= labels,
                     "3D libs": "OpenVDB" in labels, "foo.dll matches nothing": "foo.dll" not in {f for hits in got.values() for h in hits for f in h["files"]},
                     "API: hotkeys + drag-drop + MIDI found": {"global hotkeys", "drag and drop", "Windows MIDI"} <= api_labels, "API: CreateFileW is not a capability": "CreateFileW" not in {f for a in api for f in a["functions"]}},
                    metrics={"libs": len(labels)})


def run_at3() -> TestOutcome:
    """AT3: developer-level static harvest of REAL installed programs: fast, every claim carries evidence, no foreign files counted (a program in a drive root owns only its own files)"""
    from core_organs.atlas import devscan, common as C
    from core_organs import static_knowledge as sk
    st, p = _tmp_store()
    try:
        checks: Dict[str, bool] = {}
        met: Dict[str, Any] = {}
        n_ok = 0
        for name in ("notepad", "calculator", "chrome", "winword", "obs"):
            exe = sk.exe_for(name)
            if not exe:
                continue
            r = devscan.scan(exe, budget_s=9, store=st, persist=True, app_key="t_" + name)
            n_ok += 1
            claims = st.claims("t_" + name)
            checks[f"{name}: scan ok + identity"] = bool(r["ok"]) and any(c["kind"] == "arch.identity" for c in claims)
            checks[f"{name}: every stored claim has evidence"] = all(c["evidence"] for c in claims)
            checks[f"{name}: within 9 s"] = (r.get("seconds") or 99) <= 9.5
            met[f"{name}_s"] = r.get("seconds")
            met[f"{name}_claims"] = len(claims)
        env = n_ok == 0
        bl = r"D:\blender.exe"
        if os.path.isfile(bl):
            r = devscan.scan(bl, budget_s=12, store=st, persist=True, app_key="t_blender")
            inv = r.get("inventory", {})
            checks["drive-root program: own files only (<5000 files, scope stated)"] = (inv.get("files") or 99999) < 5000 and "own files" in r.get("scope", "")
            checks["drive-root program: no other program's plugins reported"] = not any("wireshark" in c["statement"].lower() or "steam" in c["statement"].lower() for c in st.claims("t_blender"))
        if env:
            return TestOutcome(passed=False, evidence="no test program installed", env_blocked=True)
        return _verdict(checks, metrics=met)
    finally:
        st.close()
        _rm(p)


def run_at4() -> TestOutcome:
    """AT4: COM object model: the registry index maps a program to its classes and the type library yields its real object model (Word: Document, Range, Selection ...)"""
    from core_organs.atlas import comlib
    t0 = time.time()
    idx = comlib.get()
    t_idx = time.time() - t0
    cls = comlib.classes_for("WINWORD.EXE")
    if not cls:
        return TestOutcome(passed=False, evidence="Word is not installed on this machine (index built in %.1fs, %d servers)" % (t_idx, len(idx.get("servers", {}))), env_blocked=True)
    om = comlib.object_model_for("WINWORD.EXE")
    libs = [l for l in om.get("typelibs", {}).values() if l.get("ok")]
    names = {t["name"].lstrip("_") for l in libs for t in l.get("top", [])} | {k.lstrip("_") for l in libs for k in l.get("methods", {})}
    return _verdict({"index complete": bool(idx.get("complete")), "Word classes found": len(cls) >= 3, "type library read": bool(libs), "hundreds of types": any(l["types"] >= 300 for l in libs),
                     "Document/Range/Selection present": {"Document", "Range", "Selection"} <= names, "method names recorded": any("SaveAs2" in ms for l in libs for ms in l.get("methods", {}).values()),
                     "bounded (under 8 s)": om.get("seconds", 99) < 8}, metrics={"types": libs[0]["types"] if libs else 0, "members": libs[0]["members"] if libs else 0, "index_s": round(t_idx, 1)})


def _scene(zoom=1.0, rot=0.0, px=0.0, py=0.0, sel=None, move=None, marks=0):
    import cv2
    import numpy as np
    W, H = 620, 500
    shapes = [("rect", -200, -120, 120, 80, (60, 20, 220)), ("ell", 60, -100, 110, 110, (225, 105, 65)), ("rect", -60, 40, 140, 70, (87, 139, 46)),
              ("ell", 160, 60, 80, 80, (0, 140, 255)), ("rect", -260, 60, 70, 70, (219, 112, 147))]
    img = np.full((H, W, 3), 255, np.uint8)
    M = cv2.getRotationMatrix2D((0, 0), -rot, zoom)
    M[0, 2] += W / 2 + px
    M[1, 2] += H / 2 + py

    def T(x, y):
        v = M @ np.array([x, y, 1.0])
        return int(round(v[0])), int(round(v[1]))
    for i in range(-600, 601, 40):
        cv2.line(img, T(i, -600), T(i, 600), (200, 200, 200), 1)
        cv2.line(img, T(-600, i), T(600, i), (200, 200, 200), 1)
    cv2.line(img, T(-600, 0), T(600, 0), (0, 0, 0), 2)
    cv2.line(img, T(0, -600), T(0, 600), (0, 0, 0), 2)
    for i, (k, x, y, w, h, col) in enumerate(shapes):
        if move and i == move[0]:
            x += move[1]
            y += move[2]
        if k == "rect":
            pts = np.array([T(x, y), T(x + w, y), T(x + w, y + h), T(x, y + h)], np.int32)
            cv2.fillPoly(img, [pts], col)
            if sel and i in sel:
                cv2.polylines(img, [pts], True, (0, 0, 255), 4)
        else:
            c = T(x + w / 2, y + h / 2)
            cv2.ellipse(img, c, (int(w / 2 * zoom), int(h / 2 * zoom)), -rot, 0, 360, col, -1)
    for m in range(marks):
        c = T(-100 + 30 * m, 20)
        cv2.line(img, (c[0] - 8, c[1]), (c[0] + 8, c[1]), (255, 0, 255), 3)
        cv2.line(img, (c[0], c[1] - 8), (c[0], c[1] + 8), (255, 0, 255), 3)
    return img


def run_at5() -> TestOutcome:
    """AT5: the motion classifier tells pan / zoom / rotate / scroll / nonrigid / local change / none / object move apart from two pictures, with verified estimates"""
    import cv2
    import numpy as np
    from core_organs.atlas import motion
    base = _scene()
    cases = []
    for dx, dy in [(40, 0), (-60, 25), (0, 80), (120, -40)]:
        cases.append(("pan", _scene(px=dx, py=dy), {"hint": "drag"}))
    for z in [1.1, 1.21, 0.909, 0.8264]:
        cases.append(("zoom", _scene(zoom=z), {"hint": "wheel"}))
    for r in [-30, -10, 12, 25, 45]:
        cases.append(("rotate", _scene(rot=r), {"hint": "drag"}))
    cases.append(("none", _scene(), {"hint": "click"}))
    cases.append(("local_change", _scene(sel=[2]), {"hint": "click"}))
    cases.append(("local_change", _scene(marks=1), {"hint": "click"}))
    cases.append(("scroll", _scene(py=60), {"hint": "wheel"}))
    cases.append(("translate_object", _scene(move=(2, 90, 20)), {"hint": "drag", "drag": {"vec": (90, 20), "button": "left"}}))
    H, W = base.shape[:2]
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    P = cv2.getPerspectiveTransform(src, np.float32([[60, 40], [W - 10, 10], [W - 90, H - 60], [10, H - 20]]))
    cases.append(("nonrigid", cv2.warpPerspective(base, P, (W, H), borderValue=(255, 255, 255)), {"hint": "drag"}))
    ok = 0
    wrong = []
    for exp, after, kw in cases:
        got = motion.describe(base, after, **kw)["class"]
        if got == exp:
            ok += 1
        else:
            wrong.append((exp, got))
    mid = base.copy()
    cv2.rectangle(mid, (100, 80), (330, 260), (0, 0, 0), 2)
    band = motion.describe(base, _scene(sel=[0, 2]), hint="drag", drag={"box": (100, 80, 331, 261), "boxes": [(100, 80, 331, 261)], "vec": (230, 180), "button": "left"}, during=mid)["class"]
    path = [(100 + i * 4, 150 + int(40 * math.sin(i / 8))) for i in range(80)]
    strk = base.copy()
    for a, b in zip(path, path[1:]):
        cv2.line(strk, a, b, (0, 0, 0), 4)
    stroke = motion.describe(base, strk, hint="drag", drag={"path": path, "vec": (316, 0), "button": "left"})["class"]
    # noise immunity: a blinking region must not read as an effect
    noisy = base.copy()
    noisy[10:60, 10:200] = 0
    ign = motion.volatility_mask([base, noisy, base])
    noise_ok = motion.describe(base, noisy, hint="click", ignore=ign)["class"] == "none"
    painted = motion.painted_box(np.pad(base, ((0, 100), (0, 150), (0, 0))))
    return _verdict({f"{ok}/{len(cases)} gesture effects classified": ok == len(cases), "rubber band seen while held": band.startswith("rubber_band"), "stroke along the path": stroke == "stroke",
                     "volatile (blinking) pixels ignored": noise_ok, "painted extent found (unpainted margin cropped)": painted is not None and painted[2] <= 625 and painted[3] <= 505},
                    extra=f"misses={wrong}", metrics={"accuracy": f"{ok}/{len(cases)}"})


def run_at6() -> TestOutcome:
    """AT6: shipped keymaps in every common shape become input grammar (pointer gestures with modifiers, key chords, contexts)"""
    from core_organs.atlas import keymaps as K
    py = '''
def km_3d_view(params):
    items = []
    items.extend([
        ("view3d.rotate", {"type": 'MIDDLEMOUSE', "value": 'PRESS'}, None),
        ("view3d.move", {"type": 'MIDDLEMOUSE', "value": 'PRESS', "shift": True}, None),
        ("view3d.zoom", {"type": 'MIDDLEMOUSE', "value": 'PRESS', "ctrl": True}, None),
        ("transform.translate", {"type": 'LEFTMOUSE', "value": 'CLICK_DRAG'}, None),
        ("wm.search_menu", {"type": 'F3', "value": 'PRESS'}, None),
        ("object.delete", {"type": 'X', "value": 'PRESS'}, {"properties": [("confirm", False)]}),
    ])
    return items
'''
    js = '// keybindings\n[\n {"key": "ctrl+shift+p", "command": "workbench.action.showCommands"},\n {"key": "ctrl+s", "command": "workbench.action.files.save", "when": "editorFocus"},\n]'
    ini = "[Master]\ncrossfader_left=Left\ncrossfader_right=Right\n[Channel1]\nplay=Space\ncue=Q\nsync=S\nloop=L\n"
    xml = '<bindings><binding key="Ctrl+Z" action="Undo"/><binding key="Ctrl+Y" action="Redo"/></bindings>'
    txt = "| Shortcut | Action |\n|---|---|\n| Ctrl+S | Save the document |\n| Ctrl+Shift+N | New window |\nUndo: Ctrl+Z\n"
    b_py, b_js, b_ini, b_xml, b_txt = (K.extract(py, "k.py"), K.extract(js, "keys.json"), K.extract(ini, "x.kbd.cfg"), K.extract(xml, "m.xml"), K.extract(txt, "docs.md"))
    find = lambda bs, act: next((b for b in bs if b["action"] == act), None)
    rot, mov, zoom = find(b_py, "view3d.rotate"), find(b_py, "view3d.move"), find(b_py, "view3d.zoom")
    drag = find(b_py, "transform.translate")
    return _verdict({"python: MMB press = rotate in 3d_view": bool(rot) and rot["input"] == "middle-mouse press" and rot["context"] == "3d_view",
                     "python: Shift+MMB = move": bool(mov) and mov["input"].startswith("Shift+middle"), "python: Ctrl+MMB = zoom": bool(zoom) and zoom["input"].startswith("Ctrl+middle"),
                     "python: left-mouse drag recognised": bool(drag) and drag["input"] == "left-mouse drag", "python: F3 key": any(b["input"].startswith("F3") for b in b_py),
                     "python: pointer gestures separated": len(K.gestures_of(b_py)) == 4, "json (comments + trailing comma)": len(b_js) == 2 and b_js[0]["input"] == "Ctrl+Shift+P",
                     "ini bindings under groups": len(b_ini) >= 5 and any(b["action"] == "play" and b["input"] == "Space" for b in b_ini), "xml bindings": len(b_xml) == 2,
                     "text tables + 'Action: Chord'": len(b_txt) >= 3 and any(b["input"] == "Ctrl+S" for b in b_txt), "claims carry the source quote": all(c.evidence[0].quote for c in K.to_claims("t", b_py, "http://x/k.py"))},
                    metrics={"python": len(b_py), "json": len(b_js), "ini": len(b_ini), "xml": len(b_xml), "text": len(b_txt)})


def run_at7() -> TestOutcome:
    """AT7: the language model cannot add facts: fabricated quotes and claims the quote does not entail are dropped; real ones kept; the meter counts"""
    from core_organs.atlas import distill, llm
    doc = ("Acme Studio is a digital audio workstation written in C++ with a Python scripting API. "
           "It supports VST3 plugins and exports WAV and FLAC files. Documentation: see the website for guides about installing.")
    fake = {"facts": [
        {"category": "language", "claim": "Acme Studio is written in C++.", "quote": "digital audio workstation written in C++ with a Python scripting API"},
        {"category": "scripting", "claim": "It offers a Python scripting API.", "quote": "written in C++ with a Python scripting API. It supports VST3 plugins"},
        {"category": "feature", "claim": "It supports the AAX plugin format.", "quote": "It supports AAX plugins and exports MP3 files"},
        {"category": "feature", "claim": "It is built on Rust and Electron with GPU shaders.", "quote": "It supports VST3 plugins and exports WAV and FLAC files"},
        {"category": "feature", "claim": "Acme exports files.", "quote": "- [Docs](https://example.org/docs)"},
    ]}
    orig_chat, orig_av = llm.chat, llm.available
    llm.available = lambda: True
    llm.chat = lambda *a, **k: {"ok": True, "json": fake, "text": "", "seconds": 0.0, "model": "fake", "error": ""}
    try:
        claims, meta = distill.with_model("acme", doc, "http://doc")
    finally:
        llm.chat, llm.available = orig_chat, orig_av
    stmts = [c.statement for c in claims]
    det = distill.deterministic("acme", doc, "http://doc")
    return _verdict({"real, entailed fact kept": any("C++" in s for s in stmts), "second real fact kept": any("Python" in s for s in stmts), "fabricated quote dropped": not any("AAX" in s for s in stmts),
                     "quote that does not entail the claim dropped": not any("Rust" in s for s in stmts), "link-list quote dropped": not any(s == "Acme exports files." for s in stmts),
                     "meter: proposed 5 kept 2 dropped 3": (meta["proposed"], meta["kept"], meta["dropped"]) == (5, 2, 3), "every claim has a quote": all(c.evidence and c.evidence[0].quote for c in claims),
                     "deterministic extractor works without the model": len(det) >= 2}, metrics={"kept": meta["kept"], "dropped": meta["dropped"]})


def run_at8() -> TestOutcome:
    """AT8: public knowledge is cached with provenance and replayable offline; structured claims carry their URL"""
    from core_organs.atlas import webknow as W, common as C
    st, p = _tmp_store()
    try:
        url = "https://example.invalid/atlas-test-doc-" + uuid.uuid4().hex[:6]
        cf = W._cache_file(url)
        with open(cf, "w", encoding="utf-8") as fh:
            fh.write('{"hello": "world"}')
        W.CACHE_ONLY = True
        try:
            r1 = W.get(url, store=st)
            j, _ = W.get_json(url, store=st)
            miss = W.get("https://example.invalid/never-cached-" + uuid.uuid4().hex[:6], store=st)
        finally:
            W.CACHE_ONLY = False
        web = {"wikidata": {"ok": True, "id": "Q1", "label": "Acme", "description": "audio software", "url": "https://www.wikidata.org/wiki/Q1", "written in": ["C++", "Python"], "license": ["GPL-3.0"]},
               "github": {"ok": True, "repo": "acme/acme", "url": "https://github.com/acme/acme", "stars": 12, "license": "GPL-3.0", "description": "Acme", "languages": {"C++": 70.0, "Python": 30.0},
                          "top_level": {"src": 90, "plugins": 40}, "default_branch": "main", "modules": {"plugins/a": 3}}}
        cl = W.structured_claims("acme", web)
        kinds = {c.kind for c in cl}
        os.remove(cf)
        return _verdict({"cache hit served with no network": r1["ok"] and r1["from_cache"], "JSON read from cache": j == {"hello": "world"}, "uncached URL fails honestly in cache-only mode": not miss["ok"],
                         "structured claims produced": {"web.identity", "web.language", "web.source", "web.layout"} <= kinds,
                         "every web claim is 'published' trust with a URL": all(c.trust == "published" and c.evidence[0].type == "url" and c.evidence[0].ref.startswith("http") for c in cl),
                         "language breakdown in the claim": any("C++ 70.0%" in c.statement for c in cl)}, metrics={"claims": len(cl)})
    finally:
        W.CACHE_ONLY = False
        st.close()
        _rm(p)


def run_at9() -> TestOutcome:
    """AT9: learning: predictions improve with observations, never-seen features are probed first (active ordering), drift names exactly what changed"""
    from core_organs.atlas import evolve, common as C
    st, p = _tmp_store()
    try:
        L = evolve.Learner(st, "app", "r1")
        feats = lambda lab: {"label": lab, "ctype": "ButtonControl"}
        first = L.predict("opener", feats("Export..."))
        for lab in ["Export...", "Import...", "Options...", "Print...", "Settings..."]:
            L.observe("opener", feats(lab), L.predict("opener", feats(lab)) or "", "dialog", lab)
        for lab in ["Add", "Clear", "Zoom"]:
            L.observe("opener", feats(lab), L.predict("opener", feats(lab)) or "", "inline_change", lab)
        pred_dots = L.predict("opener", feats("About..."))
        p_dots = L.distribution("opener", feats("About...")).get("dialog", 0.0)
        p_plain = L.distribution("opener", feats("Bold")).get("dialog", 0.0)
        unseen = {"label": "Zork", "ctype": "WeirdControl"}
        order = L.rank([feats("Export..."), unseen], "opener", lambda f: f)
        acc = L.accuracy("app")
        fp1 = evolve.fingerprint(st, "app", "", ["File", "Edit", "Save"], 3)
        fp2 = evolve.fingerprint(st, "app", "", ["File", "Edit", "Save", "Export"], 4)
        fp3 = evolve.fingerprint(st, "app", "", ["File", "Edit", "Save", "Export"], 4)
        return _verdict({"no prediction before any observation": first is None, "learned: an ellipsis label opens a dialog": pred_dots == "dialog", "a label without an ellipsis is less likely a dialog than one with it": p_dots > p_plain,
                         "never-seen item ranked first (max entropy)": order[0] is unseen, "accuracy ledger kept": acc["n"] >= 1,
                         "first scan flagged": fp1["first_scan"], "drift: added control named": fp2.get("added") == ["Export"], "drift: unchanged scan reports no change": not fp3.get("structure_changed")},
                        metrics={"ledger_n": acc["n"]})
    finally:
        st.close()
        _rm(p)


def _seed_model(path: str, key: str):
    m = _tmp_model(path)
    for name, mp, sc in [("Zoom In", "View > Zoom In", "Ctrl+Plus"), ("Reset View", "View > Reset View", ""), ("Preferences...", "Edit > Preferences...", ""), ("Save As...", "File > Save As...", "Ctrl+Shift+S"),
                         ("Exit", "File > Exit", ""), ("Show Grid", "View > Show Grid", "")]:
        m.upsert_command(key, {"name": name, "menu_path": mp, "verb": "invoke", "shortcut": sc or None, "risk": "E2" if name == "Exit" else None}, source="learned", origin="atlas:menu", evidence="t")
    return m


def run_at10() -> TestOutcome:
    """AT10: planning is grounded: each sub-goal gets real routes (menu path / dialog path / COM / switch / gesture); an unsupported goal is reported ungrounded; a pointer-ignoring app gets scripting routes promoted"""
    from core_organs.atlas import planner, common as C
    st, p = _tmp_store()
    mp = p.replace(".db", "_m.db")
    try:
        m = _seed_model(mp, "demo")
        from core_organs import knowledge_store as ks
        ks.put_dialog(m, "demo", "Preferences", [{"name": "Autosave", "kind": "checkbox"}, {"name": "Reset All Settings", "kind": "button"}], source="t", via="t")
        st.claim("demo", "ext.cli", "Command-line switches: --startrecording, --scene", trust="static", evidence=[C.Evidence("pe", "x")], value=["--startrecording", "--scene"])
        st.claim("demo", "stack.scripting", "Python: embedded Python interpreter", trust="static", evidence=[C.Evidence("pe", "x")], value={"area": "scripting", "label": "Python"})
        st.put_gesture("demo", "Viewport", "canvas", "drag-middle", "", "pan", {}, reversible=True, delivered=True, effective=True)
        pl = planner.plan("demo", "zoom in, then open preferences, then start recording, then teleport the cube", st, m, use_model=False)
        steps = {s["goal"]: s for s in pl["steps"]}
        z, pr, rec, tel = steps["zoom in"], steps["open preferences"], steps["start recording"], steps["teleport the cube"]
        pan = planner.plan("demo", "pan the view", st, m, use_model=False)["steps"][0]
        st.claim("demo", "input.channel", "Posted pointer input is IGNORED", trust="measured", evidence=[C.Evidence("gesture", "r")], value={"posted_mouse": "ineffective"})
        create = planner.plan("demo", "create a house model", st, m, use_model=False)["steps"][0]
        pan2 = planner.plan("demo", "pan the view", st, m, use_model=False)["steps"][0]
        return _verdict({"'zoom in' -> its menu command": z["grounded"] and z["chosen"]["label"] == "Zoom In", "'open preferences' grounded": pr["grounded"] and "Preferences" in pr["chosen"]["label"],
                         "'start recording' -> command-line switch": rec["grounded"] and rec["chosen"]["effector"] == "cli_switch", "unsupported goal is UNGROUNDED (nothing invented)": not tel["grounded"] and "ungrounded" in tel,
                         "gesture route from the measured atlas": pan["grounded"] and pan["chosen"]["effector"] == "gesture", "plan reports completeness honestly": (pl["grounded"], pl["total"]) == (3, 4) and not pl["complete"],
                         "destructive Exit is never the route for 'zoom in'": z["chosen"]["label"] != "Exit",
                         "creative goal falls back to the scripting runtime": create["grounded"] and create["chosen"]["effector"] == "scripting_api",
                         "pointer-ignoring app: measured gesture demoted": (not pan2["grounded"]) or pan2["chosen"]["effector"] != "gesture" or pan2["routes"][0]["score"] < pan["routes"][0]["score"]})
    finally:
        st.close()
        _rm(p)
        _rm(mp)


def run_at11() -> TestOutcome:
    """AT11: Q&A answers only from stored knowledge, with evidence; an unknown topic is answered honestly; an invented citation/number is rejected"""
    from core_organs.atlas import qa, llm, common as C
    st, p = _tmp_store()
    mp = p.replace(".db", "_m.db")
    try:
        m = _seed_model(mp, "demo")
        st.claim("demo", "stack.scripting", "Python: embedded Python interpreter (scriptable / plugin API in Python)", trust="static", evidence=[C.Evidence("file", "python312.dll")])
        st.claim("demo", "gesture.shipped", "middle-mouse press -> view3d.rotate in view3d", trust="published", evidence=[C.Evidence("url", "http://k", "middle-mouse rotate")])
        r1 = qa.ask("demo", "can I script it with python", st, m, synthesize=False)
        r2 = qa.ask("demo", "which gesture rotates the view", st, m, synthesize=False)
        r3 = qa.ask("demo", "what shortcut saves as", st, m, synthesize=False)
        r4 = qa.ask("demo", "does it support quantum teleportation", st, m, synthesize=False)
        orig_chat, orig_av, orig_emb = llm.chat, llm.available, llm.embed
        llm.available = lambda: True
        llm.embed = lambda *a, **k: None
        llm.chat = lambda *a, **k: {"ok": True, "json": {"answer": "It has 42 menus [1] and 7 plugins [9]."}, "seconds": 0.0, "model": "fake", "error": ""}
        try:
            r5 = qa.ask("demo", "can I script it with python", st, m, synthesize=True)
        finally:
            llm.chat, llm.available, llm.embed = orig_chat, orig_av, orig_emb
        return _verdict({"scripting question -> the Python fact first": "Python" in r1["facts"][0]["text"], "gesture question -> the keymap fact": any("view3d.rotate" in f["text"] for f in r2["facts"][:2]),
                         "shortcut question -> Ctrl+Shift+S command": any("Ctrl+Shift+S" in f["text"] for f in r3["facts"][:3]), "facts carry trust + evidence": all("trust" in f and f["evidence"] is not None for f in r1["facts"]),
                         "unknown topic: honest non-answer": not r4["grounded"] or not r4["facts"] or "quantum" not in r4["answer"].lower(), "invented number/citation rejected -> facts shown": r5["method"] == "facts" and "synthesis_rejected" in r5})
    finally:
        st.close()
        _rm(p)
        _rm(mp)


def run_at12() -> TestOutcome:
    """AT12: classification by evidence voting: a word processor, a DJ tool and a 3-D suite are told apart by what the evidence says; thin evidence stays 'unclassified'"""
    from core_organs.atlas import architect
    mk = lambda kind, st, value=None: {"kind": kind, "statement": st, "value": value or {}, "evidence": [{"type": "url", "ref": "x"}], "trust_name": "published"}
    word = [mk("web.kind", "Is a(n) word processor"), mk("web.identity", "Acme Writer is described as: word processor software")]
    r_word = architect.classify(word, file_types=[".docx", ".doc", ".rtf", ".txt"], labels=["Paragraph", "Font", "Styles", "Header", "Footer", "Page Layout", "References", "Track Changes"], com_types=["Document", "Range", "Selection", "Paragraph"])
    dj = [mk("stack.audio", "SoundTouch", {"area": "audio", "label": "SoundTouch"}), mk("stack.audio", "KeyFinder", {"area": "audio", "label": "KeyFinder"}), mk("stack.input", "MIDI", {"area": "input", "label": "MIDI"}),
          mk("stack.audio", "TagLib", {"area": "audio", "label": "TagLib"}), mk("web.kind", "Is a(n) open-source virtual DJ software")]
    r_dj = architect.classify(dj, file_types=[".mp3", ".flac", ".wav"], labels=["Deck", "Crossfader", "Tempo", "BPM", "Sync", "Cue", "Loop", "Mixer"], com_types=[])
    td = [mk("stack.3d", "OpenVDB", {"area": "3d", "label": "OpenVDB"}), mk("stack.3d", "Embree", {"area": "3d", "label": "Embree"}), mk("stack.3d", "USD", {"area": "3d", "label": "USD"}), mk("web.kind", "3D computer graphics software")]
    r_3d = architect.classify(td, file_types=[".blend", ".fbx", ".obj"], labels=["Viewport", "Outliner", "Modifier", "Mesh", "Material", "Render"], com_types=[])
    thin = architect.classify([mk("stack.runtime", "MSVC", {"area": "runtime", "label": "MSVC C/C++ runtime"})], file_types=[], labels=["OK", "Cancel"], com_types=[])
    return _verdict({"word processor": r_word["kind"] == "document_editor", "DJ / audio production": r_dj["kind"] == "audio_production", "3-D creation suite": r_3d["kind"] == "3d_creation",
                     "thin evidence -> unclassified (no guess)": thin["kind"] == "unclassified", "classification lists its evidence": bool(r_dj["candidates"] and r_dj["candidates"][0]["evidence"])},
                    metrics={"word": r_word["kind"], "dj": r_dj["kind"], "3d": r_3d["kind"]})


def run_at13() -> TestOutcome:
    """AT13: restoration is judged by evidence: a leftover OBJECT (a marker) is NOT restored, small rigid backlash IS; explorer vocabulary rules"""
    import numpy as np
    from core_organs.atlas import gestures as G, explorer as X
    base = _scene()
    marker = _scene(marks=1)
    shifted = _scene(px=2)
    gp = G.GestureProber.__new__(G.GestureProber)
    r_same, _ = gp.restored(base, base)
    r_marker, ev_m = gp.restored(base, marker, None, effect_px=0)
    r_shift, ev_s = gp.restored(base, shifted, None, effect_px=0)
    spec = G.Spec("drag", "left", mods=("shift",))
    return _verdict({"identical picture: restored": r_same, "leftover marker: NOT restored": not r_marker, "2 px backlash: restored": r_shift,
                     "gesture label": spec.label == "shift+drag-left", "ellipsis = opener": bool(X.OPENER_RX.search("Export...")) and not X.OPENER_RX.search("Export"),
                     "Next recognised": bool(X.NEXT_RX.search("Next >")) and not X.NEXT_RX.search("Nexus"), "destructive words flagged": bool(X.UNSAFE_RX.search("Delete All")) and not X.UNSAFE_RX.search("Zoom In"),
                     "cancel never confused with commit": bool(X.CANCEL_RX.search("Cancel")) and not X.CANCEL_RX.search("OK") and bool(X.COMMIT_RX.search("Finish"))})


def run_at14() -> TestOutcome:
    """AT14: blind-app structure: OCR reads rendered UI text; the menu bar is told from workspace tabs by the first wide gap; a title bar is not a menu"""
    from core_organs.atlas import blind
    row = [("File", 48, 24), ("Edit", 90, 24), ("Render", 132, 48), ("Window", 198, 52), ("Help", 268, 32), ("Layout", 340, 46), ("Modeling", 410, 60), ("Sculpting", 494, 62)]
    labels = [{"text": "(Unsaved) - Blender 5.2.2 LTS", "box": (60, 10, 330, 26), "conf": 90, "id": "t"}]
    for i, (t, x, w) in enumerate(row):
        labels.append({"text": t, "box": (x, 46, x + w, 62), "conf": 90, "id": f"m{i}"})
    for i in range(3):
        labels.append({"text": f"Item{i}", "box": (40, 120 + 30 * i, 100, 136 + 30 * i), "conf": 90, "id": f"x{i}"})
    cl = blind.menu_cluster(labels, 1029)
    texts = [l["text"] for l in cl]
    ocr_ok = None
    if blind.available():
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new("RGB", (520, 90), (30, 30, 30))
            d = ImageDraw.Draw(img)
            f = ImageFont.truetype("arial.ttf", 22)
            d.text((10, 10), "File  Edit  Render  Window", fill=(230, 230, 230), font=f)
            d.text((10, 50), "Location X   Rotation Y", fill=(230, 230, 230), font=f)
            words = " ".join(w["text"] for w in blind.ocr_words(img, psm=11, min_conf=40))
            ocr_ok = all(x in words for x in ("File", "Edit", "Render", "Location", "Rotation"))
        except Exception:
            ocr_ok = None
    checks = {"menu bar = File..Help (cluster ends at the wide gap)": texts == ["File", "Edit", "Render", "Window", "Help"], "tabs excluded": not ({"Layout", "Modeling"} & set(texts)),
              "title bar excluded": "(Unsaved) - Blender 5.2.2 LTS" not in texts}
    if ocr_ok is not None:
        checks["OCR reads rendered UI text"] = ocr_ok
    return _verdict(checks, metrics={"cluster": texts})


def run_at15() -> TestOutcome:
    """AT15: host-API introspection: recipe chosen by evidence, dump -> evidenced claims, planner route api_operator ranks the exact operator first, unknown programs get no recipe"""
    import json as _json
    import tempfile
    from core_organs.atlas import introspect, planner
    store, _ = _tmp_store()
    d = {"version": "9.9", "ops_count": 3, "menus_count": 1, "panels_count": 1, "workspaces": ["Layout"],
         "operators": {"mesh": [{"id": "mesh.primitive_cube_add", "name": "Add Cube", "desc": "Construct a cube mesh", "props": [["size", "FLOAT", ""]]},
                                {"id": "mesh.primitive_cube_add_gizmo", "name": "Add Cube Gizmo", "desc": "x", "props": []}],
                       "ed": [{"id": "ed.undo", "name": "Undo", "desc": "Undo previous action", "props": []}]},
         "menus": {"M_add": {"label": "Add", "n_items": 1, "items": [{"t": "op", "id": "mesh.primitive_cube_add", "text": ""}]}},
         "panels": [{"id": "P", "label": "Transform", "space": "VIEW_3D"}], "enums": {"object_modes": [["OBJECT", "Object Mode"]]}, "rna": {"Object": {"n": 1, "props": [["location", "FLOAT", ""]]}}}
    f = os.path.join(tempfile.mkdtemp(), "dump.json")
    with open(f, "w", encoding="utf-8") as fh:
        _json.dump(d, fh)
    res = {"ok": True, "recipe": "bpy", "file": f, "data": d, "route": {"runtime": "embedded Python (bpy)", "call_template": "bpy.ops.{id}()"}}
    claims = introspect.to_claims("fakeapp", res)
    for c in claims:
        store.put_claim(c)
    routes = planner.collect_routes("fakeapp", "add a cube", store, None, {"posted_mouse": "ineffective"})
    api = [r for r in routes if r["effector"] == "api_operator"]
    kinds = {c.kind for c in claims}
    return _verdict({"claims have evidence": all(c.evidence for c in claims), "kinds present": {"api.runtime", "api.operators", "api.menu", "api.panels", "api.mode", "ui.workspace", "model.struct"} <= kinds,
                     "exact operator first": bool(api) and api[0]["detail"]["id"] == "mesh.primitive_cube_add", "call rendered": bool(api) and api[0]["detail"]["call"] == "bpy.ops.mesh.primitive_cube_add()",
                     "no recipe for unknown program": introspect.pick(os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "notepad.exe")) is None,
                     "blender-named exe matches": any(__import__("re").search(r["match"]["exe_regex"], "blender.exe", __import__("re").I) for r in introspect.recipes() if r["match"].get("exe_regex"))},
                    metrics={"claims": len(claims), "routes": len(api)})



def _fake_ribbon():
    """A synthetic ribbon snapshot shaped like the one measured on a real Office window (DFS pre-order node list)."""
    from core_organs import fast_uia
    nodes = []

    def add(ctype, name="", aid="", parent=-1, depth=0, pats=(), rect=(100, 200, 160, 230), enabled=True, accel="", selected=None, toggle=-1):
        n = fast_uia.Node()
        n.idx, n.parent, n.depth, n.ctype, n.name, n.aid, n.cls = len(nodes), parent, depth, ctype, name, aid, ""
        n.rect, n.enabled, n.offscreen, n.help, n.accel, n.pats = rect, enabled, False, "", accel, list(pats)
        n.expand_state, n.selected, n.toggle_state, n.el = -1, selected, toggle, None
        nodes.append(n)
        if parent >= 0:
            nodes[parent].children.append(n.idx)
        return n.idx
    w = add("WindowControl", "Doc - App")
    rib = add("PaneControl", "Ribbon", parent=w, depth=1, rect=(0, 0, 1000, 160))
    qat = add("ToolBarControl", "Quick Access Toolbar", parent=rib, depth=2, rect=(0, 0, 300, 20))
    add("ButtonControl", "Save", "FileSave", qat, 3, ("invoke",), rect=(5, 2, 25, 18), accel="Ctrl+S")
    strip = add("TabControl", "Ribbon Tabs", parent=rib, depth=2, rect=(0, 30, 600, 50))
    for i, t in enumerate(("Home", "Insert", "View")):
        add("TabItemControl", t, "Tab" + t, strip, 3, ("select",), rect=(10 + 70 * i, 30, 70 + 70 * i, 50), selected=(t == "Home"))
    low = add("PaneControl", "Lower Ribbon", parent=rib, depth=2, rect=(0, 55, 1000, 160))
    top = add("GroupControl", "Home", parent=low, depth=3, rect=(0, 55, 1000, 160))
    g1 = add("GroupControl", "Clipboard", parent=top, depth=4, rect=(0, 60, 200, 160))
    sp = add("SplitButtonControl", "Paste", "Paste", g1, 5, ("invoke", "expand"), rect=(5, 70, 60, 120))
    add("ButtonControl", "Paste", "", sp, 6, ("invoke",), rect=(5, 70, 60, 100))
    add("MenuItemControl", "More Options", "Paste_Dropdown", sp, 6, ("expand",), rect=(5, 100, 60, 120))
    add("ButtonControl", "Cut", "Cut", g1, 5, ("invoke",), rect=(70, 70, 120, 90), accel="Ctrl+X", enabled=False)
    g2 = add("GroupControl", "Images", parent=top, depth=4, rect=(200, 60, 400, 160))
    add("MenuItemControl", "Pictures", "InsertPictures", g2, 5, ("expand",), rect=(210, 70, 270, 120))
    rec = add("ListControl", "Recent", parent=low, depth=3, rect=(500, 70, 900, 150))
    add("ListItemControl", "my_private_notes", "", rec, 4, ("invoke",), rect=(500, 70, 900, 90))
    return nodes


def run_at16() -> TestOutcome:
    """AT16: cartographer logic on a synthetic ribbon: groups assigned, split-button parts folded in, personal lists never recorded, expansion items = tree difference, map -> claims -> teacher"""
    import json as _json
    from core_organs.atlas import uimap as U, teach, common as C
    nodes = _fake_ribbon()

    class _Ex:                                                         # the cartographer only needs these from the explorer
        key, hwnd, run_id, pristine = "fakeapp", 0, "t", True
    ca = U.Cartographer.__new__(U.Cartographer)
    ca.ex = _Ex()
    strips = U.Cartographer.tab_strips(ca, nodes)
    strip, items = strips[0]
    ctrls = U.Cartographer.region_controls(ca, nodes, strip)
    names = {c["name"]: c for c in ctrls}
    # expansion diff: a popup menu appears in the tree after the click
    after = _fake_ribbon()
    from core_organs import fast_uia
    def add_after(ctype, name, parent, depth, pats, accel=""):
        n = fast_uia.Node()
        n.idx, n.parent, n.depth, n.ctype, n.name, n.aid, n.cls = len(after), parent, depth, ctype, name, "", ""
        n.rect, n.enabled, n.offscreen, n.help, n.accel, n.pats = (300, 300, 400, 320), True, False, "", accel, list(pats)
        n.expand_state, n.selected, n.toggle_state, n.el = -1, None, -1, None
        after.append(n)
        after[parent].children.append(n.idx)
    m_ = len(after)
    add_after("MenuControl", "Pictures", 0, 1, ())
    add_after("MenuItemControl", "This Device...", m_, 2, ("invoke",))
    add_after("MenuItemControl", "Online Pictures...", m_, 2, ("invoke",), "Ctrl+Shift+P")
    add_after("ListItemControl", "my_private_notes_2", m_, 2, ("invoke",))
    new = U.Cartographer._new_nodes(ca, nodes, after)
    got = U.Cartographer._read_items(ca, nodes, after, [])
    gnames = [i["name"] for i in got]
    # map -> claims -> teacher
    mp = {"app_key": "fakeapp", "surfaces": [{"id": "tab:Insert", "kind": "ribbon-tab", "name": "Insert", "groups": [{"name": "Images", "controls": [
        {"name": "Pictures", "aid": "InsertPictures", "kind": "dropdown", "pats": ["expand"], "accel": "", "enabled": True,
         "leads_to": {"type": "menu", "n_items": 2, "items": [{"name": "This Device...", "kind": "menuitem", "enabled": True,
                                                                 "leads_to": {"type": "dialog", "dialog": "Insert Picture", "fields": [{"name": "File name", "kind": "edit"}], "commit": "Open", "cancel": "Cancel"}},
                                                                {"name": "Online Pictures...", "kind": "menuitem", "enabled": True}]}},
        {"name": "Table", "aid": "InsertTable", "kind": "dropdown", "pats": ["expand"], "accel": "", "enabled": True, "leads_to": {"type": "gallery", "items": ["2x2 Table", "3x3 Table"], "n_items": 2}}]}]}]}
    store, dbp = _tmp_store()
    d = os.path.join(os.path.dirname(dbp), "uimap")
    os.makedirs(d, exist_ok=True)
    mf = os.path.join(d, "fakeapp.json")
    with open(mf, "w", encoding="utf-8") as fh:
        _json.dump(mp, fh)
    old_dir = C.ATLAS_DIR
    C.ATLAS_DIR = os.path.dirname(dbp)
    try:
        class _M:
            def upsert_command(self, *a, **k):
                self.n = getattr(self, "n", 0) + 1
        mm = _M()
        kn = U.to_knowledge("fakeapp", mp, store, mm, "t", mf)
        r = teach.howto("fakeapp", "insert a picture from my computer", use_model=False)
        r2 = teach.howto("fakeapp", "make a table", use_model=False)
        r3 = teach.howto("fakeapp", "teleport the moon", use_model=False)
    finally:
        C.ATLAS_DIR = old_dir
        _rm(dbp)
        try:
            os.remove(mf)
        except Exception:
            pass
    best = r.get("best") or {}
    return _verdict({"group assigned (Paste in Clipboard)": names.get("Paste", {}).get("group") == "Clipboard", "split button parts folded in (one Paste)": sum(1 for c in ctrls if c["name"] == "Paste") == 1,
                     "More Options part not a control": "More Options" not in names, "disabled state kept (Cut)": names.get("Cut", {}).get("enabled") is False and names["Cut"]["accel"] == "Ctrl+X",
                     "dropdown in its group (Pictures in Images)": names.get("Pictures", {}).get("group") == "Images", "quick-access / tab strip not in the ribbon region": "Save" not in names and "Home" not in names,
                     "personal list (Recent) never recorded": "my_private_notes" not in names, "expansion = tree difference": {"This Device...", "Online Pictures..."} <= set(gnames),
                     "shortcut read from the item": any(i["name"] == "Online Pictures..." and i["accel"] == "Ctrl+Shift+P" for i in got),
                     "claims + commands written": kn["claims"] >= 2 and kn["commands"] >= 4, "teacher: route to the control": "Pictures" in (best.get("text") or "") and "Images" in (best.get("text") or ""),
                     "teacher: items + dialog + fields in the outcome": all(x in (best.get("outcome") or "") for x in ("This Device", "Insert Picture", "File name")),
                     "teacher: synonym (picture ~ image) and gallery": "Table" in ((r2.get("best") or {}).get("text") or ""), "teacher: honest non-answer": not r3.get("ok")},
                    metrics={"controls": len(ctrls), "items": len(got), "claims": kn["claims"]})


OFFLINE = [("AT1", run_at1), ("AT2", run_at2), ("AT3", run_at3), ("AT4", run_at4), ("AT5", run_at5), ("AT6", run_at6), ("AT7", run_at7), ("AT8", run_at8), ("AT9", run_at9), ("AT10", run_at10),
           ("AT11", run_at11), ("AT12", run_at12), ("AT13", run_at13), ("AT14", run_at14), ("AT15", run_at15), ("AT16", run_at16)]


# ======================================================================================================= live (fixture)

def run_live() -> Dict[str, TestOutcome]:
    """AL1-AL6 against the Atlas fixture (one launch, parked, invisible). Ground truth: the fixture's state label and truth file."""
    out: Dict[str, TestOutcome] = {}
    from core_organs.atlas.fixture import harness as H, build
    from core_organs.atlas import common as C, gestures as G, explorer as X, scanner as SC, coverage as COV, planner, evolve
    from core_organs import background_window as bw
    from core_organs import organ_48_app_behavior_model as bm
    if not build.build()["ok"]:
        return {"AL": TestOutcome(False, "fixture could not be built (csc missing)", env_blocked=True)}
    truth = build.truth()
    tf = os.path.join(tempfile.gettempdir(), "atlas_truth_" + uuid.uuid4().hex[:6] + ".json")
    json.dump(truth, open(tf, "w"))
    dbp = os.path.join(tempfile.gettempdir(), "atlas_live_" + uuid.uuid4().hex[:6] + ".db")
    model = bm.BehaviorModel(dbp)
    store = C.AtlasStore(dbp)
    fx = H.launch()
    hwnd = fx["hwnd"]
    key = "atlas fixture"
    try:
        # ---- AL1: gesture atlas accuracy vs the program's own counters
        with bw.BackgroundSession(hwnd) as bg:
            nodes, waited, fo = SC.ensure_tree(hwnd, bg)
            canvas = [r for r in G.discover_regions(hwnd, nodes) if r.kind == "canvas"]
            gp = G.GestureProber(hwnd, key, store=store, run_id="al1", budget_s=70, pristine=True)
            res = {}
            if canvas:
                for g in gp.probe_region(canvas[0], max_s=65):
                    res.setdefault(g.gesture, g)
            want = {"wheel": "zoom", "drag-middle": "pan", "drag-right": "rotate", "click-right": "opens_menu", "hold": "opens_menu", "drag-left": "rubber_band", "double-click": "local_change", "hover": "no_effect"}
            right = {k: (res[k].effect_class == v) for k, v in want.items() if k in res}
            state = H.read_state(hwnd)
            rev = [g for g in res.values() if g.reversible]
            out["AL1"] = _verdict({"a canvas region was discovered": bool(canvas), f"gesture effects match ground truth ({sum(right.values())}/{len(want)})": len(right) == len(want) and all(right.values()),
                                   "every probed gesture was delivered": all(g.delivered for g in res.values()), "view restored (zoom=1.00 within backlash)": abs(state.get("zoom", 0) - 1.0) < 0.02,
                                   "view gestures reversible": sum(1 for k in ("wheel", "drag-middle", "drag-right") if k in res and res[k].reversible) >= 2,
                                   "app counters agree: ctx menu + hold + band": state.get("ctx", 0) >= 1 and state.get("hold", 0) >= 1 and state.get("bands", 0) >= 1},
                                  extra=f"effects={ {k: v.effect_class for k, v in res.items()} }", metrics={"gestures": len(res), "seconds": round(gp.t0 and (time.time() - gp.t0), 1)})
        # ---- AL2: explorer coverage vs the truth file
        with bw.BackgroundSession(hwnd) as bg:
            SC.ensure_tree(hwnd, bg)
            ex = X.Explorer(hwnd, "Atlas Fixture", key, model, store=store, pristine=True, budget_s=100, run_id="al2")
            t0 = time.time()
            st = ex.run()
            t_x = time.time() - t0
            oc = COV.oracle_coverage(model, key, COV.TruthFileOracle(tf))
            rec = COV.independent_recall(model, key, hwnd)
            wiz = ex.seen_dialogs.get("Import Wizard", {})
            pref = ex.seen_dialogs.get("Preferences", {})
            out["AL2"] = _verdict({f"ground-truth coverage >= 95% ({oc['coverage']})": (oc["coverage"] or 0) >= 0.95, "every unwind verified (no failures)": st["unwind_failures"] == 0,
                                   "wizard followed (>=2 pages after the first)": bool(wiz.get("wizard")) and wiz.get("pages", 0) >= 2, "master/detail dialog read (3 pages)": bool(pref.get("master_detail")) and pref.get("pages", 0) >= 3,
                                   "menus read (4 menus, >=14 items)": st["menus"] >= 4 and st["menu_items"] >= 14, "app left as found": bool(st["left_as_found"]),
                                   "commit buttons never pressed (no prefs/wizard/export counters)": H.read_state(hwnd).get("wiz", 0) == 0 and H.read_state(hwnd).get("prefs", 0) == 0 and H.read_state(hwnd).get("exp", 0) == 0,
                                   f"independent UIA recall >= 80% ({rec['recall']})": (rec["recall"] or 0) >= 0.80, "dialogs learned (>=6)": st["dialogs"] >= 6},
                                  extra=f"missing={oc['missing']}", metrics={"coverage": oc["coverage"], "explore_s": round(t_x, 1), "dialogs": st["dialogs"], "commands": st["commands"]})
        # ---- AL3: plan from learned knowledge and EXECUTE it; verify by the app's own state
        def state_now():
            with bw.BackgroundSession(hwnd) as bgs:
                SC.ensure_tree(hwnd, bgs)
                return H.read_state(hwnd)
        pl = planner.plan(key, "zoom in, then reset view", store, model, use_model=False)
        z0 = state_now().get("zoom", 0)
        ex_res = planner.execute(pl, hwnd, dry_run=False, allow_destructive=True, log=lambda s: None)
        z1 = state_now().get("zoom", 0)
        refused = planner.execute(pl, hwnd, dry_run=False, allow_destructive=False, log=lambda s: None)["steps"][1]["status"] if len(pl["steps"]) > 1 else ""
        steps = ex_res["steps"]
        out["AL3"] = _verdict({"both sub-goals grounded in learned commands": pl["grounded"] == 2, "baseline zoom 1.00": abs(z0 - 1.0) < 0.02,
                               "'zoom in' + 'reset view' executed: the app is back at zoom 1.00": abs(z1 - 1.0) < 0.02 and all(s.get("delivered") for s in steps),
                               "each step verified by a before/after read": all("structure_changed" in s for s in steps if s.get("delivered")),
                               "destructive-flagged step REFUSED without permission": "refused" in refused},
                              extra=f"zoom {z0:.2f}->{z1:.2f}; steps={[ (s.get('status'), s.get('how')) for s in steps]}")
        # ---- AL4: input channel facts
        ch = SC.Atlas(store=store, model=model)._channels(key, list(gp.results), True, {}, "al4")
        out["AL4"] = _verdict({"posted pointer measured EFFECTIVE on this app": ch["posted_mouse"] == "effective", "claim stored with evidence": any(c["kind"] == "input.channel" and c["evidence"] for c in store.claims(key))},
                              extra=str(ch))
    finally:
        H.close(fx)
        try:
            os.remove(tf)
        except Exception:
            pass
        store.close()
        _rm(dbp)
    return out


def main(live: bool = False) -> int:
    rows: List[tuple] = []
    for tid, fn in OFFLINE:
        t0 = time.time()
        try:
            o = fn()
        except Exception as exc:
            import traceback
            o = TestOutcome(False, f"EXCEPTION {type(exc).__name__}: {str(exc)[:200]} :: {traceback.format_exc()[-300:]}")
        rows.append((tid, o, time.time() - t0))
    if live:
        t0 = time.time()
        try:
            for tid, o in run_live().items():
                rows.append((tid, o, time.time() - t0))
        except Exception as exc:
            import traceback
            rows.append(("AL", TestOutcome(False, f"EXCEPTION {type(exc).__name__}: {str(exc)[:200]} :: {traceback.format_exc()[-400:]}"), time.time() - t0))
    npass = nfail = nenv = 0
    for tid, o, dt in rows:
        tag = "ENV-BLOCKED" if o.env_blocked else ("PASS" if o.passed else "FAIL")
        npass += tag == "PASS"
        nfail += tag == "FAIL"
        nenv += tag == "ENV-BLOCKED"
        print(f"[{tag:11s}] {tid:5s} {dt*1000:8.0f} ms  {o.evidence[:520]}")
        if o.metrics:
            print(f"{'':20s}metrics: {o.metrics}")
    print(f"\n{npass} passed, {nfail} failed, {nenv} env-blocked of {len(rows)}")
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(live="--live" in sys.argv))
