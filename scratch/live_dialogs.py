"""live_dialogs.py -- Notepad: File > Open (a real common dialog) -> sandbox fixture; File > Save as -> sandbox outbox; Edit > Paste -> fixture text, the person's clipboard untouched afterwards."""
import os, sys, time, hashlib, json
os.environ["HOJAIGA_REVEAL"] = "0"
sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes"]
from core_organs.professor import apprun as AR, dialogs as DG
from core_organs.professor.knowledge import guide_steps as GS


def clip_sig():
    try:
        return DG.ClipboardGuard().signature()
    except Exception as exc:
        return f"?{type(exc).__name__}"


import threading, _thread
threading.Timer(210, lambda: _thread.interrupt_main()).start()
sig0 = clip_sig()
run = AR.AppRun(AR.SPECS["notepad"], vision=False, log=lambda s: None, phases=())
try:
    assert run.start()
    run.perceive()
    ex = run.ex
    print("\n== dialog layer:", bool(run.dialogs), "sandbox:", run.sandbox.root if run.sandbox else None, "deny:", ex.deny.pattern[:80])
    cases = {
        "open": "1. Select **File** > **Open**.\n2. Select the file you want to open.\n3. Click Open.",
        "save_as": "1. Select **File** > **Save as**.\n2. Type a name for your file in the File name box.\n3. Click Save.",
        "paste": "1. Select **Edit** > **Paste**.",
    }
    for name, text in cases.items():
        steps = GS.parse_steps(text)
        t = {"goal": name, "cite": "live-test", "source": "test", "steps": steps, "grounded": 1.0}
        tr = run.run_task(t)
        at = tr.attempts[-1]
        print(f"\n[{name}] final={tr.final} attempts={len(tr.attempts)} done={at.done}/{at.steps} why={at.why[:140]}")
        for r in at.results:
            if "verb" in r:
                print(f"    step {r['step']} {r['verb'][:40]!r}: {r['status']} via {r['route'][:40]} | {r['summary'][:230]}")
        time.sleep(1.0)
    print("\n== dialogs handled:", json.dumps([{k: h.get(k) for k in ("kind", "title", "ok", "path")} for h in ex.dialog_log], default=str)[:700])
    print("== sandbox:", json.dumps(run.sandbox.summary(), default=str)[:600])
    from core_organs.professor.probe import snapshot
    s = snapshot(run.hwnd, with_image=False)
    print("== tabs/texts now:", [v for v in list(s.texts.values())[:6]], [v for v in list(s.names.values()) if "txt" in v.lower() or "fixture" in v.lower() or "Untitled" in v][:6])
finally:
    run.finish()
print("\nclipboard signature same as before the test:", clip_sig() == sig0, "| notes:", run.clip.notes if run.clip else None)
