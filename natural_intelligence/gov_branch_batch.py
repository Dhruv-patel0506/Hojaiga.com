"""Branch engine on a BATCH of real tasks with real agents: the many-task test that one task could not give.

For every task (data_user/gov/tasks/<task>/ = SPEC.md + stub; <task>_hidden/test_*.py = the check the agents never see):
  1. each agent works on its own copy of the task folder (OpenCode CLI, one free model per agent), in parallel;
  2. gov_branch_task runs the branch engine on what they produced (every branch measured by the hidden check);
  3. the pick of each policy is scored by the hidden check.
Policies compared on the same branches:
  single agent      - use one agent without checking (reported per agent, and as the mean over agents = a random pick)
  most confident    - use the agent that states the highest CONFIDENCE (ties -> listed first)
  NI branch engine  - recommend with proof; cross_question -> scored on its P_best leader and counted as one human ask;
                      no_feasible_branch -> NI ships nothing (counted as no pass, but also as no broken code shipped)
  oracle            - the best branch in hindsight (upper bound)
Metrics per policy: pass = the pick passes every hidden check; broken = it ships code that fails a check; quality = k/N.
Paired bootstrap over tasks (10 000 resamples) for NI minus each baseline.

Run: venv\\Scripts\\python.exe -X utf8 natural_intelligence\\gov_branch_batch.py <work_root> <report.md> task1 task2 ...
"""
import os, sys, json, re, shutil, subprocess, time, random, hashlib
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gov_branch_task, gov_ledger

TASKS = os.path.join(gov_ledger.GOV_DIR, "tasks")
OPENCODE = os.path.expandvars(r"%APPDATA%\npm\node_modules\opencode-ai\bin\opencode.exe")
AGENTS = [("opencode_deepseek", "opencode/deepseek-v4.1-flash-free"), ("opencode_glm", "opencode/glm-5.3-flash-free"),
          ("opencode_mimo", "opencode/mimo-v2.6-flash-free"), ("opencode_nemotron", "opencode/nemotron-3.5-lightning-free")]
PROMPT = ("Read SPEC.md in the current folder and implement it by editing {files} (that file only; standard library only). "
          "When you are done, end your final reply with one line exactly like CONFIDENCE: 85 (0-100, how sure you are "
          "that the code is fully correct).")
TIMEOUT = 900
if os.environ.get("NI_BATCH_AGENTS"):                                             # "name=model,name=model" overrides the agent set
    AGENTS = [tuple(x.split("=", 1)) for x in os.environ["NI_BATCH_AGENTS"].split(",") if "=" in x]
QUOTA = "usage limit"                                                             # OpenCode free tier: only visible with --print-logs


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else None


def task_files(task):
    return sorted(f for f in os.listdir(os.path.join(TASKS, task)) if f.endswith(".py"))


WORKERS = int(os.environ.get("NI_BATCH_WORKERS", "4"))
RETRIES = int(os.environ.get("NI_BATCH_RETRIES", "0"))                               # extra tries when a run times out with nothing written
KEEP = [x for x in os.environ.get("NI_BATCH_KEEP", "").split(",") if x]           # agents whose earlier result is reused, not rerun
KEEP_FROM = os.environ.get("NI_BATCH_FROM", "")                                   # root of the earlier run that holds those results


def run_agent(task, name, model, root):
    if name in KEEP and KEEP_FROM:
        old = json.load(open(os.path.join(KEEP_FROM, task, "agents.json"), encoding="utf-8"))["agents"]
        a = dict(next(x for x in old if x["name"] == name))
        work = os.path.join(root, task, name)
        if os.path.isdir(work):
            shutil.rmtree(work)
        shutil.copytree(a["dir"], work)
        a["dir"] = work; a["reused_from"] = KEEP_FROM
        return a
    for attempt in range(RETRIES + 1):
        a = _run_agent_once(task, name, model, root)
        if not (a.get("failed") and ("timeout" in a["failed"] or "usage limit" in a["failed"])) or attempt == RETRIES:
            a["attempts"] = attempt + 1
            return a
        time.sleep(60)


