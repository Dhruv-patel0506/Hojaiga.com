"""Drive a REAL Electron/CEF app through organ_24's Chromium-CDP provider: launch it with a debugging port on an
isolated profile, enumerate the page, act on one of ITS controls with zero physical input, and verify through the
app's own rendered pixels (OCR) -- a channel separate from the one that wrote.

Usage: python scratch/drive_electron.py [name-substring]
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs import cef_devtools as CEF                                      # noqa: E402
from core_organs import organ_24_dap as dap                                      # noqa: E402

MARKER = "hjprobe7"
PNG_MAGIC = bytes([0x89, 0x50, 0x4E, 0x47])
want = (sys.argv[1] if len(sys.argv) > 1 else "").lower()


def _dump(png: bytes, name: str) -> None:
    """Keep the page's own pixels so a human eye can check what the app was actually showing."""
    if not png:
        return
    path = os.path.join(r"D:\new_automation", f"_cef_page_{name.split()[0].lower()}.png")
    with open(path, "wb") as fh:
        fh.write(png)
    print(f"  page pixels written -> {path}")


def DevErr():
    """Why the endpoint refused us, in the route's own words (never a silent None)."""
    return getattr(CEF.DevTools, "last_attach_error", "") or "no attach attempt recorded"


def ocr_words(png: bytes):
    """Read the app's OWN rendered pixels - a channel separate from the one that wrote."""
    if not png:
        return []
    from PIL import Image
    import pytesseract
    im = Image.open(io.BytesIO(png)).convert("RGB")
    k = 2 if max(im.size) < 900 else 1
    big = im.resize((im.width * k, im.height * k))
    return [w for w in pytesseract.image_to_data(big, output_type=pytesseract.Output.DICT).get("text", []) if (w or "").strip()]


apps = CEF.installed_chromium_apps()
if want:
    apps = [a for a in apps if want in a["name"].lower()]
print(f"candidates: {[(a['name']) for a in apps][:8]}")

prov = dap.ChromiumDevToolsProvider()
reg = dap.ProviderRegistry()
workspace = tempfile.mkdtemp(prefix="hj_cef_ws_")
notebook = os.path.join(workspace, "notes.txt")
open(notebook, "w", encoding="utf-8").write("first line\n")

