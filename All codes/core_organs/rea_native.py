"""
rea_native -- REA (+ Ghidra) on INSTALLED WINDOWS PROGRAMS, then straight into the RAG. Static: the program is never run.

    python -m core_organs.rea_native list                          the installed programs found (main exe, size)
    python -m core_organs.rea_native app "<exe>" [--ghidra] [--no-write] [--timeout-s N]
    python -m core_organs.rea_native all [--ghidra] [--max-mb 40] [--hours H] [--no-write]     every installed program, ledger-skipped when done

What one program yields (each part says where it came from):
  identity      file version / product name (PE version resource), machine, GUI or console, .NET or native         pe_resources
  imports       REA inspect-pe-imports: the DLLs and API functions it calls  ->  UI toolkit (Qt / MFC / WPF / WinForms / Delphi / Electron / Win32 ...) and capabilities (network, crypto, registry, clipboard, drag-and-drop, audio / video, printing, hooks)
  commands      the menu tree + accelerator table + status-bar help that classic programs ship as data   pe_resources  (menu path, chord, help)
  strings       Ghidra (through REA `search`): every string the program carries -> shortcuts ("Save\\tCtrl+S"), command-line flags, URLs, file types, registry keys, UI words
Filing: one document (what it is made of, how to drive it), lexicon commands and unverified hotkey LEADS (trust 'catalog' for a program's own declarations, source 'rea_static'), nothing is ever marked verified here.
The toolkit tells the executor how much to trust the accessibility tree (a Qt / Delphi / DirectX window exposes little; WinForms / WPF / MFC expose most): it is written in the document and returned in `how_to_drive`.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Sequence

from core_organs import rea_bridge as RB

LEDGER = os.path.join(r"D:\new_automation\reports", "rea_pipeline", "native_ledger.jsonl")
GHIDRA_STARTUP_MS = 1500000                                  # REA's own default is 330 s: a 2 MB Delphi program did not finish importing in that (measured); a loaded machine needs more

TOOLKITS = [  # (DLL name fragment, toolkit, how much of the program the accessibility tree shows)
    ("microsoft.ui.xaml", "WinUI 3 (XAML)", "good tree, posted keys reach only Alt accelerators"), ("windows.ui.xaml", "UWP XAML", "good tree, packaged app: keep it on screen"),
    ("presentationframework", "WPF", "good tree"), ("system.windows.forms", "WinForms", "good tree"), ("mfc", "MFC", "good tree + menu / accelerator resources"),
    ("qt5core", "Qt 5", "thin tree: read it with vision, keys work"), ("qt6core", "Qt 6", "thin tree: read it with vision, keys work"), ("wxmsw", "wxWidgets", "fair tree"),
    ("vcl", "Delphi VCL", "thin tree: controls are custom-drawn"), ("rtl", "Delphi RTL", "thin tree"), ("gtk-3", "GTK", "poor tree"), ("sdl2", "SDL game / media", "no tree: vision only"),
    ("d3d11", "DirectX", "no tree for the drawing surface"), ("d3d9", "DirectX 9", "no tree for the drawing surface"), ("opengl32", "OpenGL", "no tree for the drawing surface"),
    ("vulkan", "Vulkan", "no tree for the drawing surface"), ("electron", "Electron", "Chromium: use the DOM, not the tree"), ("chrome_elf", "Chromium", "Chromium: use the DOM, not the tree"),
    ("mscoree", ".NET (CLR)", "managed: tree depends on the UI library"), ("jvm.dll", "Java", "poor tree"), ("python3", "embedded Python", "depends on the UI library"),
]
CAPABILITIES = [  # (label, regex over 'dll!Function' names)
    ("network", r"ws2_32|wininet|winhttp|urlmon|wsock32|WSAStartup|InternetOpen|WinHttpOpen"), ("crypto / certificates", r"crypt32|bcrypt|ncrypt|CryptAcquire|CertOpen"),
    ("registry", r"RegOpenKey|RegSetValue|RegQueryValue"), ("clipboard", r"OpenClipboard|GetClipboardData|SetClipboardData"), ("drag and drop", r"DragAcceptFiles|DoDragDrop|RegisterDragDrop|DragQueryFile"),
    ("audio / video", r"winmm|dsound|xaudio|mfplat|dxva|waveOut|mciSendString|ole32!CoCreate.*(Media|Direct)"), ("printing", r"winspool|StartDoc|PrintDlg|PrintDlgEx"),
    ("global keyboard / mouse hooks", r"SetWindowsHookEx|RegisterHotKey|GetAsyncKeyState|GetRawInputData"), ("screen capture", r"BitBlt|PrintWindow|GetDC|dxgi|DuplicateOutput|CaptureScreen"),
    ("process / service control", r"CreateProcess|ShellExecute|OpenSCManager|CreateService|TerminateProcess"), ("file dialogs / shell", r"GetOpenFileName|GetSaveFileName|SHBrowseForFolder|IFileDialog"),
    ("USB / Bluetooth / devices", r"setupapi|hid\.dll|bthprops|BluetoothFind|SetupDi"), ("scripting / COM automation", r"oleaut32!|IDispatch|CoCreateInstance"),
]
SHORTCUT = re.compile(r"^(?P<label>[^\t\r\n]{2,48})\t(?P<chord>(?:Ctrl|Alt|Shift|Win)(?:\+(?:Ctrl|Alt|Shift|Win))*\+(?:[A-Z0-9]|F\d{1,2}|Del|Ins|Home|End|Enter|Esc|Tab|Space|PgUp|PgDn|Up|Down|Left|Right|\[|\]|,|\.|/))$")
CHORD_ONLY = re.compile(r"^(?:Ctrl|Alt|Shift)(?:\+(?:Ctrl|Alt|Shift))*\+(?:[A-Z0-9]|F\d{1,2})$")
CLI_FLAG = re.compile(r"^--?[A-Za-z][A-Za-z0-9\-_]{2,24}(?:=.*)?$|^/[A-Za-z]{2,12}$")
URL = re.compile(r"https?://[^\s\"'<>]{6,120}")
REGKEY = re.compile(r"^(?:HKEY_\w+|HKLM|HKCU|Software\\)[\\A-Za-z0-9 _.\-]{4,100}$")
FILETYPE = re.compile(r"(?:\*|\b[\w\-]{1,20})\.(?:json|xml|ini|cfg|conf|db|sqlite|log|txt|csv|png|jpg|jpeg|gif|bmp|ico|pdf|zip|7z|rar|mp3|mp4|wav|avi|mkv|docx|xlsx|pptx|exe|dll|bat|lnk|iso|vhd|pcap|cap|bin|hex|dat|cache)\b", re.I)
UI_WORD = re.compile(r"^[A-Z&][A-Za-z0-9&' /\-]{2,28}(?:\.\.\.)?$")


# ------------------------------------------------------------------------------------------------------------------ finding programs
def find_programs() -> List[Dict[str, Any]]:
    roots = [r"C:\Program Files", r"C:\Program Files (x86)", os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
    skip = ("unins", "update", "setup", "crash", "helper", "install", "uninst", "repair", "elevat", "notif")
    skip_dirs = ("vanguard", "defender", "antivirus", "security")                      # security / anti-cheat products: not analysed
    out: List[Dict[str, Any]] = []
    for r in roots:
        if not r or not os.path.isdir(r):
            continue
        for d in sorted(os.listdir(r)):
            base = os.path.join(r, d)
            if not os.path.isdir(base) or any(x in d.lower() for x in skip_dirs):
                continue
            exes = [(os.path.getsize(f), f) for f in glob.glob(os.path.join(base, "*.exe")) if not any(x in os.path.basename(f).lower() for x in skip)]
            if exes:
                size, f = max(exes)
                out.append({"name": d, "exe": f, "mb": round(size / 1e6, 1), "key": re.sub(r"[^a-z0-9]+", "_", d.lower()).strip("_")})
    seen, uniq = set(), []
    for p in out:
        if p["exe"].lower() not in seen:
            seen.add(p["exe"].lower())
            uniq.append(p)
    return sorted(uniq, key=lambda p: p["mb"])


# ------------------------------------------------------------------------------------------------------------------ the parts
def toolkit_of(dlls: Sequence[str], names: Sequence[str] = ()) -> Dict[str, str]:
    low = [d.lower() for d in dlls]
    hits = []
    for frag, kit, tree in TOOLKITS:
        if any(frag in d for d in low) or (frag in ("mscoree",) and any("_corexemain" in n.lower() for n in names)):
            hits.append((kit, tree))
    if not hits:
        return {"toolkit": "plain Win32", "tree": "tree reflects the standard controls it uses"}
    # the most specific UI library wins over a graphics API or runtime
    order = ["WinUI 3 (XAML)", "UWP XAML", "WPF", "WinForms", "Qt 6", "Qt 5", "MFC", "wxWidgets", "Delphi VCL", "GTK", "Electron", "Chromium", "SDL game / media", "Java", ".NET (CLR)", "DirectX", "DirectX 9", "OpenGL", "Vulkan", "Delphi RTL", "embedded Python"]
    hits.sort(key=lambda h: order.index(h[0]) if h[0] in order else 99)
    return {"toolkit": hits[0][0], "tree": hits[0][1], "also": ", ".join(h[0] for h in hits[1:4])}


def capabilities_of(pairs: Sequence[str]) -> List[str]:
    blob = "\n".join(pairs)
    return [lab for lab, rx in CAPABILITIES if re.search(rx, blob, re.I)]


def imports_digest(exe: str) -> Dict[str, Any]:
    r = RB.run("inspect-pe-imports", exe, timeout=240)
    nr = RB.nr_of(r)
    if not r["ok"] or not nr:
        return {"ok": False, "error": r["error"][:160]}
    dlls, pairs = [], []
    for grp in (nr.get("imports") or []) + (nr.get("delay_imports") or []):
        dlls.append(grp.get("name", ""))
        for f in grp.get("functions", []):
            pairs.append(f"{grp.get('name', '').lower()}!{f.get('name') or ''}")
    kit = toolkit_of(dlls, [p.split("!")[-1] for p in pairs])
    return {"ok": True, "dlls": len(dlls), "functions": len(pairs), "dll_names": sorted({d.lower() for d in dlls})[:40], "imphash": (nr.get("imphash") or {}).get("md5"), **kit, "capabilities": capabilities_of(pairs)}


def resources_digest(exe: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False}
    with contextlib.suppress(Exception):
        from core_organs import pe_resources as PR
        info = PR.pe_info(exe)
        res = PR.read_resources(exe)
        cmds = PR.commands_from_resources(res)
        ver = res.get("version") or {}
        out = {"ok": True, "machine": info.get("machine"), "subsystem": info.get("subsystem"), "dotnet": info.get("dotnet") or info.get("clr"), "version": {k: ver[k] for k in ("ProductName", "FileDescription", "FileVersion", "CompanyName") if ver.get(k)},
               "menus": len(res.get("menus", [])), "accelerators": len(res.get("accelerators", [])), "dialogs": len(res.get("dialogs", [])), "strings": len(res.get("strings", {})),
               "commands": [{"name": c["name"], "path": " > ".join(c.get("menu_path") or []), "chord": c.get("shortcut") or "", "help": (c.get("help") or "")[:90]} for c in cmds][:400]}
    return out


def classify_strings(strings: Sequence[str]) -> Dict[str, Any]:
    """What a program's own strings say about it (each class is a regular expression, nothing per program)."""
    shortcuts, chords, flags, urls, regs, files, words = [], [], [], [], [], [], []
    seen: set = set()
    for s in strings:
        s = (s or "").strip()
        if not s or s in seen or len(s) > 200:
            continue
        seen.add(s)
        m = SHORTCUT.match(s)
        if m:
            shortcuts.append({"label": re.sub(r"&", "", m.group("label")).strip(), "chord": m.group("chord")})
        elif CHORD_ONLY.match(s):
            chords.append(s)
        elif CLI_FLAG.match(s):
            flags.append(s)
        elif URL.search(s):
            urls.append(URL.search(s).group(0))
        elif REGKEY.match(s):
            regs.append(s)
        elif FILETYPE.search(s) and len(s) < 60:
            files.append(s)
        elif UI_WORD.match(s) and not re.search(r"[a-z]{2,}[A-Z]", s) and " " in s.strip() or (UI_WORD.match(s) and s.endswith("...")):
            words.append(s)
    uniq = lambda xs, n: list(dict.fromkeys(xs))[:n]
    return {"strings_seen": len(seen), "shortcuts": shortcuts[:150], "chords_without_label": uniq(chords, 40), "flags": uniq(flags, 60), "urls": uniq(urls, 40), "registry": uniq(regs, 30), "file_types": uniq(files, 40), "ui_words": uniq(words, 120)}


