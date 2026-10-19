"""
flows -- jobs that cross applications. Each flow is a few single-app steps whose OUTPUT feeds the next one; every step saves pictures and the flow passes only when the last application really holds what the first one found.

    web_to_word      find a fact sheet on a site (browser, CDP loop) -> the brain turns it into a LinkedIn-style post body (a DRAFT: nothing is posted) -> the draft is typed into Word
    web_to_excel     read the key facts table of a page -> typed cell by cell into Excel (UI Automation)
    blender_to_note  build an object in Blender (scripting route, geometry critic) -> its measured report is typed into Notepad

    python -m core_organs.flows --only web_to_word
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, os.path.join("D:" + os.sep, "new_automation", "All codes"))

from core_organs import gauntlet as G  # noqa: E402

FACTS_JS = ("(function(){var ps=Array.from(document.querySelectorAll('#mw-content-text p')).map(function(p){return (p.innerText||'').replace(/\\[[0-9]+\\]/g,'').trim()}).filter(function(t){return t.length>80});"
            "return ps.slice(0,2).join(' ')})()")
INFOBOX_JS = ("(function(){var rows=document.querySelectorAll('table.infobox tr');var out=[];rows.forEach(function(r){var h=r.querySelector('th'),d=r.querySelector('td');"
              "if(h&&d){var k=(h.innerText||'').trim(),v=(d.innerText||'').replace(/\\[[0-9]+\\]/g,'').trim().split('\\n')[0];if(k&&v&&k.length<30&&v.length<60)out.push([k,v])}});return out.slice(0,6)})()")


def clean(text: str, n: int = 700) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(r"[\"“”]", "", t)
    return t[:n]


def web_facts(section: Any, topic: str, host: str, log: Any) -> Dict[str, Any]:
    """The browser finds the page (the agent's own search-and-open loop; a direct address is used only if it does not get there, and that is reported)."""
    from core_organs import web_delegate as WD
    out: Dict[str, Any] = {"agent": "", "direct_fallback": False, "facts": "", "table": [], "url": "", "before": None, "after": None}
    with WD.OwnedBrowser(visible=True) as br:
        drv = br.driver()
        drv.navigate("https://" + host)
        time.sleep(2.5)
        with contextlib.suppress(Exception):
            out["before"] = drv.screenshot().convert("RGB")
        agent = WD.WebAgent(section.engine.get_brain(), drv, log=log, confirm=None, max_steps=8, growth=section.growth())
        rep = agent.run(f"search for {topic} and open the article about the person", "")
        out["agent"] = rep.get("status", "")
        slug = topic.replace(" ", "_")
        if not drv.url().split("?")[0].rstrip("/").endswith(slug):
            out["direct_fallback"] = True
            drv.navigate(f"https://{host}/wiki/{slug}")
            time.sleep(3.0)
        out["url"] = drv.url()
        for key, js in (("facts", FACTS_JS), ("table", INFOBOX_JS)):
            with contextlib.suppress(Exception):
                out[key] = drv.p.call("Runtime.evaluate", {"expression": js, "returnByValue": True}).get("result", {}).get("value") or out[key]
        with contextlib.suppress(Exception):
            out["after"] = drv.screenshot().convert("RGB")
    return out


def flow_web_to_word(section: Any, log: Any) -> Dict[str, Any]:
    t0 = time.time()
    topic, host = "Ada Lovelace", "en.wikipedia.org"
    w = web_facts(section, topic, host, log)
    brain = section.engine.get_brain()
    post = ""
    if w["facts"]:
        prompt = " | ".join([f"Facts (from {host}, use only these): {clean(w['facts'], 900)}",
                             "Write a LinkedIn post of at most 80 words about this person: one hook line, then two short sentences, then three hashtags. Do not add facts that are not above. Plain text, no quotes, one paragraph.",
                             'Reply JSON {"post": "..."}'])
        obj, _m = brain.json(prompt, "You write short, honest professional posts. JSON only.", max_tokens=300)
        post = clean(str((obj or {}).get("post", "")), 600)
    typed_ok = False
    word_rep: Dict[str, Any] = {}
    if post:
        section.proof_dir = os.path.join(G.GALLERY, "raw", "flow_web_to_word")
        word_rep = section.handle(f"in Word type the words {post}", app="Word", mode="delegate", learn="auto", recall=True, live=False, vlm=True)
        section.proof_dir = ""
        v = word_rep.get("verification") or {}
        key_words = [x for x in re.findall(r"[A-Za-z]{6,}", post)][:6]
        seen = (word_rep.get("final_text") or "").lower()
        typed_ok = v.get("done") == v.get("total") and v.get("total", 0) >= 1 and sum(1 for k in key_words if k.lower() in seen) >= max(2, len(key_words) // 2)
    from PIL import Image
    pr = word_rep.get("proof") or {}
    wa = Image.open(pr["after"]).convert("RGB") if pr.get("after") and os.path.isfile(pr["after"]) else None
    verdict = f"web found {len(clean(w['facts']))} chars ({'agent' if not w['direct_fallback'] else 'direct address after the agent did not land'}), post {len(post.split())} words drafted (NOT posted), typed into Word: {typed_ok}"
    ok = bool(w["facts"]) and bool(post) and typed_ok
    out_png = os.path.join(G.GALLERY, "before_after_flow_web_to_word.png")
    G.compose_before_after(w["after"], wa, "Flow: find it online -> customise as a LinkedIn post draft -> Word (not posted)", verdict, ok, out_png, note=("draft: " + post[:150]))
    return {"case": "flow_web_to_word", "kind": "flow", "ok": ok, "verdict": verdict, "wall_s": round(time.time() - t0, 1), "png": out_png, "post": post, "web": {k: w[k] for k in ("agent", "direct_fallback", "url")}}


def excel_sheet_of(hwnd: int) -> Any:
    """The active worksheet of the Excel instance that owns this top-level window (AccessibleObjectFromWindow on its EXCEL7 pane, OBJID_NATIVEOM): one specific window, not 'whatever Excel is running'."""
    import ctypes
    import pythoncom
    import win32com.client
    import win32gui
    pythoncom.CoInitialize()
    found: List[int] = []

    def cb(h: int, _l: Any) -> bool:
        if win32gui.GetClassName(h) == "EXCEL7":
            found.append(h)
        return True
    win32gui.EnumChildWindows(hwnd, cb, None)
    if not found:
        return None
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
    iid = GUID(0x00020400, 0, 0, (ctypes.c_ubyte * 8)(0xC0, 0, 0, 0, 0, 0, 0, 0x46))                 # IID_IDispatch
    ptr = ctypes.c_void_p()
    ctypes.oledll.oleacc.AccessibleObjectFromWindow(found[0], -16, ctypes.byref(iid), ctypes.byref(ptr))
    disp = pythoncom.ObjectFromAddress(ptr.value, pythoncom.IID_IDispatch) if hasattr(pythoncom, "ObjectFromAddress") else None
    win = win32com.client.Dispatch(disp) if disp is not None else None
    return win.Application.ActiveSheet if win is not None else None


def flow_web_to_excel(section: Any, log: Any) -> Dict[str, Any]:
    from core_organs import agent_executor as AE
    from core_organs.harvest import local_recorder as LR
    t0 = time.time()
    topic, host = "Ada Lovelace", "en.wikipedia.org"
    w = web_facts(section, topic, host, log)
    rows = [r for r in (w["table"] or []) if isinstance(r, list) and len(r) == 2][:5]
    LR.OwnedApp.READY_S = 25.0
    LR.OwnedApp.VISIBLE_FALLBACK = True
    import uiautomation as auto
    from PIL import Image
    before = after = None
    written = 0
    verdict = ""
    ok = False
    if rows:
        with LR.OwnedApp("Excel") as app:
            with contextlib.suppress(Exception):
                before = app.grab(popups=True)[0].convert("RGB")
            from core_organs import office_om as OM
            cells = {f"{col}{i}": text for i, (k, v) in enumerate(rows, 1) for col, text in (("A", k), ("B", v))}
            res_kb = OM.grid_type(app.hwnd, cells)                          # the keyboard route: Name Box -> characters to the grid -> Enter
            route = "keyboard (Name Box + typed characters + Enter)"
            if sum(res_kb.values()) < len(cells):                           # whatever did not stick is written through the sheet's object model, then read back
                res_om = OM.grid_write(app.hwnd, {a: t for a, t in cells.items() if not res_kb.get(a)})
                res_kb.update({a: v for a, v in res_om.items() if v})
                route += " + object model for the rest"
            written = sum(res_kb.values())
            time.sleep(1.0)
            with contextlib.suppress(Exception):
                after = app.grab(popups=True)[0].convert("RGB")
            from core_organs.app_teaching_automation import read_back

            class _S:                                               # read_back wants a session with .app
                pass
            s = _S()
            s.app = app
            seen = read_back(s).lower()
            hits = sum(1 for k, v in rows if k.lower()[:6] in seen or v.lower()[:6] in seen)
            ok = written == len(rows) * 2
            verdict = f"{len(rows)} fact rows read from {host}; {written}/{len(rows) * 2} cells hold the value when read back through Excel's object model via the {route} (screen OCR read {hits}/{len(rows)} rows)"
    else:
        verdict = "no facts table could be read from the page"
    verdict += " | page reached by " + ("the web agent" if not w["direct_fallback"] else "a direct address (the agent did not land on it)")
    out_png = os.path.join(G.GALLERY, "before_after_flow_web_to_excel.png")
    G.compose_before_after(w["after"], after, "Flow: facts table on a site -> Excel cells", verdict, ok, out_png, note=("rows: " + "; ".join(f"{a}={b}" for a, b in rows)[:180]))
    return {"case": "flow_web_to_excel", "kind": "flow", "ok": ok, "verdict": verdict, "wall_s": round(time.time() - t0, 1), "png": out_png, "rows": rows}


FLOWS = {"web_to_word": flow_web_to_word, "web_to_excel": flow_web_to_excel}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=[])
    a = ap.parse_args(argv)
    from core_organs import app_teaching_automation as ATA
    section = ATA.AppTeachingAutomationSection(log=lambda s: print(s, flush=True))
    os.makedirs(os.path.join(G.GALLERY, "results"), exist_ok=True)
    res = []
    for name, fn in FLOWS.items():
        if a.only and name not in a.only:
            continue
        print(f"\n##### flow_{name}", flush=True)
        try:
            r = fn(section, print)
        except Exception as exc:
            r = {"case": "flow_" + name, "kind": "flow", "ok": False, "verdict": f"crash: {type(exc).__name__}: {exc}"[:200]}
        json.dump(r, open(os.path.join(G.GALLERY, "results", "flow_" + name + ".json"), "w", encoding="utf-8"), indent=1, default=str)
        print(f"##### flow_{name}: {'PASS' if r.get('ok') else 'FAIL'} - {r.get('verdict')}", flush=True)
        res.append(r)
    print(json.dumps({"passed": sum(1 for r in res if r.get("ok")), "total": len(res)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
