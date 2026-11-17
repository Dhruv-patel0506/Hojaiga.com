"""Gate 1 core: Claude Code transcripts -> action records -> leak-free features.

An ACTION is one tool call an agent made (Bash, Edit, Write, Read, a browser step, ...). Its OUTCOME is what the tool
result says happened: ok, failed (exit code, tool error), blocked (a harness or permission classifier refused it), or
rejected (the human said no). Calls whose result was never recorded are 'unknown' and are not used as labels.

Everything a feature uses must be known BEFORE the action runs: the action text, the agent's text just before it (its
stated plan), which model/agent issued it, and the history of earlier actions. History is accumulated online in time
order, so a record never sees its own outcome or any later one. The same code is used by the offline evaluator
(cc_gate.py) and by the live scorer (cc_serve.py), so live features equal training features.
"""
import os, json, math, re, hashlib, datetime, glob
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
CC_DIR = os.path.join(ROOT, "data_user", "cc"); os.makedirs(CC_DIR, exist_ok=True)
ACTIONS = os.path.join(CC_DIR, "actions.jsonl")
TX_ROOT = os.path.expanduser(os.path.join("~", ".claude", "projects"))


def tx_files():
    return sorted(glob.glob(os.path.join(TX_ROOT, "**", "*.jsonl"), recursive=True))


