"""Convert public agent-run logs (nebius/SWE-agent-trajectories) into gate records: PRE-RUN information only.
app = repository, goal = the issue text the agent was given, action = which agent/model attempted it, verdict = whether the
patch actually resolved the issue (the dataset's `target`, from running the repo's tests). Trajectory length/exit status are
NOT written: they are only known after the run, so using them would leak the answer into a before-the-action gate."""
import os, sys, glob, json, re, random
import pyarrow.parquet as pq
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data_user", "agent", "SWE-agent-trajectories"); OUT = os.path.join(ROOT, "data_user", "agent", "swe_records.jsonl")
CAP = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
files = sorted(glob.glob(os.path.join(SRC, "**", "*.parquet"), recursive=True))
rows = []
for p in files:
    f = pq.ParquetFile(p)
    for b in f.iter_batches(batch_size=256, columns=["instance_id", "model_name", "target", "trajectory"]):
        for r in b.to_pylist():
            iid = r["instance_id"] or ""; tr = r["trajectory"] or []
            u = next((m["text"] for m in tr if m.get("role") == "user" and m.get("text")), "")
            m_ = re.search(r"(?:<pr_description>|ISSUE:|issue)(.*)", u, re.S | re.I)
            txt = re.sub(r"\s+", " ", (m_.group(1) if m_ else u))[:400]
            repo = iid.split("__")[0] + "/" + iid.split("__")[1].rsplit("-", 1)[0] if "__" in iid else iid
            rows.append(dict(app=repo, goal=f"{iid}: {txt}", action=r["model_name"], verdict="PASS" if r["target"] else "FAIL"))
    print(os.path.basename(p), len(rows), flush=True)
random.Random(0).shuffle(rows)
rows = rows[:CAP]
with open(OUT, "w", encoding="utf-8") as fh:
    for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + "\n")
n = len(rows); ps = sum(r["verdict"] == "PASS" for r in rows)
print(f"wrote {n} records  PASS={ps} ({100*ps/max(n,1):.1f}%)  repos={len({r['app'] for r in rows})}  tasks={len({r['goal'].split(':')[0] for r in rows})}")
