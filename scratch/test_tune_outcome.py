import sys
sys.path.extend([r"D:\new_automation", r"D:\new_automation\All codes"])
from core_organs.professor.history import History
from core_organs.professor.ml.outcome import OutcomeModel, context_from_row, tokens, N_IN
from core_organs.professor.ml.nn import hash_features

h = History("data/professor/history.db")
rows = h.rows(limit=10000)

def test_features(token_fn, lr=0.007, hidden=64):
    import core_organs.professor.ml.outcome as OM
    orig = OM.tokens
    OM.tokens = token_fn
    m = OutcomeModel(None, hidden=hidden, lr=lr)
    last_effect = {}
    for r in rows:
        ctx = context_from_row(r)
        key = (ctx.get("app"), ctx.get("label"))
        if key in last_effect:
            ctx["prev_effect"] = last_effect[key]
        eff = r.get("effect") or ("state_change" if r.get("ok") else "no_effect")
        m.observe(ctx, eff, bool(r.get("ok")))
        if r.get("effect"):
            last_effect[key] = r["effect"]
    OM.tokens = orig
    met = m.metrics()
    return met["ok_accuracy"], met["effect_accuracy"], met["ok_brier"]

# Baseline with current tokens
b_ok, b_eff, b_br = test_features(tokens)
print(f"Current: ok={b_ok:.4f}, eff={b_eff:.4f}, brier={b_br:.4f}")

# Enhanced tokens
def enhanced_tokens(ctx):
    toks = list(tokens(ctx))
    tk = ctx.get("toolkit", "")
    route = ctx.get("route", "")
    role = ctx.get("role", "")
    app = ctx.get("app", "")
    safety = ctx.get("safety", "")
    if tk and route:
        toks.append((f"tk_rt={tk}:{route}", 1.0))
    if role and route:
        toks.append((f"rl_rt={role}:{route}", 1.0))
    if app and tk:
        toks.append((f"app_tk={app}:{tk}", 0.7))
    if safety and route:
        toks.append((f"saf_rt={safety}:{route}", 0.8))
    # interaction of role and safety
    if role and safety:
        toks.append((f"rl_saf={role}:{safety}", 0.6))
    return toks

e_ok, e_eff, e_br = test_features(enhanced_tokens)
print(f"Enhanced: ok={e_ok:.4f}, eff={e_eff:.4f}, brier={e_br:.4f}")

for lr in [0.005, 0.006, 0.007, 0.008]:
    for hid in [48, 64, 80]:
        ok, eff, br = test_features(enhanced_tokens, lr=lr, hidden=hid)
        print(f"lr={lr} hid={hid}: ok={ok:.4f}, eff={eff:.4f}, brier={br:.4f}")
