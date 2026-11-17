"""Compile the Atlas fixture (C# 5, .NET Framework csc). Idempotent: rebuilds only when the source is newer."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "AtlasFixture.cs")
CSC = os.environ.get("CSC", r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")


def out_dir() -> str:
    d = os.path.join(os.environ.get("HOJAIGA_ATLAS_DIR", os.path.join(r"D:\new_automation", "data", "atlas")), "fixture")
    os.makedirs(d, exist_ok=True)
    return d


def exe_path() -> str:
    return os.path.join(out_dir(), "AtlasFixture.exe")


def build(force: bool = False) -> dict:
    exe = exe_path()
    if not force and os.path.isfile(exe) and os.path.getmtime(exe) >= os.path.getmtime(SRC):
        return {"ok": True, "exe": exe, "built": False}
    if not os.path.isfile(CSC):
        return {"ok": False, "error": f"csc not found at {CSC}"}
    cmd = [CSC, "/nologo", "/target:winexe", f"/out:{exe}", "/r:System.dll", "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll", SRC]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    ok = p.returncode == 0 and os.path.isfile(exe)
    return {"ok": ok, "exe": exe, "built": ok, "log": (p.stdout + p.stderr)[-2500:]}


def truth() -> dict:
    b = build()
    if not b["ok"]:
        raise RuntimeError(b.get("error") or b.get("log"))
    f = os.path.join(tempfile.gettempdir(), "atlas_fixture_truth.json")
    if os.path.isfile(f):
        os.remove(f)
    subprocess.run([exe_path(), "--truth", f], timeout=30)
    with open(f, "r", encoding="utf-8") as fh:
        return json.load(fh)


if __name__ == "__main__":
    r = build(force="--force" in sys.argv)
    print(json.dumps(r, indent=1))
    if r["ok"]:
        print(json.dumps(truth(), indent=1)[:600])
