"""mastery_bench_report.py -- turn data/mastery_bench_results.json into the markdown tables used by claude_skills/15 and 16.
    python mastery_bench_report.py > data/mastery_bench_report.md"""
import json
import sys

PATH = r"D:\new_automation\data\mastery_bench_results.json"


def main() -> None:
    rows = json.load(open(PATH, encoding="utf-8"))
    print("# Mastery benchmark (fresh database per app, cumulative runs, graded against independent UIA reads)\n")
    print("| App | runs (s) | commands per run | transitions per run | dialogs | state vars | explored (n/explorable) | recall of resting controls | menu-path precision | replay reproduced |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.get("skipped"):
            print(f"| {r['app']} | skipped: {r['skipped']} | | | | | | | | |")
            continue
        c = r.get("curve") or []
        rp = r.get("replay") or {}
        d = r.get("dossier") or {}
        last = c[-1] if c else {}
        fr = (d.get("frontier") or {})
        print(f"| {r['app']} | {len(c)} runs: " + ", ".join(f"{x.get('seconds')}" for x in c) + " | "
              + " -> ".join(str(x.get("commands")) for x in c) + " | " + " -> ".join(str(x.get("transitions")) for x in c)
              + f" | {last.get('dialogs')} | {last.get('statevars')} | {fr.get('explored_n', '?')}/{fr.get('explorable', '?')} | "
              + f"{r.get('recall_resting')} ({r.get('resting_controls_independent')}) | {r.get('menu_path_precision')} ({r.get('menu_paths_known')}) | "
              + f"{rp.get('reproduced')}/{rp.get('sampled')} |")
    print("\n## What each dossier says it does NOT know (gaps)\n")
    for r in rows:
        if r.get("skipped"):
            continue
        print(f"**{r['app']}**")
        for g in (r.get("dossier") or {}).get("gaps", []):
            print(f"- {g}")
        q = (r.get("dossier") or {}).get("quick_answers") or {}
        if q:
            print("- quick answers: " + "; ".join(f"{k} -> {v['path'] or v['command']}" + (f" [{v['shortcut']}]" if v['shortcut'] else "") for k, v in list(q.items())[:8]))
        print()


if __name__ == "__main__":
    main()