def ghidra_strings(exe: str, timeout_s: float = 1800) -> Dict[str, Any]:
    """ONE Ghidra run (REA `search` for any printable run of 4+ characters): its import+analysis costs minutes whatever is asked, so every string is taken at once and sorted here."""
    os.environ.setdefault("REA_GHIDRA_STARTUP_TIMEOUT_MS", str(GHIDRA_STARTUP_MS))
    r = RB.run("search", exe, "--pattern", r"[ -~\t]{4,}", "--mode", "regex", timeout=timeout_s)
    nr = RB.nr_of(r)
    if not r["ok"] or not isinstance(nr, list):
        return {"ok": False, "error": (r["error"] or "no result")[:200], "seconds": r["seconds"]}
    vals = [x.get("value", "") for x in nr if isinstance(x, dict)]
    return {"ok": True, "seconds": r["seconds"], **classify_strings(vals)}


def how_to_drive(dg: Dict[str, Any]) -> str:
    im, rs = dg.get("imports") or {}, dg.get("resources") or {}
    bits = []
    if im.get("ok"):
        bits.append(f"{im['toolkit']}: {im['tree']}")
    if rs.get("commands"):
        bits.append(f"{len(rs['commands'])} menu commands are declared in its resources, so each can be sent by command id without opening a menu")
    if "global keyboard / mouse hooks" in (im.get("capabilities") or []):
        bits.append("it installs keyboard / mouse hooks or hotkeys: keys the executor sends may be intercepted by the program")
    return "; ".join(bits)


