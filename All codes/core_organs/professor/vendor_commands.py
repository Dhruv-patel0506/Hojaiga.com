"""
professor.vendor_commands -- THE VENDOR'S OWN COMMAND LIST: some application families publish every command their interface has, with the tab, group and menu it sits in.

A live scan sees what is on screen: one ribbon tab at a time, closed galleries hide their items, contextual tabs (Table Layout, Picture Format) exist only while such an object is selected.
A guide speaks about all of it ('Layout > Margins > Custom Margins'). Where the vendor publishes a machine-readable command manifest, the whole interface can be catalogued without
touching the screen, and the installed build itself confirms every entry:

  family     how the manifest is found                                   how each entry is checked against the INSTALLED application
  office     the application's COM ProgID (registry: the exe -> LocalServer32 -> '<Product>.Application') names its Fluent UI manifest
             (OfficeDev/office-fluent-ui-command-identifiers, MIT; fetched once, kept in data/professor/vendor_ui/office)
                                                                          an invisible COM instance answers CommandBars.GetLabelMso(id): the label THIS build shows, its screentip and
                                                                          supertip; an id the build does not know raises -> 'not in this version' (counted, never catalogued)
Nothing is clicked and no window is shown: the COM instance is created hidden (DispatchEx) and quit again unless the application was already running (then it is only read).
The result is merged into the application's Catalog with source 'vendor-manifest' and the id kept as aid 'mso:<id>' (a route the executor can use: CommandBars.ExecuteMso).
No application is named here: the family is recognised by its COM registration, the manifest by the product word of the ProgID.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from . import config as CFG
from . import safety
from .harvest import Catalog, Verb, verb_id
from .schema import fold

VENDOR_DIR = os.path.join(CFG.DATA_DIR, "vendor_ui")
OFFICE_DIR = os.path.join(VENDOR_DIR, "office")
OFFICE_RAW = "https://raw.githubusercontent.com/OfficeDev/office-fluent-ui-command-identifiers/main/Microsoft%20365/Current%20Channel/{name}"
ROLE_OF = {"button": "button", "toggleButton": "toggle", "gallery": "dropdown", "menu": "dropdown", "splitButton": "dropdown", "checkBox": "checkbox", "comboBox": "dropdown",
           "dropDown": "dropdown", "button (dialogBoxLauncher)": "button", "tab": "tab", "control": "field", "editBox": "field", "toggleButton (dialogBoxLauncher)": "toggle"}
SKIP_TYPES = {"group", "contextMenu", "tabSet", "labelControl", "category", "task", "taskFormGroup", "taskGroup", "separator"}
OPENS_MENU = {"gallery", "menu", "splitButton", "comboBox", "dropDown"}


def _camel_words(ident: str) -> str:
    """'ContextMenuTableText' -> 'Table Text', 'TabPageLayoutWord' -> 'Page Layout Word' (a readable fallback when the build has no label for an id)."""
    s = re.sub(r"^(Tab|Group|ContextMenu|TabSet)", "", ident or "")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return s.strip()


# ------------------------------------------------------------------------------------------------------------- discovery
def progid_for_exe(exe: str) -> str:
    """The '<Product>.Application' ProgID whose COM server is this executable ('' when there is none). Read from HKEY_CLASSES_ROOT; nothing is started."""
    import winreg
    base = os.path.basename(exe or "").lower()
    if not base:
        return ""
    if not base.endswith(".exe"):
        base += ".exe"
    hits: List[str] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "")
    except OSError:
        return ""
    i = 0
    while True:
        try:
            name = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        if not re.fullmatch(r"[A-Za-z]+\.Application", name):
            continue
        try:
            with winreg.OpenKey(root, name + "\\CLSID") as k:
                clsid = winreg.QueryValueEx(k, "")[0]
            with winreg.OpenKey(root, f"CLSID\\{clsid}\\LocalServer32") as k:
                srv = str(winreg.QueryValueEx(k, "")[0]).lower()
        except OSError:
            continue
        if base in srv:
            hits.append(name)
    return sorted(hits, key=len)[0] if hits else ""


def manifest_path(progid: str) -> str:
    product = (progid or "").split(".")[0].lower()
    return os.path.join(OFFICE_DIR, f"{product}controls.xlsx") if product else ""


def ensure_manifest(progid: str, web: Optional[bool] = None) -> Tuple[str, str]:
    """(path, note). A manifest already on disk is used as it is; otherwise it is fetched from the vendor's own repository when web retrieval is allowed (the vendor's GitHub organisation is on
    the official-sources allow list of professor.knowledge.guide_finder)."""
    p = manifest_path(progid)
    if not p:
        return "", "no ProgID"
    if os.path.isfile(p):
        return p, "on disk"
    from .knowledge import guide_finder as GF
    if not GF.web_enabled(web):
        return "", "manifest not on disk and web retrieval is off (HOJAIGA_GUIDE_WEB)"
    url = OFFICE_RAW.format(name=os.path.basename(p))
    ok, why = GF.allowed_host(url)
    if not ok:
        return "", f"host not on the official allow list: {why}"
    status, _ct, body, _final = GF.default_fetch(url, max_bytes=4_000_000)
    if status != 200 or not body.startswith(b"PK"):
        return "", f"fetch failed ({status})"
    os.makedirs(OFFICE_DIR, exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(body)
    src = os.path.join(OFFICE_DIR, "SOURCE.json")
    try:
        meta = json.load(open(src, encoding="utf-8")) if os.path.isfile(src) else {"source": "OfficeDev/office-fluent-ui-command-identifiers (MIT)", "requests": []}
        meta["requests"].append({"url": url, "status": status, "bytes": len(body), "at": time.strftime("%Y-%m-%d %H:%M:%S")})
        with open(src, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=1)
    except Exception:
        pass
    return p, "fetched from the vendor's repository"


def read_manifest(path: str) -> List[Dict[str, str]]:
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    head = [str(h or "").strip() for h in next(rows)]
    out: List[Dict[str, str]] = []
    for r in rows:
        d = {head[i]: (str(r[i]).strip() if i < len(r) and r[i] is not None else "") for i in range(len(head))}
        if d.get("Control Name"):
            out.append(d)
    wb.close()
    return out


# ------------------------------------------------------------------------------------------------------------- the build
def _pids(exe_base: str) -> Optional[set]:
    """Process ids running this image now (None when that cannot be read: then nothing is ever quit)."""
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe_base}", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10).stdout
        return {int(row.split('","')[1]) for row in out.splitlines() if row.lower().startswith('"' + exe_base.lower())}
    except Exception:
        return None


class OfficeLabels:
    """An invisible COM instance of the application, asked for labels only. At close() it is quit when - and only when - creating it started a NEW process (by process id: an application
    that serves every client from one process, or one the person or the run already had open, is only read, never quit)."""

    def __init__(self, progid: str, exe_base: str):
        import pythoncom
        import win32com.client as wc
        pythoncom.CoInitialize()
        self.exe_base = exe_base
        before = _pids(exe_base)
        self.app = wc.DispatchEx(progid)
        after = _pids(exe_base)
        self.started_new = bool(before is not None and after is not None and (after - before))
        self.was_running = not self.started_new
        self.cb = self.app.CommandBars
        self.build = str(getattr(self.app, "Build", "") or "")
        self.version = str(getattr(self.app, "Version", "") or "")
        self._cache: Dict[str, Tuple[Optional[str], str]] = {}

    def label(self, ident: str) -> Tuple[Optional[str], str]:
        """(label shown by this build or None when the build does not know the id, description)."""
        if not ident:
            return None, ""
        if ident in self._cache:
            return self._cache[ident]
        try:
            lab = self.cb.GetLabelMso(ident)
        except Exception:
            self._cache[ident] = (None, "")
            return self._cache[ident]
        desc = ""
        try:
            tip = self.cb.GetScreentipMso(ident) or ""
            sup = self.cb.GetSupertipMso(ident) or ""
            desc = (sup if sup else ("" if fold(tip) == fold(lab) else tip)).strip()
        except Exception:
            pass
        self._cache[ident] = (str(lab or ""), re.sub(r"\s+", " ", desc)[:240])
        return self._cache[ident]

    def close(self) -> None:
        if not self.was_running:
            try:
                self.app.Quit()
            except Exception:
                pass
        self.app = self.cb = None


def office_catalog(rows: List[Dict[str, str]], labels: Any, app_key: str) -> Tuple[List[Verb], Dict[str, Any]]:
    """Manifest rows -> verbs. Every container in a verb's path carries the label THIS build shows (or a readable fallback for ids the build has no label for: backstage pages, context menus)."""
    rep: Dict[str, Any] = {"rows": len(rows), "kept": 0, "not_in_this_version": 0, "skipped_types": 0, "not_in_ribbon": 0, "by_area": {}}
    out: Dict[Tuple[str, ...], Verb] = {}

    def name(ident: str) -> str:
        lab, _d = labels.label(ident)
        return re.sub(r"(\.\.\.|…)\s*$", "", lab).strip() if lab else _camel_words(ident)

    for r in rows:
        ident, typ, tabset, tab, grp, par, par2 = (r.get("Control Name", ""), r.get("Control Type", ""), r.get("Tab Set", ""), r.get("Tab", ""), r.get("Group/Context Menu Name", ""),
                                                  r.get("Parent Control", ""), r.get("Secondary Parent Control", ""))
        if typ in SKIP_TYPES:
            rep["skipped_types"] += 1
            continue
        if "Not in the Ribbon" in tabset:
            rep["not_in_ribbon"] += 1
            continue
        lab, desc = labels.label(ident)
        if lab is None or not lab.strip():
            rep["not_in_this_version"] += 1
            continue
        if "Context Menu" in tabset:
            area = "context menu"
            path = ["Context menu: " + _camel_words(grp)] if grp else ["Context menu"]
        elif "Backstage" in tabset:
            area = "backstage"
            path = ["File", name(tab)] + ([name(grp)] if grp else [])
        elif "Quick Access" in tabset:
            area = "quick access toolbar"
            path = ["Quick Access Toolbar"]
        else:
            area = "ribbon" if "Core Tab" in tabset else "contextual tab"
            path = [name(tab)] + ([name(grp)] if grp else [])
        path += [name(p) for p in (par, par2) if p]
        path = [p for p in path if p]
        if typ == "tab":
            path = path[:-1] if path and fold(path[-1]) == fold(lab) else path
        clean = re.sub(r"(\.\.\.|…)\s*$", "", lab).strip()
        key = tuple(fold(x) for x in path + [clean])
        if key in out:
            continue
        leads = ("opens a dialog" if (lab.rstrip().endswith(("...", "…")) or "dialogBoxLauncher" in typ) else ("opens a menu" if typ in OPENS_MENU else ""))
        if area == "contextual tab" and tabset:
            ctx = name(tabset)
            desc = (f"[contextual: '{ctx}' tabs appear only while such an object is selected] " + desc).strip()
        v = Verb(verb_id(path, clean), clean, path, "", desc, True, False, leads, 0, "mso:" + ident, ROLE_OF.get(typ, "button"), ["vendor-manifest"], "vendor+installed-build",
                 safety.classify(clean, " ".join(path)))
        out[key] = v
        rep["kept"] += 1
        rep["by_area"][area] = rep["by_area"].get(area, 0) + 1
    return list(out.values()), rep


