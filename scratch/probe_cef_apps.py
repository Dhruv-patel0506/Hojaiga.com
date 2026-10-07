"""Probe: which installed apps are Chromium/CEF/Electron surfaces, found STRUCTURALLY (module files next to
the exe), never by an app-name table. Read-only."""
import json
import os
import sqlite3
import sys

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

CHROMIUM_MARKERS = ("libcef.dll", "electron.dll", "chrome_elf.dll", "libegl.dll", "vk_swiftshader.dll")

db_path = r"D:\new_automation\All codes\core_organs\organ_40_apps.db"
if not os.path.exists(db_path):
    from core_organs import organ_40_app_launcher as o40
    db_path = str(o40.KNOWLEDGE_DB)
print("db =", db_path, os.path.exists(db_path))

rows = []
with sqlite3.connect(db_path) as c:
    c.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in c.execute("SELECT name, launcher_path, source FROM app_catalog")]
    except Exception as e:
        print("query failed", e)

print("catalog rows =", len(rows))
hits = []
for r in rows:
    p = (r.get("launcher_path") or "").strip('"')
    if not p or not os.path.exists(p):
        continue
    d = os.path.dirname(p)
    try:
        present = [m for m in CHROMIUM_MARKERS if os.path.exists(os.path.join(d, m))]
    except Exception:
        present = []
    if present:
        hits.append((r["name"], p, present))

for n, p, m in hits:
    print(f"CEF/ELECTRON  {n!r}\n    exe={p}\n    markers={m}")
print("total chromium-family installed =", len(hits))
