"""TPL1's failing leaf, with the evidence the suite throws away.

The test prints (step_id, verdict, attempts). The leaf result also carries `evidence` (the postcondition
verdict text) and `effectors` (which rung delivered) - that is the difference between a name and a cause.
"""
import logging
import os
import sys
import tempfile
import time
import uuid

sys.path.insert(0, r"D:\new_automation")
sys.path.insert(0, r"D:\new_automation\All codes")

logging.basicConfig(level=logging.INFO,
                    filename=os.path.join(r"D:\new_automation\scratch", "_bench_tpl.log"),
                    filemode="w", format="%(asctime)s %(levelname)s %(name)s %(message)s")

from core_organs import organ_48_app_behavior_model as bm            # noqa: E402
from core_organs import si_tests_behavior as sib                     # noqa: E402

APPS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["notepad", "paint"]

# Which effector did the ladder actually pick, and what did the structural probe tell it? The leaf summary
# only shows the LAST attempt's effectors, and three attempts on one effector has two quite different causes
# (rotation never happened vs the rung ran and silently returned).
_ORIG = bm.EffectorLadder.perform


def _titles(hs):
    return sorted({(bm._win_title(h) or bm._win_class(h)).lower() for h in hs})


def _traced(self, app_key, hwnd, action, avoid=None):
    # the dialog question, measured: is a popup ALREADY open before this act? A failed attempt that really did
    # open its dialog leaves it sitting there, and the next attempt's `before` state then contains it - so
    # `window_opened` diffs to nothing and can never pass. Self-poisoning retry.
    pop_before = _titles(bm._popups(hwnd))
    t0 = time.time()
    out = _ORIG(self, app_key, hwnd, action, avoid)
    lp = getattr(self, "last_probe", {}) or {}
    prof = lp.get("profile") or {}
    pop_now = _titles(bm._popups(hwnd))
    print(f"      perform verb={action.get('verb')} keys={action.get('keys')!r} avoid={sorted(avoid or [])} "
          f"-> delivered={out[0]} eff={out[1]!r} note={str(out[2])[:110]}")
    print(f"        order={lp.get('order')} surface={prof.get('surface')!r} hmenu={prof.get('hmenu')} "
          f"native={prof.get('native_reach')}")
    print(f"        popups before={pop_before} at+{time.time() - t0:.2f}s={pop_now}")
    return out


bm.EffectorLadder.perform = _traced


def main() -> int:
    db = tempfile.mktemp(suffix=".db")
    m = bm.BehaviorModel(db)
    m.load_pack_dir()
    try:
        for app in APPS:
            task = "write text and save as file" if app == "notepad" else "save the image as file"
            ext = ".txt" if app == "notepad" else ".png"
            params = {"text": "hello " + uuid.uuid4().hex[:6]} if app == "notepad" else {}
            path = os.path.join(tempfile.gettempdir(), "hj_btpl_" + uuid.uuid4().hex[:6] + ext)
            with sib.LiveApp(app) as la:
                if not la.ok:
                    print(f"{app}: env - {la.why}")
                    continue
                arch = ""
                try:
                    from core_organs.organ_47_app_intelligence import classify_archetype
                    arch = classify_archetype(app)
                except Exception:
                    pass
                tpl = m.match_template(app, task, arch)
                print(f"=== {app} template={getattr(tpl, 'name', None)} source={getattr(tpl, 'source', None)} "
                      f"conf={getattr(tpl, 'confidence', None)}")
                if tpl:
                    for s in tpl.steps:
                        print(f"    step {s.get('id')}: goal={s.get('goal')!r} risk={s.get('risk')} "
                              f"do={s.get('do')} post={s.get('post')}")
                r = bm.TemplateRunner(m).run(app, task, dict(params, path=path),
                                             hwnd_fn=lambda h=la.hwnd: h)
                print(f"  completed={r.get('completed')} blocked_at={r.get('blocked_at')} "
                      f"escalated={r.get('escalated')} file_exists={os.path.exists(path)}")
                for l in r.get("leaves", []):
                    print(f"    leaf {l['step_id']:12} {l['verdict']:9} attempts={l['attempts']} "
                          f"gate={l.get('gate')} effectors={l.get('effectors')}")
                    print(f"      evidence: {str(l.get('evidence'))[:400]}")
                try:
                    os.remove(path)
                except Exception:
                    pass
    finally:
        m.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
