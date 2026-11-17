"""Harvest every Claude Code transcript into data_user/cc/:
  actions.jsonl   one line per tool call with a known outcome (and the turn it belongs to)
  humans.jsonl    one line per human message: id, time, session, which agent turn it reacts to, kind. NO TEXT is stored.
  human_emb.npz   frozen MiniLM embedding of each human message (used by cc_turns.py to recognise corrections)

Merges with what was harvested before, so records survive Claude Code's own transcript cleanup; a fresh parse of a record
replaces the stored copy (so new fields reach old records).
Run:  venv\\Scripts\\python.exe -X utf8 natural_intelligence\\cc_harvest.py
"""
import json, os, sys, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cc_core

HUMANS = os.path.join(cc_core.CC_DIR, "humans.jsonl")
HUMAN_EMB = os.path.join(cc_core.CC_DIR, "human_emb.npz")


def _load_jsonl(p, key):
    out = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line); out[r[key]] = r
            except Exception:
                pass
    return out


def _write_jsonl(p, rows):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def load_human_emb():
    if not os.path.exists(HUMAN_EMB):
        return {}
    z = np.load(HUMAN_EMB)
    return dict(zip(z["k"].tolist(), z["v"].astype(np.float32)))


def harvest(verbose=True):
    t0 = time.time()
    recs = cc_core.load_actions(); before = len(recs)
    hums = _load_jsonl(HUMANS, "uuid"); hemb = load_human_emb(); texts = {}
    files = cc_core.tx_files()
    fresh = {}
    for f in files:
        p = cc_core.TxParser(f)
        for r in p.feed_file():
            if r.get("ts") is not None:
                fresh.setdefault(r["id"], r)
        for e in p.events:
            if e["uuid"] and e["uuid"] not in hums:
                texts[e["uuid"]] = e.pop("text"); hums[e["uuid"]] = e
            else:
                e.pop("text", None)
    recs.update(fresh)
    todo = [u for u in texts if u not in hemb]
    if todo:
        E = cc_core.embed([texts[u] for u in todo])
        for u, v in zip(todo, E):
            hemb[u] = v
        np.savez(HUMAN_EMB, k=np.array(list(hemb.keys())), v=np.stack(list(hemb.values())).astype(np.float16))
    out = sorted(recs.values(), key=lambda r: (r["ts"], r["id"]))
    _write_jsonl(cc_core.ACTIONS, out)
    _write_jsonl(HUMANS, sorted(hums.values(), key=lambda h: h["ts"] or 0))
    if verbose:
        oc = collections.Counter(r["outcome"] for r in out)
        hk = collections.Counter(h["kind"] for h in hums.values())
        print(f"[harvest] {len(files)} transcripts -> {len(out)} actions ({len(out) - before} new), {len(hums)} human messages {dict(hk)} in {time.time() - t0:.0f}s")
        print("[harvest] outcomes:", dict(oc.most_common()))
    return out


if __name__ == "__main__":
    harvest()
