"""Overnight orchestrator: fill -> OUTER training -> INNER training on the outer's outcomes -> feedback, repeat.

Cycle 0 is the outer-only bootstrap (user's rule: outer first, inner after): every phase's outer rounds run,
their outcomes are collected, and only then is the inner brain trained on that dataset.
Cycles >= 1 interleave: outer round -> inner assesses (self-question + JEV) -> feedback -> inner learns.
"""
import os, sys, json, time, argparse, threading, traceback
import numpy as np
import torch
from ni_common import RUNS, VRAM_LIMIT_GB, set_logfile, log, seed_for, write_json
import ni_fill, ni_data
from ni_data import PHASES, MODALITIES, load_task
from ni_outer import OuterBrain, NAMES
from ni_inner import InnerBrain, build_features

STOP = threading.Event()


READY = threading.Event()
STAGES = [dict(t=10, i=3, a=3, v=2), dict(t=40, i=12, a=9, v=5), dict(t=80, i=25, a=9, v=5), dict(t=120, i=50, a=9, v=5)]


def filler_thread(smoke, only=None):
    for stage, c in enumerate(STAGES):
        if STOP.is_set():
            return
        caps = {"text/ag_news": c["t"], "image/cifar10": c["i"], "audio/urbansound8k": c["a"], "video/hmdb51": c["v"]}
        if smoke:
            caps = {"text/ag_news": 2, "image/cifar10": 1, "audio/urbansound8k": 1, "video/hmdb51": 1}
        if only:
            caps = {k: (v if k.startswith(only + "/") else 0) for k, v in caps.items()}
        try:
            ni_fill.fill(caps, budget_s=3600, graphs=(only in (None, "graph")))
        except Exception as e:
            log("[fill-thread] error", repr(e)[:200])
        READY.set()
        log(f"[fill] stage {stage} complete")
        if smoke:
            return
        for _ in range(30):
            if STOP.is_set():
                return
            time.sleep(10)


def mean_last(rows, f, k=20):
    v = [f(r) for r in rows[-k:]]
    v = [x for x in v if x is not None and not (isinstance(x, float) and np.isnan(x))]
    return float(np.mean(v)) if v else None


