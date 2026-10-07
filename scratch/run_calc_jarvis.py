"""Jarvis loop live proof: run 'add 21 and 21' TWICE in one process.
Run 1 = first time (record writes the outcome). Run 2 = prefetch must report seen/confident/hint.
No cleanup: Calculator stays warm for run 2 (a kill between runs would hit the cold-start blocker)."""
import time, json, sys, logging

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(levelname)s %(name)s: %(message)s")

from core_organs.desktop_grounding import operate_app


def show(tag, res):
    out = {
        "tag": tag,
        "completed": res.get("completed"),
        "steps": res.get("steps"),
        "elapsed_s": res.get("elapsed_s"),
        "launch_note": (res.get("launch_note") or "")[:300],
        "recipe": res.get("recipe"),
        "memory_hint": (res.get("memory_hint") or "")[:200],
    }
    print("RESULT " + json.dumps(out, default=str))


res1 = operate_app("Calculator", ["add 21 and 21"], isolated=True)
show("run1(first-ever)", res1)
time.sleep(1.5)
res2 = operate_app("Calculator", ["add 21 and 21"], isolated=True)
show("run2(should-remember)", res2)
