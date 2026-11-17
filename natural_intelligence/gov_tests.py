"""Governor property tests (brief 1 sections 5.6, 4.3 L1/L2/L15/L17/L18; 6.6 honesty rule). Offline, no live runs.

Run: venv\\Scripts\\python.exe -X utf8 natural_intelligence\\gov_tests.py      -> prints PASS/FAIL per test, exit 1 on any FAIL
"""
import os, sys, json, random, tempfile, shutil, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gov_policy, gov_decide, gov_beliefs, gov_ledger, gov_cow, gov_select

P, _ = gov_policy.load()
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail)); print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def rand_s(rng):
    cl = rng.choice(P["classes"])
    q = rng.random() ** 0.3
    s = dict(q_raw=q, q_prior=rng.random() ** 0.3, self_budget=1.0, loss=cl["loss"] * rng.choice([1.0, 3.0]),
             irreversible=bool(cl.get("irreversible")), requires_human=bool(cl.get("requires_human")), hard_value=cl.get("hard_value"),
             level=rng.randint(0, 4), required_level=int(cl.get("required_level", 2)), drift=rng.random() < 0.2,
             human_acc=0.5 + rng.random() * 0.5, asks_hour=rng.randint(0, 30), N=100, F=3)
    s["q"] = q
    return s


def esc(s):
    return gov_decide.decide(s, P)[0] != "proceed"


def t_monotonicity(n=4000):
    rng = random.Random(7); bad = {"q": 0, "loss": 0, "level": 0, "drift": 0}
    for _ in range(n):
        s = rand_s(rng)
        t = dict(s); t["q"] = min(1.0, s["q"] + rng.random() * (1 - s["q"]))          # more reliable
        bad["q"] += int(esc(t) and not esc(s))
        t = dict(s); t["loss"] = s["loss"] * (1 + rng.random() * 5)                   # higher stakes
        bad["loss"] += int(esc(s) and not esc(t))
        t = dict(s); t["level"] = min(4, s["level"] + 1)                             # more earned autonomy
        bad["level"] += int(esc(t) and not esc(s))
        t = dict(s); t["drift"] = True                                                # drift alarm on
        bad["drift"] += int(esc(s) and not esc(t))
    check("monotonicity: reliability up never raises escalation", bad["q"] == 0, f"{bad['q']} violations / {n}")
    check("monotonicity: stakes up never lowers escalation", bad["loss"] == 0, f"{bad['loss']} violations / {n}")
    check("monotonicity: earned level up never raises escalation", bad["level"] == 0, f"{bad['level']} violations / {n}")
    check("monotonicity: drift alarm never lowers escalation", bad["drift"] == 0, f"{bad['drift']} violations / {n}")


def base_s(**kw):
    s = dict(q_raw=0.97, q=0.97, q_prior=0.97, self_budget=1.0, loss=2.0, irreversible=False, requires_human=False, hard_value=None,
             level=3, required_level=2, drift=False, human_acc=0.9, asks_hour=0, N=200, F=6)
    s.update(kw); return s


def t_counterfactual_pairs():
    """Pairs that differ in exactly one factor, each with the expected direction (brief 1, 5.6 item 2)."""
    V = lambda s: gov_decide.decide(s, P)[0]
    pairs = [
        ("read action, reliable agent -> proceed", V(base_s(loss=0.5, q=0.99)) == "proceed"),
        ("same action, failure chance 60% -> not proceed", V(base_s(loss=0.5, q=0.4)) != "proceed"),
        ("shell 97% ok -> proceed; shell 80% ok -> escalate", V(base_s(q=0.97)) == "proceed" and V(base_s(q=0.80)) != "proceed"),
        ("delete class always asks the human, even at q=0.9999", V(base_s(q=0.9999, loss=30, irreversible=True, requires_human=True)) == "ask_human"),
        ("new agent (level 0) on an edit -> verify, not proceed", V(base_s(level=0, loss=3)) == "verify"),
        ("drift alarm demotes level 2 -> verify", V(base_s(level=2, drift=True)) == "verify" and V(base_s(level=2)) == "proceed"),
        ("busy human: same uncertain action asks less", not (V(base_s(q=0.75, loss=6, asks_hour=40)) == "ask_human" and
                                                                V(base_s(q=0.75, loss=6, asks_hour=0)) != "ask_human")),
        ("useless human (a=0.5) is never asked for VOI", V(base_s(q=0.6, loss=6, human_acc=0.5)) != "ask_human"),
        ("reliable human + uncertain costly action -> ask", V(base_s(q=0.6, loss=20, human_acc=0.98)) == "ask_human"),
        ("same shell command: test env proceeds, production (loss x3) verifies", V(base_s(q=0.9, loss=2)) == "proceed" and V(base_s(q=0.9, loss=6)) == "verify"),
        ("policy integrity broken -> ask even for a read", gov_decide.decide(base_s(loss=0.5, q=0.999), P, integrity_ok=False)[0] == "ask_human"),
    ]
    for name, ok in pairs:
        check("pair: " + name, ok)


