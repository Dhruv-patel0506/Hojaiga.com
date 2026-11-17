"""
atlas.comlib -- an application's own OBJECT MODEL, read from the registry and its type library (no launch, no UI).

Windows applications that can be automated register COM classes (HKCR\\CLSID) whose server is the program; the class names a type
library that lists every class, interface, property and method the program exposes to scripts. That list is the most direct
developer-level description of what an application can do that exists on a machine -- it is what its own macro language uses.

    regindex.get()                          cached map: program file -> its COM classes, plus URL protocols and App Paths
    classes_for(exe)                        COM classes whose server is that program
    typelib_for(clsid)                      path of the class's type library
    enumerate_typelib(path)                 {types, members, top types, method names}

Everything is bounded (time, count) and degrades to an empty answer, never an exception.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from . import common as C

try:
    import winreg
except Exception:  # pragma: no cover
    winreg = None

_SYSTEM_DIRS = (os.environ.get("SystemRoot", r"C:\Windows").lower(),)
TKIND = {0: "enum", 1: "record", 2: "module", 3: "interface", 4: "dispatch", 5: "coclass", 6: "alias", 7: "union"}
INVKIND = {1: "method", 2: "property get", 4: "property put", 8: "property putref"}


def _val(key, name: str = "") -> str:
    try:
        v, _ = winreg.QueryValueEx(key, name)
        return str(v) if v is not None else ""
    except OSError:
        return ""


def _exe_in(cmd: str) -> str:
    m = re.search(r'"?([A-Za-z]:\\[^"]*?\.(?:exe|dll|ocx))', cmd or "", re.I)
    return m.group(1) if m else ""


def _index_path() -> str:
    return os.path.join(C.ensure_dir(C.ATLAS_DIR), "regindex.json")


def build_index(budget_s: float = 12.0) -> Dict[str, Any]:
    """One pass over HKCR: COM servers that are programs, URL protocols, App Paths. Cached by get()."""
    t0 = time.time()
    idx: Dict[str, Any] = {"built": t0, "servers": {}, "protocols": {}, "app_paths": {}, "complete": True}
    if winreg is None:
        idx["complete"] = False
        return idx
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "CLSID") as ck:
            i = 0
            while True:
                if time.time() - t0 > budget_s:
                    idx["complete"] = False
                    break
                try:
                    clsid = winreg.EnumKey(ck, i)
                except OSError:
                    break
                i += 1
                server = ""
                for sub in ("LocalServer32", "InprocServer32"):
                    try:
                        with winreg.OpenKey(ck, f"{clsid}\\{sub}") as sk:
                            server = _exe_in(_val(sk))
                    except OSError:
                        continue
                    if server:
                        break
                if not server or server.lower().startswith(_SYSTEM_DIRS):
                    continue
                prog, tl, ver, name = "", "", "", ""
                try:
                    with winreg.OpenKey(ck, clsid) as k0:
                        name = _val(k0)
                    for sub, slot in (("ProgID", "p"), ("TypeLib", "t"), ("Version", "v")):
                        try:
                            with winreg.OpenKey(ck, f"{clsid}\\{sub}") as sk:
                                v = _val(sk)
                                if slot == "p":
                                    prog = v
                                elif slot == "t":
                                    tl = v
                                else:
                                    ver = v
                        except OSError:
                            pass
                except OSError:
                    pass
                idx["servers"].setdefault(os.path.basename(server).lower(), []).append(
                    {"clsid": clsid, "name": name, "progid": prog, "typelib": tl, "version": ver, "server": server})
    except OSError:
        idx["complete"] = False
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "") as rk:
            j = 0
            while time.time() - t0 < budget_s + 6:
                try:
                    nm = winreg.EnumKey(rk, j)
                except OSError:
                    break
                j += 1
                if nm.startswith(".") or len(nm) > 40:
                    continue
                try:
                    with winreg.OpenKey(rk, nm) as pk:
                        if _val(pk, "URL Protocol") == "" and not _has_value(pk, "URL Protocol"):
                            continue
                    with winreg.OpenKey(rk, f"{nm}\\shell\\open\\command") as ck2:
                        exe = _exe_in(_val(ck2))
                    if exe:
                        idx["protocols"].setdefault(os.path.basename(exe).lower(), []).append(nm)
                except OSError:
                    continue
    except OSError:
        pass
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as ak:
                k = 0
                while True:
                    try:
                        nm = winreg.EnumKey(ak, k)
                    except OSError:
                        break
                    k += 1
                    try:
                        with winreg.OpenKey(ak, nm) as sk:
                            p = _val(sk).strip('"')
                            if p:
                                idx["app_paths"][nm.lower()] = p
                    except OSError:
                        pass
        except OSError:
            pass
    idx["seconds"] = round(time.time() - t0, 2)
    return idx


def _has_value(key, name: str) -> bool:
    try:
        winreg.QueryValueEx(key, name)
        return True
    except OSError:
        return False


_INDEX: Dict[str, Any] = {}


def get(max_age_s: float = 3 * 86400, refresh: bool = False) -> Dict[str, Any]:
    global _INDEX
    if _INDEX and not refresh:
        return _INDEX
    p = _index_path()
    if not refresh and os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            if time.time() - float(d.get("built", 0)) < max_age_s and d.get("complete", False):
                _INDEX = d
                return d
        except Exception:
            pass
    d = build_index()
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
    except Exception:
        pass
    _INDEX = d
    return d


def classes_for(exe: str) -> List[Dict[str, Any]]:
    return list(get().get("servers", {}).get(os.path.basename(exe or "").lower(), []))


def protocols_for(exe: str) -> List[str]:
    return sorted(set(get().get("protocols", {}).get(os.path.basename(exe or "").lower(), [])))


# --------------------------------------------------------------------------------------------------
# type libraries
# --------------------------------------------------------------------------------------------------

def typelib_path(guid: str, version: str = "") -> str:
    """Registered path of a type library GUID (highest version unless one is given), 64-bit flavour first."""
    if winreg is None or not guid:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"TypeLib\\{guid}") as tk:
            vers = []
            i = 0
            while True:
                try:
                    vers.append(winreg.EnumKey(tk, i))
                except OSError:
                    break
                i += 1

            def vkey(v: str) -> Tuple[int, ...]:
                try:
                    return tuple(int(x, 16) for x in v.split("."))
                except Exception:
                    return (0,)
            want = [v for v in vers if version and v.split(".")[0] == version.split(".")[0]] or vers
            for v in sorted(want, key=vkey, reverse=True):
                for lcid in ("0", "409", "9"):
                    for plat in ("win64", "win32"):
                        try:
                            with winreg.OpenKey(tk, f"{v}\\{lcid}\\{plat}") as pk:
                                path = _val(pk).strip('"')
                                path = re.sub(r"\\\d+$", "", path)           # "x.dll\\2" selects a resource inside the module
                                if path and os.path.isfile(path):
                                    return path
                        except OSError:
                            continue
    except OSError:
        pass
    return ""


VERB_RX = re.compile(r"^(Add|Insert|Create|New|Open|Save|SaveAs|Export|Import|Apply|Set|Delete|Remove|Run|Print|Close|Copy|Paste|Cut|Select|Find|Replace|Merge|Split|Sort|Filter|Group|Format|Convert|Refresh|Update)", re.I)


def enumerate_typelib(path: str, *, budget_s: float = 4.0, keep_methods: int = 110) -> Dict[str, Any]:
    """Classes, interfaces, members of a type library. Method names are kept for the `keep_methods` largest types."""
    t0 = time.time()
    out: Dict[str, Any] = {"path": path, "ok": False}
    try:
        import pythoncom
    except Exception as exc:
        out["why"] = f"pywin32 unavailable: {exc}"
        return out
    try:
        tlb = pythoncom.LoadTypeLib(path)
    except Exception as exc:
        out["why"] = f"LoadTypeLib failed: {str(exc)[:100]}"
        return out
    try:
        nm, doc, _, _ = tlb.GetDocumentation(-1)
        out["name"], out["doc"] = nm, doc
    except Exception:
        out["name"], out["doc"] = "", ""
    n = tlb.GetTypeInfoCount()
    types: List[Dict[str, Any]] = []
    for i in range(n):
        if time.time() - t0 > budget_s:
            out["truncated"] = True
            break
        try:
            ti = tlb.GetTypeInfo(i)
            attr = ti.GetTypeAttr()
            tname, tdoc, _, _ = tlb.GetDocumentation(i)
            kind = TKIND.get(attr[5], str(attr[5])) if attr[5] in TKIND else TKIND.get(attr[6], "")
            # pywin32 layout: (iid, lcid, memidConstructor, memidDestructor, schema, cbSizeInstance, typekind, cFuncs, cVars, ...)
            tk = attr[5] if attr[5] in TKIND and attr[6] not in TKIND else attr[6]
            kind = TKIND.get(tk, str(tk))
            nfuncs, nvars = (attr[7], attr[8]) if tk == attr[6] else (attr[6], attr[7])
            types.append({"i": i, "name": tname, "kind": kind, "doc": (tdoc or "")[:140], "funcs": int(nfuncs), "vars": int(nvars)})
        except Exception:
            continue
    types.sort(key=lambda t: -(t["funcs"] + t["vars"]))
    methods: Dict[str, List[str]] = {}
    sigs: Dict[str, Dict[str, List[str]]] = {}
    for t in types[:keep_methods]:
        if time.time() - t0 > budget_s:
            break
        if t["kind"] not in ("dispatch", "interface") or not t["funcs"]:
            continue
        try:
            ti = tlb.GetTypeInfo(t["i"])
            names: List[str] = []
            for j in range(min(t["funcs"], 1500)):
                fd = ti.GetFuncDesc(j)
                try:
                    nm_ = ti.GetNames(fd[0])[0]
                except Exception:
                    continue
                inv = fd[4] if len(fd) > 4 else 1
                names.append(nm_ if inv == 1 else f"{nm_}[{INVKIND.get(inv, inv)}]")
            methods[t["name"]] = sorted(set(names))
            # signatures (parameter names) of the verbs that DO things: enough to write a call without opening the documentation
            for j in range(min(t["funcs"], 1500)):
                try:
                    fd = ti.GetFuncDesc(j)
                    nm_all = ti.GetNames(fd[0])
                except Exception:
                    continue
                if nm_all and fd[4] == 1 and VERB_RX.match(nm_all[0]) and len(sigs.setdefault(t["name"], {})) < 120:
                    sigs[t["name"]][nm_all[0]] = list(nm_all[1:9])
        except Exception:
            continue
    out.update(ok=True, types=len(types), members=sum(t["funcs"] + t["vars"] for t in types),
               coclasses=[t["name"] for t in types if t["kind"] == "coclass"][:60],
               enums=sum(1 for t in types if t["kind"] == "enum"),
               top=[{k: t[k] for k in ("name", "kind", "funcs", "vars", "doc")} for t in types[:20]],
               methods=methods, sigs=sigs, seconds=round(time.time() - t0, 2))
    return out


def object_model_for(exe: str, *, budget_s: float = 5.0) -> Dict[str, Any]:
    """Everything COM says about a program: its classes, their type libraries' content. {} when the program is not automatable."""
    t0 = time.time()
    cls = classes_for(exe)
    if not cls:
        return {}
    libs: Dict[str, Dict[str, Any]] = {}
    for c in cls:
        if time.time() - t0 > budget_s:
            break
        g = c.get("typelib") or ""
        if not g or g in libs:
            continue
        p = typelib_path(g, c.get("version", ""))
        if p:
            libs[g] = enumerate_typelib(p, budget_s=max(1.0, budget_s - (time.time() - t0)))
    if not libs:                                    # the registry names no type library for the class (an Office click-to-run install keeps the main automation class
        best, best_n = None, 0
        for p in sibling_typelibs(exe):             # without one): the exe itself or an .olb/.tlb beside it holds it
            if time.time() - t0 > budget_s + 10:
                break
            r = enumerate_typelib(p, budget_s=max(2.0, budget_s - (time.time() - t0)))
            if not r.get("ok") or r.get("types", 0) < 40:
                continue
            if any(c.lower() == "application" for c in r.get("coclasses", [])):
                best = (p, r)                       # the library that defines the program's Application object IS its object model
                break
            if r.get("members", 0) > best_n:
                best, best_n = (p, r), r.get("members", 0)
        if best:
            libs[best[0]] = best[1]
    return {"classes": cls[:80], "n_classes": len(cls), "typelibs": libs, "seconds": round(time.time() - t0, 2)}