def iso_ts(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def result_text(c):
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    return str(c or "")


def classify(text, is_error):
    """Outcome class from the tool result. Order matters: the most specific signal wins."""
    t = text[:600].lower()
    if "session ended before this call" in t or "outcome is unknown" in t:
        return "unknown"
    if "doesn't want to proceed" in t or "tool use was rejected" in t or "user rejected" in t:
        return "rejected"
    if "permission for this action was denied" in t or t.startswith("<tool_use_error>blocked") or "blocked:" in t[:40]:
        return "blocked"
    if not is_error:
        return "ok"
    if "<tool_use_error>" in t:
        return "tool_error"
    if t.startswith("exit code"):
        return "exit_nonzero"
    return "error"


def summarize(tool, inp):
    """(action text for the embedding, target path or '') - a readable one-line description of the call."""
    inp = inp if isinstance(inp, dict) else {}
    p = inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or ""
    if tool in ("Bash", "PowerShell"):
        return f"{tool}: {str(inp.get('command', ''))[:400]}", ""
    if tool == "Edit":
        return f"Edit {p} | old: {str(inp.get('old_string', ''))[:160]} | new {len(str(inp.get('new_string', '')))} chars", p
    if tool == "Write":
        return f"Write {p} | {len(str(inp.get('content', '')))} chars", p
    if tool == "Read":
        return f"Read {p}" + (f" from line {inp.get('offset')}" if inp.get("offset") else ""), p
    if tool in ("Grep", "Glob"):
        return f"{tool} {inp.get('pattern', '')} in {p}", p
    return f"{tool}: {json.dumps(inp, ensure_ascii=False)[:300]}", str(p)


def head_of(tool, text, target):
    """Coarse 'kind of action' key: the program a shell command starts with, the file type a file tool touches."""
    if tool in ("Bash", "PowerShell"):
        cmd = text.split(":", 1)[1] if ":" in text else text
        for seg in re.split(r"&&|;|\|\|", cmd):
            w = seg.strip().split()
            if w and w[0] not in ("cd", "set", "export"):
                return tool + ":" + os.path.basename(w[0].strip("\"'"))[:40].lower()
        return tool + ":cd"
    if target:
        return tool + ":" + (os.path.splitext(target)[1].lower() or "noext")
    return tool


class TxParser:
    """Streams one transcript file; emits a record when a tool call's result arrives."""

    def __init__(self, path):
        self.path = path; self.offset = 0
        self.pending = {}; self.plan = ""; self.human_ts = None; self.n_human = 0; self.model = "?"; self.side = 0
        self.turn = None; self.events = []          # events: human messages (drained by the harvester)

    def feed_file(self):
        out = []
        try:
            with open(self.path, "rb") as f:
                f.seek(self.offset)
                data = f.read()
        except OSError:
            return out
        cut = data.rfind(b"\n")
        if cut < 0:
            return out
        self.offset += cut + 1
        for line in data[:cut].split(b"\n"):
            out.extend(self.feed(line))
        return out

    def feed(self, line):
        try:
            r = json.loads(line)
        except Exception:
            return []
        m = r.get("message")
        if not isinstance(m, dict):
            return []
        ts = iso_ts(r.get("timestamp"))
        c = m.get("content")
        out = []
        if r.get("type") == "assistant" and isinstance(c, list):
            self.model = m.get("model", self.model); self.side = int(bool(r.get("isSidechain")))
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    self.plan = (self.plan + " " + b.get("text", ""))[-600:]
                elif b.get("type") == "tool_use":
                    tool = b.get("name", "?"); text, target = summarize(tool, b.get("input"))
                    self.pending[b.get("id")] = dict(
                        id=b.get("id"), ts=ts, session=r.get("sessionId", ""), project=r.get("cwd", ""),
                        side=int(bool(r.get("isSidechain"))), model=m.get("model", "?"), tool=tool, text=text,
                        plan=self.plan.strip()[-300:], target=target, human_ts=self.human_ts, n_human=self.n_human, turn=self.turn)
        elif r.get("type") == "user":
            if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        rec = self.pending.pop(b.get("tool_use_id"), None)
                        if rec is None:
                            continue
                        txt = result_text(b.get("content"))
                        rec["outcome"] = classify(txt, bool(b.get("is_error")))
                        rec["err_head"] = txt[:200] if rec["outcome"] != "ok" else ""
                        rec["ts_res"] = ts
                        out.append(rec)
                self.plan = ""
            elif not r.get("isMeta"):
                txt = c if isinstance(c, str) else result_text(c)
                t = txt.strip()
                if t and (not t.startswith("<") or t.startswith("<pasted_content")):
                    # a human message ends the agent's current turn (it is the reaction to it) and starts the next one
                    self.events.append(dict(uuid=r.get("uuid"), ts=ts, session=r.get("sessionId", ""), prev_turn=self.turn,
                                            kind=human_kind(t), text=t[:2000]))
                    self.human_ts = ts; self.n_human += 1; self.turn = r.get("uuid")
        return out


def human_kind(t):
    """Messages Claude Code itself writes into the user channel are not reactions to the agent's work."""
    if "[Request interrupted by user" in t:
        return "interrupt"
    if t.startswith("This session is being continued from a previous conversation"):
        return "summary"
    if t.startswith("I hit my usage limit while you were working"):
        return "limit"
    return "human"


def load_actions():
    recs = {}
    if os.path.exists(ACTIONS):
        with open(ACTIONS, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line); recs[r["id"]] = r
                except Exception:
                    pass
    return recs


# ------------------------------------------------------------------------------------------------ features
LEX_CHARS = "'\"`\\$|&<>(){}[]%*"
FAIL_CLASSES = ("exit_nonzero", "tool_error", "blocked", "error", "rejected")


def err_cos(Ea, El, Ee, has):
    """Similarity of the current action to the last failed action and to its error message (0 when there was none)."""
    return np.stack([(Ea * El).sum(1) * has, (Ea * Ee).sum(1) * has], 1).astype(np.float32)


def lexical(text):
    t = text.split(":", 1)[1] if ":" in text[:20] else text
    v = [math.log1p(len(t)), math.log1p(t.count("\n"))]
    for ch in LEX_CHARS:
        v.append(math.log1p(t.count(ch)))
    v += [t.count("'") % 2, t.count('"') % 2, t.count("(") - t.count(")"), t.count("{") - t.count("}"),
          math.log1p(sum(1 for ch in t if ord(ch) > 127))]
    return v


LEX_NAMES = ["len", "lines"] + [f"c[{c}]" for c in LEX_CHARS] + ["odd'", 'odd"', "paren_bal", "brace_bal", "nonascii"]


class Rate:
    __slots__ = ("n", "f")

    def __init__(self):
        self.n = 0; self.f = 0


def akey(rec):
    return hashlib.sha1((rec["tool"] + "|" + rec["text"][:120]).encode("utf-8", "replace")).hexdigest()[:16]


class History:
    """Online counts. features(rec) uses only what was update()d before; call update(rec) after the outcome is known."""
    PRIOR_A = 5.0

    def __init__(self, tools=None, models=None):
        self.tools = list(tools or []); self.models = list(models or [])
        self.g = {}; self.all = Rate(); self.sess = {}

    def _rate(self, key):
        r = self.g.get(key)
        p0 = (self.all.f + 1) / (self.all.n + 2)
        if r is None:
            return p0, 0.0
        return (r.f + self.PRIOR_A * p0) / (r.n + self.PRIOR_A), math.log1p(r.n)

    def features(self, rec):
        s = self.sess.get(rec["session"]) or dict(n=0, f=0, last=[], prev_tool=None, consec=0, prev_ts=None, keys={}, tg={}, human_seen=-1)
        tool, head, k, tgt = rec["tool"], head_of(rec["tool"], rec["text"], rec.get("target", "")), akey(rec), rec.get("target", "")
        v = []
        for key in (("tool", tool), ("head", head), ("model", rec["model"]), ("proj", rec.get("project", "")), ("key", k)):
            v.extend(self._rate(key))
        ts = rec.get("ts") or 0
        sr = (s["f"] + 1) / (s["n"] + 2 + 1e-9)
        tg = s["tg"].get(tgt, [0, 0, 0]) if tgt else [0, 0, 0]
        kk = s["keys"].get(k, [0, 0])
        human_ts = rec.get("human_ts")
        v += [math.log1p(s["n"]), sr, sum(s["last"][-5:]), (s["last"][-1] if s["last"] else 0),
              math.log1p(s["consec"] if s["prev_tool"] == tool else 0),
              math.log1p(max(ts - s["prev_ts"], 0)) if s["prev_ts"] else 0.0,
              float(rec.get("n_human", 0) != s["human_seen"]),
              math.log1p(max(ts - human_ts, 0)) if human_ts else 10.0,
              math.log1p(kk[0]), math.log1p(kk[1]),
              math.log1p(tg[0]), math.log1p(tg[1]), math.log1p(tg[2]),
              float(rec.get("side", 0)), float(len(rec.get("plan", "")) > 0), math.log1p(len(rec.get("plan", "")))]
        v += lexical(rec["text"])
        v += [float(tool == t) for t in self.tools] + [float(tool not in self.tools)]
        v += [float(rec["model"] == m) for m in self.models] + [float(rec["model"] not in self.models)]
        # the agent's most recent failure in this session: how long ago, of what kind, on the same tool or target
        lf = s.get("lf")
        if lf:
            v += [1.0, math.log1p(s["n"] - lf["n"]), math.log1p(max(ts - (lf["ts"] or ts), 0)), float(lf["tool"] == tool),
                  float(bool(tgt) and lf["target"] == tgt)] + [float(lf["cls"] == c) for c in FAIL_CLASSES]
        else:
            v += [0.0, 10.0, 15.0, 0.0, 0.0] + [0.0] * len(FAIL_CLASSES)
        return np.array(v, np.float32)

    def err_ctx(self, rec):
        """(text of the last failed action, its error message) in this session, '' if none - embedded by the caller."""
        lf = (self.sess.get(rec["session"]) or {}).get("lf")
        return (lf["text"], lf["err"] or "(no message)") if lf else ("", "")

    def names(self):
        n = []
        for k in ("tool", "head", "model", "proj", "key"):
            n += [f"g_{k}_fail", f"g_{k}_logn"]
        n += ["s_logn", "s_fail", "s_fail_last5", "s_last_fail", "s_consec_same_tool", "s_log_dt_prev", "s_new_human_msg",
              "s_log_dt_human", "s_same_action_logn", "s_same_action_fails", "s_target_reads", "s_target_writes", "s_target_fails",
              "sidechain", "has_plan", "plan_len"]
        n += ["lex_" + x for x in LEX_NAMES]
        n += [f"tool={t}" for t in self.tools] + ["tool=other"] + [f"model={m}" for m in self.models] + ["model=other"]
        n += ["lf_any", "lf_steps_ago", "lf_secs_ago", "lf_same_tool", "lf_same_target"] + [f"lf_cls={c}" for c in FAIL_CLASSES]
        return n

    def update(self, rec):
        fail = int(rec["outcome"] != "ok")
        tool, head, k, tgt = rec["tool"], head_of(rec["tool"], rec["text"], rec.get("target", "")), akey(rec), rec.get("target", "")
        for key in (("tool", tool), ("head", head), ("model", rec["model"]), ("proj", rec.get("project", "")), ("key", k)):
            r = self.g.setdefault(key, Rate()); r.n += 1; r.f += fail
        self.all.n += 1; self.all.f += fail
        s = self.sess.setdefault(rec["session"], dict(n=0, f=0, last=[], prev_tool=None, consec=0, prev_ts=None, keys={}, tg={}, human_seen=-1))
        s["n"] += 1; s["f"] += fail; s["last"] = (s["last"] + [fail])[-5:]
        s["consec"] = s["consec"] + 1 if s["prev_tool"] == tool else 1
        s["prev_tool"] = tool; s["prev_ts"] = rec.get("ts") or s["prev_ts"]; s["human_seen"] = rec.get("n_human", 0)
        kk = s["keys"].setdefault(k, [0, 0]); kk[0] += 1; kk[1] += fail
        if tgt:
            tg = s["tg"].setdefault(tgt, [0, 0, 0])
            tg[0 if tool == "Read" else 1] += 1; tg[2] += fail
        if fail:
            s["lf"] = dict(text=rec["text"], err=rec.get("err_head", ""), ts=rec.get("ts"), n=s["n"], tool=tool, target=tgt, cls=rec["outcome"])


# ------------------------------------------------------------------------------------------------ text embedding
_ENC = {}
EMB_CACHE = os.path.join(CC_DIR, "emb_cache.npz")


def _load_cache():
    if "cache" not in _ENC:
        _ENC["cache"] = {}
        if os.path.exists(EMB_CACHE):
            z = np.load(EMB_CACHE)
            _ENC["cache"] = dict(zip(z["k"].tolist(), z["v"].astype(np.float32)))
    return _ENC["cache"]


def save_cache():
    c = _load_cache()
    if c:
        np.savez(EMB_CACHE, k=np.array(list(c.keys())), v=np.stack(list(c.values())).astype(np.float16))


def embed(texts, device=None):
    """Frozen MiniLM sentence embedding (the same encoder the gate and the text datasets use), cached on disk by text hash."""
    import torch, transformers as T
    import torch.nn.functional as TF
    cache = _load_cache()
    keys = [hashlib.sha1(t.encode("utf-8", "replace")).hexdigest()[:20] for t in texts]
    todo = sorted({(k, t) for k, t in zip(keys, texts) if k not in cache})
    if todo:
        dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
        if "m" not in _ENC or _ENC.get("dev") != dev:
            md = os.path.join(ROOT, "models_hf", "all-MiniLM-L6-v2")
            _ENC["tok"] = T.AutoTokenizer.from_pretrained(md); _ENC["m"] = T.AutoModel.from_pretrained(md).eval().to(dev); _ENC["dev"] = dev
        for i in range(0, len(todo), 256):
            b = todo[i:i + 256]
            t = _ENC["tok"]([x[1] for x in b], padding=True, truncation=True, max_length=128, return_tensors="pt").to(dev)
            with torch.no_grad():
                h = _ENC["m"](**t).last_hidden_state
            mk = t["attention_mask"].unsqueeze(-1).float()
            e = TF.normalize((h * mk).sum(1) / mk.sum(1), dim=1).float().cpu().numpy()
            for (k, _), v in zip(b, e):
                cache[k] = v
    return np.stack([cache[k] for k in keys]).astype(np.float32)