for a in apps[:4]:
    exe = a["exe"]
    print(f"\n=== {a['name']} :: {exe}")
    profile = tempfile.mkdtemp(prefix="hj_cef_prof_")
    pid, port, prof = CEF.launch_with_devtools(
        exe, ["--no-first-run", "--disable-extensions", "--disable-sync", workspace])
    try:
        if not pid:
            print("  launch refused")
            continue
        t0 = time.time()
        hwnd = CEF.wait_for_window(pid, timeout=30.0)
        print(f"  pid={pid} port={port} window hwnd={hex(hwnd) if hwnd else 'NONE'} after {time.time()-t0:.1f}s")
        if not hwnd:
            continue
        print(f"  class={dap.Win32Provider().build_node(hwnd, None).class_name!r} "
              f"title={dap.Win32Provider().read_value(prov.build_node(hwnd, None))[:60]!r}")
        print(f"  registry routes this hwnd to: {reg.resolve(hwnd, dap.WIN32.get_class_name(hwnd)).name}")
        dt = prov.session(hwnd)
        print(f"  attach: {'OK' if dt else 'NONE ' + DevErr()}")
        if not dt:
            continue
        els = CEF.wait_for_elements(dt, timeout=45.0, min_count=3)
        nodes = prov.page_nodes(hwnd)
        print(f"  page: title={els.get('title','')[:40]!r} url={str(els.get('url',''))[:60]} "
              f"viewport={els.get('vw')}x{els.get('vh')} elements={len(nodes)} settled_after={els.get('settled_s')}s")
        for n in nodes[:12]:
            print(f"     {n.control_type:<12} name={n.name[:28]!r:<30} id={n.automation_id[:18]!r:<20} "
                  f"box={n.css_center[0]:.0f},{n.css_center[1]:.0f} dom={n.dom_index}")
        editables = [n for n in nodes if "input" in (n.control_type or "").lower()
                     or "textarea" in (n.control_type or "").lower()
                     or (n.control_type or "").lower() in ("textbox", "searchbox", "combobox")]
        # Rank by what the element actually COVERS on screen: an app keeps hidden helper inputs
        # (screen-reader bridges) in its DOM, and text typed into one is real but invisible - so it
        # could never be verified through the pixels. Biggest first is the field a person would use.
        areas = {e.get("idx", -1): float(e.get("w", 0)) * float(e.get("h", 0)) for e in (els.get("elements") or [])}
        editables.sort(key=lambda n: -areas.get(n.dom_index, 0.0))
        print(f"  editable nodes: {len(editables)} "
              f"areas={[int(areas.get(n.dom_index, 0)) for n in editables[:5]]}")

        def _try(cands):
            for cand in cands[:3]:
                print(f"  typing {MARKER!r} into dom#{cand.dom_index} "
                      f"({cand.control_type} {cand.name[:24]!r}, area={int(areas.get(cand.dom_index, 0))}px)")
                t1 = time.time()
                ok = prov.set_value(cand, MARKER)
                print(f"  set_value -> {ok} in {time.time()-t1:.1f}s; "
                      f"provider read back: {prov.read_value(cand)[:40]!r}")
                if ok:
                    return cand, True
            return None, False

        target = None
        cands, landed = editables, False
        if cands:
            target, landed = _try(cands)
        if target is None:
            # nothing typeable took the text: a modal is probably in front of the app's own fields.
            # Escape is the generic way to step back (the popup engine's first rung for the same reason),
            # then ask the app for a field the way a person does.
            for step in (("escape",), ("ctrl+shift+p", "ctrl+k", "ctrl+p", "ctrl+f")):
                for chord in step:
                    if not CEF.shortcut(dt, chord):
                        continue
                    time.sleep(1.4)
                    els = CEF.page_elements(dt)
                    areas.update({e.get("idx", -1): float(e.get("w", 0)) * float(e.get("h", 0))
                                  for e in (els.get("elements") or [])})
                    nodes = prov.page_nodes(hwnd)
                    e2 = [n for n in nodes if "input" in (n.control_type or "").lower()
                          or "textarea" in (n.control_type or "").lower()
                          or (n.control_type or "").lower() in ("textbox", "searchbox", "combobox")]
                    e2.sort(key=lambda n: -areas.get(n.dom_index, 0.0))
                    print(f"  after {chord}: elements={len(nodes)} editables={len(e2)} "
                          f"areas={[int(areas.get(n.dom_index, 0)) for n in e2[:5]]}")
                    if e2:
                        target, landed = _try(e2)
                        if target is not None:
                            break
                if target is not None:
                    break
            if target is None:
                print("  no typeable element found on this page")
                for n in nodes[:20]:
                    print(f"     ~ {n.control_type:<12} {n.name[:40]!r} id={n.automation_id[:20]!r}")
                _dump(prov.page_screenshot(hwnd), a["name"])
                continue
        png = prov.page_screenshot(hwnd)
        print(f"  page pixels: {len(png)} bytes png={'yes' if png[:4] == PNG_MAGIC else 'NO'}")
        _dump(png, a["name"])
        words = ocr_words(png)
        print(f"  OCR words={len(words)} marker_in_pixels={'YES' if MARKER in ' '.join(words) else 'no'} "
              f"sample={' '.join(words[:18])!r}")
        print(f"  VERDICT {a['name']}: provider-write={landed} independent-pixel-proof="
              f"{'YES' if MARKER in ' '.join(words) else 'no'}")
        CEF.press_key(dt, "escape")
        break
    finally:
        prov.close_all()
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        except Exception:
            pass
        time.sleep(1.0)
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(prof, ignore_errors=True)

shutil.rmtree(workspace, ignore_errors=True)
print("\ndone")
