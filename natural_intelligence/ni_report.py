"""Builds MORNING_REPORT.md from the files the run writes (COMPARE.md, scheduler state/log, probes). Re-run any time; report_loop.py does it every 30 min."""
import os, re, json, time, glob, subprocess, collections
ROOT = os.path.dirname(os.path.abspath(__file__)); PY = r"D:\new_automation\venv\Scripts\python.exe"
subprocess.run([PY, "ni_compare.py"], cwd=ROOT, capture_output=True, creationflags=0x08000000)

def table(path):
    best = {}
    pri = lambda v: ("enc2" in v) * 6 + ("enc v4" in v) * 5 + ("enc v3" in v) * 4 + ("enc v2" in v) * 3 + ("enc v1" in v) * 2 + ("hand" in v and "legacy" not in v)
    for l in open(path, encoding="utf-8"):
        c = [x.strip() for x in l.strip().strip("|").split("|")]
        if len(c) >= 10 and "/" in c[0] and c[0].split("/")[0] in ("text", "image", "audio", "video", "graph") and c[1] != "variant":
            try: acc = float(c[3]); maj = float(c[9])
            except ValueError: continue
            if c[0] not in best or pri(c[1]) > pri(best[c[0]][0]): best[c[0]] = (c[1], acc, maj, c[2])
    return best

now, base = table(os.path.join(ROOT, "COMPARE.md")), table(os.path.join(ROOT, "COMPARE_baseline_nov08_0300.md"))
by = collections.defaultdict(list)
for d, v in now.items(): by[d.split("/")[0]].append((d, v))
L = ["# Overnight report", time.strftime("generated %Y-%m-%d %H:%M"), "",
     "Accuracy = vote of the 4 predictors on a held-out 30% (grouped split), mean of the last 30 rounds, best variant per dataset. 'majority' = always guessing the biggest class.", "",
     "## Per modality", "", "| modality | datasets | mean accuracy | mean majority | at 03:20 start |", "|---|---|---|---|---|"]
tot = []
for m in ("text", "image", "audio", "video", "graph"):
    l = by.get(m, [])
    if not l: continue
    a = sum(v[1] for _, v in l) / len(l); mj = sum(v[2] for _, v in l) / len(l); tot += [v[1] for _, v in l]
    b0 = [base[d][1] for d, _ in l if d in base]
    L.append(f"| {m} | {len(l)} | {100*a:.1f}% | {100*mj:.1f}% | {('%.1f%% (%d sets)' % (100*sum(b0)/len(b0), len(b0))) if b0 else 'n/a'} |")
L += [f"| **all** | **{len(tot)}** | **{100*sum(tot)/max(len(tot),1):.1f}%** | | {100*sum(v[1] for v in base.values())/max(len(base),1):.1f}% ({len(base)} sets) |", "",
      "## Datasets new since 03:20 (and not in the first table)", ""]
newd = [d for d in now if d not in base]
L += ([f"- {d}: {100*now[d][1]:.1f}%  ({now[d][0]}, majority {100*now[d][2]:.1f}%)" for d in sorted(newd)] or ["- none trained yet"])
L += ["", "## Changes on datasets that existed at 03:20 (points of accuracy)", ""]
ch = [(100 * (now[d][1] - base[d][1]), d) for d in now if d in base and abs(now[d][1] - base[d][1]) >= 0.003]
L += ([f"- {d}: {x:+.1f}  ({base[d][0]} -> {now[d][0]})" for x, d in sorted(ch, reverse=True)] or ["- no dataset has changed yet"])
L += ["", "## Weakest datasets now", ""] + [f"- {d}: {100*v[1]:.1f}% (majority {100*v[2]:.1f}%)" for d, v in sorted(now.items(), key=lambda kv: kv[1][1] - kv[1][2])[:8]]
# files that exist
enc = collections.Counter(os.path.relpath(p, os.path.join(ROOT, "data_enc")).split(os.sep)[0] for p in glob.glob(os.path.join(ROOT, "data_enc", "enc*", "*", "*.npz")) if "__smoke" not in p)
L += ["", "## Encoded feature sets on disk", "", f"- enc: {enc.get('enc', 0)}   enc2 (stronger encoders): {enc.get('enc2', 0)}"]
try:
    st = json.load(open(os.path.join(ROOT, "sched_state.json"), encoding="utf-8")); L.append(f"- encode failures recorded: {st.get('_encfail', {})}")
except Exception: pass
tail = open(os.path.join(ROOT, "sched_log.txt"), encoding="utf-8", errors="replace").read().splitlines()
L += ["", "## Scheduler: last 12 log lines", "", "```"] + [x[:170] for x in tail[-12:]] + ["```", "",
      "## Findings from the algorithm work", "",
      "- PROBE_gbdt.md / PROBE_v4.md / PROBE_v4b.md: boosted trees beat the 4-predictor vote on all 6 graph sets; v4 (tree joins only when it beats every predictor on the calibration slice) gave twitch +3.1, imdb_binary +3.5, aids +0.8, deezer +0.75, and was identical to v3 on text/emotion and audio/ravdess.",
      "- GATE_PUBLIC.md: manager trust gate on 3937 public agent runs (SWE-agent trajectories): AUROC ~0.52 = no predictive power from pre-run information; no transfer to your own ledger (0.48). The gate is NOT ready to control a manager.", ""]
open(os.path.join(ROOT, "MORNING_REPORT.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L[:20]))
