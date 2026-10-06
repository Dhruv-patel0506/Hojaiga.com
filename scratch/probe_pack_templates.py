"""Dump the file-saving templates from the DATA packs (no code hardcodes these leaf names)."""
import json, io, re

for p in (r"d:\new_automation\data\knowledge_packs\text_editor.archetype.pack.json",
          r"d:\new_automation\data\knowledge_packs\raster_editor.archetype.pack.json"):
    d = json.load(io.open(p, encoding="utf-8"))
    print("===", p.split("\\")[-1], "templates:", len(d.get("templates", [])))
    for t in d.get("templates", []):
        blob = json.dumps(t)
        if "save_to_path" in blob or "open_save_as" in blob:
            print(json.dumps(t, indent=1)[:2600])
            print("-" * 60)