def harvest(app_key: str, exe: str, cat: Optional[Catalog] = None, web: Optional[bool] = None, save: bool = True) -> Tuple[Optional[Catalog], Dict[str, Any]]:
    """Catalogue an application's whole command set from its vendor manifest, verified against the installed build. Returns (catalog or None, report). Merges into `cat` (or the stored catalog)."""
    t0 = time.time()
    rep: Dict[str, Any] = {"app": app_key, "exe": exe, "family": "", "progid": "", "manifest": "", "note": ""}
    progid = progid_for_exe(exe)
    rep["progid"] = progid
    if not progid:
        rep["note"] = "no COM automation server registered for this executable: no vendor manifest route"
        return None, rep
    path, note = ensure_manifest(progid, web)
    rep["manifest"], rep["note"] = path, note
    if not path:
        return None, rep
    rep["family"] = "office"
    rows = read_manifest(path)
    labels = OfficeLabels(progid, os.path.basename(exe) if exe.lower().endswith(".exe") else os.path.basename(exe) + ".exe")
    try:
        verbs, r2 = office_catalog(rows, labels, app_key)
        rep.update(r2)
        rep["build"], rep["version"] = labels.build, labels.version
    finally:
        labels.close()
    cat = cat if cat is not None else (Catalog.load(app_key) or Catalog(app_key=app_key, process=os.path.basename(exe)))
    have = {(tuple(fold(p) for p in v.path), fold(v.label)): v for v in cat.verbs}
    added = 0
    for v in verbs:
        k = (tuple(fold(p) for p in v.path), fold(v.label))
        old = have.get(k)
        if old is None:
            cat.verbs.append(v)
            have[k] = v
            added += 1
        else:
            if "vendor-manifest" not in old.sources:
                old.sources.append("vendor-manifest")
            old.aid = old.aid or v.aid
            old.desc = old.desc or v.desc
            old.leads_to = old.leads_to or v.leads_to
    cat.sources["vendor-manifest"] = len(verbs)
    cat.notes = [n for n in cat.notes if not n.startswith("vendor manifest:")] + [f"vendor manifest: {os.path.basename(path)} checked against build {rep.get('build')} - {rep.get('kept')} commands present, "
                                                                                f"{rep.get('not_in_this_version')} listed but unknown to this build"]
    cat.verbs.sort(key=lambda v: (v.path, v.label.lower()))
    rep["added"], rep["catalog_verbs"], rep["seconds"] = added, len(cat.verbs), round(time.time() - t0, 1)
    if save:
        cat.save()
    return cat, rep


