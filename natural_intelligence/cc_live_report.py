"""Gate 1 forward test: join every live pre-action score (data_user/cc/live_scores.jsonl, written by cc_serve.py BEFORE the
tool ran) to the real outcome harvested afterwards from the transcript, and report how well the live scores ranked them.

This is the strictest test: the model never saw these actions, and the score was fixed before the outcome existed.
Run:  venv\\Scripts\\python.exe -X utf8 natural_intelligence\\cc_live_report.py   -> CC_GATE1_LIVE.md
"""
import os, sys, json, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cc_core, cc_harvest
from cc_gate import metrics

LIVE = os.path.join(cc_core.CC_DIR, "live_scores.jsonl")
OUT = os.path.join(cc_core.ROOT, "CC_GATE1_LIVE.md")


def main():
    acts = {r["id"]: r for r in cc_harvest.harvest(verbose=False)}
    rows = []
    if os.path.exists(LIVE):
        for line in open(LIVE, encoding="utf-8"):
            try:
                s = json.loads(line)
            except Exception:
                continue
            a = acts.get(s.get("tool_use_id"))
            if a and a["outcome"] != "unknown":
                rows.append((s, a))
    n = len(rows); L = ["# Gate 1 live (forward) test", "", f"Generated {time.strftime('%Y-%m-%d %H:%M')}. Scores were made before each action ran, in shadow mode.", ""]
    if n == 0:
        L.append("No scored actions with a known outcome yet.")
    else:
        risk = np.array([s["risk"] for s, _ in rows]); fail = np.array([int(a["outcome"] != "ok") for _, a in rows])
        lat = np.array([s.get("latency_ms", 0) for s, _ in rows])
        L += [f"- Actions scored and resolved: **{n}** (target for gate 1: 300). Failed or refused: **{fail.sum()}** ({fail.mean():.1%}).",
              f"- Scoring latency: median {np.median(lat):.0f} ms, 95th percentile {np.percentile(lat, 95):.0f} ms (async hook, so the agent never waits).", ""]
        if 0 < fail.sum() < n:
            m = metrics(risk, fail)
            L += ["| AUROC | AUPRC | P@5% | R@5% | R@10% |", "|---|---|---|---|---|",
                  f"| {m['auroc']:.3f} | {m['auprc']:.3f} | {m['p@5%']:.2f} | {m['r@5%']:.2f} | {m['r@10%']:.2f} |", ""]
            bands = collections.defaultdict(lambda: [0, 0])
            for (s, a), f in zip(rows, fail):
                bands[s.get("band", "?")][0] += 1; bands[s.get("band", "?")][1] += f
            L += ["| Band | Actions | Failure rate |", "|---|---|---|"] + [f"| {b} | {c} | {f / c:.1%} |" for b, (c, f) in sorted(bands.items())]
        else:
            L.append("All resolved actions have the same outcome so far; ranking metrics need both kinds.")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