def sibling_typelibs(exe: str) -> List[str]:
    """Candidate type libraries for a program: the exe (embedded resource), then *.olb / *.tlb beside it whose name shares letters with the exe's name (most similar first)."""
    out: List[str] = []
    if exe and os.path.isfile(exe):
        out.append(exe)
        d = os.path.dirname(exe)
        stem = re.sub(r"[^a-z]", "", os.path.splitext(os.path.basename(exe))[0].lower())
        try:
            files = [f for f in os.listdir(d) if f.lower().endswith((".olb", ".tlb"))]
        except OSError:
            files = []

        def lcs(x: str, y: str) -> int:
            prev = [0] * (len(y) + 1)
            for ch in x:
                cur = [0]
                for j, cy in enumerate(y):
                    cur.append(prev[j] + 1 if ch == cy else max(prev[j + 1], cur[j]))
                prev = cur
            return prev[-1]

        def sim(f: str) -> float:
            b = re.sub(r"[^a-z]", "", os.path.splitext(f)[0].lower())
            b = b[2:] if b.startswith("ms") and len(b) > 3 else b             # MSPPT -> ppt: the vendor prefix says nothing about the program
            return lcs(b, stem) / max(1, len(b)) if b else 0.0
        out += [os.path.join(d, f) for f in sorted(files, key=lambda f: -sim(f))[:6] if sim(f) >= 0.6]
    return out