def t_voi_and_shapley():
    rng = random.Random(3); neg = 0; sh_bad = 0
    for _ in range(1500):
        s = rand_s(rng); U, V = gov_decide.utilities(s, P)
        neg += int(V["VOI"] < -1e-9)
        v, b, U, _ = gov_decide.decide(s, P)
        if v != "proceed" and b is None:
            phi = gov_decide.shapley(s, P); base = gov_decide.baseline(s, P)
            t = dict(s); t.update(base); Ub, _ = gov_decide.utilities(t, P)
            eff = (U[v] - U["proceed"]) - (Ub[v] - Ub["proceed"])
            sh_bad += int(abs(sum(phi.values()) - eff) > 1e-6)
    check("VOI is never negative (information cannot hurt an expected-utility maximiser)", neg == 0, f"{neg} negatives")
    check("Shapley efficiency: reasons sum to the full escalation margin", sh_bad == 0, f"{sh_bad} mismatches")


def t_trace_rederive():
    rng = random.Random(11); bad = 0
    for _ in range(500):
        s = rand_s(rng); tr = gov_decide.govern(s, P, True, "x")
        bad += int(gov_decide.rederive(tr, P) != tr["verdict"])
        for c in tr["counterfactuals"]:
            t = dict(s); t[c["factor"]] = c["flips_at"]
            bad += int(gov_decide.decide(t, P)[0] != c["to"])
    check("L17 trace: verdict and every counterfactual re-derive from the trace alone", bad == 0, f"{bad} mismatches")


def t_tone_honesty():
    rng = random.Random(5); bad = 0
    for _ in range(3000):
        s = rand_s(rng); v, b, _, _ = gov_decide.decide(s, P); t = gov_decide.tone(s, v, b)
        bad += int(t["assertiveness"] > t["cap"] + 1e-9)
    check("tone honesty: assertiveness never exceeds f(calibrated confidence)", bad == 0, f"{bad} violations")


def t_beliefs():
    B = gov_beliefs.Beliefs(gamma=1.0, k=5.0)
    mk = lambda o, m="A", i=0: dict(model=m, tool="Bash", text="Bash: pytest -q", target="", outcome=o, ts=i)
    for i in range(50):
        B.update(mk("ok", "A", i))
    p_new = B.posterior("B", "bash:pytest")
    check("hierarchical prior: an unseen agent starts at the region's pooled rate", abs(p_new["mean"] - B.posterior("A", "bash:pytest")["prior_region"]) < 1e-9)
    B2 = gov_beliefs.Beliefs(gamma=0.9)
    for i in range(200):
        B2.update(mk("ok", "A", i))
    k = B2.keys[("agent_region", "A", gov_beliefs.Beliefs.region_of(mk("ok")))]
    check("forgetting: discounted count converges to 1/(1-gamma)", abs(k.s - (1 - 0.9 ** 200) / 0.1) < 1e-6, f"s={k.s:.3f}")
    # drift: 400 events at 3% failure, then the 'vendor update' makes it 30%
    rng = random.Random(1); B3 = gov_beliefs.Beliefs(gamma=1.0); first = None; false = 0
    for i in range(700):
        p = 0.03 if i < 400 else 0.30
        al = B3.update(mk("ok" if rng.random() > p else "exit_nonzero", "A", i))
        if any(a["key"][0] == "agent_region" for a in al):
            if i < 400:
                false += 1
            elif first is None:
                first = i - 400
    check("CUSUM catches an injected vendor update (3% -> 30% failures)", first is not None and first <= 60 and false == 0,
          f"delay {first} events, false alarms before change {false}")
    check("Hoeffding: eps=0.05, delta=0.05 needs 738 probes", gov_beliefs.hoeffding_n(0.05, 0.05) == 738)


