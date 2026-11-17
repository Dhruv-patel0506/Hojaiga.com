"""Read the corpus report rows of the applications that still have no guide: what did the finder TRY and why did each attempt fail?"""
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

rep = json.load(open(r"d:\new_automation\data\professor\guides\corpus_report.json", encoding="utf-8"))
want = sys.argv[1:] or ["autocad", "tableau", "matlab", "sharex", "vlc", "skype", "taskmgr", "task"]
rows = [a for a in rep.get("apps", []) if any(w in (a.get("key", "") + a.get("name", "")).lower() for w in want)]
print(f"{len(rows)} row(s), totals: {rep.get('totals')}")
for a in rows:
    print("\n===", a.get("key"), "|", a.get("name"), "| docs:", a.get("documents"), "| official_found:", a.get("official_found"),
          "| provider:", a.get("search_provider"), "| skipped:", a.get("skipped"), "| error:", a.get("error"))
    print("   coverage:", json.dumps(a.get("coverage"), ensure_ascii=False)[:400])
    print("   first_sources:", a.get("first_sources"), "kinds:", a.get("kinds"), "seconds:", a.get("seconds"))
print("\nblocked providers:", rep.get("blocked_providers"))
