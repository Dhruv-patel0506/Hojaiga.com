"""L18 + hard values: the governor's policy file, its integrity lock, and the action risk classifier.

Math / invariant
  policy P is a JSON file; lock = sha256(P) written ONLY by a human (`python gov_policy.py approve`, interactive).
  integrity(P) = [sha256(P) == lock].  If integrity fails the governor is LOCKED: every verdict becomes ask_human with
  binding constraint "policy_integrity" (gov_decide). NI therefore cannot loosen its own hard constraints by editing them.
  Running `gov_policy.py approve` is itself in the destructive_local class, so an agent trying it is escalated.

Action classifier
  class(a) = first class c in policy order whose patterns match the action text or whose tools match the tool name.
  The order is by severity (money > secret > publish > destructive > ... > read), so the most severe reading wins.

Failure reason (brief 2, 6.3): reason(o, err) from the outcome class, then the error text, by the policy's table.
"""
import os, sys, json, re, hashlib, time

ROOT = os.path.dirname(os.path.abspath(__file__))
POLICY = os.path.join(ROOT, "gov_policy.json")
LOCK = os.path.join(ROOT, "gov_policy.lock")
_CACHE = {}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load(path=POLICY, lock=LOCK):
    """(policy dict, integrity dict). Re-read when the file changes, so a live edit is noticed at once."""
    st = os.stat(path).st_mtime_ns
    key = (path, lock)
    c = _CACHE.get(key)
    if c is None or c["mtime"] != st or c.get("lock_mtime") != (os.stat(lock).st_mtime_ns if os.path.exists(lock) else None):
        h = sha(path)
        lk = open(lock, encoding="utf-8").read().split()[0] if os.path.exists(lock) else None
        with open(path, encoding="utf-8") as f:
            P = json.load(f)
        for cl in P["classes"]:
            cl["_re"] = [re.compile(p, re.I) for p in cl.get("patterns", [])]
        P["_fr"] = [(re.compile(a, re.I), b) for a, b in P["failure_reasons"]["by_error_text"]]
        P["_prod"] = [re.compile(p, re.I) for p in P["environment"]["production_patterns"]]
        integ = dict(ok=(lk == h), sha=h, lock=lk, reason=None if lk == h else ("no lock file" if lk is None else "policy changed since the human approved it"))
        c = _CACHE[key] = dict(mtime=st, lock_mtime=os.stat(lock).st_mtime_ns if os.path.exists(lock) else None, P=P, integ=integ)
    return c["P"], c["integ"]


def short_tool(tool):
    return tool.rsplit("__", 1)[-1] if tool else "?"


def _tool_match(entries, tool):
    s = short_tool(tool)
    for e in entries:
        if s == e or tool == e or (e.endswith("_") and s.startswith(e)):
            return True
    return False


def classify(tool, text, P=None):
    """-> (class dict, environment 'production'|'test', loss after the environment multiplier)."""
    P = P or load()[0]
    body = text.split(":", 1)[1] if tool in ("Bash", "PowerShell") and ":" in text[:20] else text
    executes = _tool_match(P.get("pattern_tools", ["Bash", "PowerShell"]), tool)
    for cl in P["classes"]:
        if (executes and any(r.search(body) for r in cl["_re"])) or _tool_match(cl.get("tools", []), tool):
            break
    else:
        cl = P["classes"][-1]
    env = "production" if executes and any(r.search(body) for r in P["_prod"]) else "test"
    loss = cl["loss"] * (P["environment"]["production_loss_multiplier"] if env == "production" else 1.0)
    return cl, env, loss


def failure_reason(outcome, err="", P=None):
    if outcome == "ok":
        return None
    P = P or load()[0]
    fr = P["failure_reasons"]
    if outcome in fr["by_outcome"]:
        return fr["by_outcome"][outcome]
    for r, name in P["_fr"]:
        if r.search(err or ""):
            return name
    return fr["default"]


def approve():
    """Human-only: show the policy hash and require the human to type its first 8 characters."""
    if not sys.stdin.isatty():
        print("refused: approval needs an interactive human at a terminal (stdin is not a TTY)"); return 2
    h = sha(POLICY)
    old = open(LOCK, encoding="utf-8").read().split()[0] if os.path.exists(LOCK) else None
    print(f"policy: {POLICY}\nnew sha256: {h}\nold lock:   {old}")
    typed = input("Type the first 8 characters of the new sha256 to approve: ").strip()
    if typed != h[:8]:
        print("not approved"); return 1
    with open(LOCK, "w", encoding="utf-8") as f:
        f.write(f"{h} approved {time.strftime('%Y-%m-%d %H:%M:%S')} by a human at the terminal\n")
    print("approved"); return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "approve":
        sys.exit(approve())
    P, I = load()
    print(json.dumps(I, indent=1))
