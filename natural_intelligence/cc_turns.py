"""Task-level outcomes for gate 1.

A TURN is everything an agent does between two human messages. Its outcome is the human's reaction:
  bad      the next human message is a correction (teacher label, or the classifier below for unlabelled messages),
           or the user interrupted the turn, or rejected one of its tool calls
  good     the next human message is anything else (a new request, an approval, a question)
  unknown  no reaction yet, or the next 'message' is a continuation summary / usage-limit notice written by Claude Code

Correction classifier: logistic regression on the frozen MiniLM embedding of the human message, trained on the teacher
labels in data_user/cc/turn_labels.jsonl. Its cross-validated quality is reported, so its labels are not taken on faith.
Run:  venv\\Scripts\\python.exe -X utf8 natural_intelligence\\cc_turns.py      (prints the classifier's CV result)
"""
import os, sys, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cc_core, cc_harvest

LABELS = os.path.join(cc_core.CC_DIR, "turn_labels.jsonl")


def load():
    hums = list(cc_harvest._load_jsonl(cc_harvest.HUMANS, "uuid").values())
    labels = {r["uuid"]: r["label"] for r in cc_harvest._load_jsonl(LABELS, "uuid").values()}
    return hums, labels, cc_harvest.load_human_emb()


def classifier(hums, labels, emb, folds=5, seed=0):
    """Fit C-vs-N on the labelled messages; return (model, cv report). Folds are grouped so identical messages
    (the same text sent several times) never sit on both sides."""
    from sklearn.linear_model import LogisticRegression
    ids = [h["uuid"] for h in hums if h["uuid"] in labels and h["uuid"] in emb]
    X = np.stack([emb[u] for u in ids]); y = np.array([int(labels[u] == "C") for u in ids])
    grp = {}
    g = np.array([grp.setdefault(np.round(x, 2).tobytes(), len(grp)) for x in X])
    rng = np.random.RandomState(seed); ug = np.unique(g); rng.shuffle(ug); fold = {k: i % folds for i, k in enumerate(ug)}
    f = np.array([fold[k] for k in g]); oof = np.zeros(len(y))
    mk = lambda: LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced")
    for k in range(folds):
        tr, te = f != k, f == k
        oof[te] = mk().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    import ni_outer
    pred = oof >= 0.5
    rep = dict(n=len(y), corrections=int(y.sum()), cv_auroc=ni_outer._auc(oof, y), cv_accuracy=float((pred == y).mean()),
               cv_precision=float(y[pred].mean()) if pred.any() else 0.0, cv_recall=float(pred[y == 1].mean()) if y.any() else 0.0,
               majority_accuracy=float(max(y.mean(), 1 - y.mean())))
    return mk().fit(X, y), rep


def turn_outcomes(actions=None):
    """dict turn_uuid -> (bad 0/1, source) for every turn with a known reaction."""
    hums, labels, emb = load()
    clf, rep = classifier(hums, labels, emb)
    out = {}
    for h in hums:
        t = h.get("prev_turn")
        if not t:
            continue
        if h["kind"] == "interrupt":
            out[t] = (1, "interrupt")
        elif h["kind"] == "human" and t not in out:
            if h["uuid"] in labels:
                out[t] = (int(labels[h["uuid"]] == "C"), "teacher")
            elif h["uuid"] in emb:
                out[t] = (int(clf.predict_proba(emb[h["uuid"]][None])[0, 1] >= 0.5), "classifier")
    for r in (actions or []):
        if r.get("outcome") == "rejected" and r.get("turn"):
            out[r["turn"]] = (1, "rejected")
    return out, rep


if __name__ == "__main__":
    o, rep = turn_outcomes(list(cc_core.load_actions().values()))
    print("[turns] correction classifier (5-fold, grouped):", json.dumps({k: round(v, 3) if isinstance(v, float) else v for k, v in rep.items()}))
    c = collections.Counter((b, s) for b, s in o.values())
    print("[turns] turns with a known outcome:", len(o), dict(c))