# ------------------------------------------------------------------------------------------------------------------ what Ghidra is the wrong tool for
# A program's COM type library is its object model as data (Excel 24,827 members, Word 14,767, PowerPoint 6,711; ~0.02 s to read): exact for the installed version, no size cap.
# A Store (MSIX) app's code is not readable here, but its manifest says what it is, what it may do and what it opens. DIE names the toolkit from the file's signatures.
TLB_KINDS = {1: "method", 2: "property get", 4: "property set", 8: "property set (by reference)"}


def typelib_digest(exe: str, limit: int = 60000) -> Dict[str, Any]:
    """The type library the program carries (in the .exe) or ships beside it (*.olb / *.tlb in its folder whose library name is in the program's own name or description)."""
    import pythoncom
    cands = [exe] + sorted(glob.glob(os.path.join(os.path.dirname(exe), "*.olb")) + glob.glob(os.path.join(os.path.dirname(exe), "*.tlb")))
    desc = " ".join(str(v) for v in ((resources_digest(exe).get("version") or {}).values())).lower() + " " + os.path.basename(exe).lower()
    for path in cands:
        try:
            tl = pythoncom.LoadTypeLib(path)
        except Exception:
            continue
        lib = str(tl.GetDocumentation(-1)[0] or "")
        if path != exe and lib.lower() not in desc:
            continue
        objects: List[Dict[str, Any]] = []
        n_members = 0
        for i in range(tl.GetTypeInfoCount()):
            with contextlib.suppress(Exception):
                ti = tl.GetTypeInfo(i)
                ta = ti.GetTypeAttr()
                name = ti.GetDocumentation(-1)[0]
                if ta.typekind not in (pythoncom.TKIND_DISPATCH, pythoncom.TKIND_INTERFACE) or name.startswith("_") and not ta.cFuncs:
                    continue
                mem: Dict[str, str] = {}
                for k in range(ta.cFuncs):
                    fd = ti.GetFuncDesc(k)
                    nm = ti.GetNames(fd.memid)
                    if nm and not nm[0].startswith(("_", "QueryInterface", "AddRef", "Release", "GetTypeInfo", "GetIDsOfNames", "Invoke")):
                        mem[nm[0]] = TLB_KINDS.get(fd.invkind, "member") + (f"({', '.join(nm[1:6])})" if len(nm) > 1 else "")
                for k in range(ta.cVars):
                    vd = ti.GetVarDesc(k)
                    mem.setdefault(ti.GetNames(vd.memid)[0], "property")
                if mem:
                    objects.append({"object": name.lstrip("_"), "members": mem})
                    n_members += len(mem)
            if n_members >= limit:
                break
        return {"ok": True, "library": lib, "file": path, "objects": len(objects), "members": n_members, "detail": objects}
    return {"ok": False, "error": "no type library in or beside the program"}


