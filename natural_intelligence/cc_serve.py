"""Gate 1 live scorer (shadow mode): POST /score with a Claude Code PreToolUse hook payload -> risk that the action fails.

It never blocks anything. Every score is appended to data_user/cc/live_scores.jsonl together with the tool_use_id, so the
real outcome (harvested later from the transcript) can be joined to the prediction made before the action ran.

Features are built by the same cc_core code as training: the history is replayed from the harvested store, then each
transcript the hooks name is read incrementally, so the live session's own earlier outcomes count too.

Run:  venv\\Scripts\\python.exe -X utf8 natural_intelligence\\cc_serve.py      (port 8766, 127.0.0.1 only)
GET /status  -> model info, number of scores, median latency.
"""
import os, sys, json, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("NI_ALGO", "v4")
import numpy as np
import torch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import cc_core
import ni_outer
import gov_core, gov_decide

PORT = int(os.environ.get("NI_CC_PORT", "8766"))
MODEL_F = os.path.join(cc_core.CC_DIR, "cc_model.pt")
LIVE = os.path.join(cc_core.CC_DIR, "live_scores.jsonl")
LOG = os.path.join(cc_core.CC_DIR, "serve_log.txt")
LOCK = threading.Lock()


def log(*a):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a) + "\n")


class Scorer:
    def __init__(self):
        t0 = time.time()
        b = torch.load(MODEL_F, map_location="cpu", weights_only=False)
        self.m, self.variant, self.trained_at = b["model"], b["variant"], b["trained_at"]
        self.cuts = np.array(b.get("risk_quantiles", []), np.float32)
        self.H = cc_core.History(b["tools"], b["models"])
        self.seen = set()
        self.G = gov_core.Governor()                 # NI governor (L1/L2/L5/L11/L17/L18); its beliefs replay the same store
        self.decided = set()
        for r in sorted(cc_core.load_actions().values(), key=lambda r: r["ts"]):
            if r["outcome"] != "unknown":
                self.H.update(r); self.G.observe(r); self.seen.add(r["id"])
        self.parsers = {}
        self.lat = []
        log(f"[serve] loaded {self.variant} trained {self.trained_at}; history {len(self.seen)} actions in {time.time() - t0:.1f}s; "
            f"governor policy ok={self.G.policy[1]['ok']}, unit={self.G.autonomy_unit()}, budget={self.G.selfst.get('budget')}")

    def _catch_up(self, path):
        if not path or not os.path.exists(path):
            return None
        p = self.parsers.get(path)
        if p is None:
            p = self.parsers[path] = cc_core.TxParser(path)
        for r in p.feed_file():
            if r["id"] not in self.seen and r["outcome"] != "unknown" and r.get("ts"):
                self.H.update(r); self.seen.add(r["id"])
                reason, alarms = self.G.observe(r)                       # online learning: O(1) belief update
                for a in alarms:
                    log("[gov] drift alarm", json.dumps(a))
                if r["id"] in self.decided:
                    self.G.record_outcome(r, reason); self.decided.discard(r["id"])
        return p

    def score(self, hook):
        t0 = time.time()
        p = self._catch_up(hook.get("transcript_path"))
        tool = hook.get("tool_name", "?"); text, target = cc_core.summarize(tool, hook.get("tool_input"))
        tid = hook.get("tool_use_id", "")
        plan = ""
        if p is not None:
            pend = p.pending.get(tid)
            plan = pend["plan"] if pend else p.plan.strip()[-300:]
        rec = dict(id=tid, ts=time.time(), session=hook.get("session_id", ""), project=hook.get("cwd", ""),
                   side=p.side if p else 0, model=p.model if p else "?", tool=tool, text=text, plan=plan, target=target,
                   human_ts=p.human_ts if p else None, n_human=p.n_human if p else 0)
        xh = self.H.features(rec)
        ea = cc_core.embed([text], device="cpu")
        if self.variant == "NI + action text + agent's plan text":
            parts = [xh[None], ea, cc_core.embed([plan or "(no stated plan)"], device="cpu")]
        elif self.variant == "NI + action text + recent errors":
            lf_text, lf_err = self.H.err_ctx(rec); has = np.array([float(bool(lf_text))], np.float32)
            el, ee = cc_core.embed([lf_text or "(none)"], device="cpu"), cc_core.embed([lf_err or "(none)"], device="cpu")
            parts = [xh[None], ea, cc_core.err_cos(ea, el, ee, has)]
        else:
            parts = [xh[None]] + ([ea] if self.variant == "NI + action text" else [])
        X = np.concatenate(parts, 1)
        Xn = torch.as_tensor((X - self.m["mu"]) / self.m["sd"], dtype=torch.float32)
        ctx = ni_outer.RoundContext(self.m["preds"], None, None, Xn, None, 2, np.ones(4, np.float32), self.m["cal"])
        risk = float(ctx.vote(ctx.probs(Xn))[0, 0])
        pct = float((self.cuts < risk).mean()) if len(self.cuts) else None
        band = "high" if pct is not None and pct >= 0.95 else ("elevated" if pct is not None and pct >= 0.80 else "normal")
        # governor verdict (shadow: logged, never enforced). If the human has not approved the policy yet the real verdict
        # is ask_human/policy_integrity; the verdict it WOULD give once approved is logged too, so evidence accrues.
        tr = self.G.govern(rec, risk=risk, now=rec["ts"]); self.decided.add(tid)
        tr_if = tr
        if not tr["integrity"]["ok"]:
            s, cls = self.G.scenario(rec, risk, rec["ts"])
            tr_if = gov_decide.govern(s, self.G.policy[0], True, cls["name"], cls.get("verify", ""))
            if tr_if["verdict"] == "ask_human":
                self.G.asks.append(rec["ts"])
        ms = (time.time() - t0) * 1000; self.lat = (self.lat + [ms])[-500:]
        out = dict(risk=round(risk, 4), percentile=None if pct is None else round(pct, 3), band=band, mode="shadow",
                   variant=self.variant, latency_ms=round(ms, 1),
                   verdict=tr["verdict"], binding=tr["binding"], verdict_if_approved=tr_if["verdict"],
                   binding_if_approved=tr_if["binding"], cls=tr["cls"], q=tr["factors"]["q"], level=tr["factors"]["level"],
                   reason=tr_if["message"][:300])
        with open(LIVE, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ts=rec["ts"], tool_use_id=tid, session=rec["session"], tool=tool, model=rec["model"],
                                    text=("" if tr["cls"] == "secret_exposure" else text[:200]), **out), ensure_ascii=False) + "\n")
        self.last_trace = tr_if
        return out


S = None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/status"):
            n = sum(1 for _ in open(LIVE, encoding="utf-8")) if os.path.exists(LIVE) else 0
            self._send(200, dict(ok=S is not None, variant=S.variant if S else None, trained_at=S.trained_at if S else None,
                                 history=len(S.seen) if S else 0, live_scores=n,
                                 median_latency_ms=float(np.median(S.lat)) if S and S.lat else None,
                                 governor=dict(policy=S.G.policy[1]["ok"] if S else None, policy_reason=S.G.policy[1]["reason"] if S else None,
                                               unit=S.G.autonomy_unit() if S else None, budget=S.G.selfst.get("budget") if S else None,
                                               drift_alarms=len(S.G.alarms) if S else 0)))
        elif self.path.startswith("/trace"):
            self._send(200, getattr(S, "last_trace", None) or {})
        else:
            self._send(404, {})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            with LOCK:
                out = S.score(body)
            self._send(200, out)
        except Exception as e:
            log("[serve] error", repr(e)[:300]); self._send(500, dict(error=repr(e)[:200]))


if __name__ == "__main__":
    S = Scorer()
    cc_core.embed(["warm up"], device="cpu")
    log(f"[serve] listening on 127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
