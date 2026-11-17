"""Repair the guide corpus for the thin / zero-document applications (top_up re-search; polite, vendor sources only)."""
import sys
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.professor.knowledge import guide_corpus as GCP

APPS = ["mspaint", "notepad", "calculator", "blender", "excel", "winword", "powerpnt", "systemsettings", "whatsapp",
        "skype", "vlc", "taskmgr", "studio64", "acad", "sharex", "matlab", "tableau", "docker_desktop", "postman", "obsidian", "anydesk"]
rep = GCP.build(apps=APPS, top_up=40, budget_per_app=150.0, pages_other=20, delay_s=0.4, max_queries=3,
                log=lambda s: print(s, flush=True))
print("TOTALS", rep["totals"])