def store_apps(names: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """Installed Store (MSIX) packages, from Windows' own package list (the WindowsApps folder itself is not readable without elevation)."""
    import subprocess
    ps = "Get-AppxPackage | Where-Object { -not $_.IsFramework -and $_.SignatureKind -ne 'System' } | Select-Object Name,PackageFullName,InstallLocation,Version | ConvertTo-Json -Compress"
    with contextlib.suppress(Exception):
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=90).stdout
        rows = json.loads(out or "[]")
        rows = rows if isinstance(rows, list) else [rows]
        want = [n.lower() for n in names]
        return [r for r in rows if not want or any(w in (r.get("Name") or "").lower() for w in want)]
    return []


def store_digest(pkg: Dict[str, Any]) -> Dict[str, Any]:
    """A Store app's manifest (Get-AppxPackageManifest): identity, its apps and entry points, capabilities (what it may touch), protocols and file types it opens.
    Display names that are 'ms-resource:' references stay references: resolving them needs the package's resources.pri, which is not read here."""
    import subprocess
    import xml.etree.ElementTree as ET
    ps = f"(Get-AppxPackageManifest -Package '{pkg['PackageFullName']}').OuterXml"
    try:
        xml_text = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout
        root = ET.fromstring(xml_text)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    local = lambda el: el.tag.rsplit("}", 1)[-1]
    els = list(root.iter())
    apps = [{"id": e.get("Id"), "exe": e.get("Executable"), "entry": e.get("EntryPoint")} for e in els if local(e) == "Application"]
    caps = sorted({e.get("Name") for e in els if local(e) in ("Capability", "DeviceCapability") and e.get("Name")})
    protocols = sorted({e.get("Name") for e in els if local(e) == "Protocol" and e.get("Name")})
    ftypes = sorted({(e.text or "").strip() for e in els if local(e) == "FileType" and (e.text or "").strip()})
    disp = next((e.text for e in els if local(e) == "DisplayName" and e.text), pkg.get("Name"))
    return {"ok": True, "name": pkg.get("Name"), "version": pkg.get("Version"), "display": disp, "apps": apps, "capabilities": caps, "protocols": protocols,
            "file_types": ftypes, "how_to_drive": "a packaged XAML/WinUI app: background input is refused (live Oct-27), its tree is the reliable source; protocols start it with an argument"}