def _run_agent_once(task, name, model, root):
    src = os.path.join(TASKS, task)
    work = os.path.join(root, task, name)
    if os.path.isdir(work):
        shutil.rmtree(work)
    shutil.copytree(src, work)
    files = task_files(task)
    before = {f: _sha(os.path.join(work, f)) for f in files}
    # OpenCode keeps one SQLite store per data dir; parallel runs on the person's own store fail with "database is locked"
    # (seen on the first attempt). Each job gets its own data dir holding only a copy of the auth file.
    data = os.path.join(root, "_ocdata", f"{task}_{name}")
    os.makedirs(os.path.join(data, "opencode"), exist_ok=True)
    auth = os.path.join(os.path.expanduser("~"), ".local", "share", "opencode", "auth.json")
    if os.path.isfile(auth):
        shutil.copy2(auth, os.path.join(data, "opencode", "auth.json"))
    env = dict(os.environ, XDG_DATA_HOME=data)
    t0 = time.time(); rc = None; err = ""; quota = False
    logf = work + ".log.txt"
    with open(logf, "w", encoding="utf-8") as lf:
        p = subprocess.Popen([OPENCODE, "run", "--print-logs", "--dir", work, "-m", model, "--auto", PROMPT.format(files=", ".join(files))],
                             cwd=work, stdout=subprocess.PIPE, stderr=lf, text=True, encoding="utf-8", errors="replace",
                             stdin=subprocess.DEVNULL, env=env)
        import threading
        buf = []
        th = threading.Thread(target=lambda: buf.append(p.stdout.read()), daemon=True); th.start()
        while p.poll() is None:
            time.sleep(5)
            try:
                if QUOTA in open(logf, encoding="utf-8", errors="replace").read():
                    quota = True
            except OSError:
                pass
            if quota or time.time() - t0 > TIMEOUT:
                p.kill(); break                                                    # this run's own process only
        p.wait(); th.join(10)
        rc, out = p.returncode, (buf[0] if buf else "")
    if quota:
        err = "provider free usage limit reached"
    elif time.time() - t0 > TIMEOUT:
        err = f"timeout after {TIMEOUT}s"
    secs = time.time() - t0
    open(work + ".out.txt", "w", encoding="utf-8").write(out or "")
    open(work + ".err.txt", "w", encoding="utf-8").write(err or "")
    changed = any(_sha(os.path.join(work, f)) != before[f] for f in files)
    m = re.findall(r"CONFIDENCE:\s*(\d{1,3})", out or "")
    conf = min(100, int(m[-1])) if m else None
    leak = "_hidden" in (out or "") + (err or "")                                  # did the agent go looking for the hidden check?
    extra = sorted(set(os.listdir(work)) - set(os.listdir(src)) - {".opencode"})
    a = dict(name=name, vendor=f"OpenCode + {model.split('/')[-1]}", dir=work, secs=round(secs, 1), rc=rc,
             leak_suspect=leak, extra_files=extra)
    if conf is not None:
        a["confidence"] = conf
    if not changed:
        a["failed"] = "left the stub unchanged" + (f" ({err.strip()[-160:]})" if err.strip() else "")
    return a


def boot(diff, n=10000, seed=0):
    r = random.Random(seed); k = len(diff)
    if k == 0:
        return None, None, None
    ms = sorted(sum(diff[r.randrange(k)] for _ in range(k)) / k for _ in range(n))
    return sum(diff) / k, ms[int(0.025 * n)], ms[int(0.975 * n) - 1]