def t_ledger():
    d = tempfile.mkdtemp(); f = os.path.join(d, "l.jsonl"); L = gov_ledger.Ledger(f)
    for i in range(20):
        L.append("decision", dict(id=f"a{i}", verdict="proceed")); L.append("outcome", dict(id=f"a{i}", o="ok"))
    ok1 = gov_ledger.verify(f)
    lines = open(f, encoding="utf-8").read().splitlines(); lines[7] = lines[7].replace('"ok"', '"exit_nonzero"')
    open(f, "w", encoding="utf-8").write("\n".join(lines) + "\n"); ok2 = gov_ledger.verify(f)
    check("ledger: intact chain verifies, all decisions resolved", ok1["ok"] and ok1["resolved_fraction"] == 1.0)
    check("ledger: one edited past outcome is detected at that line", (not ok2["ok"]) and ok2["broken_at"] == 7, str(ok2["broken_at"]))
    shutil.rmtree(d, ignore_errors=True)


def t_cow():
    d = tempfile.mkdtemp(); src = os.path.join(d, "proj"); os.makedirs(src)
    open(os.path.join(src, "m.py"), "w").write("def f(x):\n    return x*2\n")
    open(os.path.join(src, "test_m.py"), "w").write("from m import f\nassert f(3) == 6\n")
    h0 = gov_cow.tree_hash(src)[0]
    def good(c):
        open(os.path.join(c, "m.py"), "w").write("def f(x):\n    return x + x\n")
    def bad(c):
        open(os.path.join(c, "m.py"), "w").write("def f(x):\n    return x + 1\n")
    py = sys.executable
    p1 = gov_cow.propose(src, good, f'"{py}" test_m.py'); p2 = gov_cow.propose(src, bad, f'"{py}" test_m.py')
    check("COW: a correct transform on the copy is eligible, original hash unchanged",
          p1["eligible_for_promotion"] and not p1["invariant_violation"] and gov_cow.tree_hash(src)[0] == h0)
    check("COW: a breaking transform is refused, original hash unchanged",
          (not p2["eligible_for_promotion"]) and gov_cow.tree_hash(src)[0] == h0)
    def sneaky(c):                                         # a transform that reaches back and edits the ORIGINAL
        open(os.path.join(src, "m.py"), "a").write("# touched\n")
    p3 = gov_cow.propose(src, sneaky, f'"{py}" test_m.py')
    check("COW: a transform that touches the original is caught as an invariant violation", p3["invariant_violation"] and not p3["eligible_for_promotion"])
    rc = gov_cow.promote(p1["id"]) if not sys.stdin.isatty() else 2
    check("COW: promotion without an interactive human is refused", rc == 2)
    shutil.rmtree(d, ignore_errors=True)


def t_policy_lock():
    d = tempfile.mkdtemp(); pf = os.path.join(d, "p.json"); lf = os.path.join(d, "p.lock")
    shutil.copy(gov_policy.POLICY, pf)
    open(lf, "w").write(gov_policy.sha(pf) + " test\n")
    ok1 = gov_policy.load(pf, lf)[1]["ok"]
    j = json.load(open(pf)); j["epsilon_irreversible"] = 0.9; time.sleep(0.02); json.dump(j, open(pf, "w"))
    ok2 = gov_policy.load(pf, lf)[1]["ok"]
    check("policy lock: approved policy is trusted; a loosened policy is detected", ok1 and not ok2)
    import gov_core
    G = gov_core.Governor(ledger=False, policy_path=pf, lock_path=lf)
    tr = G.govern(dict(id="t", ts=1.0, model="m", tool="Read", text="Read x.py", target="x.py"), risk=0.0001, record=False)
    check("policy lock: governor with a tampered policy asks the human for everything", tr["verdict"] == "ask_human" and tr["binding"] == "policy_integrity")
    check("policy: running the approve command is itself classed destructive (needs a human)",
          gov_policy.classify("Bash", "Bash: python gov_policy.py approve", P)[0]["name"] == "destructive_local")
    shutil.rmtree(d, ignore_errors=True)