def _makepri() -> str:
    """The Windows SDK's makepri.exe (newest x64), '' when the SDK is not installed (HOJAIGA_MAKEPRI overrides)."""
    if os.environ.get("HOJAIGA_MAKEPRI"):
        return os.environ["HOJAIGA_MAKEPRI"]
    import glob
    found = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\makepri.exe"), key=lambda p: [int(x) for x in re.findall(r"\d+", p.split("\\bin\\")[1].split("\\")[0])])
    return found[-1] if found else ""


def pri_digest(install_dir: str, lang: str = "EN-US", cap: int = 6000) -> Dict[str, Any]:
    """Every string a packaged app SHOWS, read from its resources.pri files (makepri dump; read, never run): button names, tooltips, menu and dialog text, keyed
    by the control they belong to ('AbsoluteValueButton.AutomationProperties.Name' = 'Absolute value'), plus the app's pages (its compiled .xbf views). This is how a
    Store app that Ghidra cannot explain (XAML UI, metadata in .winmd) is understood without opening it: Calculator 1,323 named resources, Paint's views."""
    import glob
    import subprocess
    import xml.etree.ElementTree as ET
    mp = _makepri()
    if not mp:
        return {"ok": False, "error": "makepri.exe not found (Windows SDK)"}
    pris = [p for p in glob.glob(os.path.join(install_dir, "**", "*.pri"), recursive=True) if not re.search(r"MergedResources", p)]
    strings: Dict[str, str] = {}
    views: List[str] = []
    tmp = tempfile.mkdtemp(prefix="pri_")
    try:
        for i, pri in enumerate(pris):
            out = os.path.join(tmp, f"{i}.xml")
            with contextlib.suppress(Exception):
                subprocess.run([mp, "dump", "/if", pri, "/of", out, "/dt", "detailed", "/o"], capture_output=True, timeout=120,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if not os.path.isfile(out):
                continue
            with contextlib.suppress(Exception):
                for nr in ET.parse(out).getroot().iter("NamedResource"):
                    uri = nr.get("uri") or ""
                    if uri.endswith(".xbf"):
                        views.append(uri.rsplit("/", 1)[-1][:-4])
                        continue
                    if "/Resources/" not in uri and "/resources/" not in uri:
                        continue
                    best = ""
                    for cand in nr.iter("Candidate"):
                        if cand.get("type") != "String":
                            continue
                        val = (cand.findtext("Value") or "").strip()
                        langs = {q.get("value", "").upper() for q in cand.iter("Qualifier") if q.get("name") == "Language"}
                        if val and (lang in langs or not best):
                            best = val
                            if lang in langs:
                                break
                    if best:
                        key = re.sub(r"\[using:[^\]]+\]", "", uri.split("/Resources/", 1)[-1].split("/resources/", 1)[-1]).replace("/", ".")
                        strings.setdefault(key, best[:200])
                    if len(strings) >= cap:
                        break
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": bool(strings or views), "files": len(pris), "strings": strings, "views": sorted(set(views))}


def file_pri_into_rag(rag: Any, dg: Dict[str, Any], key: str, name: str, run_id: str, per_doc: int = 150) -> int:
    """The app's own words as documents under its key: what each control is called and says (tooltips), and the pages it has, so a question about any button
    of a Store app is answered from the app itself."""
    if not dg.get("ok"):
        return 0
    rows = [f"- {k} = {v}" for k, v in sorted(dg["strings"].items())]
    src = f"store_pri:{run_id}"
    docs = [(key, f"# {name}: the app's own UI words, part {i // per_doc + 1} (from its resources.pri)\n\n" + "\n".join(rows[i:i + per_doc]), src, "web_doc", "catalog")
            for i in range(0, len(rows), per_doc)]
    if dg["views"]:
        docs.append((key, f"# {name}: its pages / views (compiled XAML)\n\n" + ", ".join(dg["views"]), src, "web_doc", "catalog"))
    with contextlib.suppress(Exception):
        rep = rag.proc.ingest_documents(docs)
        return int(getattr(rep, "inserted", 0) or 0) + int(getattr(rep, "updated", 0) or 0)
    return 0


def store_key(rag: Any, pkg: Dict[str, Any], dg: Dict[str, Any], words: Dict[str, str]) -> str:
    """The app key a Store app is known by: the first of its shown name (an 'ms-resource:' name resolved through its own strings), its program's name and its package
    name that the knowledge already has; else its program's name ('Microsoft.Paint' -> 'mspaint', 'Microsoft.WindowsCalculator' -> 'calculator')."""
    disp = dg.get("display") or ""
    if disp.startswith("ms-resource:"):
        ref = disp.split(":", 1)[1].rsplit("/", 1)[-1]
        disp = words.get(ref, "") or next((v for k, v in words.items() if k.lower().endswith(ref.lower())), "")
    exe = next((os.path.splitext(os.path.basename(a.get("exe") or ""))[0] for a in dg.get("apps") or [] if a.get("exe")), "")
    cands = [re.sub(r"[^a-z0-9]+", "", c.lower()) for c in (disp, exe, (pkg.get("Name") or "").split(".")[-1], re.sub(r"(?i)app$", "", exe)) if c]
    for c in cands:
        with contextlib.suppress(Exception):
            if c and rag.resolve_app(c) == c:
                return c
    return cands[1] if len(cands) > 1 and cands[1] else (cands[0] if cands else "store_app")


def learn_store_apps(rag: Any, names: Sequence[str] = (), run_id: str = "", say=print) -> Dict[str, Any]:
    """Every installed Store app (or the named ones) understood without opening it: its manifest (entry points, links, file types) and every word its UI shows
    (resources.pri: controls, tooltips, pages), filed in the knowledge under the app's key."""
    run_id = run_id or "store_" + time.strftime("%Y%m%d_%H%M%S")
    out: Dict[str, Any] = {}
    for pkg in store_apps(names):
        dg = store_digest(pkg)
        if not dg.get("ok"):
            continue
        pri = pri_digest(pkg.get("InstallLocation") or "") if pkg.get("InstallLocation") else {"ok": False}
        key = store_key(rag, pkg, dg, pri.get("strings") or {})
        n = file_store_into_rag(rag, dg, key, run_id) + file_pri_into_rag(rag, pri, key, pkg.get("Name") or key, run_id)
        out[pkg.get("Name")] = {"key": key, "ui_words": len(pri.get("strings") or {}), "views": len(pri.get("views") or []), "chunks": n}
        say(f"{pkg.get('Name')} -> {key}: {out[pkg.get('Name')]['ui_words']} UI words, {out[pkg.get('Name')]['views']} views, {n} chunks")
    return out


def file_store_into_rag(rag: Any, dg: Dict[str, Any], key: str, run_id: str) -> int:
    """A Store app's manifest digest as one document under the app's key (what it is, its entry points, what it may touch, how it can be started)."""
    if not dg.get("ok"):
        return 0
    text = "\n".join([f"# {dg['name']} {dg.get('version', '')}: the Store package's own manifest (read, never run)", "",
                      "- entry points: " + "; ".join(f"{a['id']} = {a['exe']} ({a['entry']})" for a in dg["apps"]),
                      "- may use: " + (", ".join(dg["capabilities"]) or "nothing declared"),
                      "- starts from links: " + (", ".join(p + ":" for p in dg["protocols"]) or "none"),
                      "- opens files: " + (", ".join(dg["file_types"][:40]) or "none declared"),
                      "- how to drive it: " + dg["how_to_drive"]])
    with contextlib.suppress(Exception):
        rep = rag.proc.ingest_document(key, text, f"store_manifest:{run_id}", kind="web_doc", title=f"{dg['name']} (Store manifest)", trust="catalog")
        return int(getattr(rep, "inserted", 0) or 0) + int(getattr(rep, "updated", 0) or 0)
    return 0


DIEC = os.environ.get("HOJAIGA_DIEC", os.path.join(RB.TOOLS, "die_3.21", "die", "diec.exe"))


def die_digest(exe: str) -> Dict[str, Any]:
    """Detect It Easy's verdict on the file (compiler / linker / packer / framework / protector), when diec.exe is installed under tools\\die_3.21."""
    import subprocess
    if not os.path.isfile(DIEC):
        return {"ok": False, "error": "diec.exe is not installed (tools\\die_3.21)"}
    try:
        out = subprocess.run([DIEC, "-j", exe], capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace").stdout
        d = json.loads(out[out.find("{"):]) if "{" in out else {}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:120]}"}
    found = [f"{v.get('type', '')}: {v.get('name', '')} {v.get('version', '')}".strip() for det in d.get("detects", []) for v in det.get("values", [])]
    return {"ok": True, "found": found[:20]}


