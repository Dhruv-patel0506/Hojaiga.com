"""Continuous NI scheduler: keeps the GPU/CPU as busy as is SAFE, forever.

  python ni_sched.py            # run (detached) - loops until the file SCHED_STOP appears
  python ni_sched.py --status   # table of jobs / running processes / GPU memory
  python ni_sched.py --stop-all # kill every job it launched (by PID tree) and exit

Rules (each one exists because of something that broke):
  * GPU admission: a GPU job starts only if  max(GPU memory used over the last 5 min) + job_peak + context <= GPU_BUDGET.
    Last night and again at 14:10 runs froze when the 6 GB card was ~5.6 GB full, so the budget leaves headroom.
    job_peak comes from MEASURED peaks in runs/*/metrics.jsonl (vram_peak_gb); unknown tasks use a conservative size formula.
  * CPU jobs (hand-feature baselines, graphs) start only while overall CPU use is below CPU_LIMIT and fewer than MAX_CPU_JOBS run.
  * A task is never trained by two processes at once (command lines of ALL running ni_run.py are scanned, managed or not).
  * A job whose log has not been written for STALE_S seconds is killed (PID tree, never by image name) and restarted with --resume.
  * Segments are SEGMENT_H hours; every restart passes --resume so cycle counter, meta-weights and the inner net continue.
  * New encoded datasets (data_enc/enc/**.npz, graph hand features) get jobs automatically ("auto planning").
"""
import os, sys, json, time, glob, subprocess, ctypes, argparse, collections
from ni_common import ROOT, RUNS, log, set_logfile

PY = sys.executable
# CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP. NOT DETACHED_PROCESS: Windows ignores NO_WINDOW when DETACHED is set, and the
# venv python.exe is a stub that starts the real interpreter - with no console to inherit, that child opens a VISIBLE one
# (one terminal window per job). With NO_WINDOW alone the stub gets one hidden console that the real interpreter inherits.
NO_WINDOW = 0x08000000 | 0x00000200
JOBS_F = os.path.join(ROOT, "ni_jobs.json"); STATE_F = os.path.join(ROOT, "sched_state.json"); STOP_F = os.path.join(ROOT, "SCHED_STOP")
GPU_BUDGET_GB, CTX_GB = 4.0, 0.35          # 15:50: CUDA 'illegal memory access' / 'unspecified launch failure' killed 4 runs at once (42 nvlddmkm
GPU_COOLDOWN_S, MAX_GPU_PROCS = 240, 2      # driver errors/hour): the card is unstable under multi-process load, so keep GPU work small and the rest on CPU
MAX_CPU_JOBS, CPU_LIMIT = 5, 0.85
SMALL_NPZ_MB = 100                          # tasks whose feature file is smaller than this train fine on the CPU
GPU_SEGMENT_H, STARVE_S = 1.0, 7200         # a GPU job that never ran and waited this long makes the scheduler stop launching other GPU jobs
STALE_S, LOOP_S, SEGMENT_H = 900, 45, 2.0
ENC_DIR = os.path.join(ROOT, "data_enc")


# ------------------------------------------------------------------ system probes
def gpu_used_gb():
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=15).stdout
        return float(o.strip().splitlines()[0]) / 1024.0
    except Exception:
        return None


class _FT(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


def _times():
    i, k, u = _FT(), _FT(), _FT()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
    v = lambda f: (f.hi << 32) | f.lo
    return v(i), v(k) + v(u)          # idle, busy(kernel includes idle) -> total = k+u


def pid_alive(pid):
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)); ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259


