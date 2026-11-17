"""
machine_sweep -- EVERY application on this computer, accounted for, sorted into the app patterns (the 25 archetypes), and learned into the RAG.

    python -m core_organs.harvest.machine_sweep inventory        read the machine: Start menu, shortcuts, packaged (Store) apps, the uninstall list, Program Files -> ledger (nothing is run)
    python -m core_organs.harvest.machine_sweep static           what each program says about itself (version, toolkit, menus + shortcuts in its resources, manifest) -> RAG; nothing is started
    python -m core_organs.harvest.machine_sweep classify         place every app in an archetype from its own words (name, description, commands) and write it to the RAG; propose new patterns for the unplaced
    python -m core_organs.harvest.machine_sweep live [--per-app-min 10] [--limit N] [--hours H]    scan the apps it is safe to drive, one process each, parked off-screen; resumable
    python -m core_organs.harvest.machine_sweep report           who is in the ledger, in what state, and why

Every entry in the ledger ends in exactly one state, so nothing is missed silently:
    learned_live    scanned while running (controls, menus, child windows, shortcuts) and filed
    static_only     read from the program file / manifest and filed; NOT driven because it holds the person's accounts, messages, files, money or the machine (the reason is written next to it)
    running_now     the person has it open: it is never started a second time or touched; static only until it is closed
    not_an_app      documentation / website / uninstaller / console shortcut, or a shortcut whose program is gone
    pending         still in the queue
The person can lift any static_only reason for a named app; the sweep never lifts it on its own.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import glob
import json
import math
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = r"D:\new_automation"
OUT = os.path.join(ROOT, "data", "machine_sweep")
LEDGER = os.path.join(OUT, "ledger.json")

_PS = r"""
$ErrorActionPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$w = New-Object -ComObject WScript.Shell
$lnks = @(Get-ChildItem "$env:ProgramData\Microsoft\Windows\Start Menu\Programs","$env:APPDATA\Microsoft\Windows\Start Menu\Programs" -Recurse -Filter *.lnk | ForEach-Object { $s=$w.CreateShortcut($_.FullName); [pscustomobject]@{name=$_.BaseName; target=$s.TargetPath; args=$s.Arguments; folder=($_.DirectoryName -replace '^.*\\Start Menu\\Programs\\?','')} })
$start = @(Get-StartApps | ForEach-Object { [pscustomobject]@{name=$_.Name; appid=$_.AppID} })
$appx = @(Get-AppxPackage | Where-Object { -not $_.IsFramework } | ForEach-Object { [pscustomobject]@{name=$_.Name; pfn=$_.PackageFamilyName; loc=$_.InstallLocation; pub=$_.Publisher; sig=[string]$_.SignatureKind; nonrem=[bool]$_.NonRemovable} })
$keys='HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
$un = @(Get-ItemProperty $keys | Where-Object { $_.DisplayName -and -not $_.SystemComponent -and -not $_.ParentKeyName } | ForEach-Object { [pscustomobject]@{name=$_.DisplayName; pub=$_.Publisher; loc=$_.InstallLocation; icon=$_.DisplayIcon; ver=$_.DisplayVersion} })
@{lnks=$lnks; start=$start; appx=$appx; un=$un} | ConvertTo-Json -Depth 4 -Compress
"""

_NOT_APP = re.compile(r"uninstall|\bmanuals?\b|\bmodule docs\b|\bhelp\b|documentation|dokumentation|\bfaq|website|homepage|donate|changelog|release notes|readme|read me|\blicen[cs]e|sample|offers|promotion|video instructions|"
                      r"user manual|feedback|get started|get help|tools for (desktop|uwp)|report a bug|\bpdf\b|^reset |reset options|release|what'?s new|^changes$|^news$", re.I)
_SHELL = re.compile(r"command prompt|powershell|\bcmd\b|\bbash\b|terminal|\bwsl\b|ubuntu|developer command|native tools|cross tools|git cmd|anaconda prompt|node\.js command|^console$", re.I)
_COMPONENT = re.compile(r"redistributable|\bruntime\b|\bdriver\b|\bsdk\b|\.net |odbc|ole db|vss writer|clr types|\bsetup\b|add-in|addon|physx|npcap|usbpcap|compatibility fix|oneapi|gameinput|^vs_|xbox(speechtotext|identityprovider|\.tcui)|improvement program|\bjre\b|\bjdk\b|temurin|fonts$|hotfix|update for|language pack|python launcher|remote desktop host|browser for sql|^6365217|debuggable|icu |webview2|vc_redist|toolchain|winget|package manager|extension|experience|platform|companions|enhancements|speech\.|handwriting|singleton|storepurchase|actionsserver|pushnotification|\baimgr|apprunt|startexperiences|crossdevice|widgets", re.I)
_DOC_EXT = (".pdf", ".url", ".chm", ".html", ".htm", ".txt", ".rtf", ".md", ".docx", ".xps")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")[:40]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


# ---- the ledger -----------------------------------------------------------------------------------------------------------------------------------------
def load() -> Dict[str, Any]:
    try:
        return json.load(open(LEDGER, encoding="utf-8"))
    except Exception:
        return {"entries": {}, "made": time.strftime("%Y-%m-%d %H:%M:%S")}


def save(led: Dict[str, Any]) -> None:
    os.makedirs(OUT, exist_ok=True)
    led["saved"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = LEDGER + ".tmp"
    json.dump(led, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
    os.replace(tmp, LEDGER)


# ---- 1 inventory ----------------------------------------------------------------------------------------------------------------------------------------
def _read_ps() -> Dict[str, Any]:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS], capture_output=True, text=True, encoding="utf-8", timeout=240)
    txt = (r.stdout or "").strip()
    return json.loads(txt) if txt else {}


def _manifest_info(loc: str) -> Dict[str, Any]:
    """What a packaged (Store) app declares: its executable, capabilities, file types and protocols. Read-only, from AppxManifest.xml."""
    out: Dict[str, Any] = {}
    p = os.path.join(loc or "", "AppxManifest.xml")
    try:
        x = open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        return out
    m = re.search(r'<Application\b[^>]*\bExecutable="([^"]+)"', x)
    out["executable"] = m.group(1) if m else ""
    out["capabilities"] = sorted(set(re.findall(r'<(?:\w+:)?Capability\s+Name="([^"]+)"', x)))
    out["file_types"] = sorted(set(t.lower() for t in re.findall(r"<(?:\w+:)?FileType>(\.[\w]+)</", x)))[:40]
    out["protocols"] = sorted(set(re.findall(r'<(?:\w+:)?Protocol\s+Name="([^"]+)"', x)))[:20]
    return out


def _exe_from_icon(icon: str) -> str:
    p = (icon or "").split(",")[0].strip().strip('"')
    return p if p.lower().endswith(".exe") and os.path.isfile(p) else ""


def _biggest_exe(folder: str) -> str:
    if not folder or not os.path.isdir(folder) or len(os.path.splitdrive(folder.rstrip("\\/"))[1]) <= 1:          # a drive root is not an install folder (Blender's entry said 'D:\' and picked up a 1 GB Anaconda installer lying there)
        return ""
    skip = ("unins", "update", "setup", "crash", "helper", "install", "uninst", "repair", "elevat", "notif", "-windows-", "redist", "anaconda3-", "launcher_")
    exes = [(os.path.getsize(f), f) for f in glob.glob(os.path.join(folder, "*.exe")) if not any(x in os.path.basename(f).lower() for x in skip)]
    if not exes:                                                                                       # one or two folders down (bin\, app\)
        exes = [(os.path.getsize(f), f) for pat in ("*/*.exe", "*/*/*.exe") for f in glob.glob(os.path.join(folder, pat)) if not any(x in os.path.basename(f).lower() for x in skip)]
    return max(exes)[1] if exes else ""


def inventory() -> Dict[str, Any]:
    """Read the machine. Returns the ledger with one entry per distinct application / shortcut."""
    d = _read_ps()
    start, lnks, appx, un = d.get("start") or [], d.get("lnks") or [], d.get("appx") or [], d.get("un") or []
    lnk_by = {}
    for l in lnks:
        lnk_by.setdefault(_norm(l.get("name", "")), l)
    appx_by_pfn = {a.get("pfn", ""): a for a in appx}
    led = load()
    ent = led["entries"]
    seen_norm: Dict[str, str] = {}

    def put(name: str, **kw: Any) -> str:
        key = slug(name)
        n = _norm(name)
        if n in seen_norm:
            e = ent[seen_norm[n]]
            e["sources"] = sorted(set(e.get("sources", [])) | set(kw.get("sources", [])))
            for k, v in kw.items():
                if k != "sources" and v and not e.get(k):
                    e[k] = v
            return seen_norm[n]
        k = key
        i = 2
        while k in ent and _norm(ent[k]["name"]) != n:
            k = f"{key}_{i}"
            i += 1
        e = ent.setdefault(k, {"key": k, "name": name, "state": "pending"})
        e["name"] = name
        e["sources"] = sorted(set(e.get("sources", [])) | set(kw.get("sources", [])))
        for kk, v in kw.items():
            if kk != "sources" and v and not e.get(kk):
                e[kk] = v
        seen_norm[n] = k
        return k

    for s in start:                                                                                    # 1 the Start menu: what a person could search for and open
        name, appid = (s.get("name") or "").strip(), s.get("appid") or ""
        if not name:
            continue
        kw: Dict[str, Any] = {"sources": ["start_menu"], "appid": appid}
        if "!" in appid and not appid.lower().endswith(".exe"):                                         # a packaged app: <PackageFamilyName>!<App>
            ap = appx_by_pfn.get(appid.split("!")[0])
            if ap:
                mi = _manifest_info(ap.get("loc", ""))
                kw.update(sources=["start_menu", "packaged"], publisher=(ap.get("pub") or "")[:80], package=ap.get("name"), install_dir=ap.get("loc"), manifest=mi, kind_hint="packaged")
                exe = os.path.join(ap.get("loc", ""), mi.get("executable", "")) if mi.get("executable") else ""
                if exe and os.path.isfile(exe):
                    kw["exe"] = exe
        l = lnk_by.get(_norm(name))
        if l:
            kw.update(shortcut_target=l.get("target") or "", shortcut_args=l.get("args") or "", suite=(l.get("folder") or "").split("\\")[0])
            t = l.get("target") or ""
            if t.lower().endswith(".exe") and os.path.isfile(t):
                kw["exe"] = t
        put(name, **kw)
    for l in lnks:                                                                                     # 2 shortcuts the Start-apps list did not show
        t = l.get("target") or ""
        put(l.get("name", ""), sources=["shortcut"], shortcut_target=t, shortcut_args=l.get("args") or "", suite=(l.get("folder") or "").split("\\")[0], **({"exe": t} if t.lower().endswith(".exe") and os.path.isfile(t) else {}))
    for u in un:                                                                                       # 3 the uninstall list: programs with no Start entry
        loc = (u.get("loc") or "").strip().strip('"')
        exe = _exe_from_icon(u.get("icon") or "") or _biggest_exe(loc)
        put(u.get("name", ""), sources=["installed_programs"], publisher=(u.get("pub") or "")[:80], version=u.get("ver") or "", install_dir=loc, **({"exe": exe} if exe else {}))
    have_pkg = {e.get("package") for e in ent.values() if e.get("package")}
    for ap in appx:                                                                                    # 4 packaged apps with no Start entry (non-framework)
        if ap.get("nonrem") or ap.get("sig") == "System" or ap.get("name") in have_pkg:
            continue
        nm = re.sub(r"^(Microsoft\.|MicrosoftCorporationII\.)", "", ap.get("name", ""))
        if _norm(nm) in seen_norm or any(_norm(nm) in n or n in _norm(nm) for n in list(seen_norm)[:400] if len(n) > 5 and len(_norm(nm)) > 5):
            continue
        mi = _manifest_info(ap.get("loc", ""))
        put(nm, sources=["packaged"], publisher=(ap.get("pub") or "")[:80], package=ap.get("name"), install_dir=ap.get("loc"), manifest=mi, kind_hint="packaged")
    known_dirs = {os.path.normcase(e.get("install_dir", "")) for e in ent.values() if e.get("install_dir")} | {os.path.normcase(os.path.dirname(e["exe"])) for e in ent.values() if e.get("exe")}
    for root in (r"C:\Program Files", r"C:\Program Files (x86)", os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"), r"D:\Program Files", r"D:\Program Files (x86)"):   # 5 folders no list mentions
        if not os.path.isdir(root):
            continue
        for dname in sorted(os.listdir(root)):
            base = os.path.join(root, dname)
            if not os.path.isdir(base) or os.path.normcase(base) in known_dirs or re.search(r"windows|microsoft\.net|common files|reference assemblies|modifiableww|windowsapps|internet explorer|^uninstall", dname, re.I):
                continue
            exe = _biggest_exe(base)
            if exe:
                put(dname, sources=["program_files"], install_dir=base, exe=exe)
    for k, e in ent.items():
        e["exe_exists"] = bool(e.get("exe") and os.path.isfile(e["exe"]))
    _merge_duplicates(ent)
    for k, e in ent.items():                                                                           # classes of entry
        if e.get("state") == "merged":
            e["kind"], e["kind_why"] = "duplicate", f"the same program as '{e.get('merged_into_name', '?')}'"
            continue
        e["kind"], e["kind_why"] = _kind_of(e)
    led["inventory_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    led["counts_by_source"] = {"start_apps": len(start), "shortcuts": len(lnks), "packaged_apps": len(appx), "installed_programs": len(un)}
    save(led)
    return led


_VERSION_TAIL = re.compile(r"(\s*[\(\[]?(x64|x86|64-bit|32-bit|user|en-us|english)[\)\]]?)+$|\s+(version\s*)?v?\d+([.\-]\d+)+\S*|\s+(version\s*)?v?\d{1,4}$", re.I)


def _base_name(name: str) -> str:
    n = (name or "").strip()
    for _ in range(3):
        n2 = _VERSION_TAIL.sub("", n).strip()
        if n2 == n:
            break
        n = n2
    return _norm(n)


def _merge_duplicates(ent: Dict[str, Dict[str, Any]]) -> None:
    """The same program appears under several names (Start menu 'Blender 5.2', uninstall list 'Blender', the folder 'Blender Foundation'). One survivor per executable or per name-without-version; the others stay in the
    ledger marked 'merged' so every line the machine showed is still accounted for."""
    def rank(e: Dict[str, Any]) -> Tuple[int, int]:
        return (0 if "start_menu" in e.get("sources", []) else 1, len(e["name"]))
    groups: Dict[str, List[str]] = collections.defaultdict(list)
    for k, e in ent.items():
        if e.get("state") == "merged":
            e.pop("state")
        if e.get("exe_exists"):
            groups["exe:" + os.path.normcase(e["exe"])].append(k)
        else:
            groups["name:" + _base_name(e["name"])].append(k)
    for g, ks in groups.items():
        if len(ks) < 2:
            continue
        ks.sort(key=lambda k: rank(ent[k]))
        keep = ent[ks[0]]
        for k in ks[1:]:
            d = ent[k]
            keep["sources"] = sorted(set(keep.get("sources", [])) | set(d.get("sources", [])))
            for kk in ("publisher", "version", "install_dir", "package", "manifest", "appid", "suite", "exe", "shortcut_target"):
                if d.get(kk) and not keep.get(kk):
                    keep[kk] = d[kk]
            d["state"], d["merged_into"], d["merged_into_name"] = "merged", ks[0], keep["name"]
    names: Dict[str, str] = {}
    for k, e in ent.items():                                                                           # an entry with no program of its own whose name is the start of another entry's name ('Blender' / 'Blender 5.2')
        if e.get("state") != "merged" and e.get("exe_exists"):
            names[_base_name(e["name"])] = k
    for k, e in ent.items():
        if e.get("state") == "merged" or e.get("exe_exists"):
            continue
        b = _base_name(e["name"])
        for other_b, ok in names.items():
            if ok != k and len(b) >= 4 and (other_b == b) and ent[ok].get("exe_exists"):
                e["state"], e["merged_into"], e["merged_into_name"] = "merged", ok, ent[ok]["name"]
                break


def _kind_of(e: Dict[str, Any]) -> Tuple[str, str]:
    name, tgt = e["name"], (e.get("shortcut_target") or "")
    if _NOT_APP.search(name):
        return "not_an_app", "documentation / website / uninstaller / licence shortcut"
    if tgt and not tgt.lower().endswith(".exe") and tgt.lower().endswith(_DOC_EXT):
        return "not_an_app", f"opens a document / link ({os.path.splitext(tgt)[1]})"
    if _SHELL.search(name):
        return "shell", "a command shell: a person types in it, there is no interface to learn"
    if _COMPONENT.search(name) and not e.get("exe_hint_gui"):
        return "component", "a runtime / driver / SDK / add-in: it has no interface of its own"
    if tgt and re.search(r"\.(exe|bat|cmd|msc|lnk)$", tgt, re.I) and not os.path.exists(tgt):
        return "not_an_app", "stale: the shortcut's program was uninstalled and only the Start-menu entry is left"
    if "installed_programs" in e.get("sources", []) and len(e.get("sources", [])) == 1 and not e.get("exe") and e.get("install_dir") and not os.path.isdir(e["install_dir"]):
        return "not_an_app", "stale: listed as installed, but its folder is gone"
    if tgt.lower().endswith(".msc"):
        return "system_tool", "a Windows management console snap-in (part of the machine, not an app)"
    return "app", ""


# ---- 2 safety tier + categories -------------------------------------------------------------------------------------------------------------------------
def running_exes() -> Dict[str, int]:
    out: Dict[str, int] = {}
    try:
        import psutil
        for p in psutil.process_iter(["exe", "pid"]):
            ex = (p.info.get("exe") or "").lower()
            if ex:
                out.setdefault(ex, p.info["pid"])
        return out
    except Exception:
        pass
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object {$_.Path} | ForEach-Object { $_.Path + '|' + $_.Id }"], capture_output=True, text=True, timeout=60)
    for ln in r.stdout.splitlines():
        if "|" in ln:
            pth, pid = ln.rsplit("|", 1)
            out.setdefault(pth.lower(), int(pid))
    return out


def is_running(e: Dict[str, Any], running: Dict[str, int]) -> int:
    """The pid of a process that IS this application, or 0: the same program file, the same file name, or any process started from inside its install folder (packaged apps live in versioned folders, so the path alone is not enough)."""
    exe = (e.get("exe") or "").lower()
    if exe and exe in running:
        return running[exe]
    base = os.path.basename(exe)
    d = (e.get("install_dir") or "").lower().rstrip("\\/")
    for p, pid in running.items():
        if base and os.path.basename(p) == base:
            return pid
        if d and len(d) > 12 and p.startswith(d + os.sep):
            return pid
    return 0


def safety(e: Dict[str, Any], running: Dict[str, int]) -> Tuple[str, str]:
    """('live' | 'static_only' | 'running_now' | 'not_an_app', why). The live learner's own exclusion list (accounts, messages, files, money, the machine, launchers, games) is the rule for 'static_only'."""
    from core_organs.harvest import catalogue as CAT
    if e["kind"] in ("not_an_app", "shell", "component"):
        return "not_an_app", e["kind_why"]
    if e["kind"] == "system_tool":
        return "static_only", e["kind_why"]
    if re.match(r"^(microsoft edge|google chrome|chrome|firefox|brave|opera|vivaldi|notepad|visual studio code|code)\b", e["name"], re.I):
        return "static_only", "starting it restores the person's own session (tabs, profile, last workspace); it is learned from earlier owned-sandbox scans and its program file only"
    m = CAT.EXCLUDE.search(e["name"])
    if m:
        return "static_only", f"holds accounts / messages / files / the machine, or is a launcher / game / tool that must not be driven unattended (matched '{m.group(0).strip()}')"
    pid = is_running(e, running)
    if pid:
        return "running_now", f"the person has it open (pid {pid}); it is never started a second time"
    if not e.get("exe") and not e.get("appid"):
        return "static_only", "no program or launch id was found to start it"
    if "start_menu" not in e.get("sources", []) and not e.get("appid"):
        return "static_only", "not in the Start menu: a vendor folder, service or background agent with no window of its own to open by name"
    return "live", ""


