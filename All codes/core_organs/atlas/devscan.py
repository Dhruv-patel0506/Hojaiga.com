"""
atlas.devscan -- the DEVELOPER-LEVEL static harvest: how is this program built and what surfaces does it expose?

No launch, no UI, no per-app code. Everything comes from places an installed program leaves behind:

    program file      PE imports (which OS/library APIs it uses), size, subsystem, managed or native
    install tree      every DLL / plugin folder / runtime file -> toolkit, language runtime, rendering API, audio engine, codecs,
                      network stack, embedded interpreters, plugin ecosystem            (atlas/data/lib_signatures.json)
    strings           command-line switches, endpoints (domains), build tags (Qt/Python/Electron/compiler versions)
    registry          COM classes it serves + their type libraries (the OBJECT MODEL), URL protocols it handles, App Paths
    user data         where it keeps settings/projects (folder names, file kinds), the SCHEMA of its config files and SQLite
                      databases (key and column NAMES only, never values) = its persisted data model
    managed/web       .NET deps.json / runtimeconfig.json, Electron package.json (dependencies)

Each finding becomes a `Claim` with `Evidence` (type + exact ref) at 'static' trust. The result also carries a `summary` (areas ->
libraries) that atlas.architect uses to reason about what the program IS.
"""

from __future__ import annotations

import collections
import concurrent.futures as cf
import json
import os
import re
import sqlite3
import time
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from . import common as C
from . import comlib