def kill_tree(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def running_ni_runs(script="ni_run.py"):
    """[(pid, tasks_set, run_id)] for every `script` process, launched by us or not."""
    ps = "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match '" + script + "' } | ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"
    try:
        o = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return []
    out = []
    for line in o.splitlines():
        if "\t" not in line:
            continue
        pid, cmd = line.split("\t", 1); t = set()
        parts = cmd.split()
        for i, p in enumerate(parts):
            if p == "--tasks" and i + 1 < len(parts):
                t = set(parts[i + 1].split(","))
        rid = parts[parts.index("--run-id") + 1] if "--run-id" in parts else "?"
        out.append((int(pid), t, rid))
    return out


# ------------------------------------------------------------------ VRAM estimates
_vt = dict(t=0, v={})


def vram_table():
    if time.time() - _vt["t"] < 600 and _vt["v"]:
        return _vt["v"]
    best = {}
    for mf in glob.glob(os.path.join(RUNS, "*", "metrics.jsonl")):
        try:
            sz = os.path.getsize(mf)
            with open(mf, "rb") as f:
                f.seek(max(0, sz - 300_000)); lines = f.read().decode("utf-8", "ignore").splitlines()[1:]
            for ln in lines:
                try:
                    r = json.loads(ln); v = r["outer"]["vram_peak_gb"]; k = r["task"]
                    best[k] = max(best.get(k, 0.0), float(v))
                except Exception:
                    pass
        except Exception:
            pass
    _vt.update(t=time.time(), v=best)
    return best


def est_task_vram(key):
    t = vram_table()
    if key in t and t[key] > 0:
        return t[key] * 1.15 + 0.05
    p = os.path.join(ENC_DIR, key.replace("/", os.sep) + ".npz")
    gb = os.path.getsize(p) / 1e9 if os.path.exists(p) else 0.5
    return min(4.5, 0.5 + 6.0 * gb)          # conservative; replaced by the measured peak after the first run


def est_job_vram(job):
    return max(est_task_vram(k) for k in job["tasks"]) if job["tasks"] else 1.0


# ------------------------------------------------------------------ jobs
def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(p, obj):
    tmp = p + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, p)


def encoded_keys():
    """Tasks that can be trained: encoder embeddings, plus hand features where no encoder exists (graphs)."""
    ks = []
    for p in glob.glob(os.path.join(ENC_DIR, "enc", "*", "*.npz")):
        if "__smoke" not in p:
            ks.append("enc/" + os.path.relpath(p, os.path.join(ENC_DIR, "enc")).replace("\\", "/")[:-4])
    for p in glob.glob(os.path.join(ENC_DIR, "enc2", "*", "*.npz")):          # stronger-encoder A/B set (bge-base, dinov2-base, ...)
        if "__smoke" not in p:
            ks.append("enc2/" + os.path.relpath(p, os.path.join(ENC_DIR, "enc2")).replace("\\", "/")[:-4])
    for p in glob.glob(os.path.join(ENC_DIR, "hand", "graph", "*.npz")):       # old-style graph features only where no WL fingerprint exists
        if "__smoke" not in p and not os.path.exists(os.path.join(ENC_DIR, "enc", "graph", os.path.basename(p))):
            ks.append("hand/graph/" + os.path.basename(p)[:-4])
    return sorted(ks)


def task_device(key):
    """CPU for hand-feature baselines, graphs and any task whose feature file is small; GPU only for the big ones."""
    if key.startswith("hand/") or "/graph/" in key:
        return "cpu"
    p = os.path.join(ENC_DIR, key.replace("/", os.sep) + ".npz")
    return "cpu" if os.path.exists(p) and os.path.getsize(p) / 1e6 < SMALL_NPZ_MB else "gpu"


def autoplan(jobs):
    covered = {k for j in jobs for k in j["tasks"]}
    new = [k for k in encoded_keys() if k not in covered]
    if not new:
        return False
    by_dev = collections.defaultdict(list)
    for k in new:
        by_dev[task_device(k)].append(k)
    for dev, ks in by_dev.items():
        ks.sort(key=est_task_vram); cur = []
        for k in ks:
            if cur and (len(cur) >= 4 or est_task_vram(k) > 1.8 or max(est_task_vram(c) for c in cur) > 1.8):
                jobs.append(dict(name=f"auto_{dev}_{len(jobs):03d}", tasks=cur, device=dev, segment_hours=SEGMENT_H, priority=1)); cur = []
            cur.append(k)
        if cur:
            jobs.append(dict(name=f"auto_{dev}_{len(jobs):03d}", tasks=cur, device=dev, segment_hours=SEGMENT_H, priority=1))
    log("[sched] auto-planned jobs for new tasks:", new)
    return True


