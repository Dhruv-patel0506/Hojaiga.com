"""Gap A: retrain the modality gatekeeper so `drag` is a class it can actually predict.

The shipped deep_rag_ml_reranker.pkl lists drag in id_to_label but its classifier was fit on
click/hotkey/type only (classes_ == [0, 2, 3]).  drag training rows live in qwen_24k_train_ready.jsonl.

Honesty rules: prompts are de-duplicated, any train prompt that also appears in the held-out set is
dropped, and the held-out set is qwen_10k_test_ready.jsonl (never trained on).  The original pkl is
left untouched; the result is written to data/deep_rag_ml_reranker_v2.pkl.
"""
import json, pickle, time, collections, random, pathlib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import HashingVectorizer

ROOT = pathlib.Path(r"D:\new_automation")
T = ROOT / "data" / "ai_root" / "harvest" / "training"
OUT = ROOT / "data" / "deep_rag_ml_reranker_v2.pkl"
REP = ROOT / "reports"
REP.mkdir(exist_ok=True)
KINDS = ["click", "drag", "hotkey", "type"]
PER_KIND = 3000


def parse(r):
    u = a = ""
    for m in r.get("messages", []):
        c = m.get("content", "")
        t = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
        if m.get("role") == "user":
            u = t.strip()
        elif m.get("role") == "assistant":
            a = t.strip()
    try:
        g = json.loads(a)
        g = g[0] if isinstance(g, list) and g else g
        k = str(g.get("action", "")).lower().strip()
    except Exception:
        k = ""
    # qwen_24k_train_ready.jsonl tags drag rows only in meta (the reply schema is click|hotkey|type).
    if (r.get("meta") or {}).get("action") == "drag":
        k = "drag"
    return u, k


def load(fn):
    out = []
    with open(T / fn, encoding="utf-8") as f:
        for l in f:
            if l.strip():
                out.append(parse(json.loads(l)))
    return out


test = load("qwen_10k_test_ready.jsonl")
test_prompts = {u for u, _ in test}
train, seen = collections.defaultdict(list), set()
for fn in ("qwen_50k_mega_overnight_train.jsonl", "qwen_24k_train_ready.jsonl"):
    for u, k in load(fn):
        if k in KINDS and u not in seen and u not in test_prompts:
            seen.add(u)
            train[k].append(u)
random.seed(42)
for k in KINDS:
    random.shuffle(train[k])
    train[k] = train[k][:PER_KIND]
print("train rows per kind (deduped, leak-free):", {k: len(v) for k, v in train.items()})
print("sample drag prompt:", repr(train["drag"][0][:300]) if train["drag"] else None)

vec = HashingVectorizer(n_features=512, alternate_sign=False, norm="l2", ngram_range=(1, 2))
Xtr_t, ytr = [], []
for i, k in enumerate(KINDS):
    for u in train[k]:
        Xtr_t.append(u)
        ytr.append(i)
clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, random_state=42)
t0 = time.time()
clf.fit(vec.transform(Xtr_t).toarray(), np.array(ytr))
print(f"fit {time.time()-t0:.1f}s classes_={list(clf.classes_)}")

# Held-out: balanced per kind (all drag rows available), plus the legacy 50-sample round-robin.
by = collections.defaultdict(list)
for u, k in test:
    if k in KINDS:
        by[k].append(u)
n = min(len(by[k]) for k in KINDS)
res = {}
tot_ok = tot = 0
for i, k in enumerate(KINDS):
    sample = by[k][:n]
    pred = clf.predict(vec.transform(sample).toarray())
    ok = int((pred == i).sum())
    res[k] = {"n": len(sample), "acc": round(ok / len(sample), 4)}
    tot_ok += ok
    tot += len(sample)
res["macro_balanced"] = round(tot_ok / tot, 4)
print("held-out balanced per-kind:", json.dumps(res))

# Compare with the shipped gatekeeper on the exact same balanced held-out set.
old = pickle.load(open(ROOT / "data" / "deep_rag_ml_reranker.pkl", "rb"))
ovec, oclf, oid = old["vectorizer"], old["modality_classifier"], old["id_to_label"]
old_res = {}
for k in KINDS:
    pred = oclf.predict(ovec.transform(by[k][:n]).toarray())
    old_res[k] = round(sum(oid[int(p)] == k for p in pred) / n, 4)
print("shipped gatekeeper on same set:", old_res, "macro", round(sum(old_res.values()) / 4, 4))

pickle.dump({"vectorizer": vec, "modality_classifier": clf, "label_to_id": {k: i for i, k in enumerate(KINDS)},
             "id_to_label": {i: k for i, k in enumerate(KINDS)}, "modality_test_acc": res["macro_balanced"] * 100,
             "heldout": res, "train_counts": {k: len(v) for k, v in train.items()}}, open(OUT, "wb"))
(REP / "cp2_gatekeeper_v2.json").write_text(json.dumps({"v2": res, "shipped_same_set": old_res,
                                                         "train_counts": {k: len(v) for k, v in train.items()}}, indent=2))
print("wrote", OUT)