_SIGS: Dict[str, Any] = {}
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def signatures() -> Dict[str, Any]:
    global _SIGS
    if not _SIGS:
        try:
            with open(os.path.join(_DATA_DIR, "lib_signatures.json"), "r", encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            d = {"libs": [], "api": []}
        extra = os.path.join(C.ATLAS_DIR, "learned_signatures.json")        # appended by the learning loop
        if os.path.isfile(extra):
            try:
                with open(extra, "r", encoding="utf-8") as fh:
                    e = json.load(fh)
                d["libs"] += e.get("libs", [])
                d["api"] += e.get("api", [])
            except Exception:
                pass
        for kind in ("libs", "api"):
            for s in d.get(kind, []):
                try:
                    s["_rx"] = re.compile(s["re"], re.I)
                except re.error:
                    s["_rx"] = None
        _SIGS = d
    return _SIGS


PLUGIN_DIR_RX = re.compile(r"plug-?ins?|add-?ons?|extensions?|modules?|\bvst\w*|\bclap\b|codecs?|components?|imageformats|platforms|styles|sqldrivers|iconengines|"
                           r"mediaservice|bearer|generic|tls|scripting|\bscripts?\b|controllers?|mappings?|presets?|effects?|filters?|mods?", re.I)
RESOURCE_DIR_RX = re.compile(r"^(locale|lang|languages|resources|data|assets|skins?|themes?|templates?|shaders?|samples?|sounds?|images?|fonts?|icons?|docs?|help)$", re.I)
SECRET_RX = re.compile(r"(token|cookie|password|passwd|credential|secret|login|session|auth|vault|keychain|private|\.key$|\.pem$|oauth)", re.I)
NAMESPACE_DOMAINS = ("w3.org", "schemas.microsoft.com", "schemas.openxmlformats.org", "purl.org", "xmlsoap.org", "openxmlformats.org", "microsoft.com/fwlink",
                     "example.com", "example.org", "localhost", "ns.adobe.com", "xmlns", "apache.org/licenses", "gnu.org/licenses", "mozilla.org/MPL",
                     "www.w3.org", "go.microsoft.com", "ocsp", "crl.", "digicert", "verisign", "globalsign", "sectigo", "symcauth", "symcb", "thawte", "entrust")
STOP_TOKENS = {"microsoft", "windows", "corporation", "inc", "ltd", "llc", "software", "systems", "company", "the", "and", "for", "studio", "app", "application"}


# --------------------------------------------------------------------------------------------------
# file-system inventory
# --------------------------------------------------------------------------------------------------

def is_drive_root(d: str) -> bool:
    return os.path.splitdrive(os.path.abspath(d))[1].strip("\\/") == ""


def own_filter(exe: str, prod_tokens: List[str]):
    """For a program that lives in a SHARED place (a drive root, Downloads...), the only files that are ITS: the program, the libraries
    it imports that sit beside it, siblings sharing its name, and folders named after the product or a version number ('5.2').
    Returns a predicate(name, is_dir) for the entries of that directory."""
    from core_organs import pe_resources as pr
    d = os.path.dirname(exe)
    stem = os.path.splitext(os.path.basename(exe))[0].lower()
    here = {n.lower() for n in os.listdir(d)} if os.path.isdir(d) else set()
    mine = {os.path.basename(exe).lower()}
    frontier = [exe]
    for _ in range(2):
        nxt = []
        for f in frontier:
            for imp in pr.pe_info(f).get("imports", []):
                if imp in here and imp not in mine:
                    mine.add(imp)
                    nxt.append(os.path.join(d, imp))
        frontier = nxt
    toks = [t for t in prod_tokens if len(t) >= 3]

    def pred(name: str, is_dir: bool) -> bool:
        low = name.lower()
        if is_dir:
            return bool(re.fullmatch(r"\d+(\.\d+){0,3}", low)) or any(low == t or low.startswith(t) for t in toks) or low.startswith(stem)
        return low in mine or low.startswith(stem)
    return pred


def inventory(root: str, *, budget_s: float = 2.5, max_files: int = 12000, max_depth: int = 4, only=None) -> Dict[str, Any]:
    t0 = time.time()
    inv: Dict[str, Any] = {"root": root, "files": 0, "bytes": 0, "ext": collections.Counter(), "dlls": {}, "top_dirs": [], "plugin_dirs": {},
                           "exes": [], "json_cfg": [], "truncated": False}
    stack: List[Tuple[str, int]] = [(root, 0)]
    try:
        inv["top_dirs"] = sorted(e.name for e in os.scandir(root) if e.is_dir() and (only is None or only(e.name, True)))[:80]
    except OSError:
        pass
    while stack:
        if time.time() - t0 > budget_s or inv["files"] > max_files:
            inv["truncated"] = True
            break
        d, depth = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            continue
        rel = os.path.relpath(d, root).replace("\\", "/")
        if only is not None and depth == 0:
            entries = [e for e in entries if only(e.name, e.is_dir(follow_symlinks=False))]
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if depth < max_depth:
                        stack.append((e.path, depth + 1))
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            inv["files"] += 1
            inv["bytes"] += st.st_size
            ext = os.path.splitext(e.name)[1].lower()
            inv["ext"][ext] += 1
            low = e.name.lower()
            if ext in (".dll", ".pyd", ".ocx", ".bpl", ".vst3", ".flt", ".plugin", ".node"):
                inv["dlls"].setdefault(low, {"size": st.st_size, "dir": rel})
            elif ext == ".exe":
                inv["exes"].append({"name": e.name, "size": st.st_size, "dir": rel})
            if ext == ".json" and (low.endswith(".deps.json") or low.endswith(".runtimeconfig.json") or low == "package.json") and depth <= 1:
                inv["json_cfg"].append(e.path)
            parts = rel.split("/")
            for pd in parts:
                if PLUGIN_DIR_RX.search(pd):
                    pdk = "/".join(parts[:parts.index(pd) + 1])
                    rec = inv["plugin_dirs"].setdefault(pdk, {"files": 0, "bins": [], "ext": collections.Counter(), "n_bins": 0})
                    rec["files"] += 1
                    rec["ext"][ext] += 1
                    if ext in (".dll", ".pyd", ".vst3", ".node", ".plugin", ".flt"):
                        rec["n_bins"] += 1
                        if len(rec["bins"]) < 60:
                            rec["bins"].append(e.name)
                    break
                if RESOURCE_DIR_RX.match(pd):
                    pdk = "/".join(parts[:parts.index(pd) + 1])
                    inv.setdefault("resource_dirs", {}).setdefault(pdk, 0)
                    inv["resource_dirs"][pdk] += 1
                    break
    inv["seconds"] = round(time.time() - t0, 2)
    return inv


# --------------------------------------------------------------------------------------------------
# binary reading: imports, strings
# --------------------------------------------------------------------------------------------------

def _read_cap(path: str, cap: int) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read(cap)
    except OSError:
        return b""


FLAG_RX = re.compile(rb"--[a-z][a-z0-9]*(?:-[a-z0-9]+){0,4}")
_WORDC = frozenset(b"-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
URL_RX = re.compile(rb"https?://[A-Za-z0-9._~:/?#@!$&'()*+,;=%\-]{4,140}")
TAG_RXS: List[Tuple[str, bytes, "re.Pattern"]] = [
    ("Qt", b"Qt ", re.compile(rb"Qt (\d+\.\d+\.\d+)")), ("Python", b"Python 3.", re.compile(rb"Python (3\.\d+\.\d+)")),
    ("Electron", b"Electron/", re.compile(rb"Electron/(\d+\.\d+\.\d+)")), ("Chromium", b"Chrome/", re.compile(rb"Chrome/(\d+\.\d+\.\d+\.\d+)")),
    ("clang", b"clang version", re.compile(rb"clang version (\d+\.\d+\.\d+)")), ("GCC", b"GCC: (", re.compile(rb"GCC: \([^)]*\) (\d+\.\d+\.\d+)")),
    ("rustc", b"rustc", re.compile(rb"rustc[ /](\d+\.\d+\.\d+)")), ("Go", b"Go build ID", re.compile(rb"Go build ID")),
    ("OpenSSL", b"OpenSSL ", re.compile(rb"OpenSSL (\d+\.\d+\.\d+[a-z]?)")), ("SQLite", b"SQLite", re.compile(rb"SQLite version (\d+\.\d+\.\d+)|SQLite format 3")),
    ("libcurl", b"libcurl/", re.compile(rb"libcurl/(\d+\.\d+\.\d+)")), ("LuaJIT", b"LuaJIT", re.compile(rb"LuaJIT (\d\.\d+\.\d+)")),
    ("Boost", b"boost_", re.compile(rb"boost_(\d_\d+(?:_\d+)?)")), ("Delphi", b"Embarcadero", re.compile(rb"Embarcadero")),
    ("Mono", b"Mono JIT", re.compile(rb"Mono JIT compiler")), (".NET", b".NETFramework,Version", re.compile(rb"\.NETFramework,Version=v(\d\.\d(?:\.\d)?)")),
    (".NET", b".NETCoreApp,Version", re.compile(rb"\.NETCoreApp,Version=v(\d+\.\d+)")), ("Java", b"java/lang/", re.compile(rb"java/lang/")),
    ("WebView2", b"WebView2", re.compile(rb"WebView2")), ("ICU", b"ICU ", re.compile(rb"ICU (\d+\.\d+)")),
]


def scan_binary(path: str, cap: int = 24 * 1024 * 1024) -> Dict[str, Any]:
    data = _read_cap(path, cap)
    out: Dict[str, Any] = {"path": path, "bytes_read": len(data), "flags": collections.Counter(), "domains": collections.Counter(), "tags": {}, "api": set()}
    if not data:
        return out
    clean = data.replace(b"\x00", b"")                                  # UTF-16 strings become ASCII
    for m in FLAG_RX.finditer(clean):
        st, en = m.start(), m.end()
        if (st > 0 and clean[st - 1] in _WORDC) or (en < len(clean) and clean[en] in _WORDC):
            continue
        f = m.group(0).decode("ascii", "ignore")
        if 4 <= len(f) <= 32:
            out["flags"][f] += 1
    for m in URL_RX.finditer(clean):
        try:
            u = urllib.parse.urlparse(m.group(0).decode("ascii", "ignore"))
        except Exception:
            continue
        dom = (u.hostname or "").lower()
        if dom and "." in dom and not any(n in dom + u.path for n in NAMESPACE_DOMAINS) and not re.search(r"\{|\}|%s|%d|<|>", u.netloc):
            out["domains"][dom] += 1
    for name, needle, rx in TAG_RXS:
        if name in out["tags"] or needle not in clean:
            continue
        m = rx.search(clean)
        if m:
            out["tags"][name] = next((g.decode("ascii", "ignore") for g in m.groups() if g), "present") if m.groups() else "present"
    try:
        from core_organs import pe_imports
        out["api"] = set(pe_imports.imported_function_names(data)) if len(data) <= cap else set()
    except Exception:
        pass
    return out


def match_libs(names: Iterable[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Library/DLL names -> {area: [signature hits]} (each hit lists the matched file names)."""
    sigs = signatures()
    by_area: Dict[str, Dict[str, Dict[str, Any]]] = collections.defaultdict(dict)
    for n in names:
        low = n.lower()
        for s in sigs.get("libs", []):
            rx = s.get("_rx")
            if rx is not None and rx.search(low):
                rec = by_area[s["area"]].setdefault(s["label"], {"label": s["label"], "meaning": s["meaning"], "lang": s.get("lang", ""), "files": []})
                if len(rec["files"]) < 6:
                    rec["files"].append(n)
    return {a: list(v.values()) for a, v in by_area.items()}


def match_api(names: Iterable[str]) -> List[Dict[str, Any]]:
    sigs = signatures()
    hits: Dict[str, Dict[str, Any]] = {}
    for n in names:
        for s in sigs.get("api", []):
            rx = s.get("_rx")
            if rx is not None and rx.search(n):
                rec = hits.setdefault(s["label"], {"label": s["label"], "area": s["area"], "meaning": s["meaning"], "functions": []})
                if len(rec["functions"]) < 5:
                    rec["functions"].append(n)
    return list(hits.values())


# --------------------------------------------------------------------------------------------------
# user data: where it keeps state, and the SCHEMA of that state (names only)
# --------------------------------------------------------------------------------------------------

def _tokens(version: Dict[str, str], exe: str, pkg_name: str = "") -> Tuple[List[str], List[str]]:
    comp = [t for t in re.findall(r"[a-z0-9]{3,}", version.get("CompanyName", "").lower()) if t not in STOP_TOKENS]
    raw = [t for t in re.findall(r"[a-z0-9]{3,}", " ".join([version.get("ProductName", ""), os.path.splitext(os.path.basename(exe))[0], pkg_name]).lower())
           if t not in STOP_TOKENS and not t.isdigit()]
    raw += [re.sub(r"\d+$", "", t) for t in raw if len(re.sub(r"\d+$", "", t)) >= 3 and re.sub(r"\d+$", "", t) not in STOP_TOKENS]
    prod = [t for t in raw if t not in comp] or raw                    # 'Google Chrome': 'google' names the vendor folder, 'chrome' the product
    return sorted(set(prod)), sorted(set(comp))


def _known_dirs() -> List[Tuple[str, str]]:
    home = os.path.expanduser("~")
    out = [("%APPDATA%", os.environ.get("APPDATA", "")), ("%LOCALAPPDATA%", os.environ.get("LOCALAPPDATA", "")),
           ("%PROGRAMDATA%", os.environ.get("PROGRAMDATA", "")), ("Documents", os.path.join(home, "Documents")),
           ("Documents/My Games", os.path.join(home, "Documents", "My Games"))]
    return [(n, p) for n, p in out if p and os.path.isdir(p)]


def find_user_dirs(prod: List[str], comp: List[str], *, budget_s: float = 1.5) -> List[Dict[str, str]]:
    t0 = time.time()
    found: List[Dict[str, str]] = []
    for label, base in _known_dirs():
        try:
            names = [e for e in os.scandir(base) if e.is_dir()]
        except OSError:
            continue
        for e in names:
            if time.time() - t0 > budget_s:
                return found
            f = re.sub(r"[^a-z0-9]", "", e.name.lower())
            if any(f == t or f.startswith(t) or (len(f) >= 4 and t.startswith(f)) for t in prod):
                found.append({"base": label, "path": e.path, "match": "product"})
            elif any(t in f for t in comp):                              # Company\Product layout
                try:
                    for e2 in os.scandir(e.path):
                        f2 = re.sub(r"[^a-z0-9]", "", e2.name.lower())
                        if e2.is_dir() and any(t in f2 or (len(f2) >= 4 and f2 in t) for t in prod):
                            found.append({"base": label, "path": e2.path, "match": "company/product"})
                except OSError:
                    pass
    return found


def _json_paths(obj: Any, prefix: str = "", depth: int = 0, out: Optional[List[str]] = None, cap: int = 90) -> List[str]:
    out = [] if out is None else out
    if len(out) >= cap or depth > 3:
        return out
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:40]:
            p = f"{prefix}.{k}" if prefix else str(k)
            kind = "object" if isinstance(v, dict) else "list" if isinstance(v, list) else type(v).__name__
            out.append(f"{p}:{kind}")
            _json_paths(v, p, depth + 1, out, cap)
    elif isinstance(obj, list) and obj:
        _json_paths(obj[0], prefix + "[]", depth + 1, out, cap)
    return out


def _sqlite_schema(path: str) -> Dict[str, List[str]]:
    """Table -> column NAMES of a SQLite file, opened read-only and immutable (no lock, no rows read)."""
    try:
        uri = "file:" + urllib.parse.quote(path.replace("\\", "/")) + "?mode=ro&immutable=1"
        con = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")][:60]
            return {t: [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')][:40] for t in tabs}
        finally:
            con.close()
    except Exception:
        return {}


def user_data_schema(path: str, *, budget_s: float = 2.0, max_files: int = 400) -> Dict[str, Any]:
    t0 = time.time()
    rec: Dict[str, Any] = {"path": path, "files": 0, "bytes": 0, "ext": collections.Counter(), "sample": [], "schemas": [], "dbs": []}
    structured: List[str] = []
    for dp, dn, fn in os.walk(path):
        depth = dp[len(path):].count(os.sep)
        if depth >= 3:
            dn[:] = []
        dn[:] = [d for d in dn if not SECRET_RX.search(d) and d.lower() not in ("cache", "code cache", "gpucache", "crashpad", "logs", "temp", "tmp")]
        for f in fn:
            if rec["files"] >= max_files or time.time() - t0 > budget_s:
                break
            rec["files"] += 1
            p = os.path.join(dp, f)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            rec["bytes"] += sz
            ext = os.path.splitext(f)[1].lower()
            rec["ext"][ext] += 1
            if len(rec["sample"]) < 40:
                rec["sample"].append(os.path.relpath(p, path).replace("\\", "/"))
            if SECRET_RX.search(f):
                continue
            if ext in (".json", ".ini", ".cfg", ".conf", ".xml", ".toml", ".yaml", ".yml") and sz <= 512 * 1024 and len(structured) < 12:
                structured.append(p)
            elif ext in (".db", ".sqlite", ".sqlite3") and len(rec["dbs"]) < 4:
                sch = _sqlite_schema(p)
                if sch:
                    rec["dbs"].append({"file": os.path.relpath(p, path).replace("\\", "/"), "tables": sch})
    for p in structured:
        ext = os.path.splitext(p)[1].lower()
        try:
            txt = _read_cap(p, 400_000).decode("utf-8", "ignore")
        except Exception:
            continue
        keys: List[str] = []
        try:
            if ext == ".json":
                keys = _json_paths(json.loads(txt))
            elif ext in (".ini", ".cfg", ".conf"):
                sec = ""
                for ln in txt.splitlines()[:400]:
                    ln = ln.strip()
                    if ln.startswith("[") and ln.endswith("]"):
                        sec = ln[1:-1]
                        keys.append(f"[{sec}]")
                    elif "=" in ln and not ln.startswith((";", "#")):
                        keys.append(f"{sec}.{ln.split('=', 1)[0].strip()}")
                keys = keys[:90]
            elif ext in (".yaml", ".yml", ".toml"):
                keys = [m.group(1) for m in re.finditer(r"^\s*([A-Za-z_][\w.-]{1,40})\s*[:=]", txt, re.M)][:90]
            elif ext == ".xml":
                keys = sorted(set(re.findall(r"<([A-Za-z_][\w.:-]{1,40})[\s>/]", txt)))[:90]
        except Exception:
            continue
        if keys:
            rec["schemas"].append({"file": os.path.relpath(p, path).replace("\\", "/"), "keys": keys})
    rec["seconds"] = round(time.time() - t0, 2)
    return rec


def registry_software(vendor: str, product: str) -> Dict[str, Any]:
    """Sub-key and VALUE NAMES (never values) of HKCU\\Software\\<vendor>\\<product>."""
    try:
        import winreg
    except Exception:
        return {}
    out: Dict[str, Any] = {}
    for path in {f"Software\\{vendor}\\{product}", f"Software\\{product}", f"Software\\{vendor}"}:
        if not path.strip("\\") or path.count("\\") < 1:
            continue
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
                subs, vals = [], []
                i = 0
                while i < 60:
                    try:
                        subs.append(winreg.EnumKey(k, i))
                    except OSError:
                        break
                    i += 1
                j = 0
                while j < 60:
                    try:
                        vals.append(winreg.EnumValue(k, j)[0])
                    except OSError:
                        break
                    j += 1
                if subs or vals:
                    out["HKCU\\" + path] = {"subkeys": subs, "values": [v for v in vals if not SECRET_RX.search(v)]}
        except OSError:
            continue
    return out


def services_for(root: str) -> List[Dict[str, str]]:
    try:
        import winreg
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    rl = root.lower()
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services") as k:
            i = 0
            while i < 1500:
                try:
                    nm = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(k, nm) as sk:
                        img = str(winreg.QueryValueEx(sk, "ImagePath")[0]).lower()
                        if rl and rl in img:
                            out.append({"name": nm, "image": img[:160]})
                except OSError:
                    continue
    except OSError:
        pass
    return out


def managed_info(json_files: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for p in json_files[:6]:
        low = os.path.basename(p).lower()
        try:
            with open(p, "r", encoding="utf-8-sig") as fh:
                d = json.load(fh)
        except Exception:
            continue
        if low.endswith(".runtimeconfig.json"):
            rc = d.get("runtimeOptions", {})
            out["runtime"] = {"tfm": rc.get("tfm"), "frameworks": rc.get("frameworks") or ([rc["framework"]] if rc.get("framework") else [])}
        elif low.endswith(".deps.json"):
            libs = sorted(k.split("/")[0] for k in (d.get("libraries") or {}).keys())
            out["packages"] = libs[:120]
            out["target"] = (d.get("runtimeTarget") or {}).get("name")
        elif low == "package.json":
            out["package_json"] = {"name": d.get("name"), "version": d.get("version"), "main": d.get("main"),
                                   "dependencies": sorted((d.get("dependencies") or {}).keys())[:80]}
    return out


# --------------------------------------------------------------------------------------------------
# the scan
# --------------------------------------------------------------------------------------------------

def scan(target: Any, *, budget_s: float = 9.0, app_key: str = "", store: Optional[C.AtlasStore] = None, persist: bool = True,
         com: bool = True) -> Dict[str, Any]:
    """Developer-level static harvest of `target` (hwnd | exe path | app name). Returns the structured result; with persist=True the claims
    are also written to the store."""
    from core_organs import static_knowledge as sk
    from core_organs import pe_resources as pr
    t0 = time.time()
    exe = sk.exe_for(target)
    key = app_key or C.app_key_of(str(target) if not isinstance(target, int) else os.path.basename(exe))
    res: Dict[str, Any] = {"app_key": key, "exe": exe, "ok": False, "claims": [], "timings": {}}
    if not exe or not os.path.isfile(exe):
        res["why"] = "program file not found (name only: use atlas.webknow for public knowledge)"
        return res
    pkg = sk.package_root(exe)
    root = pkg or sk._install_root(exe)
    shared = (sk._is_shared_dir(root) or is_drive_root(root)) and not pkg
    version = pr.read_version(exe)
    info = pr.pe_info(exe)
    res.update(ok=True, root=root, shared_install_dir=shared, version_info=version, pe={k: info.get(k) for k in ("machine", "subsystem", "clr", "size", "pe32plus")})
    ev_exe = C.Evidence("pe", exe)
    claims: List[C.Claim] = []

    def add(kind: str, statement: str, evidence: List[C.Evidence], conf: float = 0.8, value: Any = None) -> None:
        claims.append(C.Claim(key, kind, statement, "static", conf, evidence, value, "atlas.devscan"))

    # ---- identity
    prod = version.get("ProductName") or version.get("FileDescription") or os.path.basename(exe)
    add("arch.identity", f"{prod} {version.get('ProductVersion', '')} by {version.get('CompanyName', 'unknown vendor')} "
        f"({info.get('machine', '?')}, {info.get('subsystem', '?')} subsystem, {C.human_bytes(info.get('size', 0))})".replace("  ", " "),
        [ev_exe], 0.95, {"product": prod, "company": version.get("CompanyName"), "version": version.get("ProductVersion")})
    if info.get("clr"):
        add("stack.runtime", "Managed .NET program (CLR header present)", [C.Evidence("pe", exe, "CLR runtime header (data directory 14)")], 0.97)

    # ---- parallel work
    big_dlls: List[str] = []
    jobs: Dict[str, Any] = {}
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        prod_t, comp_t = _tokens(version, exe, os.path.basename(pkg).split("_")[0] if pkg else "")
        if not shared:
            jobs["inventory"] = ex.submit(inventory, root, budget_s=min(3.0, budget_s * 0.4))
        else:
            root = os.path.dirname(exe)                               # the shared folder itself is never "the install tree"
            res["root"] = root
            res["scope"] = "own files only (the program sits in a shared location)"
            jobs["inventory"] = ex.submit(inventory, root, budget_s=min(3.0, budget_s * 0.4), only=own_filter(exe, prod_t))
        jobs["main_bin"] = ex.submit(scan_binary, exe)
        jobs["user_dirs"] = ex.submit(find_user_dirs, prod_t, comp_t, budget_s=min(2.0, budget_s * 0.3))
        jobs["registry"] = ex.submit(registry_software, re.sub(r"[^\w .-]", "", version.get("CompanyName", "")).split(",")[0].strip().split(" ")[0] if version.get("CompanyName") else "",
                                     re.sub(r"[^\w .-]", "", version.get("ProductName", "")).strip())
        jobs["services"] = ex.submit(services_for, exe if shared else root)
        if com:
            jobs["com"] = ex.submit(comlib.object_model_for, exe, budget_s=min(5.0, budget_s * 0.5))
            jobs["protocols"] = ex.submit(comlib.protocols_for, exe)
        results: Dict[str, Any] = {}
        for name, fut in jobs.items():
            try:
                results[name] = fut.result(timeout=max(1.0, budget_s - (time.time() - t0) + 1.5))
            except Exception as exc:
                results[name] = None
                res["timings"][f"{name}_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
    inv = results.get("inventory") or {}
    main_bin = results.get("main_bin") or {}
    res["timings"]["parallel_s"] = round(time.time() - t0, 2)

    # ---- the largest DLLs hold the logic of launcher-style programs (a small exe + big libraries)
    dlls = inv.get("dlls", {})
    big = sorted(((v["size"], k, v["dir"]) for k, v in dlls.items()), reverse=True)[:3]
    extra_bins: List[Dict[str, Any]] = []
    for _, k, d in big:
        if time.time() - t0 > budget_s * 0.55:
            break
        p = os.path.join(root, d, k) if d != "." else os.path.join(root, k)
        if os.path.isfile(p):
            extra_bins.append(scan_binary(p, cap=8 * 1024 * 1024))
    all_bins = [main_bin] + extra_bins

    # ---- libraries / APIs / areas
    tree_imports: Set[str] = set(info.get("imports", []))
    t_imp = time.time()
    for k, v in list(dlls.items())[:320]:
        if time.time() - t_imp > 1.5:
            break
        p_ = os.path.join(root, v["dir"], k) if v["dir"] != "." else os.path.join(root, k)
        try:
            tree_imports |= set(pr.pe_info(p_).get("imports", []))
        except Exception:
            continue
    res["timings"]["imports_s"] = round(time.time() - t_imp, 2)
    names = tree_imports | set(dlls.keys()) | {e["name"].lower() for e in inv.get("exes", [])}
    areas = match_libs(names)
    api_names: Set[str] = set()
    for b in all_bins:
        api_names |= set(b.get("api", set()))
    apis = match_api(api_names)
    res["areas"] = areas
    res["apis"] = apis
    for area, hits in sorted(areas.items()):
        for h in hits:
            files = h["files"]
            add(f"stack.{area}", f"{h['label']}: {h['meaning']}", [C.Evidence("file" if files and files[0] in dlls else "pe", os.path.join(root, files[0]) if files and files[0] in dlls else exe,
                                                                               f"matches {', '.join(files[:3])}")], 0.85, {"area": area, "label": h["label"], "files": files})
    for a in apis:
        add(f"stack.{a['area']}.api", f"{a['label']}: {a['meaning']}", [C.Evidence("pe", exe, "imports " + ", ".join(a["functions"]))], 0.7, {"label": a["label"]})

    # ---- the engine's tested toolkit fingerprint (identifies toolkits that leave no library name, e.g. XAML hosts)
    try:
        files = sk._list_files(pkg or os.path.dirname(exe)) if not shared else []
        appx = sk.appx_info(pkg) if pkg else {}
        fws = sk.fingerprint_framework(exe, info, files, appx)
        res["toolkits"] = [{"id": f["id"], "family": f.get("family"), "notes": (f.get("strategy") or {}).get("notes", "")} for f in fws]
        for f in fws[:3]:
            if f["id"] == "win32-native" and len(fws) > 1:
                continue
            add("stack.toolkit", f"UI toolkit: {f['id']} ({f.get('family', '')}). {(f.get('strategy') or {}).get('notes', '')}".strip(),
                [C.Evidence("pe", exe, "imports + sibling files (static_knowledge.FRAMEWORKS)")], 0.85, {"id": f["id"], "strategy": f.get("strategy")})
    except Exception as exc:
        res["timings"]["toolkit_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
    # ---- languages and build tags
    langs: Dict[str, List[str]] = collections.defaultdict(list)
    for area_hits in areas.values():
        for h in area_hits:
            if h["lang"]:
                langs[h["lang"]].append(h["label"])
    tags: Dict[str, str] = {}
    for b in all_bins:
        tags.update(b.get("tags", {}))
    if "rustc" in tags:
        langs["Rust"].append("rustc build string")
    if "Go" in tags:
        langs["Go"].append("Go build ID")
    if "Delphi" in tags:
        langs["Delphi"].append("Embarcadero string")
    if "Java" in tags and not langs.get("Java"):
        langs["Java"].append("JNI strings")
    res["languages"] = {k: v[:4] for k, v in langs.items()}
    res["tags"] = tags
    if langs:
        order = sorted(langs.items(), key=lambda kv: -len(kv[1]))
        add("stack.language", "Implementation languages indicated: " + ", ".join(f"{k} ({'; '.join(v[:2])})" for k, v in order), [ev_exe, C.Evidence("file", root, "library names in the install tree")], 0.7, dict(order))
    for t, v in tags.items():
        add("stack.version", f"{t} {v if v != 'present' else '(referenced)'} embedded in the binaries", [C.Evidence("pe", exe, f"build tag: {t} {v}")], 0.8, {t: v})

    # ---- plugin ecosystem
    pds = inv.get("plugin_dirs", {})
    res["plugin_dirs"] = {k: {"files": v["files"], "n_bins": v.get("n_bins", 0), "bins": v["bins"][:60], "ext": dict(v["ext"].most_common(4))}
                          for k, v in sorted(pds.items(), key=lambda kv: (-kv[1].get("n_bins", 0), -kv[1]["files"]))[:14]}
    for k, v in list(res["plugin_dirs"].items())[:10]:
        if v["n_bins"] or v["files"] >= 8:
            stems = sorted({os.path.splitext(b)[0] for b in v["bins"]})
            add("ext.plugins", f"Extension/module folder '{k}': {v['files']} files, {v['n_bins']} loadable module(s)" + (f" e.g. {', '.join(stems[:12])}" if stems else ""),
                [C.Evidence("file", os.path.join(root, k))], 0.8, v)
    if inv.get("resource_dirs"):
        res["resource_dirs"] = dict(sorted(inv["resource_dirs"].items(), key=lambda kv: -kv[1])[:10])

    # ---- command line, endpoints
    flags = collections.Counter()
    for b in all_bins:
        flags.update(b.get("flags", {}))
    skip = {"--help", "--version"}
    flag_list = [f for f, _ in flags.most_common(80)]
    res["cli_flags"] = flag_list
    if flag_list:
        add("ext.cli", "Command-line switches found in the binaries: " + ", ".join(flag_list[:30]), [C.Evidence("pe", exe, "string table")], 0.6, flag_list)
    doms = collections.Counter()
    for b in all_bins:
        doms.update(b.get("domains", {}))
    res["domains"] = [d for d, _ in doms.most_common(25)]
    if res["domains"]:
        add("net.endpoints", "Network hosts referenced: " + ", ".join(res["domains"][:15]), [C.Evidence("pe", exe, "URLs in string table")], 0.6, res["domains"])

    # ---- COM object model
    comm = results.get("com") or {}
    if comm:
        res["com"] = {"n_classes": comm.get("n_classes"), "classes": [{k: c[k] for k in ("progid", "name", "clsid") if c.get(k)} for c in comm.get("classes", [])[:25]],
                      "typelibs": {g: {k: v for k, v in lib.items() if k != "methods"} for g, lib in comm.get("typelibs", {}).items()}}
        mfile = os.path.join(C.ensure_dir(os.path.join(C.ATLAS_DIR, "com")), f"{key}.json")
        try:
            with open(mfile, "w", encoding="utf-8") as fh:
                json.dump(comm, fh)
            res["com_model_file"] = mfile
        except Exception:
            mfile = ""
        progs = [c["progid"] for c in comm.get("classes", []) if c.get("progid")]
        add("ext.com", f"Automatable through COM: {comm.get('n_classes')} registered class(es)" + (f" (ProgIDs {', '.join(progs[:5])})" if progs else ""),
            [C.Evidence("registry", r"HKCR\CLSID (LocalServer32 -> " + os.path.basename(exe) + ")")], 0.9, res["com"])
        for g, lib in comm.get("typelibs", {}).items():
            if lib.get("ok"):
                tops = ", ".join(f"{t['name']}({t['funcs']})" for t in lib.get("top", [])[:6])
                add("ext.com.model", f"Object model '{lib.get('name')}': {lib.get('types')} types, {lib.get('members')} members; largest: {tops}",
                    [C.Evidence("typelib", lib.get("path", ""), f"{lib.get('types')} types"), C.Evidence("file", mfile)] if mfile else [C.Evidence("typelib", lib.get("path", ""))], 0.95,
                    {"name": lib.get("name"), "types": lib.get("types"), "members": lib.get("members"), "file": mfile})
    prots = results.get("protocols") or []
    if prots:
        res["protocols"] = prots
        add("ext.protocol", "Handles URL protocol(s): " + ", ".join(p + ":" for p in prots), [C.Evidence("registry", r"HKCR\<protocol>\shell\open\command")], 0.9, prots)

    # ---- managed / web package metadata
    mi = managed_info(inv.get("json_cfg", []))
    asar = os.path.join(root, "resources", "app.asar")
    if os.path.isfile(asar):
        txt = sk._read_asar_member(asar, "package.json")
        try:
            d = json.loads(txt)
            mi["package_json"] = {"name": d.get("name"), "version": d.get("version"), "main": d.get("main"), "dependencies": sorted((d.get("dependencies") or {}).keys())[:80]}
        except Exception:
            pass
    if mi:
        res["managed"] = mi
        if mi.get("runtime"):
            add("stack.runtime", f"Runs on .NET: {mi['runtime'].get('tfm') or ''} frameworks {mi['runtime'].get('frameworks')}", [C.Evidence("file", root, "*.runtimeconfig.json")], 0.9)
        if mi.get("packages"):
            add("stack.packages", f"{len(mi['packages'])} .NET packages incl. " + ", ".join(mi["packages"][:12]), [C.Evidence("file", root, "*.deps.json")], 0.85, mi["packages"])
        if mi.get("package_json"):
            pj = mi["package_json"]
            add("stack.packages", f"Web app package '{pj.get('name')}' {pj.get('version')}; dependencies: {', '.join(pj.get('dependencies', [])[:15])}",
                [C.Evidence("file", asar if os.path.isfile(asar) else root, "package.json")], 0.9, pj)

    # ---- user data, registry, services
    udirs = results.get("user_dirs") or []
    udata: List[Dict[str, Any]] = []
    for ud in udirs[:3]:
        if time.time() - t0 > budget_s + 3:
            break
        rec = user_data_schema(ud["path"], budget_s=1.5)
        rec["base"] = ud["base"]
        udata.append(rec)
        kinds = ", ".join(f"{e or 'noext'}x{n}" for e, n in rec["ext"].most_common(5))
        add("cfg.location", f"Keeps user data under {ud['base']}\\{os.path.relpath(ud['path'], dict(_known_dirs()).get(ud['base'], ud['path'])).replace('/', chr(92))}: {rec['files']} files ({kinds})",
            [C.Evidence("file", ud["path"])], 0.8, {"path": ud["path"], "files": rec["files"], "sample": rec["sample"][:12]})
        for sc in rec["schemas"][:6]:
            add("cfg.schema", f"Config file '{sc['file']}' has keys: " + ", ".join(sc["keys"][:24]), [C.Evidence("config", os.path.join(ud["path"], sc["file"]), "key names only")], 0.8, sc)
        for db in rec["dbs"]:
            tabs = "; ".join(f"{t}({', '.join(c[:6])})" for t, c in list(db["tables"].items())[:8])
            add("cfg.database", f"Database '{db['file']}' tables: {tabs}", [C.Evidence("config", os.path.join(ud["path"], db["file"]), "sqlite_master (names only)")], 0.9, db)
    res["user_data"] = [{k: (dict(v) if isinstance(v, collections.Counter) else v) for k, v in u.items()} for u in udata]
    reg = results.get("registry") or {}
    if reg:
        res["registry_software"] = reg
        for p, v in reg.items():
            add("cfg.registry", f"Registry settings at {p}: subkeys {', '.join(v['subkeys'][:10])}; values {', '.join(v['values'][:10])}", [C.Evidence("registry", p, "names only")], 0.75, v)
    svcs = results.get("services") or []
    if svcs:
        res["services"] = svcs
        add("arch.process", f"Installs Windows service(s): {', '.join(s['name'] for s in svcs[:6])} (background component alongside the UI)", [C.Evidence("registry", r"HKLM\SYSTEM\CurrentControlSet\Services\\" + svcs[0]["name"])], 0.85, svcs)
    helpers = [e for e in inv.get("exes", []) if e["name"].lower() != os.path.basename(exe).lower()]
    if helpers:
        res["helper_exes"] = [h["name"] for h in helpers[:20]]
        add("arch.process", f"Ships {len(helpers)} other executable(s) in its install tree (helper/worker processes or tools): {', '.join(h['name'] for h in helpers[:8])}",
            [C.Evidence("file", root)], 0.7, res["helper_exes"])
    res["inventory"] = {"files": inv.get("files"), "bytes": inv.get("bytes"), "top_dirs": inv.get("top_dirs", [])[:30], "ext": dict(inv.get("ext", {}).most_common(10)) if hasattr(inv.get("ext", {}), "most_common") else {},
                        "dlls": len(dlls), "truncated": inv.get("truncated")}
    if inv.get("files"):
        add("arch.install", f"Install tree: {inv['files']} files, {C.human_bytes(inv['bytes'])}, {len(dlls)} libraries; folders: {', '.join(inv.get('top_dirs', [])[:12])}", [C.Evidence("file", root)], 0.9)

    res["claims"] = [{"kind": c.kind, "statement": c.statement, "confidence": c.confidence, "evidence": [e.to_dict() for e in c.evidence]} for c in claims]
    res["seconds"] = round(time.time() - t0, 2)
    if persist:
        st = store or C.get_store()
        st.delete_claims(key, source="atlas.devscan")
        for c in claims:
            try:
                st.put_claim(c)
            except C.EvidenceRequired:
                continue
    return res
