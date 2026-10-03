"""task_one.py - run ONE task through the system and verify the outcome independently. See task_bench.py."""
import json
import os
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes\core_organs")
sys.path.insert(0, r"D:\new_automation\All codes")
sys.path.insert(0, r"D:\new_automation")


def verify(truth: dict, app: str) -> tuple:
    if "file_has" in truth:
        path, text = truth["file_has"]
        end = time.time() + 4
        while time.time() < end and not os.path.exists(path):
            time.sleep(0.3)
        try:
            body = open(path, encoding="utf-8", errors="replace").read()
            return text in body, f"file exists, {len(body)} chars"
        except Exception as exc:
            return False, f"file missing ({type(exc).__name__})"
    if "png" in truth:
        try:
            with open(truth["png"], "rb") as fh:
                return fh.read(8) == b"\x89PNG\r\n\x1a\n", "png header ok"
        except Exception as exc:
            return False, f"png missing ({type(exc).__name__})"
    # UI-state truths: read the live window (parked so nothing is shown or focused)
    from core_organs import universal_scan as us, fast_uia, background_window as bw
    from core_organs import desktop_grounding as dg
    hwnd = dg.DesktopGrounding().find_window(app) or 0
    if not hwnd:
        return False, "app window not found"
    with bw.BackgroundSession(hwnd):
        time.sleep(1.0)
        snap = fast_uia.snapshot(hwnd, timeout_ms=8000) or []
        names = [n.name for n in snap if n.name]
    if "calc_display" in truth:
        want = truth["calc_display"]
        hit = [n for n in names if n.lower().startswith("display is") and want in n]
        return bool(hit), f"display reads {[n for n in names if n.lower().startswith('display is')][:2]}"
    if "window_text" in truth:
        w = truth["window_text"].lower()
        return any(w in n.lower() for n in names), f"{len(names)} names read; match={any(w in n.lower() for n in names)}"
    return False, "no truth spec"


def main():
    name, app, task, truth, entry = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4]), sys.argv[5]
    t0 = time.time()
    out = {"entry": entry}
    try:
        if "|" in task:                                    # "template task|path|text": the template runner path
            from core_organs import organ_48_app_behavior_model as bm
            ttask, path, text = task.split("|")
            m = bm.get_model()
            m.load_pack_dir()
            r = bm.TemplateRunner(m).run(app, ttask, {"path": path, "text": text})
            out.update(claimed_done=bool(r.get("completed")), steps=len(r.get("leaves", [])), matched=r.get("matched"),
                       blocked_at=r.get("blocked_at"), seconds_run=r.get("elapsed_s"))
        else:                                              # the existing "leave the bot working" entry point
            from core_organs.desktop_grounding import operate_app
            r = operate_app(app, task, max_steps_per_goal=5)
            out.update(claimed_done=bool(r.get("completed")), steps=r.get("steps"), launched=r.get("launched"),
                       awaiting_human=r.get("awaiting_human"), blocked_at_goal=r.get("blocked_at_goal"),
                       seconds_run=r.get("elapsed_s"), trace_tail=[(t.get("goal", "")[:30], t.get("verdict"), t.get("element", "")[:20])
                                                                    for t in (r.get("trace") or [])[-4:]])
    except Exception as exc:
        import traceback
        out.update(error=f"{type(exc).__name__}: {str(exc)[:160]}", trace=traceback.format_exc()[-500:], claimed_done=False)
    ok, why = verify(truth, app)
    out.update(truth_ok=ok, truth_detail=why, total_s=round(time.time() - t0, 1))
    print("TASK_JSON " + json.dumps(out, default=str))


if __name__ == "__main__":
    main()