def pending_encodes(st):
    """[(name, kind)]: hub-registered datasets with no embedding yet (kind enc), then datasets that have enc but no stronger-encoder
    embedding (kind enc2: text/image/video only, smallest first so results arrive early)."""
    reg = load_json(os.path.join(ROOT, "data_user", "hub_registry.json"), {}); out = []
    reg.update(load_json(os.path.join(ROOT, "data_user", "extra_tasks.json"), {}))      # tasks with their own source in ni_encode.TASKS (video folders)
    fails = st.get("_encfail", {})
    for name, spec in reg.items():
        if not spec.get("ok"):
            continue
        if not os.path.exists(os.path.join(ENC_DIR, "enc", name.replace("/", os.sep) + ".npz")) and fails.get(name, 0) < 2:
            out.append((name, "enc"))
    order = {"graph": 0, "video": 1, "text": 2, "audio": 3, "image": 4}; e2 = []    # graph enc2 is CPU-only and cheap, so it goes first
    for p in glob.glob(os.path.join(ENC_DIR, "enc", "*", "*.npz")):
        rel = os.path.relpath(p, os.path.join(ENC_DIR, "enc")).replace("\\", "/")[:-4]; mod = rel.split("/")[0]
        if mod not in order or "__smoke" in p or os.path.exists(os.path.join(ENC_DIR, "enc2", rel.replace("/", os.sep) + ".npz")):
            continue
        if fails.get(rel + "#enc2", 0) < 2:
            e2.append((order[mod], os.path.getsize(p), rel))
    out += [(rel, "enc2") for _, _, rel in sorted(e2)]
    return out


def enc_rows(name):
    """Approximate number of items of an encoded dataset (feature file size / bytes per row)."""
    p = os.path.join(ENC_DIR, "enc", name.replace("/", os.sep) + ".npz")
    dim = {"text": 384, "image": 768, "audio": 768, "video": 1536}.get(name.split("/")[0], 512)
    return os.path.getsize(p) / (4.0 * dim) if os.path.exists(p) else 1e9


def launch_encode(name, st, cpu=False, kind="enc"):
    out = open(os.path.join(ENC_DIR, "sched_encode.out.txt"), "a"); err = open(os.path.join(ENC_DIR, "sched_encode.err.txt"), "a")
    env = os.environ.copy(); env["NI_ENCODE_FROM_SCHED"] = "1"
    if cpu:
        env["CUDA_VISIBLE_DEVICES"] = "-1"; env["OMP_NUM_THREADS"] = "8"
    args = [PY, "-u", "ni_encode.py", "--tasks", name] + (["--kinds", "enc2"] if kind == "enc2" else [])
    p = subprocess.Popen(args, cwd=ROOT, env=env, stdout=out, stderr=err, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    st["_enc"] = dict(name=name, kind=kind, pid=p.pid, started=time.time())
    log(f"[sched] ENCODE[{kind}] {name} pid {p.pid} on {'CPU' if cpu else 'GPU'}")


def launch(job, st):
    dev = job["device"]; est = est_job_vram(job); run_id = job["name"]
    env = os.environ.copy(); env["NI_ALGO"] = job.get("algo", "v4")
    if dev == "cpu":
        env["CUDA_VISIBLE_DEVICES"] = "-1"; env["OMP_NUM_THREADS"] = str(job.get("threads", 4))
    else:
        env["NI_VRAM_FRAC"] = f"{min(0.92, (est * 1.3 + CTX_GB) / 6.14):.3f}"
    seg = job.get("segment_hours", SEGMENT_H)
    if dev == "gpu":
        seg = min(seg, GPU_SEGMENT_H)          # GPU slots rotate hourly so big jobs are not starved by small ones
    job["runs"] = job.get("runs", 0) + 1
    args = [PY, "-u", "ni_run.py", "--tasks", ",".join(job["tasks"]), "--hours", str(seg), "--run-id", run_id, "--resume"]
    out = open(os.path.join(RUNS, run_id + ".out.txt"), "a"); err = open(os.path.join(RUNS, run_id + ".err.txt"), "a")
    p = subprocess.Popen(args, cwd=ROOT, env=env, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                         creationflags=NO_WINDOW)
    st[job["name"]] = dict(pid=p.pid, started=time.time(), device=dev, est=round(est, 2))
    log(f"[sched] START {run_id} ({dev}, est {est:.2f} GB) pid {p.pid} tasks={job['tasks']}")


def log_tail(path, n=3000):
    try:
        sz = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, sz - n)); return f.read().decode("utf-8", "ignore")
    except Exception:
        return ""


