"""Weekly agents' report card (brief 2, gate G2): which agent to trust with what, earned autonomy, drift, failure map,
NI's own trust, and the live shadow verdicts joined to real outcomes.   -> REPORT_CARD.md

Run: venv\\Scripts\\python.exe -X utf8 natural_intelligence\\gov_card.py [--days 7]
"""
import os, sys, json, time, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cc_core, gov_core, gov_policy, gov_ledger

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "REPORT_CARD.md")
LEVEL_NAMES = ["0 intern", "1 junior", "2 worker", "3 senior", "4 lead"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=7); a = ap.parse_args()
    recs = [r for r in sorted(cc_core.load_actions().values(), key=lambda r: r["ts"]) if r["outcome"] != "unknown"]
    now = recs[-1]["ts"] if recs else time.time(); since = now - a.days * 86400
    G = gov_core.Governor(ledger=False); P, integ = G.policy
    week = collections.defaultdict(lambda: [0, 0]); before = collections.defaultdict(lambda: [0, 0])
    reasons = collections.defaultdict(collections.Counter)
    for r in recs:
        reason, _ = G.observe(r)
        cls = gov_policy.classify(r["tool"], r["text"], P)[0]["name"]; key = (r["model"], cls)
        d = week if r["ts"] >= since else before
        d[key][0] += 1; d[key][1] += int(r["outcome"] != "ok")
        if reason:
            reasons[key][reason] += 1
    L = [f"# Agents' report card ({time.strftime('%Y-%m-%d')}, last {a.days} days vs before)", "",
         f"Source: {len(recs)} real Claude Code actions on this machine. Autonomy = earned level from the lower 95% bound of "
         f"success (unit: agent x action class). Policy approved by a human: **{'yes' if integ['ok'] else 'NO - ' + str(integ['reason'])}**.", "",
         "| agent | action class | actions (week) | failure rate week | failure rate before | lower bound of success | level | drift | top failure reasons |",
         "|---|---|---|---|---|---|---|---|---|"]
    keys = sorted(set(week) | set(before), key=lambda k: -(week[k][0] + before[k][0]))
    for k in keys:
        if week[k][0] + before[k][0] < 10:
            continue
        post = G.B.posterior(k[0], k[1], unit="class"); lvl, lcb = G.level(post)
        fw = week[k][1] / week[k][0] if week[k][0] else None; fb = before[k][1] / before[k][0] if before[k][0] else None
        rs = ", ".join(f"{x} {n}" for x, n in reasons[k].most_common(3))
        L.append(f"| {k[0]} | {k[1]} | {week[k][0]} | {'-' if fw is None else f'{fw:.1%}'} | {'-' if fb is None else f'{fb:.1%}'} | "
                 f"{lcb:.3f} | {LEVEL_NAMES[lvl]} | {'ALARM' if post['drift'] else '-'} | {rs} |")
    L += ["", "Irreversible classes (publish, delete, money, secrets) need a human at every level, whatever the record.", ""]
    # live shadow verdicts joined to outcomes
    lf = os.path.join(cc_core.CC_DIR, "live_scores.jsonl"); acts = cc_core.load_actions(); rows = []
    if os.path.exists(lf):
        for line in open(lf, encoding="utf-8"):
            try:
                x = json.loads(line)
            except Exception:
                continue
            if "verdict_if_approved" in x and not str(x.get("tool_use_id", "")).startswith("e2e_test"):
                o = acts.get(x["tool_use_id"]); x["outcome"] = o["outcome"] if o else None; rows.append(x)
    L += ["## Live shadow verdicts (logged before each action, never enforced)", ""]
    if rows:
        res = [x for x in rows if x["outcome"] not in (None, "unknown")]
        v = collections.Counter(x["verdict_if_approved"] for x in rows)
        esc = [x for x in res if x["verdict_if_approved"] != "proceed"]; fails = [x for x in res if x["outcome"] != "ok"]
        L += [f"{len(rows)} actions scored, {len(res)} with a known outcome, {len(fails)} failed. Verdicts (as if approved): {dict(v)}.",
              f"Escalated and failed: {sum(x['outcome'] != 'ok' for x in esc)} of {len(esc)} escalations; "
              f"failures escalated: {sum(x['verdict_if_approved'] != 'proceed' for x in fails)} of {len(fails)}.", ""]
    else:
        L += ["No governor verdicts logged yet (cc_serve.py must be restarted with the governor build).", ""]
    st = gov_core.load_self_state()
    L += ["## NI's own record (L18)", "",
          f"Gate calibration on held-out actions: ECE {st.get('ece_raw')} raw -> {st.get('ece_adopted')} after the adopted map; "
          f"autonomy budget {st.get('budget')}. Ledger: {gov_ledger.verify()}.", ""]
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