def _cache_path(app_key: str) -> str:
    return os.path.join(VENDOR_DIR, "cache", re.sub(r"[^A-Za-z0-9_.-]+", "_", app_key) + ".verbs.json")


def merge_into(cat: Catalog, app_key: str, exe: str, web: Optional[bool] = None) -> Dict[str, Any]:
    """Add the vendor-manifest commands to a live catalog. The verified list is cached per application and reused while the executable's FileVersion is unchanged (an update re-checks it)."""
    from .knowledge.guide_finder import version_info
    from dataclasses import asdict
    ver = (version_info(exe) or {}).get("FileVersion", "") if exe and os.path.isfile(exe) else ""
    cp = _cache_path(app_key)
    verbs: List[Verb] = []
    rep: Dict[str, Any] = {"app": app_key, "exe_version": ver, "cached": False}
    try:
        with open(cp, encoding="utf-8") as fh:
            d = json.load(fh)
        if ver and d.get("exe_version") == ver:
            verbs = [Verb(**v) for v in d["verbs"]]
            from .harvest import reclassify
            reclassify(verbs)
            rep.update(d.get("report", {}))
            rep["cached"] = True
    except Exception:
        pass
    if not verbs:
        tmp = Catalog(app_key=app_key)
        c2, r2 = harvest(app_key, exe, cat=tmp, web=web, save=False)
        rep.update(r2)
        if c2 is None:
            return rep
        verbs = list(c2.verbs)
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump({"exe_version": ver, "report": {k: r2.get(k) for k in ("family", "progid", "build", "version", "kept", "not_in_this_version", "by_area")}, "verbs": [asdict(v) for v in verbs]}, fh, ensure_ascii=False)
    have = {(tuple(fold(p) for p in v.path), fold(v.label)): v for v in cat.verbs}
    added = 0
    for v in verbs:
        k = (tuple(fold(p) for p in v.path), fold(v.label))
        old = have.get(k)
        if old is None:
            cat.verbs.append(v)
            have[k] = v
            added += 1
        else:
            if "vendor-manifest" not in old.sources:
                old.sources.append("vendor-manifest")
            old.aid = old.aid if (old.aid and not old.aid.startswith("mso:")) else (old.aid or v.aid)
            old.desc = old.desc or v.desc
    cat.sources["vendor-manifest"] = len(verbs)
    rep["added"], rep["vendor_verbs"] = added, len(verbs)
    return rep


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Catalogue an application's commands from its vendor manifest (headless)")
    ap.add_argument("app_key")
    ap.add_argument("exe")
    a = ap.parse_args()
    _c, r = harvest(a.app_key, a.exe)
    print(json.dumps(r, indent=1, default=str))