def sign_p(w, l):
    from math import comb
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def failed_checks(task, work):
    hd = os.path.join(TASKS, task + "_hidden")
    hidden = os.path.join(hd, [f for f in os.listdir(hd) if f.startswith("test_")][0])
    p = subprocess.run([sys.executable, "-X", "utf8", hidden], cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace")
    f = [ln[8:] for ln in p.stdout.splitlines() if ln.startswith("FAILED: ")]
    return f or [((p.stderr or "").strip().splitlines() or ["no output"])[-1][:200]]


def main(root, report, tasks):
    os.makedirs(root, exist_ok=True)
    jobs = [(t, n, m) for t in tasks for n, m in AGENTS]                            # task-major: each wave = 4 different models
    with ThreadPoolExecutor(WORKERS) as ex:
        res = list(ex.map(lambda j: (j[0], run_agent(j[0], j[1], j[2], root)), jobs))
    by_task = {}
    for t, a in res:
        by_task.setdefault(t, []).append(a)
    S = []
    for t in tasks:
        af = os.path.join(root, t, "agents.json")
        json.dump(dict(files=task_files(t), agents=by_task[t]), open(af, "w", encoding="utf-8"), indent=1)
        hd = os.path.join(TASKS, t + "_hidden")
        hidden = os.path.join(hd, [f for f in os.listdir(hd) if f.startswith("test_")][0])
        s = gov_branch_task.main(os.path.join(TASKS, t), hidden, af, os.path.join(root, t, "REPORT.md"))
        s["agents"] = by_task[t]
        S.append(s)
    json.dump(S, open(os.path.join(root, "batch.json"), "w", encoding="utf-8"), indent=1, default=str)
    write_report(S, report)


def picks(s):
    names = [a["name"] for a in s["agents"]]
    ni, asked = s["ni"], False
    if s["verdict"] == "cross_question" and s["p_best"]:
        ni, asked = max(s["p_best"], key=s["p_best"].get), True
    best = max(names, key=lambda n: (s["passed"][n], s["quality"][n]))
    out = {"NI branch engine": ni, "most confident agent": s["most_confident"], "oracle (best in hindsight)": best}
    for n in names:
        out[f"single agent: {n}"] = n
    return out, asked


def score(s, pick):
    if pick is None:
        return dict(passed=0.0, broken=0.0, quality=0.0)
    p = s["passed"][pick]
    return dict(passed=float(p), broken=float(not p), quality=s["quality"][pick])


def write_report(S, report):
    allnames = list(dict.fromkeys(a["name"] for s in S for a in s["agents"]))   # agent sets may differ between tasks
    names = [n for n in allnames if all(n in s["passed"] for s in S)]            # single-agent rows: agents present on every task
    rows = {}; asks = 0
    for s in S:
        pk, asked = picks(s); asks += asked
        for pol, pick in pk.items():
            if pol.startswith("single agent: ") and pol[14:] not in names:
                continue
            rows.setdefault(pol, []).append(score(s, pick))
        here = [a["name"] for a in s["agents"]]
        rows.setdefault("random single agent (mean over agents)", []).append(
            {k: sum(score(s, n)[k] for n in here) / len(here) for k in ("passed", "broken", "quality")})
    T = len(S)
    M = [f"# Branch engine on a batch of {T} real tasks ({time.strftime('%Y-%m-%d %H:%M')})", "",
         "Each task: SPEC.md + empty stub given to every agent on its own copy; scored by a hidden check the agents never saw "
         "(each check proven first: reference passes fully, stub fails).", "",
         "## Branches (hidden-check result per agent)", "",
         "| task | " + " | ".join(allnames) + " | NI verdict | NI pick |", "|---|" + "---|" * (len(allnames) + 2)]
    for s in S:
        cell = lambda n: ("-" if n not in s["passed"] else f"{s['quality'][n]:.2f}{' ok' if s['passed'][n] else ''}"
                          + (f" (c{s['confidence'][n]})" if s["confidence"].get(n) is not None else ""))
        M.append(f"| {s['task']} | " + " | ".join(cell(n) for n in allnames) + f" | {s['verdict']} | {s['ni'] or '-'} |")
    M += ["", "Cell = hidden-check quality (passed/total); `ok` = passed every check; (cN) = the agent's stated confidence.", "",
          "## Policies (same branches, scored by the hidden checks)", "",
          "| policy | tasks shipped fully correct | tasks shipped with a failing check | mean quality |", "|---|---|---|---|"]
    order = ["NI branch engine", "most confident agent", "random single agent (mean over agents)"] + \
            [f"single agent: {n}" for n in names] + ["oracle (best in hindsight)"]
    for pol in order:
        r = rows[pol]
        M.append(f"| {pol} | {sum(x['passed'] for x in r):.2f} / {T} | {sum(x['broken'] for x in r):.2f} / {T} | "
                 f"{sum(x['quality'] for x in r) / T:.3f} |")
    M += ["", f"NI asked the human on {asks} of {T} tasks (cross_question).", "",
          "## NI minus baseline, paired bootstrap over tasks (10 000 resamples, 95% interval)", "",
          "| baseline | metric | mean difference | 95% interval | reading |", "|---|---|---|---|---|"]
    for base in ["most confident agent", "random single agent (mean over agents)"]:
        for k in ("passed", "broken", "quality"):
            d = [a[k] - b[k] for a, b in zip(rows["NI branch engine"], rows[base])]
            m, lo, hi = boot(d)
            better = (m > 0) if k != "broken" else (m < 0)
            read = "interval spans 0: not shown" if lo <= 0 <= hi else ("NI better" if better else "NI worse")
            M.append(f"| {base} | {k} | {m:+.3f} | [{lo:+.3f}, {hi:+.3f}] | {read} |")
    M += ["", "Exact sign test (tasks where NI's pick scored higher vs lower than the baseline's; ties dropped). With few tasks "
          "the percentile bootstrap is optimistic, so this is the stricter reading:", "",
          "| baseline | NI higher | NI lower | two-sided p |", "|---|---|---|---|"]
    for base in ["most confident agent", "random single agent (mean over agents)"]:
        d = [a["quality"] - b["quality"] for a, b in zip(rows["NI branch engine"], rows[base])]
        w, l = sum(x > 1e-12 for x in d), sum(x < -1e-12 for x in d)
        M.append(f"| {base} | {w} | {l} | {sign_p(w, l):.3f} |")
    M += ["", "## What the failing branches got wrong (hidden-check lines)", ""]
    for s in S:
        for a in s["agents"]:
            if not s["passed"][a["name"]]:
                M.append(f"- {s['task']} / {a['name']} (stated confidence {a.get('confidence', '-')}): "
                         + "; ".join(failed_checks(s["task"], a["dir"])[:6]))
    leaks = [(s["task"], a["name"]) for s in S for a in s["agents"] if a.get("leak_suspect")]
    extra = [(s["task"], a["name"], a["extra_files"]) for s in S for a in s["agents"] if a.get("extra_files")]
    M += ["", "## Integrity", "",
          f"- Original task folders unchanged by every branch: {all(s['invariant_ok'] for s in S)}.",
          f"- Agents whose output mentions the hidden folder (possible peeking): {leaks or 'none'}.",
          f"- Extra files agents created against the spec (ignored by the branch copy): {extra or 'none'}.",
          f"- Mean agent wall time: {sum(a['secs'] for s in S for a in s['agents']) / sum(len(s['agents']) for s in S):.0f} s.", "",
          "Honest reading: with this many tasks, a difference whose interval spans 0 is not evidence. The tasks were written "
          "by the same author as the checks (me), from NI's own needs; they are small single-file functions, not real "
          "repository work."]
    open(report, "w", encoding="utf-8").write("\n".join(M) + "\n")
    print("\n".join(M))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