def fmt(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def write_report(run_dir, state, metrics, inner, started, notes):
    L = [f"# NI overnight report ({time.strftime('%Y-%m-%d %H:%M')})", "",
         f"- run: `{os.path.basename(run_dir)}`  cycles completed: **{state['cycle']}**  rounds: **{state['rounds']}**  "
         f"elapsed: {(time.time() - started) / 3600:.2f} h  status: **{state['status']}**",
         f"- GPU: {state.get('gpu')}  peak VRAM seen: **{state.get('vram_peak', 0):.2f} / {VRAM_LIMIT_GB} GB**", ""]
    L += ["## Outer brain (ground-truth accuracy on the held-out 30% window, last 20 rounds per task)", "",
          "| task | rounds | vote acc | uniform-weight acc | Logic | Pattern | Verifier | Exploratory | best single | majority-class |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for t in sorted({m["task"] for m in metrics}):
        rs = [m for m in metrics if m["task"] == t]
        pa = {n: mean_last(rs, lambda r: r["outer"]["acc_pred"][n]) for n in NAMES}
        best = max(pa.values())
        L.append(f"| {t} | {len(rs)} | {fmt(mean_last(rs, lambda r: r['outer']['acc_vote']))} | "
                 f"{fmt(mean_last(rs, lambda r: r['outer']['acc_uniform']))} | " + " | ".join(fmt(pa[n]) for n in NAMES) +
                 f" | {fmt(best)} | {fmt(mean_last(rs, lambda r: r['outer']['chance']))} |")
    inn = [m for m in metrics if m.get("inner")]
    L += ["", "## Inner brain (trained only on outer outcomes; judged on samples it never trains on)", ""]
    if inn:
        L += ["| task | rounds | inner AUC | vote-conf AUC | inner ECE | vote-conf ECE | acc kept: inner | acc kept: vote-conf | outer acc (all) | coverage | composite grade |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for t in sorted({m["task"] for m in inn}):
            rs = [m for m in inn if m["task"] == t]
            g = lambda k: mean_last(rs, lambda r: (r["inner"]["selective"] or {}).get(k))
            L.append(f"| {t} | {len(rs)} | {fmt(g('inner_auc'))} | {fmt(g('voteconf_auc'))} | {fmt(g('inner_ece'))} | {fmt(g('voteconf_ece'))} | "
                     f"{fmt(g('acc_by_inner_same_cov'))} | {fmt(g('acc_by_voteconf_same_cov'))} | {fmt(g('outer_acc_all'))} | {fmt(g('cov_final'))} | "
                     f"{fmt(mean_last(rs, lambda r: r['inner']['composite_grade']))} |")
        L += ["", "### JEV sandbox (re-runs the outer brain on perturbed input / leave-one-predictor-out)", "",
              "| task | triggered share | acc of VERIFIED | acc of REJECTED | mean consistency |", "|---|---|---|---|---|"]
        for t in sorted({m["task"] for m in inn}):
            rs = [m for m in inn if m["task"] == t]
            j = lambda k: mean_last(rs, lambda r: (r["inner"]["jev"] or {}).get(k))
            L.append(f"| {t} | {fmt(j('frac_triggered'))} | {fmt(j('acc_verified'))} | {fmt(j('acc_rejected'))} | {fmt(j('consistency_mean'))} |")
        L += ["", "### Four factors (last 20 rounds, mean)", "", "| task | reliability | truthfulness | adaptability | scalability |", "|---|---|---|---|---|"]
        for t in sorted({m["task"] for m in inn}):
            rs = [m for m in inn if m["task"] == t]
            f = lambda k: mean_last(rs, lambda r: r["inner"]["factors"][k])
            L.append(f"| {t} | {fmt(f('reliability'))} | {fmt(f('truthfulness'))} | {fmt(f('adaptability'))} | {fmt(f('scalability'))} |")
    else:
        L.append("(inner brain has not produced assessments yet)")
    if inner.history:
        h = inner.history[-1]
        L += ["", f"### Inner net on its permanent hold-out (n={h['n_val']}), after {h['n_records']} outcome records",
              f"- inner: AUC {fmt(h['inner']['auc'])}, ECE {fmt(h['inner']['ece'])}, Brier {fmt(h['inner']['brier'])}, acc@80% {fmt(h['inner']['acc80'])}",
              f"- raw outer vote confidence: AUC {fmt(h['outer_conf']['auc'])}, ECE {fmt(h['outer_conf']['ece'])}, Brier {fmt(h['outer_conf']['brier'])}, acc@80% {fmt(h['outer_conf']['acc80'])}",
              f"- base rate of outer being right: {fmt(h['base_rate'])}"]
    if notes:
        L += ["", "## Problems logged", ""] + [f"- {n}" for n in notes[-25:]]
    L += ["", "## How to read this honestly",
          "- 'inner AUC' > 'vote-conf AUC' (and lower ECE) means the inner brain really knows when the outer brain is wrong; equal numbers mean it added nothing.",
          "- 'uniform-weight acc' vs 'vote acc' is the ablation for the inner->outer feedback loop.",
          "- Accuracy is against dataset ground-truth labels (AG News, PROTEINS/MUTAG, CIFAR-10 thumbnails, UrbanSound8K, HMDB51 top-10 classes).",
          "- No LLM fine-tuning happened: the predictors are small heads (<1M params), so NF4/QLoRA were not needed and bitsandbytes/peft are not installed."]
    with open(os.path.join(run_dir, "MORNING_REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--max-cycles", type=int, default=10**6)
    ap.add_argument("--run-id", default=time.strftime("run_%Y%m%d_%H%M%S"))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", default=None, choices=["text", "graph", "image", "audio", "video"])
    ap.add_argument("--no-fill", action="store_true")
    ap.add_argument("--tasks", default=None, help="comma list of task keys, e.g. enc/text/ag_news,hand/text/ag_news (implies --no-fill)")
    ap.add_argument("--resume", action="store_true", help="continue run-id from its checkpoint (cycle counter, meta-weights, inner net, metrics history)")
    a = ap.parse_args()
    if a.tasks:
        a.no_fill = True

    try:  # keep Windows from idle-sleeping while this process lives (released automatically on exit)
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:
        pass
    run_dir = os.path.join(RUNS, a.run_id); os.makedirs(run_dir, exist_ok=True)
    set_logfile(os.path.join(run_dir, "log.txt"))
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if dev.type == "cuda":
        torch.cuda.set_per_process_memory_fraction(float(os.environ.get("NI_VRAM_FRAC", "0.92")))   # cap this process so several runs cannot oversubscribe the 6 GB card
    gpu = torch.cuda.get_device_name(0) if dev.type == "cuda" else "CPU"
    log(f"NI run {a.run_id} on {gpu}; hours={a.hours} smoke={a.smoke}")
    started = time.time(); deadline = started + a.hours * 3600
    outer, inner = OuterBrain(dev), InnerBrain(dev)
    state = dict(cycle=0, rounds=0, status="starting", gpu=gpu, vram_peak=0.0)
    metrics, notes, cache = [], [], {}
    mf = open(os.path.join(run_dir, "metrics.jsonl"), "a", encoding="utf-8")
    tf = open(os.path.join(run_dir, "transcripts.jsonl"), "a", encoding="utf-8")

    if not a.no_fill:
        threading.Thread(target=filler_thread, args=(a.smoke, a.only), daemon=True).start()
        log("waiting for the first fill stage (seed shards for every modality)...")
        READY.wait(timeout=3 * 3600)

    def get_data(key):
        n = 1 if (key.startswith("graph") or key.startswith(ni_data.EXTERNAL_PREFIXES)) else len(ni_fill.existing_shards(key))
        if key in cache and cache[key][0] == n:
            return cache[key][1]
        d = load_task(key)
        cache[key] = (n, d)
        if d is not None:
            log(f"[data] {key}: n={d['n']} C={d['n_classes']} D={d['X'].shape[1]} shards={n}")
        return d

    def heartbeat(extra=""):
        state["elapsed_h"] = round((time.time() - started) / 3600, 3)
        state["note"] = extra
        write_json(os.path.join(run_dir, "status.json"), state)

    if a.tasks:   # explicit task list: one "phase" per task, curriculum order = modality order, then as given
        tl = [k.strip() for k in a.tasks.split(",") if k.strip()]
        plan = sorted(((MODALITIES.index(ni_data.key_modality(k)) + 1, ni_data.key_modality(k), [k]) for k in tl), key=lambda p: p[0])
        log("explicit task list:", tl)
    else:
        plan = [p for p in PHASES if a.only in (None, p[1])]
    start_cycle = 0
    ck_path = os.path.join(run_dir, "checkpoint.pt")
    if a.resume and os.path.exists(ck_path):
        try:
            ck = torch.load(ck_path, map_location="cpu", weights_only=False)
            if ck.get("d"):
                inner.load_state(ck["inner"], ck["d"])
            outer.weights = ck["weights"]; outer.last_acc = ck["last_acc"]
            start_cycle = int(ck["cycle"]) + 1; state["rounds"] = int(ck.get("rounds", 0))
            mp = os.path.join(run_dir, "metrics.jsonl")
            if os.path.exists(mp):
                with open(mp, encoding="utf-8") as fh:
                    for line in fh:
                        try:
                            metrics.append(json.loads(line))
                        except Exception:
                            pass
            log(f"[resume] from checkpoint: next cycle {start_cycle}, rounds {state['rounds']}, {len(metrics)} metric rows, "
                f"inner net {'restored' if ck.get('d') else 'not in checkpoint (will retrain)'}")
        except Exception as e:
            log("[resume] could not load checkpoint, starting fresh:", repr(e)[:160]); start_cycle = 0
    cycle, fails = start_cycle, 0
    while time.time() < deadline and cycle < a.max_cycles:
        state["cycle"] = cycle
        bootstrap = cycle == start_cycle     # first cycle of a (re)started process rebuilds the inner pool outer-only
        log(f"===== CYCLE {cycle} ({'OUTER-ONLY BOOTSTRAP' if bootstrap else 'OUTER -> INNER -> FEEDBACK'}) =====")
        for phase, modality, keys in plan:
            for key in keys:
                if time.time() >= deadline:
                    break
                state["status"] = f"cycle {cycle} phase {phase} {key}"; heartbeat()
                try:
                    data = get_data(key)
                    if data is None or data["n"] < 120:
                        notes.append(f"cycle {cycle}: {key} has too little data yet ({0 if data is None else data['n']})"); continue
                    if dev.type == "cuda":
                        torch.cuda.reset_peak_memory_stats()
                    t0 = time.time()
                    res = outer.run_round(key, data, seed_for(key, cycle), seed_for(key, cycle, 1))
                    if res is None:
                        continue
                    rec, info, ctx = res
                    vram = info["vram_peak_gb"]; state["vram_peak"] = max(state["vram_peak"], vram)
                    state["rounds"] += 1; round_id = state["rounds"]
                    inner.ingest(rec, modality, round_id)           # OUTER OUTCOMES -> INNER DATASET
                    row = dict(task=key, cycle=cycle, round=round_id, outer=info, inner=None, t=time.strftime("%H:%M:%S"))
                    if not bootstrap:
                        thr = info["n_val"] / max(info["infer_s"], 1e-3)
                        out, w_new, trs = inner.assess(key, modality, rec, info, ctx, outer.last_acc.get(key), cycle, round_id, thr, vram)
                        outer.weights[key] = w_new                  # INNER FEEDBACK -> OUTER META-WEIGHTS
                        row["inner"] = out
                        for t in trs:
                            tf.write(json.dumps(t, default=str) + "\n")
                        tf.flush()
                        inner.train(cycle, steps=400)
                    outer.last_acc[key] = info["acc_vote"]
                    mf.write(json.dumps(row, default=str) + "\n"); mf.flush()
                    metrics.append(row)
                    log(f"[{key}] vote={info['acc_vote']:.3f} uniform={info['acc_uniform']:.3f} best1={max(info['acc_pred'].values()):.3f} "
                        f"n_val={info['n_val']} vram={vram:.2f}GB {time.time() - t0:.0f}s" +
                        ("" if row['inner'] is None else f" | grade={row['inner']['composite_grade']:.3f} "
                         f"inner_auc={fmt(((row['inner']['selective'] or {}).get('inner_auc')))} vs conf_auc={fmt(((row['inner']['selective'] or {}).get('voteconf_auc')))}"))
                    del ctx, rec
                    if dev.type == "cuda":
                        torch.cuda.empty_cache()
                    fails = 0
                except torch.cuda.OutOfMemoryError:
                    notes.append(f"cycle {cycle}: CUDA OOM on {key}"); log("OOM", key); torch.cuda.empty_cache(); fails += 1
                except Exception as e:
                    notes.append(f"cycle {cycle}: {key} failed: {repr(e)[:160]}"); log("ERROR", key, traceback.format_exc()[-600:]); fails += 1
                if fails > 40:
                    log("too many consecutive failures; stopping"); STOP.set(); break
        if bootstrap:
            r = inner.train(cycle, steps=1500)
            log("[inner] bootstrap training on the outer's outcome dataset:", json.dumps(r, default=str)[:400])
        else:
            r = inner.train(cycle, steps=800)
        torch.save(dict(inner=inner.state(), weights=outer.weights, last_acc=outer.last_acc, cycle=cycle, rounds=state["rounds"],
                        d=(int(inner.X.shape[1]) if inner.X.shape[1] else None)), os.path.join(run_dir, "checkpoint.pt"))
        write_report(run_dir, state, metrics, inner, started, notes)
        cycle += 1; state["cycle"] = cycle
        if fails > 40:
            break
    state["status"] = "finished"; heartbeat("done")
    STOP.set()
    write_report(run_dir, state, metrics, inner, started, notes)
    log("RUN COMPLETE")


if __name__ == "__main__":
    main()