def status_table():
    jobs = load_json(JOBS_F, []); st = load_json(STATE_F, {})
    print(f"GPU used: {gpu_used_gb()} GB   (budget {GPU_BUDGET_GB})")
    for j in jobs:
        s = st.get(j["name"]); alive = bool(s and pid_alive(s["pid"]))
        lp = os.path.join(RUNS, j["name"], "log.txt"); age = int(time.time() - os.path.getmtime(lp)) if os.path.exists(lp) else None
        print(f"{j['name']:18} {j['device']:3} {'RUNNING' if alive else 'idle   '} est={est_job_vram(j):.2f}GB log_age={age}s fails={j.get('fails', 0)} "
              f"{'DISABLED ' if j.get('disabled') else ''}{','.join(j['tasks'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true"); ap.add_argument("--stop-all", action="store_true")
    a = ap.parse_args()
    if a.status:
        status_table(); return
    st = load_json(STATE_F, {})
    if a.stop_all:
        for n, s in st.items():
            if isinstance(s, dict) and "pid" in s and pid_alive(s["pid"]):
                kill_tree(s["pid"]); print("killed", n, s["pid"])
        return
    set_logfile(os.path.join(ROOT, "sched_log.txt")); os.makedirs(RUNS, exist_ok=True)
    if os.path.exists(STOP_F):
        os.remove(STOP_F)
    log(f"[sched] up. budget {GPU_BUDGET_GB} GB GPU, {MAX_CPU_JOBS} cpu jobs, segment {SEGMENT_H} h, stale {STALE_S}s")
    gpu_hist = collections.deque(maxlen=int(300 / LOOP_S) + 2); prev_t = _times(); cpu_hist = collections.deque(maxlen=4)
    while not os.path.exists(STOP_F):
        try:
            jobs = load_json(JOBS_F, [])
            if autoplan(jobs):
                save_json(JOBS_F, jobs)
            u = gpu_used_gb()
            if u is not None:
                gpu_hist.append(u)
            t = _times(); di, dt = t[0] - prev_t[0], t[1] - prev_t[1]; prev_t = t
            if dt > 0:
                cpu_hist.append(1.0 - di / dt)
            cpu_u = sum(cpu_hist) / len(cpu_hist) if cpu_hist else 0.0
            runs = running_ni_runs(); busy_tasks = set().union(*[r[1] for r in runs]) if runs else set()
            now = time.time(); changed = False
            for j in jobs:                                           # 1) supervise our own jobs
                s = st.get(j["name"])
                if not s:
                    continue
                alive = pid_alive(s["pid"]); lp = os.path.join(RUNS, j["name"], "log.txt")
                age = now - os.path.getmtime(lp) if os.path.exists(lp) else 1e9
                if alive and now - s["started"] > STALE_S and age > STALE_S:
                    log(f"[sched] STALE {j['name']}: no log for {age:.0f}s -> kill pid {s['pid']} and restart later")
                    kill_tree(s["pid"]); alive = False; j["stalls"] = j.get("stalls", 0) + 1; j["not_before"] = now + 60; changed = True
                if not alive:
                    tail = log_tail(lp); dur = now - s["started"]
                    if "RUN COMPLETE" in tail:
                        j["fails"] = 0; log(f"[sched] segment complete {j['name']} after {dur / 3600:.2f} h")
                    elif dur < 300:
                        j["fails"] = j.get("fails", 0) + 1; j["not_before"] = now + 600 * j["fails"]
                        log(f"[sched] {j['name']} died after {dur:.0f}s (fail {j['fails']}); backoff {600 * j['fails'] // 60} min. err: {log_tail(os.path.join(RUNS, j['name'] + '.err.txt'), 300)[-200:]!r}")
                        if j["fails"] >= 5:
                            j["disabled"] = True; log(f"[sched] DISABLED {j['name']} after 5 quick failures")
                    if j["device"] == "gpu" and tail.count("OOM") >= 3:
                        j["device"] = "cpu"; log(f"[sched] {j['name']}: repeated CUDA OOM -> moved to CPU")
                    st.pop(j["name"], None); changed = True
            fresh = [s for s in st.values() if isinstance(s, dict) and s.get("device") == "gpu" and now - s.get("started", 0) < 300]
            reserve = sum(s.get("est", 0.0) for s in fresh)
            last_gpu_launch = max([s.get("started", 0) for s in st.values() if isinstance(s, dict) and s.get("device") == "gpu"] + [0])
            # 1b) encode stage: one hub dataset at a time (needs ~1.6 GB on the GPU for the encoder + batches)
            e = st.get("_enc")
            if e and not pid_alive(e["pid"]):
                ek = e.get("kind", "enc")
                if not os.path.exists(os.path.join(ENC_DIR, ek, e["name"].replace("/", os.sep) + ".npz")):
                    fk = e["name"] + ("#enc2" if ek == "enc2" else "")
                    st.setdefault("_encfail", {})[fk] = st.get("_encfail", {}).get(fk, 0) + 1
                    log(f"[sched] encode[{ek}] of {e['name']} produced no file (fail {st['_encfail'][fk]})")
                st.pop("_enc", None); changed = True
            if "_enc" not in st and not running_ni_runs("ni_encode.py"):
                for nm, kind in pending_encodes(st):                 # first pending dataset that fits (no head-of-line blocking)
                    mod = nm.split("/")[0]
                    need = {"graph": 0.0, "text": 0.8, "image": 1.2, "audio": 1.6, "video": 2.0}.get(mod, 1.6)   # graph features are CPU-only
                    if kind == "enc2":
                        need = {"text": 1.3, "image": 2.0, "video": 3.0, "audio": 2.0, "graph": 0.0}.get(mod, 2.0)
                    if need == 0.0 or (gpu_hist and max(gpu_hist) + reserve + need + CTX_GB <= GPU_BUDGET_GB and now - last_gpu_launch >= 120):
                        launch_encode(nm, st, cpu=(need == 0.0), kind=kind); changed = True; break
                    if mod == "text" and cpu_u < 0.7 and (kind == "enc" or enc_rows(nm) < 25000):   # small text sets are fine on the CPU
                        launch_encode(nm, st, cpu=True, kind=kind); changed = True; break
            # 2) admit new jobs: highest priority first, least recently run first; one launch per loop
            managed_cpu = sum(1 for j in jobs if j["name"] in st and j["device"] == "cpu")
            cand = [j for j in jobs if j["name"] not in st and not j.get("disabled") and now >= j.get("not_before", 0)
                    and not (set(j["tasks"]) & busy_tasks)]
            cand.sort(key=lambda j: (j.get("priority", 5), j.get("last_end", 0)))
            used_peak = max(gpu_hist) if gpu_hist else 0.0
            # memory of managed jobs launched in the last 5 min may not be visible yet: reserve their estimate on top of the reading
            fresh = [s for n, s in st.items() if isinstance(s, dict) and s.get("device") == "gpu" and now - s.get("started", 0) < 300]
            reserve = sum(s.get("est", 0.0) for s in fresh)
            gpu_procs = sum(1 for s in st.values() if isinstance(s, dict) and s.get("device") == "gpu" and "pid" in s and pid_alive(s["pid"]))
            last_gpu_launch = max([s.get("started", 0) for s in st.values() if isinstance(s, dict) and s.get("device") == "gpu"] + [0])
            for j in jobs:
                j.setdefault("created", now)
            starving = [j for j in cand if j["device"] == "gpu" and j.get("runs", 0) == 0 and now - j["created"] > STARVE_S]
            for j in cand:
                if j["device"] == "gpu":
                    est = est_job_vram(j)
                    if starving and j["name"] not in {s["name"] for s in starving}:
                        continue                  # drain: let running GPU jobs finish their segment so the starving job can fit
                    if (used_peak + reserve + est + CTX_GB <= GPU_BUDGET_GB and u is not None and gpu_procs < MAX_GPU_PROCS
                            and now - last_gpu_launch >= GPU_COOLDOWN_S):
                        launch(j, st); j["last_end"] = now; changed = True; break
                elif managed_cpu < MAX_CPU_JOBS and cpu_u < CPU_LIMIT:
                    launch(j, st); j["last_end"] = now; changed = True; break
            if changed:
                save_json(JOBS_F, jobs); save_json(STATE_F, st)
        except Exception as e:
            import traceback
            log("[sched] loop error:", traceback.format_exc()[-500:])
        time.sleep(LOOP_S)
    log("[sched] stop file seen; leaving jobs running and exiting")


if __name__ == "__main__":
    main()
