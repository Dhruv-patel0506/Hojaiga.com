"""L15 copy-on-write: NI changes only copies; the original is provably unchanged until a human promotes the change.

Invariant:  H(F) = sha256 over (relative path, bytes) of every file in F, sorted.  H(F) before == H(F) after every step
            up to promotion. It is MEASURED at each step and any difference is a violation, recorded in the ledger.
Gate:       promote(F' -> F) only if  test(F') passed  and  score(F') >= score(F) + margin  and  a human approves.
            The approval is interactive (a TTY and the first 8 characters of the proposal hash); NI never supplies it.

Usage (also how the wrapper L14 works on any codebase):
  p = propose(src_dir, transform, test_cmd)   # copy -> transform the copy -> run test_cmd on original AND copy -> verdict
  python gov_cow.py promote <proposal_id>      # human only
"""
import os, sys, json, shutil, hashlib, subprocess, time, uuid
import gov_ledger

SANDBOX = os.path.join(gov_ledger.GOV_DIR, "sandboxes")
PROPOSALS = os.path.join(gov_ledger.GOV_DIR, "proposals"); os.makedirs(PROPOSALS, exist_ok=True)
SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def tree_hash(root):
    h = hashlib.sha256(); n = 0
    if os.path.isfile(root):
        h.update(open(root, "rb").read()); return h.hexdigest(), 1
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in SKIP)
        for f in sorted(fn):
            p = os.path.join(dp, f); rel = os.path.relpath(p, root).replace("\\", "/")
            h.update(rel.encode() + b"\0")
            with open(p, "rb") as fh:
                h.update(hashlib.sha256(fh.read()).digest())
            n += 1
    return h.hexdigest(), n


def _copy(src, dst):
    if os.path.isfile(src):
        os.makedirs(dst, exist_ok=True); shutil.copy2(src, os.path.join(dst, os.path.basename(src)))
    else:
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP))


def _run(cmd, cwd, timeout):
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)
        return dict(code=r.returncode, secs=round(time.time() - t0, 2), tail=(r.stdout + r.stderr)[-800:])
    except subprocess.TimeoutExpired:
        return dict(code=None, secs=timeout, tail="timeout")


def propose(src, transform, test_cmd=None, score_fn=None, margin=0.0, timeout=600, ledger=None):
    """transform(copy_dir) edits the COPY. score_fn(dir) -> float (higher is better; default: test passes = 1).
    Returns the proposal dict; it is also saved under data_user/gov/proposals/<id>.json."""
    src = os.path.abspath(src); pid = time.strftime("%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    h0, nfiles = tree_hash(src)
    work = os.path.join(SANDBOX, pid); copy_dir = os.path.join(work, "copy")
    _copy(src, copy_dir)
    hc0, _ = tree_hash(copy_dir if os.path.isdir(src) else os.path.join(copy_dir, os.path.basename(src)))
    checks = [dict(step="copied", original=tree_hash(src)[0] == h0)]
    err = None
    try:
        transform(copy_dir)
    except Exception as e:
        err = repr(e)[:300]
    checks.append(dict(step="transformed", original=tree_hash(src)[0] == h0))
    res = {}
    if test_cmd:
        res["original"] = _run(test_cmd, src if os.path.isdir(src) else os.path.dirname(src), timeout)
        checks.append(dict(step="tested original", original=tree_hash(src)[0] == h0))
        res["copy"] = _run(test_cmd, copy_dir, timeout)
        checks.append(dict(step="tested copy", original=tree_hash(src)[0] == h0))
    sf = score_fn or (lambda d, r=res: float(r.get("copy" if d == copy_dir else "original", {}).get("code") == 0))
    s_orig, s_copy = sf(src), sf(copy_dir)
    hc1, _ = tree_hash(copy_dir if os.path.isdir(src) else os.path.join(copy_dir, os.path.basename(src)))
    violation = not all(c["original"] for c in checks)
    ok = (err is None and not violation and hc1 != hc0 and s_copy >= s_orig + margin and
          (not test_cmd or res["copy"]["code"] == 0))
    p = dict(id=pid, src=src, files=nfiles, hash_original=h0, hash_copy_before=hc0, hash_copy_after=hc1,
             changed=hc1 != hc0, transform_error=err, tests=res, score_original=s_orig, score_copy=s_copy, margin=margin,
             checks=checks, invariant_violation=violation, eligible_for_promotion=ok, promoted=False, ts=time.time())
    p["proposal_hash"] = hashlib.sha256(json.dumps({k: p[k] for k in ("id", "hash_original", "hash_copy_after")}).encode()).hexdigest()
    json.dump(p, open(os.path.join(PROPOSALS, pid + ".json"), "w", encoding="utf-8"), indent=1)
    if ledger is not None:
        ledger.append("cow", dict(id=pid, src=src, invariant_violation=violation, eligible=ok, changed=p["changed"]))
    return p


def promote(pid):
    """Human-only: copies the transformed copy over the original after re-checking the original did not move."""
    p = json.load(open(os.path.join(PROPOSALS, pid + ".json"), encoding="utf-8"))
    if not sys.stdin.isatty():
        print("refused: promotion needs an interactive human at a terminal"); return 2
    if not p["eligible_for_promotion"]:
        print("refused: proposal is not eligible (tests, margin or invariant)"); return 1
    if tree_hash(p["src"])[0] != p["hash_original"]:
        print("refused: the original changed since the proposal was made; re-propose"); return 1
    print(json.dumps({k: p[k] for k in ("src", "files", "score_original", "score_copy", "tests")}, indent=1)[:3000])
    if input(f"Type the first 8 characters of {p['proposal_hash']} to promote: ").strip() != p["proposal_hash"][:8]:
        print("not promoted"); return 1
    copy_dir = os.path.join(SANDBOX, pid, "copy")
    if os.path.isfile(p["src"]):
        shutil.copy2(os.path.join(copy_dir, os.path.basename(p["src"])), p["src"])
    else:
        shutil.copytree(copy_dir, p["src"], dirs_exist_ok=True)
    p["promoted"] = True; p["promoted_ts"] = time.time()
    json.dump(p, open(os.path.join(PROPOSALS, pid + ".json"), "w", encoding="utf-8"), indent=1)
    print("promoted"); return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "promote":
        sys.exit(promote(sys.argv[2]))
    print(__doc__)
