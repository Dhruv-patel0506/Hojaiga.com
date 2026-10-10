"""The pointer matrix: every verb x every route x every lab target. Prints what was RECEIVED (the target's own event log) and whether the person's cursor moved.
   python -m core_organs.professor.lab.lab_matrix [winforms wpf] [--routes posted,shim,touch]"""
import os, sys, time, tempfile, json, ctypes
os.environ.setdefault("HOJAIGA_PROF_DIR", os.path.join(tempfile.gettempdir(), "hojaiga_prof_lab"))
sys.path.insert(0, r"D:\new_automation"); sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.professor import pointer as PT
from core_organs.professor.lab.labkit import Lab, CursorWatch, client_origin


class Fx:
    allowed = True
    owned = True
    def why_not(self): return ""


def summarize(ev):
    k = {}
    for e in ev:
        key = e["kind"].split(":")[0] + (":" + (e.get("btn") or e["kind"].split(":")[-1]) if e["kind"].split(":")[0] in ("down", "up") else "")
        k[key] = k.get(key, 0) + 1
    return k


def checks(verb, ev, extra=None):
    ks = summarize(ev)
    has = lambda p: any(key.startswith(p) for key in ks)
    if verb == "hover": return ks.get("move", 0) >= 2
    if verb == "click-left": return "down:Left" in ks and "up:Left" in ks or "down:canvas" in ks
    if verb == "click-right": return any(k.startswith("down") and "Right" in k for k in ks)
    if verb == "click-middle": return any(k.startswith("down") and "Middle" in k for k in ks)
    if verb == "double": return ks.get("dblclick", 0) >= 1 or sum(v for k, v in ks.items() if k.startswith("down")) >= 2
    if verb == "drag": return ks.get("move", 0) >= 8 and has("down") and has("up")
    if verb == "wheel": return ks.get("wheel", 0) >= 1
    if verb == "wheel-mod": return any("Control" in e.get("mods", "") or "Shift" in e.get("mods", "") for e in ev if e["kind"].startswith("wheel") or e["kind"].startswith("down"))
    if verb == "drop": return any(e["kind"] == "drop" for e in ev)
    if verb == "flick": return ks.get("move", 0) >= 4 and has("up")
    return False


def run(name, routes):
    lab = Lab(name)
    app_key = "lab_" + name
    l, t, r, b = lab.rect()
    out = {}
    for route in routes:
        vp = PT.VirtualPointer(lab.hwnd, app_key, Fx(), only=[route])
        cx, cy = client_origin(lab.hwnd)[0] + 200, client_origin(lab.hwnd)[1] + 160
        tests = [
            ("hover", lambda: vp.hover(cx, cy)),
            ("click-left", lambda: vp.click(cx, cy)),
            ("click-right", lambda: vp.right_click(cx, cy)),
            ("click-middle", lambda: vp.middle_click(cx, cy)),
            ("double", lambda: vp.double_click(cx, cy)),
            ("drag", lambda: vp.drag((cx, cy), (cx + 250, cy + 120))),
            ("flick", lambda: vp.flick(cx, cy, "right", 200)),
            ("wheel", lambda: vp.wheel(cx, cy, 2)),
            ("wheel-mod", lambda: vp.wheel(cx, cy, 1, mods=("ctrl",))),
            ("drop", lambda: vp.drag_drop((client_origin(lab.hwnd)[0] + 80, client_origin(lab.hwnd)[1] + 40), (client_origin(lab.hwnd)[0] + 750, client_origin(lab.hwnd)[1] + 200))),
        ]
        res = {}
        for verb, fn in tests:
            m = lab.mark()
            with CursorWatch() as cw:
                try:
                    pr = fn()
                except Exception as exc:
                    pr = None
                    res[verb] = f"ERR {type(exc).__name__}: {exc}"
                    continue
            time.sleep(0.25)
            ev = lab.since(m)
            ok = checks(verb, ev)
            res[verb] = ("OK" if ok else "--") + ("" if not cw.moved else f" CURSOR-MOVED({cw.max_dev}px{', but real input arrived (the person)' if cw.person_moved_it else ', NO real input: the route moved it'})") + ("" if pr and pr.tried and (pr.ok or True) else "") + (f" [{(pr.tried[-1] if pr.tried else pr.note)[:90]}]" if pr and not ok else "")
        vp.close()
        out[route] = res
    lab.close()
    return out


if __name__ == "__main__":
    labs = [a for a in sys.argv[1:] if not a.startswith("--")] or ["winforms", "wpf"]
    routes = ["posted", "shim"]
    for a in sys.argv[1:]:
        if a.startswith("--routes="):
            routes = a.split("=")[1].split(",")
    for lab in labs:
        res = run(lab, routes)
        print("=====", lab)
        for route, r in res.items():
            print("  route", route)
            for verb, v in r.items():
                print(f"    {verb:13s} {v}")