def digest(prog: Dict[str, Any], use_ghidra: bool = False, ghidra_timeout_s: float = 1800) -> Dict[str, Any]:
    t0 = time.time()
    dg: Dict[str, Any] = {"name": prog["name"], "exe": prog["exe"], "key": prog["key"], "mb": prog["mb"]}
    dg["imports"] = imports_digest(prog["exe"]) if RB.available() else {"ok": False, "error": "REA not installed"}
    dg["resources"] = resources_digest(prog["exe"])
    dg["typelib"] = typelib_digest(prog["exe"])
    dg["die"] = die_digest(prog["exe"])
    if use_ghidra:
        dg["ghidra"] = ghidra_strings(prog["exe"], ghidra_timeout_s)
    dg["how_to_drive"] = how_to_drive(dg)
    dg["seconds"] = round(time.time() - t0, 1)
    return dg


# ------------------------------------------------------------------------------------------------------------------ text and filing
def text_of(dg: Dict[str, Any]) -> str:
    im, rs, gh = dg.get("imports") or {}, dg.get("resources") or {}, dg.get("ghidra") or {}
    ver = rs.get("version") or {}
    md = [f"# {dg['name']}: what the installed program is made of (read statically with REA, never run)", "",
          f"- file {os.path.basename(dg['exe'])}, {dg['mb']} MB" + (f", {ver.get('ProductName') or ver.get('FileDescription')} {ver.get('FileVersion', '')}".rstrip() if ver else "") + (f" by {ver['CompanyName']}" if ver.get("CompanyName") else "")]
    if im.get("ok"):
        md.append(f"- user interface: {im['toolkit']}" + (f" (also uses {im['also']})" if im.get("also") else "") + f"; {im['dlls']} DLLs, {im['functions']} imported functions")
        if im.get("capabilities"):
            md.append("- it can: " + ", ".join(im["capabilities"]))
    if dg.get("how_to_drive"):
        md.append("- how to drive it: " + dg["how_to_drive"])
    if (dg.get("die") or {}).get("ok") and dg["die"]["found"]:
        md.append("- built with (Detect It Easy): " + "; ".join(dg["die"]["found"][:8]))
    tlb = dg.get("typelib") or {}
    if tlb.get("ok"):
        md += ["", f"## Its object model ({tlb['library']} type library: {tlb['objects']} objects, {tlb['members']} members; scripting reaches all of them without a window)"]
        for o in sorted(tlb["detail"], key=lambda o: -len(o["members"]))[:40]:
            md.append(f"- {o['object']}: " + ", ".join(list(o["members"])[:45]))
    if rs.get("commands"):
        md += ["", f"## Commands the program declares ({len(rs['commands'])}; menu path, shortcut)"]
        md += [f"- {c['path'] + ' > ' if c['path'] else ''}{c['name']}" + (f" [{c['chord']}]" if c["chord"] else "") + (f": {c['help']}" if c["help"] else "") for c in rs["commands"][:120]]
    if gh.get("ok"):
        md += ["", f"## From the program's own strings (Ghidra, {gh['strings_seen']} strings)"]
        if gh["shortcuts"]:
            md.append("Shortcuts: " + "; ".join(f"{s['label']} = {s['chord']}" for s in gh["shortcuts"][:60]))
        if gh["flags"]:
            md.append("Command-line options: " + ", ".join(gh["flags"][:40]))
        if gh["urls"]:
            md.append("Addresses it talks to: " + ", ".join(gh["urls"][:15]))
        if gh["file_types"]:
            md.append("Files it works with: " + ", ".join(gh["file_types"][:25]))
        if gh["registry"]:
            md.append("Registry keys: " + "; ".join(gh["registry"][:10]))
        if gh["ui_words"]:
            md.append("Words from its interface: " + ", ".join(gh["ui_words"][:80]))
    elif "ghidra" in dg:
        md += ["", f"(Ghidra did not finish: {gh.get('error', '')[:120]})"]
    return "\n".join(md)


