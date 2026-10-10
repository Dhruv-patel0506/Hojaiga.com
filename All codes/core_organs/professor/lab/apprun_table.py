"""Before / after task table of two apprun reports: goal, steps, result, and the CAUSE of each failure (the first step that did not go, with what was tried).
   python -m core_organs.professor.lab.apprun_table <before.json> <after.json>"""
import json
import sys


def rows(path):
    d = json.load(open(path, encoding="utf-8"))
    out = []
    for t in d.get("tasks", []):
        att = t.get("attempts") or [{}]
        last = att[-1]
        first_bad = None
        for a in att:
            for r in a.get("results", []) or []:
                if isinstance(r, dict) and r.get("verb") is not None and r.get("status") not in ("done", "dry_run"):
                    first_bad = (a.get("n"), r)
                    break
            if first_bad:
                break
        cause = ""
        if t.get("final") != "ok":
            why = (last.get("why") or "")
            cause = why.split(" | tried:")[0][:170]
            if first_bad:
                r = first_bad[1]
                tried = "; ".join((r.get("tried") or [])[:1])[:150]
                cause = f"step {r.get('step')} '{(r.get('verb') or '')[:34]}': {(r.get('summary') or cause)[:170]}" + (f" [{tried}]" if tried else "")
        out.append({"goal": t["goal"].replace("¶", "")[:46], "cite": t.get("cite", "").replace("¶", "")[:70], "steps": t.get("steps_in_guide"), "final": t.get("final"), "attempts": len(att), "cause": cause})
    return d.get("counts", {}), out, d


def main(a, b):
    for label, p in (("BEFORE", a), ("AFTER", b)):
        counts, rs, d = rows(p)
        print(f"\n### {label}  {counts}  (set aside with a reason: {d.get('ledger_counts', {}).get('skipped', 0)})")
        print("| # | task | steps | result | cause of failure |")
        print("|---|---|---|---|---|")
        for i, r in enumerate(rs, 1):
            print(f"| {i} | {r['goal']} | {r['steps']} | {r['final']} ({r['attempts']} att.) | {r['cause'] or '-'} |")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