def t_classifier():
    C = lambda t, x: gov_policy.classify(t, x, P)[0]["name"]
    cases = [("Bash", "Bash: git push origin main", "external_publish"), ("Bash", "Bash: rm -rf build", "destructive_local"),
             ("PowerShell", "PowerShell: Remove-Item -Recurse x", "destructive_local"), ("Bash", "Bash: pytest -q", "shell"),
             ("Edit", "Edit a.py | old: x", "reversible_write"), ("Read", "Read a.py", "read"),
             ("mcp__Claude_Browser__computer", "mcp__Claude_Browser__computer: {}", "ui_action"),
             ("mcp__b8__send_message", "x", "external_publish"), ("Bash", "Bash: curl -H 'Authorization: Bearer abcdefghijklmnop' x", "secret_exposure"),
             ("mcp__ccd_turn__update_plan", "x", "plan_ui"),
             ("mcp__ccd_turn__update_plan", 'mcp__ccd_turn__update_plan: {"items": [{"content": "git push, Vercel deploy, transfer"}]}', "plan_ui"),
             ("PowerShell", "PowerShell: Stop-Process -Id 9644 -Force", "process_control"),
             ("PowerShell", "PowerShell: Stop-Process -Name chrome", "destructive_local"),
             ("Bash", "Bash: curl -s -X POST http://127.0.0.1:11500/pick -d x", "shell"),
             ("Bash", "Bash: curl -s -X POST https://api.github.com/repos/x/issues", "external_publish"),
             ("Bash", 'Bash: curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user', "shell"),
             ("Read", "Read notes.md (mentions rm -rf and git push)", "read"),
             ("Bash", "Bash: ls | grep -i transfer", "shell")]
    bad = [(t, x, C(t, x), e) for t, x, e in cases if C(t, x) != e]
    check("action classifier on known cases", not bad, str(bad)[:300])
    fr = gov_policy.failure_reason
    check("failure reasons kept with a cause", fr("blocked", "", P) == "unsafe_blocked" and fr("exit_nonzero", "No such file or directory", P) == "wrong_fact"
          and fr("tool_error", "<tool_use_error>String to replace not found... old_string", P) in ("wrong_fact", "wrong_scope") and fr("ok", "", P) is None)


def t_select():
    r = gov_select.simulate(T=6000, seeds=6)
    ni = r["NI Thompson + CUSUM reset (L2 drift rule)"]; fx = r["fixed router (best at start)"]; nf = r["Thompson, no forgetting"]
    check("selection (SIMULATED vendor update): NI regret < fixed router and < no-forgetting at T=6000",
          ni["regret_at"][6000] < fx["regret_at"][6000] and ni["regret_at"][6000] < nf["regret_at"][6000],
          f"NI {ni['regret_at'][6000]} vs fixed {fx['regret_at'][6000]} vs no-forget {nf['regret_at'][6000]}")
    check("selection (SIMULATED): NI regret curve flattens after the change (slope < fixed router's / 10)",
          ni["slope_last_1000"] < fx["slope_last_1000"] / 10, f"{ni['slope_last_1000']} vs {fx['slope_last_1000']}")


