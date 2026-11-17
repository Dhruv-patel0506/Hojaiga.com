"""
professor.state_protect -- leave an application's own state exactly as the user left it.

A run launches a REAL application (an owned instance). Applications keep state between launches - a notepad reopens the tabs of last time, a messenger stays signed in, a browser has a profile - and
a test must neither show the user's state to the test nor change it. Nothing here knows an application by name; it works from what the system says about the launch target:

  packaged (Store) app   launch id 'PackageFamily!App' -> the package's per-user folder (%LOCALAPPDATA%\\Packages\\<family>): the folder is COPIED aside, entries that look like restored sessions
                         (tab / window / session / saved-state files) are removed so the instance starts fresh, and the copy is put back afterwards (journal on disk: a crashed run is repaired by
                         the next one)
  Chromium-family app    a throw-away --user-data-dir is passed by the launcher (professor.apprun); this guard only owns its deletion
  anything else          nothing to protect (the launcher still never touches documents)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from typing import Any, Dict, List, Optional

from . import config as CFG

JOURNAL = os.path.join(CFG.DATA_DIR, "state_backups.json")
# names under which applications keep 'what was open last time' - a fresh instance must not reopen it
SESSION_LIKE_RX = re.compile(r"(tabstate|windowstate|session|savedstate|saved_state|restore|recent|lastopen|openfiles|workspace\.json)", re.I)


def _journal() -> List[Dict[str, Any]]:
    try:
        with open(JOURNAL, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def _write_journal(rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(JOURNAL), exist_ok=True)
    with open(JOURNAL, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)


def package_family_of(appid: str) -> str:
    """'Microsoft.WindowsNotepad_8wekyb3d8bbwe!App' -> 'Microsoft.WindowsNotepad_8wekyb3d8bbwe' ('' for a path or a classic id)."""
    m = re.match(r"^([A-Za-z0-9.\-]+_[a-z0-9]{13})!", appid or "")
    return m.group(1) if m else ""


def package_dir(family: str) -> str:
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages", family)
    return base if (family and os.path.isdir(base)) else ""


class StateGuard:
    def __init__(self, target: str = "", appid: str = ""):
        self.target = target
        self.family = package_family_of(appid)
        self.dir = package_dir(self.family)
        self.backup = ""
        self.tmp_dirs: List[str] = []
        self.report: Dict[str, Any] = {"packaged": bool(self.dir), "family": self.family}

    def new_temp_dir(self, prefix: str = "hojaiga_state_") -> str:
        d = tempfile.mkdtemp(prefix=prefix)
        self.tmp_dirs.append(d)
        return d

    def before(self) -> Dict[str, Any]:
        recover()                                                      # a previous run that died halfway is repaired first
        if not self.dir:
            return self.report
        self.backup = tempfile.mkdtemp(prefix="state_backup_")
        try:
            shutil.copytree(os.path.join(self.dir, "LocalState"), os.path.join(self.backup, "LocalState")) if os.path.isdir(os.path.join(self.dir, "LocalState")) else None
        except Exception as exc:
            self.report["backup_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
            return self.report
        rows = _journal()
        rows.append({"dir": os.path.join(self.dir, "LocalState"), "backup": os.path.join(self.backup, "LocalState"), "when": time.time(), "family": self.family})
        _write_journal(rows)
        cleared = 0
        root = os.path.join(self.dir, "LocalState")
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth > 2:
                dirnames[:] = []
                continue
            for f in list(filenames):
                if SESSION_LIKE_RX.search(f) or SESSION_LIKE_RX.search(os.path.basename(dirpath)):
                    try:
                        os.remove(os.path.join(dirpath, f))
                        cleared += 1
                    except OSError:
                        pass
        self.report.update({"backed_up": root, "session_files_cleared": cleared})
        return self.report

    def after(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.backup:
            out.update(_restore_one(os.path.join(self.dir, "LocalState"), os.path.join(self.backup, "LocalState")))
            shutil.rmtree(self.backup, ignore_errors=True)
            rows = [r for r in _journal() if r.get("backup", "").startswith(self.backup)]
            _write_journal([r for r in _journal() if r not in rows])
        for d in self.tmp_dirs:
            for _ in range(6):
                shutil.rmtree(d, ignore_errors=True)
                if not os.path.isdir(d):
                    break
                time.sleep(1.0)                                         # a closing browser holds its profile files for a moment
            out["temp_removed"] = out.get("temp_removed", 0) + (0 if os.path.isdir(d) else 1)
        self.tmp_dirs = []
        return out


def _restore_one(target: str, backup: str) -> Dict[str, Any]:
    if not os.path.isdir(backup):
        return {"restored": False, "why": "no backup copy"}
    try:
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(backup, target)
        return {"restored": target}
    except Exception as exc:
        return {"restored": False, "why": f"{type(exc).__name__}: {str(exc)[:80]}"}


def recover() -> int:
    """Put back every state folder whose run never finished (the journal still lists it). Returns how many were restored."""
    rows = _journal()
    n = 0
    keep: List[Dict[str, Any]] = []
    for r in rows:
        if os.path.isdir(r.get("backup", "")):
            res = _restore_one(r["dir"], r["backup"])
            if res.get("restored"):
                n += 1
                shutil.rmtree(os.path.dirname(r["backup"]), ignore_errors=True)
                continue
        if time.time() - r.get("when", 0) < 14 * 86400 and os.path.isdir(r.get("backup", "")):
            keep.append(r)
    if rows:
        _write_journal(keep)
    return n
