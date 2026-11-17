"""Run the branch engine on a REAL task whose branches were produced by real agents, and compare NI's pick with baselines.

Inputs: a task folder (the original: spec + stub), a hidden check the agents never saw, and one folder per agent holding
what that agent produced, plus its run metadata (stated confidence, failure if it never produced code).
Baselines (what people do today):
  first branch      - use the incumbent agent's answer (the agent listed first)
  most confident    - use the agent that states the highest confidence
NI: every branch on its own copy, measured by the check; recommend with proof or cross-question (gov_branch).
Outcome: each branch's hidden-check result. Each agent's outcome is appended to data_user/gov/branch_outcomes.jsonl, so its
track record (L2) starts from real results.

Run: venv\\Scripts\\python.exe -X utf8 natural_intelligence\\gov_branch_task.py <task_dir> <hidden_test.py> <agents.json> <report.md>
"""
import os, sys, json, re, shutil, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gov_branch, gov_ledger

OUTCOMES = os.path.join(gov_ledger.GOV_DIR, "branch_outcomes.jsonl")


def main(task, hidden, agents_file, report):
    A = json.load(open(agents_file, encoding="utf-8-sig"))
    task, hidden = os.path.abspath(task), os.path.abspath(hidden)          # the check runs with cwd = each copy
    if not os.path.isfile(hidden):
        raise SystemExit(f"hidden check not found: {hidden}")
    files = A["files"]; agents = A["agents"]
    branches = []
    for a in agents:
        def tf(copy_dir, a=a):
            if a.get("failed"):
                raise RuntimeError(f"agent produced no code: {a['failed']}")
            for f in files:
                shutil.copy2(os.path.join(a["dir"], f), os.path.join(copy_dir, f))
        branches.append(dict(name=a["name"], agent=a["vendor"], transform=tf))
    cmd = f'"{sys.executable}" "{hidden}"'
    L = gov_ledger.Ledger()
    rec = gov_branch.explore(task, branches, cmd, ledger=L)
    by = {r["name"]: r for r in rec["branches"]}
    conf = {a["name"]: a.get("confidence") for a in agents}
    first = agents[0]["name"]
    stated = [a for a in agents if a.get("confidence") is not None]
    most = max(stated, key=lambda a: a["confidence"])["name"] if stated else None
    ni = rec.get("recommend")
    q = lambda n: None if n is None else by[n]["v_raw"]["quality"]
    best_q = max(r["v_raw"]["quality"] for r in rec["branches"])
    rows = [("first branch (incumbent agent)", first), ("most confident agent", most), ("NI branch engine", ni)]
    with open(OUTCOMES, "a", encoding="utf-8") as f:
        for r in rec["branches"]:
            f.write(json.dumps(dict(ts=time.time(), task=os.path.basename(task), branch_run=rec["id"], agent=r["name"], vendor=r["agent"],
                                    outcome="ok" if r["feasible"] else "fail", quality=r["v_raw"]["quality"],
                                    stated_confidence=conf.get(r["name"]), reason=r.get("infeasible_reason"))) + "\n")
    M = [f"# Branch run on a real task: {os.path.basename(task)} ({time.strftime('%Y-%m-%d %H:%M')})", "",
         f"Task: `{task}` (SPEC.md + empty stub). Hidden check: {os.path.basename(hidden)} (the agents never saw it). "
         f"Every branch ran on its own copy; original unchanged: **{rec['invariant_ok']}**. Branch record: `data_user/gov/branches/{rec['id']}.json`.", "",
         "| branch (agent) | vendor / model | stated confidence | hidden check passed | quality | lines changed | NI's reason |", "|---|---|---|---|---|---|---|"]
    for a in agents:
        r = by[a["name"]]; v = r["v_raw"]
        M.append(f"| {a['name']} | {a['vendor']} | {a.get('confidence', '-')} | {'yes' if r['feasible'] else 'no'} | {v['quality']:.2f} | "
                 f"{int(-v['compact'])} | {r['kept_because']} |")
    M += ["", "| policy | picks | hidden-check quality of the pick |", "|---|---|---|"]
    for name, pick in rows:
        M.append(f"| {name} | {pick or 'nothing (no usable answer)'} | {'-' if pick is None else f'{q(pick):.2f}'} |")
    M += ["", f"Best achievable quality among the branches: {best_q:.2f}. NI verdict: **{rec['verdict']}**"
          + (f"; P_best {rec['p_best']}" if rec.get("p_best") else "") + ".", "", "NI's message:", "", "```", rec["message"], "```", "",
          "Honest reading: NI's advantage here comes from RUNNING the check on every branch instead of trusting one agent or a stated "
          "confidence. One task is a demonstration, not evidence; the claim needs many tasks (section 5.1 test).", ""]
    open(report, "w", encoding="utf-8").write("\n".join(M) + "\n")
    print("\n".join(M))
    return dict(task=os.path.basename(task), run=rec["id"], verdict=rec["verdict"], ni=ni, first=first, most_confident=most,
                p_best=rec.get("p_best") or {}, invariant_ok=rec["invariant_ok"],
                quality={r["name"]: r["v_raw"]["quality"] for r in rec["branches"]},
                passed={r["name"]: bool(r["feasible"]) for r in rec["branches"]}, confidence=conf)


if __name__ == "__main__":
    main(*sys.argv[1:5])