def t_branch():
    import gov_branch
    d = tempfile.mkdtemp(); src = os.path.join(d, "proj"); os.makedirs(src)
    open(os.path.join(src, "m.py"), "w").write("def f(x):\n    return x*2\n")
    open(os.path.join(src, "test_m.py"), "w").write("from m import f\nassert f(3) == 6 and f(-2) == -4\n")
    h0 = gov_cow.tree_hash(src)[0]; py = f'"{sys.executable}" test_m.py'
    w = lambda body: (lambda c: open(os.path.join(c, "m.py"), "w").write(body))
    small = w("def f(x):\n    return x + x\n")
    verbose = w("def f(x):\n    # doubled\n    y = x\n    y = y + x\n    z = y\n    if z is None:\n        z = 0\n    return z\n")
    broken = w("def f(x):\n    return x + 1\n")
    rec = gov_branch.explore(src, [dict(name="small", agent="A", transform=small), dict(name="verbose", agent="B", transform=verbose),
                                   dict(name="broken", agent="C", transform=broken)], py)
    by = {r["name"]: r for r in rec["branches"]}
    check("branch: all three children evaluated and kept (none pruned from the record)", len(rec["branches"]) == 3)
    check("branch: the failing child is kept with its failure reason", (not by["broken"]["feasible"]) and "check failed" in by["broken"]["kept_because"])
    check("branch: recommends the correct, smallest change with P_best >= 0.8",
          rec["verdict"] == "recommend" and rec["recommend"] == "small", f"{rec['verdict']} {rec.get('p_best')}")
    check("branch: original unchanged after evaluating every branch", rec["invariant_ok"] and gov_cow.tree_hash(src)[0] == h0)
    # a real trade-off: smaller change from a less trusted agent vs larger change from a trusted one -> cross-question
    small2 = dict(name="small_low_trust", agent="A", transform=small, extra=dict(agent_trust=0.55))
    big2 = dict(name="verbose_high_trust", agent="B", transform=verbose, extra=dict(agent_trust=0.97))
    r2 = gov_branch.explore(src, [small2, big2], py, extra_dims=("agent_trust",))
    q = (r2.get("question") or {}).get("more_important")
    check("branch: an unresolved trade-off is not decided silently; NI asks the most informative question",
          r2["verdict"] == "cross_question" and q is not None and set(q) == {"compact", "agent_trust"}, f"{r2['verdict']} q={q} p={r2.get('p_best')}")
    a1 = gov_branch.answer(json.loads(json.dumps(r2)), "agent_trust", "compact")
    a2 = gov_branch.answer(json.loads(json.dumps(r2)), "compact", "agent_trust")
    check("branch: the human's answer moves the pick in the stated direction (trust -> trusted branch; compact -> small branch)",
          a1["p_best"]["verbose_high_trust"] > r2["p_best"]["verbose_high_trust"] and a2["p_best"]["small_low_trust"] > r2["p_best"]["small_low_trust"],
          f"{a1['p_best']} / {a2['p_best']}")
    # tree: a child refines its parent; both levels evaluated
    fix_name = lambda c: open(os.path.join(c, "m.py"), "a").write("\n\ndouble = f\n")
    r3 = gov_branch.explore(src, [dict(name="broken", agent="C", transform=broken, children=[dict(name="refine", agent="C", transform=small)])], py)
    names = [r["name"] for r in r3["branches"]]
    check("branch tree: a failed parent's child is still explored, and it can succeed", names == ["broken", "broken/refine"]
          and r3["recommend"] == "broken/refine", f"{names} {r3['verdict']} {r3.get('recommend')}")
    shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    for t in (t_branch,t_monotonicity, t_counterfactual_pairs, t_voi_and_shapley, t_trace_rederive, t_tone_honesty, t_beliefs,
              t_ledger, t_cow, t_policy_lock, t_classifier, t_select):
        try:
            t()
        except Exception as e:
            import traceback; traceback.print_exc(); check(t.__name__ + " crashed", False, repr(e)[:200])
    n_ok = sum(ok for _, ok, _ in RESULTS)
    print(f"\n{n_ok}/{len(RESULTS)} passed")
    json.dump([dict(name=a, ok=b, detail=c) for a, b, c in RESULTS],
              open(os.path.join(gov_ledger.GOV_DIR, "tests_last.json"), "w", encoding="utf-8"), indent=1)
    sys.exit(0 if n_ok == len(RESULTS) else 1)
