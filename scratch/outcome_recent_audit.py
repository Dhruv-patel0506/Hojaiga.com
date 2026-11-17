"""Why did outcome ok-accuracy slip (0.856 overall -> 0.764 recent)? Grade the model's own predictions on the LAST 500 history rows, grouped by app and by verb-kind, and show where it misses."""
import sys, json
sys.path.insert(0, r"d:\new_automation\All codes")
from core_organs.professor import history as HS
from core_organs.professor.ml import learner as LN
from core_organs.professor.ml.outcome import context_from_row

h = HS.History()
all_rows = h.rows(since_id=0, limit=100000)
print("total rows", len(all_rows))
last = all_rows[-500:]
l = LN.Learner()
l.attach.__doc__  # no attach: grade directly
def grade(rows):
    tp = fn = 0
    per_app = {}
    per_kind = {}
    wrong = []
    for r in rows:
        ctx = context_from_row(r)
        actual = bool(r.get("ok"))
        try:
            p = l.outcome.predict(ctx)
        except Exception as exc:
            print("predict err", exc); continue
        pred = bool((p.get("ok") or p.get("p_ok") or 0) >= 0.5)
        conf = float(p.get("ok") or p.get("p_ok") or 0)
        a = ctx.get("app") or "?"
        k = ctx.get("label") or ctx.get("verb") or "?"
        d = per_app.setdefault(a, [0, 0]); e = per_kind.setdefault(k, [0, 0])
        d[1] += 1; e[1] += 1
        if pred == actual:
            tp += 1; d[0] += 1; e[0] += 1
        else:
            fn += 1
            if len(wrong) < 25:
                wrong.append({"app": a, "label": k, "effect": r.get("effect"), "route": ctx.get("route"), "conf": round(conf, 3), "actual_ok": actual})
    return tp, fn, per_app, per_kind, wrong

tp, fn, per_app, per_kind, wrong = grade(last)
print(f"recent 500: right {tp} wrong {fn} -> {tp/(tp+fn):.3f}")
print("by app (right/total):")
for a, (c, n) in sorted(per_app.items(), key=lambda kv: -kv[1][1]):
    print(f"  {a:24s} {c}/{n} = {c/n:.2f}")
print("worst labels (right/total, n>=8):")
rows = sorted(((c, n, k) for k, (c, n) in per_kind.items() if n >= 8))
for c, n, k in rows[:12]:
    print(f"  {k[:40]:40s} {c}/{n} = {c/n:.2f}")
print("sample misses:")
for w in wrong[:12]:
    print("  ", json.dumps(w))
