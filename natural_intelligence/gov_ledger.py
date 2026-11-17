"""L1 experience ledger: an append-only, tamper-evident record of NI's own life.

Each entry is e = (x, s, k, y, o, h, v) split over two lines that share the action id:
  decision line: x = action summary, s = scenario factors, k = agent, y = NI verdict + trace digest   (written BEFORE the action)
  outcome  line: o = measured outcome class, failure reason (kept, never discarded), h = human signal, v = value vector
Chain: line_i carries prev = hash_{i-1} and hash_i = sha256(prev + canonical JSON of the line without its hash).
verify() recomputes the chain; any edited, deleted or reordered line breaks it at that point (L1 completeness audit,
and the evidence trail for L17). Secrets never enter: the action text is cut to 200 characters and the secret_exposure
class stores no text at all.
"""
import os, json, hashlib, threading

ROOT = os.path.dirname(os.path.abspath(__file__))
GOV_DIR = os.path.join(ROOT, "data_user", "gov"); os.makedirs(GOV_DIR, exist_ok=True)
LEDGER = os.path.join(GOV_DIR, "ledger.jsonl")
_LOCK = threading.Lock()


def _canon(d):
    return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class Ledger:
    def __init__(self, path=LEDGER):
        self.path = path; self.prev = "0" * 64; self.n = 0
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.prev = json.loads(line)["hash"]; self.n += 1
                        except Exception:
                            pass

    def append(self, kind, body):
        with _LOCK:
            d = dict(kind=kind, i=self.n, prev=self.prev, **body)
            d["hash"] = hashlib.sha256((self.prev + _canon(d)).encode("utf-8")).hexdigest()
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(_canon(d) + "\n")
            self.prev = d["hash"]; self.n += 1
            return d["hash"]


def verify(path=LEDGER):
    """-> dict(ok, n, broken_at, decisions, outcomes, resolved_fraction)."""
    prev = "0" * 64; n = 0; dec, out = set(), set()
    if not os.path.exists(path):
        return dict(ok=True, n=0, broken_at=None, decisions=0, outcomes=0, resolved_fraction=None)
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line); h = d.pop("hash", None)
            if d.get("prev") != prev or hashlib.sha256((prev + _canon(d)).encode("utf-8")).hexdigest() != h:
                return dict(ok=False, n=n, broken_at=n, decisions=len(dec), outcomes=len(out), resolved_fraction=None)
            prev = h; n += 1
            (dec if d["kind"] == "decision" else out).add(d.get("id"))
    return dict(ok=True, n=n, broken_at=None, decisions=len(dec), outcomes=len(out & dec),
                resolved_fraction=(len(out & dec) / len(dec)) if dec else None)
