"""Does a supervised model beat the hand-weighted archetype router? Leave-one-out on the real labelled scans (name withheld). Nothing is adopted unless it wins."""
import sys, math, json
sys.path.insert(0, r"D:\new_automation\All codes")
import numpy as np
from collections import Counter
from core_organs.rag import archetypes as A
from core_organs.harvest import app_profile as AP
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB, ComplementNB

data = AP._labelled()                                   # [(label, signature)]
router = A.ArchetypeRouter()
labels = sorted({l for l, _ in data})
ids = [a["id"] for a in A.ARCHETYPES]
docs = [" ".join(" ".join(A._toks(c[1] if isinstance(c, (list, tuple)) else str(c))) for c in s["controls"]) for _, s in data]
y = np.array([l for l, _ in data])
print("apps", len(data), "classes present", len(labels), "class sizes", dict(Counter(y)))


def router_probs(sig, T):
    return AP.shares(sig, T, router)


def loo(make_probs):
    top1 = ll = 0.0
    n = len(data)
    for i in range(n):
        p = make_probs(i)
        top1 += max(p, key=p.get) == y[i]
        ll += -math.log(max(p.get(y[i], 1e-9), 1e-9))
    return round(top1 / n, 3), round(ll / n, 3)


def model_probs(kind, alpha=0.0):
    def f(i):
        tr = [j for j in range(len(data)) if j != i]
        vec = TfidfVectorizer(sublinear_tf=True, min_df=1)
        X = vec.fit_transform([docs[j] for j in tr])
        if kind == "lr":
            m = LogisticRegression(C=20.0, max_iter=2000)
        elif kind == "nb":
            m = MultinomialNB(alpha=0.3)
        else:
            m = ComplementNB(alpha=0.3)
        m.fit(X, y[tr])
        pr = dict(zip(m.classes_, m.predict_proba(vec.transform([docs[i]]))[0]))
        base = router_probs(dict(data[i][1]), AP.calibrated_temperature())
        out = {k: (1 - alpha) * base.get(k, 0.0) + alpha * pr.get(k, 0.0) for k in ids}
        z = sum(out.values()) or 1.0
        return {k: v / z for k, v in out.items()}
    return f


T = AP.calibrated_temperature()
print("router only         top1/logloss:", loo(lambda i: router_probs(dict(data[i][1]), T)))
for kind in ("lr", "nb", "cnb"):
    for alpha in (0.3, 0.5, 0.7, 1.0):
        print(f"{kind:<4} blend alpha={alpha}: ", loo(model_probs(kind, alpha)))
