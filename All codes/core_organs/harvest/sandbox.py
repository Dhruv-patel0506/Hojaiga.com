"""
harvest.sandbox -- a scan opens documents and folders that are OURS, never the person's.

An application started with no arguments opens whatever it opened last: a file manager shows the last folder (C:\\Users\\<name>\\Downloads), Word offers an auto-recovered document of the person's. So an owned
instance of such an application is started with an explicit path inside a workspace made for scanning -- a blank document, a blank workbook, a blank deck, an empty folder. Which application takes which kind of
path is data (the table below, keyed by the program's file name), not code that knows an application.
"""
from __future__ import annotations

import contextlib
import os
from typing import List, Tuple

WORKSPACE = r"D:\new_automation\sandbox_workspace"
# program file name -> (leading flags, kind of path it takes). Flags only suppress splash / start screens; the path is always the sandbox's.
ARGS = {"winword.exe": (["/q"], "docx"), "excel.exe": (["/e"], "xlsx"), "powerpnt.exe": ([], "pptx"), "7zfm.exe": ([], "dir")}


def ensure_workspace(root: str = WORKSPACE) -> str:
    """The workspace and its blank files (created once; python-docx / openpyxl / python-pptx when present)."""
    os.makedirs(root, exist_ok=True)
    with contextlib.suppress(Exception):
        p = os.path.join(root, "blank.docx")
        if not os.path.isfile(p):
            import docx
            d = docx.Document()
            d.add_paragraph("")
            d.save(p)
    with contextlib.suppress(Exception):
        p = os.path.join(root, "blank.xlsx")
        if not os.path.isfile(p):
            import openpyxl
            openpyxl.Workbook().save(p)
    with contextlib.suppress(Exception):
        p = os.path.join(root, "blank.pptx")
        if not os.path.isfile(p):
            import pptx
            pptx.Presentation().save(p)
    with contextlib.suppress(Exception):
        r = os.path.join(root, "readme.txt")
        if not os.path.isfile(r):
            open(r, "w", encoding="utf-8").write("Scratch files for application scans. Safe to delete.\n")
    return root


def args_for(exe: str, root: str = WORKSPACE) -> List[str]:
    """The command-line arguments that make `exe` open the sandbox instead of the person's last file / folder ([] for a program that takes none)."""
    base = os.path.basename(exe or "").lower()
    if base not in ARGS:
        return []
    flags, kind = ARGS[base]
    ensure_workspace(root)
    target = root if kind == "dir" else os.path.join(root, f"blank.{kind}")
    return list(flags) + [target] if os.path.exists(target) else list(flags)


def sandbox_path(path: str, root: str = WORKSPACE) -> bool:
    return os.path.abspath(path).lower().startswith(os.path.abspath(root).lower())