# ---- 3 static harvest -----------------------------------------------------------------------------------------------------------------------------------
KNOWN_KEYS_SQL = "SELECT DISTINCT app_key FROM commands"


def known_keys() -> set:
    import sqlite3
    try:
        db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'ai_root', 'rag', 'lexicon.db')}?mode=ro", uri=True)
        ks = {r[0] for r in db.execute(KNOWN_KEYS_SQL)}
        db.close()
        return ks
    except Exception:
        return set()


def rag_key(e: Dict[str, Any], keys: set) -> str:
    """The app key the RAG already uses for this application, if any (word / winword / microsoft word are one program): otherwise a slug of its name."""
    cands = [slug(e["name"])]
    if e.get("exe"):
        cands.append(slug(os.path.splitext(os.path.basename(e["exe"]))[0]))
    cands.append(slug(re.sub(r"^(microsoft|google|adobe|ms|windows)\s+", "", e["name"], flags=re.I)))
    for c in cands:
        if c in keys:
            return c
    return cands[0]


def static_harvest(rag: Any, e: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    from core_organs import rea_native as RN
    key = e["rag_key"]
    res: Dict[str, Any] = {"at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if e.get("exe_exists") and "WindowsApps" not in e["exe"]:
        size = os.path.getsize(e["exe"]) / 1e6
        dg = RN.digest({"name": e["name"], "exe": e["exe"], "key": key, "mb": round(size, 1)}, use_ghidra=False)
        res["toolkit"] = (dg.get("imports") or {}).get("toolkit")
        res["capabilities"] = (dg.get("imports") or {}).get("capabilities")
        res["version"] = ((dg.get("resources") or {}).get("version") or {})
        res["menu_commands"] = len((dg.get("resources") or {}).get("commands") or [])
        res["filed"] = RN.file_into_rag(rag, dg, run_id)
    mi = e.get("manifest") or {}
    if mi:
        text = (f"{e['name']} is a packaged (Store) application" + (f" by {e.get('publisher')}" if e.get("publisher") else "") + ". It declares these capabilities: "
                + (", ".join(mi.get("capabilities", [])) or "none") + ". It opens these file types: " + (", ".join(mi.get("file_types", [])) or "none declared")
                + ". Protocols it handles: " + (", ".join(mi.get("protocols", [])) or "none") + ".")
        from core_organs.harvest import web_learn as WL
        with WL.rag_lock():
            with contextlib.suppress(Exception):
                rep = rag.proc.ingest_document(key, text, f"machine_sweep:{run_id}", kind="web_doc", title=f"{e['name']} (manifest)", trust="catalog")
                res["manifest_chunks"] = int(getattr(rep, "inserted", 0) or 0) + int(getattr(rep, "updated", 0) or 0)
        res["capabilities"] = mi.get("capabilities")
        res["file_types"] = mi.get("file_types")
    return res


# ---- 4 archetypes ---------------------------------------------------------------------------------------------------------------------------------------
def _labels_of(key: str) -> List[str]:
    import sqlite3
    try:
        db = sqlite3.connect(f"file:{os.path.join(ROOT, 'data', 'ai_root', 'rag', 'lexicon.db')}?mode=ro", uri=True)
        out = [r[0] for r in db.execute("SELECT label FROM commands WHERE app_key=?", (key,))]
        db.close()
        return out
    except Exception:
        return []


def place(e: Dict[str, Any], router: Any = None) -> Dict[str, Any]:
    """Which of the archetypes does this app's own vocabulary fit (name, what it says it is, every command found in it)? Honest statuses: candidate / weak_candidate / ambiguous / insufficient."""
    from core_organs.rag import archetypes as A
    router = router or A.ArchetypeRouter()
    desc = " ".join(str(x) for x in ((e.get("static") or {}).get("version") or {}).values() if isinstance(x, str))
    labels = _labels_of(e["rag_key"])
    sig = {"app": e["name"], "title": f"{e['name']} {desc} {e.get('publisher', '')} {e.get('suite', '')}", "controls": [("control", l) for l in labels[:400]]}
    a = router.assess(sig, top=3)
    return {"status": a["status"], "ranked": [[k, round(v, 3)] for k, v in a["ranked"]], "signals": a["supporting_signals"], "margin": a["margin"], "n_commands": len(labels)}


def classify_all(rag: Any, led: Dict[str, Any]) -> Dict[str, Any]:
    from core_organs.harvest import catalogue as CAT
    from core_organs.rag import archetypes as A
    router = A.ArchetypeRouter()
    c = collections.Counter()
    for k, e in led["entries"].items():
        if e["kind"] != "app":
            continue
        cat = CAT.classify(e["name"])
        e["category"], e["tier_hint"] = cat["category"], cat["tier_hint"]
        e["archetype"] = place(e, router)
        st = e["archetype"]["status"]
        c[st] += 1
        if st in ("candidate", "weak_candidate") and e["archetype"]["ranked"]:
            with contextlib.suppress(Exception):
                rag.lex.set_app(e["rag_key"], tier=e["tier_hint"], archetype=e["archetype"]["ranked"][0][0], toolkit=str((e.get("static") or {}).get("toolkit") or ""))
        else:
            with contextlib.suppress(Exception):
                rag.lex.set_app(e["rag_key"], tier=e["tier_hint"], toolkit=str((e.get("static") or {}).get("toolkit") or ""))
    led["placement_counts"] = dict(c)
    return led


def propose_patterns(led: Dict[str, Any], min_size: int = 3, threshold: float = 0.3) -> List[Dict[str, Any]]:
    """Apps no archetype fits, grouped by the words they share (name, description, commands): PROPOSED new patterns, to be confirmed by a person. Greedy single-link on TF-IDF cosine."""
    un = [e for e in led["entries"].values() if e.get("kind") == "app" and (e.get("archetype") or {}).get("status") in ("insufficient", "ambiguous")]
    docs = []
    for e in un:
        words = re.findall(r"[a-z]{3,}", f"{e['name']} {e.get('suite', '')} {' '.join(_labels_of(e['rag_key'])[:150])} {' '.join(str(v) for v in ((e.get('static') or {}).get('version') or {}).values() if isinstance(v, str))}".lower())
        docs.append(collections.Counter(w for w in words if w not in {"the", "and", "for", "with", "from", "all", "new", "open", "file", "microsoft", "windows", "tools", "application", "inc", "corporation", "ltd"}))
    df = collections.Counter(w for d in docs for w in d)
    n = max(len(docs), 1)
    vec = [{w: (1 + math.log(c)) * math.log(1 + n / df[w]) for w, c in d.items()} for d in docs]
    norm = [math.sqrt(sum(v * v for v in x.values())) or 1.0 for x in vec]

    def cos(i: int, j: int) -> float:
        a, b = vec[i], vec[j]
        if len(a) > len(b):
            a, b = b, a
        return sum(v * b.get(w, 0.0) for w, v in a.items()) / (norm[i] * norm[j])
    group = list(range(len(un)))

    def find(x: int) -> int:
        while group[x] != x:
            group[x] = group[group[x]]
            x = group[x]
        return x
    for i in range(len(un)):
        for j in range(i + 1, len(un)):
            if cos(i, j) >= threshold:
                group[find(i)] = find(j)
    clusters: Dict[int, List[int]] = collections.defaultdict(list)
    for i in range(len(un)):
        clusters[find(i)].append(i)
    out = []
    for idx in sorted((v for v in clusters.values() if len(v) >= min_size), key=lambda v: -len(v)):
        cnt = collections.Counter()
        for i in idx:
            cnt.update(w for w in vec[i])
        out.append({"apps": [un[i]["name"] for i in idx], "shared_words": [w for w, c in cnt.most_common(40) if c >= max(2, len(idx) // 2)][:8]})
    return out


# ---- 5 live scan queue ----------------------------------------------------------------------------------------------------------------------------------
def live(per_app_min: float, limit: int, hours: float) -> None:
    from core_organs import owned_guard as OG
    led = load()
    end = time.time() + hours * 3600
    running = running_exes()
    todo = [e for e in led["entries"].values() if e.get("kind") == "app" and e.get("safety") == "live" and e.get("state") in ("pending", "retry")]
    order: List[Dict[str, Any]] = []                                                                   # tier 0 first, categories round-robin, like the catalogue: a stopped run has covered many KINDS of software
    for tier in (0, 1, 2):
        pools: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
        for e in todo:
            if e.get("tier_hint", 1) == tier:
                pools[e.get("category", "other")].append(e)
        i = 0
        while any(i < len(p) for p in pools.values()):
            for p in pools.values():
                if i < len(p):
                    order.append(p[i])
            i += 1
    if limit:
        order = order[:limit]
    print(f"[sweep-live] {len(order)} apps queued, {per_app_min} min each at most", flush=True)
    for n, e in enumerate(order, 1):
        if time.time() > end:
            print("[sweep-live] time budget used; the rest stays pending", flush=True)
            break
        running = running_exes()
        pid = is_running(e, running)
        if pid:
            e.update(state="running_now", why=f"the person has it open (pid {pid}); left alone")
            save(led)
            print(f"[sweep-live] {n}/{len(order)} {e['name']}: running now, left alone", flush=True)
            continue
        OG.reap_orphans()
        t0 = time.time()
        cmd = [sys.executable, "-u", "-W", "ignore", "-m", "core_organs.overnight", "one", e["name"], "--per-app-min", str(per_app_min)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=per_app_min * 60 + 420, env=dict(os.environ, PYTHONIOENCODING="utf-8"), cwd=r"D:\new_automation\All codes")
            line = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), "")
            res = json.loads(line[7:]) if line else {"ok": False, "error": "the process ended without a result line"}
        except subprocess.TimeoutExpired:
            res = {"ok": False, "error": "hard time limit: the process and its app were ended"}
        e["live"] = {k: res.get(k) for k in ("ok", "actions", "pairs", "pairs_v2", "menus_found", "tier_measured", "controls_seen", "seconds", "error", "crashed_on")}
        e["live"]["child_windows"] = len(res.get("child_windows") or [])
        e["attempts"] = e.get("attempts", 0) + 1
        if res.get("ok"):
            e["state"] = "learned_live"
        elif "could not start" in (res.get("error") or "") or "never showed" in (res.get("error") or ""):
            e["state"] = "static_only"
            e["why"] = "no window appeared when started quietly; learned from the program file only"
        else:
            e["state"] = "retry" if e["attempts"] < 2 else "static_only"
            e["why"] = (res.get("error") or "")[:160]
        save(led)
        print(f"[sweep-live] {n}/{len(order)} {e['name']}: {e['state']} actions={res.get('actions')} pairs={res.get('pairs')} child_windows={e['live']['child_windows']} {time.time() - t0:.0f}s {str(res.get('error') or '')[:90]}", flush=True)
        time.sleep(3)


# ---- driver ---------------------------------------------------------------------------------------------------------------------------------------------
def do_static(limit: int = 0) -> Dict[str, Any]:
    from core_organs import rag as R
    rag = R.get_rag()
    led = load()
    running = running_exes()
    keys = known_keys()
    run_id = time.strftime("sweep_%Y%m%d_%H%M%S")
    n = 0
    for k, e in led["entries"].items():
        e["rag_key"] = rag_key(e, keys)
        e["safety"], why = safety(e, running)
        if e["safety"] == "not_an_app":
            e["state"], e["why"] = "not_an_app", why
            continue
        if e["safety"] == "static_only":
            e["why"] = why
        elif e["safety"] == "running_now":
            e["why"] = why
        if e.get("static", {}).get("at") and not e.get("static", {}).get("error"):
            continue
        if limit and n >= limit:
            continue
        try:
            e["static"] = static_harvest(rag, e, run_id)
        except Exception as ex:
            e["static"] = {"error": f"{type(ex).__name__}: {str(ex)[:140]}", "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        n += 1
        if e["state"] in ("pending",):
            e["state"] = {"static_only": "static_only", "running_now": "running_now"}.get(e["safety"], "pending")
        if n % 20 == 0:
            save(led)
            print(f"[sweep-static] {n} done", flush=True)
    save(led)
    return led


def do_classify() -> Dict[str, Any]:
    from core_organs import rag as R
    rag = R.get_rag()
    led = load()
    led = classify_all(rag, led)
    led["proposed_patterns"] = propose_patterns(led)
    save(led)
    return led


def report() -> str:
    led = load()
    ent = led["entries"]
    st = collections.Counter(e.get("state", "?") for e in ent.values())
    kinds = collections.Counter(e.get("kind") for e in ent.values())
    lines = [f"# Machine sweep - {len(ent)} entries (inventory {led.get('inventory_at', '?')})", "", f"by state: {dict(st)}", f"by kind: {dict(kinds)}", f"placement: {led.get('placement_counts', {})}",
             f"read from: {led.get('counts_by_source', {})}", ""]
    arch = collections.defaultdict(list)
    for e in ent.values():
        a = e.get("archetype") or {}
        if e.get("kind") == "app" and a.get("status") in ("candidate", "weak_candidate"):
            arch[a["ranked"][0][0]].append(e["name"])
    lines.append("## apps by archetype (candidate / weak candidate)")
    for k, v in sorted(arch.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- {k} ({len(v)}): {', '.join(sorted(v)[:14])}{' ...' if len(v) > 14 else ''}")
    lines += ["", "## static only, and why"]
    for e in sorted(ent.values(), key=lambda x: x["name"].lower()):
        if e.get("state") == "static_only":
            lines.append(f"- {e['name']}: {e.get('why', '')[:150]}")
    lines += ["", "## running now (left alone)"] + [f"- {e['name']}: {e.get('why', '')}" for e in ent.values() if e.get("state") == "running_now"]
    lines += ["", "## not an app"] + [f"- {e['name']}: {e.get('why', '')}" for e in sorted(ent.values(), key=lambda x: x["name"].lower()) if e.get("state") == "not_an_app"][:80]
    lines += ["", "## proposed new patterns (unplaced apps grouped by shared words; to be confirmed)"]
    for p in led.get("proposed_patterns", []):
        lines.append(f"- {len(p['apps'])} apps, words {p['shared_words']}: {', '.join(p['apps'][:10])}")
    txt = "\n".join(lines)
    open(os.path.join(OUT, "REPORT.md"), "w", encoding="utf-8").write(txt)
    return txt


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["inventory", "static", "classify", "live", "report", "all"])
    ap.add_argument("--per-app-min", type=float, default=10.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--hours", type=float, default=12.0)
    a = ap.parse_args(argv)
    if a.cmd in ("inventory", "all"):
        led = inventory()
        print(f"inventory: {len(led['entries'])} entries", led["counts_by_source"], flush=True)
    if a.cmd in ("static", "all"):
        do_static(a.limit)
    if a.cmd in ("classify", "all"):
        do_classify()
    if a.cmd == "live":
        live(a.per_app_min, a.limit, a.hours)
    if a.cmd in ("report", "all", "classify"):
        print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