def file_into_rag(rag: Any, dg: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    from core_organs.harvest import bridge as BR, web_learn as WL
    key, res = dg["key"], {"document_chunks": 0, "commands": 0, "hotkeys": 0}
    rs, gh = dg.get("resources") or {}, dg.get("ghidra") or {}
    pairs: List[Dict[str, str]] = []
    for c in rs.get("commands", []):
        if c.get("chord"):
            pairs.append({"action": (c["path"] + " > " if c["path"] else "") + c["name"], "chord": c["chord"], "src": "menu resource"})
    for s in gh.get("shortcuts", []) if gh.get("ok") else []:
        pairs.append({"action": s["label"], "chord": s["chord"], "src": "string table"})
    rows = []
    for p in pairs:
        kind, payload = BR.norm_keys(re.sub(r"\s*\+\s*", "+", p["chord"].lower()))
        if not payload:
            continue
        rows.append({"app_key": key, "kind": kind, "task_pattern": p["action"][:80], "payload": payload, "source": "rea_static", "trust": "catalog", "verified": False,
                     "context": f"declared by the program itself ({p['src']}); not yet pressed live", "params_schema_json": BR.infer_schema(payload)})
    with WL.rag_lock():
        with contextlib.suppress(Exception):
            rep = rag.proc.ingest_document(key, text_of(dg), f"rea_native:{run_id}", kind="web_doc", title=f"{dg['name']} (REA, static)", trust="catalog")
            res["document_chunks"] = int(getattr(rep, "inserted", 0) or 0) + int(getattr(rep, "updated", 0) or 0)
        with contextlib.suppress(Exception):
            for c in rs.get("commands", []):
                rag.lex.add_command(key, c["name"][:80], archetype="native", source="rea_static", trust="catalog")
                res["commands"] += 1
        with contextlib.suppress(Exception):
            for o in (dg.get("typelib") or {}).get("detail", []) if (dg.get("typelib") or {}).get("ok") else []:
                for m, kind in o["members"].items():
                    rag.lex.add_command(key, f"{o['object']}.{m}"[:80], archetype=f"com:{kind.split('(')[0].strip()}", source="typelib", trust="catalog")
                    res["commands"] += 1
        with contextlib.suppress(Exception):
            for r in rows:
                r["command_id"] = rag.lex.add_command(key, r["task_pattern"], archetype="native", source="rea_static", trust="catalog")
            if rows:
                rag.fast.upsert(rows)
                res["hotkeys"] = len(rows)
    return res


def ledger_done() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if os.path.isfile(LEDGER):
        for ln in open(LEDGER, encoding="utf-8"):
            with contextlib.suppress(Exception):
                e = json.loads(ln)
                out[e["key"]] = e
    return out


def record(entry: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_all(rag: Any, use_ghidra: bool = False, max_mb: float = 40.0, hours: float = 8.0, write: bool = True, log=print, ghidra_timeout_s: float = 1800, redo_ghidra: bool = True) -> Dict[str, Any]:
    done = ledger_done()
    deadline = time.time() + hours * 3600
    run_id = "native_" + time.strftime("%Y%m%d_%H%M%S")
    n = 0
    for prog in find_programs():
        if time.time() > deadline:
            log("STOPPING: time budget used")
            break
        prev = done.get(prog["key"])
        need_gh = use_ghidra and prog["mb"] <= max_mb
        if prev and (not need_gh or prev.get("ghidra_ok") or prev.get("ghidra_tried")):
            continue
        log(f"NATIVESTART {prog['name']} ({prog['mb']} MB{', + Ghidra' if need_gh else ''})")
        dg = digest(prog, need_gh, ghidra_timeout_s)
        res = file_into_rag(rag, dg, run_id) if write else {}
        gh = dg.get("ghidra") or {}
        entry = {"key": prog["key"], "name": prog["name"], "when": time.strftime("%Y-%m-%d %H:%M:%S"), "toolkit": (dg.get("imports") or {}).get("toolkit"), "capabilities": (dg.get("imports") or {}).get("capabilities"),
                 "commands": len((dg.get("resources") or {}).get("commands", [])), "ghidra_tried": bool(need_gh), "ghidra_ok": bool(gh.get("ok")), "ghidra_strings": gh.get("strings_seen"),
                 "ghidra_shortcuts": len(gh.get("shortcuts", [])) if gh.get("ok") else 0, "filed": res, "seconds": dg["seconds"]}
        record(entry)
        done[prog["key"]] = entry
        os.makedirs(os.path.join(os.path.dirname(LEDGER), "digests"), exist_ok=True)
        json.dump(dg, open(os.path.join(os.path.dirname(LEDGER), "digests", prog["key"] + ".json"), "w", encoding="utf-8"), indent=1, default=str, ensure_ascii=False)
        log(f"NATIVEDONE {prog['name']}: {entry['toolkit']}; {entry['commands']} menu commands; ghidra {'ok ' + str(entry['ghidra_strings']) + ' strings, ' + str(entry['ghidra_shortcuts']) + ' shortcuts' if entry['ghidra_ok'] else ('failed: ' + str(gh.get('error', ''))[:60] if need_gh else 'skipped')}; filed {res}; {dg['seconds']} s")
        n += 1
    return {"programs": n}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="REA / Ghidra on installed Windows programs, filed in the RAG.")
    ap.add_argument("cmd", choices=["list", "app", "all", "store"])
    ap.add_argument("path", nargs="?", default="")
    ap.add_argument("--ghidra", action="store_true", help="also run Ghidra for the program's strings (minutes per program)")
    ap.add_argument("--max-mb", type=float, default=40.0)
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--timeout-s", type=float, default=1800)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for p in find_programs():
            print(f"{p['name'][:36]:36s} {p['mb']:7.1f} MB  {os.path.basename(p['exe'])}")
        return 0
    from core_organs import rag as R
    rag = R.get_rag()
    if a.cmd == "store":                                                                               # path = comma-separated name filter ('' = every Store app)
        print(json.dumps(learn_store_apps(rag, [n for n in a.path.split(",") if n.strip()], say=lambda s: print(s, flush=True))))
        return 0
    if a.cmd == "app":
        prog = {"name": os.path.basename(os.path.dirname(a.path)) or os.path.basename(a.path), "exe": a.path, "key": re.sub(r"[^a-z0-9]+", "_", os.path.basename(os.path.dirname(a.path)).lower()).strip("_"), "mb": round(os.path.getsize(a.path) / 1e6, 1)}
        dg = digest(prog, a.ghidra, a.timeout_s)
        print(text_of(dg))
        if not a.no_write:
            print(json.dumps(file_into_rag(rag, dg, "app_" + time.strftime("%Y%m%d_%H%M%S"))))
        return 0
    print(json.dumps(run_all(rag, a.ghidra, a.max_mb, a.hours, not a.no_write, lambda s: print(s, flush=True), a.timeout_s)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
