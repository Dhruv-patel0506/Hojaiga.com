"""
day_runner.py -- the "I'm gone all day" runner: a persistent ticket queue that survives a crash, never stalls, never fakes a result.

  * every ticket is a row in the behavior DB (bm_day_tickets): PENDING -> RUNNING -> DONE | FAILED | ESCALATED | TIMEOUT
  * RESUME: start the SAME run_id again (after a crash, a reboot, a kill) and finished tickets are never redone; a ticket that was
    RUNNING when the process died is INTERRUPTED and retried ONCE (never when it is destructive: that goes to a human)
  * WATCHDOG: each ticket runs on a worker thread with a hard budget; a hung ticket is marked TIMEOUT and the queue moves on
  * RISK GATE: a destructive ticket (organ_48 classify_risk == E2) is ESCALATED for a human and not executed, unless explicitly
    allowed; the rest of the day continues
  * HONESTY: a ticket is DONE only if the executor says so AND the independent `verify(task, result)` agrees; a claim the verifier
    rejects is FAILED ("claimed done, independent check failed"). The report lists done / failed / waiting-for-you with evidence
  * HUD: the capsule shows "N done / N failed / N waiting for you" after every ticket; the report is written to
    data/day_reports/<run_id>.md (+ .json) for the click-through

    run_day(tasks, run_id=..., executor=..., verify=...)       tasks: [{"id","task","app"?,"params"?,"allow_destructive"?}]
    day_report(model, run_id)                                  the same report from the DB (also after a crash)
    python day_runner.py run tasks.json [--run-id X] [--budget 240] [--executor module:function]
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

REPORT_DIR = os.environ.get("HOJAIGA_DAY_REPORT_DIR", os.path.join(r"D:\new_automation", "data", "day_reports"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS bm_day_tickets (
    run_id TEXT, idx INTEGER, task_id TEXT, task TEXT, app TEXT, params_json TEXT, allow_destructive INTEGER DEFAULT 0,
    status TEXT DEFAULT 'PENDING', reason TEXT DEFAULT '', evidence TEXT DEFAULT '', attempts INTEGER DEFAULT 0,
    risk TEXT DEFAULT '', started REAL, finished REAL, heartbeat REAL,
    PRIMARY KEY (run_id, idx));
CREATE INDEX IF NOT EXISTS bm_day_run ON bm_day_tickets(run_id, status);
"""

FINAL = ("DONE", "FAILED", "ESCALATED", "TIMEOUT")


def _ensure(model) -> None:
    if getattr(model, "_day_ready", None) is model._conn:
        return
    model._conn.executescript(SCHEMA)
    model._conn.commit()
    model._day_ready = model._conn


# ------------------------------------------------------------------------------------------------ queue operations

def register(model, run_id: str, tasks: List[Dict[str, Any]]) -> int:
    """Create the tickets of a run once. Registering an existing run_id adds nothing (that is what resume means)."""
    from core_organs import organ_48_app_behavior_model as bm
    _ensure(model)
    have = model._conn.execute("SELECT COUNT(*) c FROM bm_day_tickets WHERE run_id=?", (run_id,)).fetchone()["c"]
    if have:
        return 0
    for i, t in enumerate(tasks):
        model._conn.execute(
            "INSERT INTO bm_day_tickets(run_id, idx, task_id, task, app, params_json, allow_destructive, risk) VALUES (?,?,?,?,?,?,?,?)",
            (run_id, i, str(t.get("id") or f"t{i}"), t["task"], t.get("app", ""), json.dumps(t.get("params") or {}, default=str),
             1 if t.get("allow_destructive") else 0, bm.classify_risk(t["task"])))
    model._conn.commit()
    return len(tasks)


def recover(model, run_id: str, *, stale_s: float = 0.0, max_attempts: int = 2) -> List[str]:
    """A RUNNING ticket in a run nobody is executing was cut off by a crash. Retry it once (non-destructive), else send it to a human."""
    _ensure(model)
    notes = []
    for r in model._conn.execute("SELECT * FROM bm_day_tickets WHERE run_id=? AND status='RUNNING'", (run_id,)).fetchall():
        if time.time() - float(r["heartbeat"] or r["started"] or 0) < stale_s:
            continue
        if r["risk"] == "E2" and not r["allow_destructive"]:
            new, why = "ESCALATED", "interrupted mid-run and destructive: a human decides whether it already happened"
        elif r["attempts"] >= max_attempts:
            new, why = "FAILED", f"interrupted {r['attempts']} times (crash or kill): not retried again"
        else:
            new, why = "PENDING", f"interrupted by a crash on attempt {r['attempts']}: retried"
        model._conn.execute("UPDATE bm_day_tickets SET status=?, reason=? WHERE run_id=? AND idx=?", (new, why, run_id, r["idx"]))
        notes.append(f"#{r['idx']} {r['task_id']}: {new} ({why})")
    model._conn.commit()
    return notes


def _counts(model, run_id: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in model._conn.execute("SELECT status, COUNT(*) c FROM bm_day_tickets WHERE run_id=? GROUP BY status", (run_id,)):
        out[r["status"]] = r["c"]
    return out


def capsule_text(model, run_id: str) -> str:
    c = _counts(model, run_id)
    return (f"{c.get('DONE', 0)} done / {c.get('FAILED', 0) + c.get('TIMEOUT', 0)} failed / "
            f"{c.get('ESCALATED', 0)} waiting for you")


def day_report(model, run_id: str) -> Dict[str, Any]:
    _ensure(model)
    rows = [dict(r) for r in model._conn.execute("SELECT * FROM bm_day_tickets WHERE run_id=? ORDER BY idx", (run_id,))]
    rep: Dict[str, Any] = {"run_id": run_id, "done": [], "failed": [], "waiting_for_you": [], "pending": [], "running": []}
    for r in rows:
        item = {"idx": r["idx"], "id": r["task_id"], "task": r["task"], "app": r["app"], "reason": r["reason"], "evidence": r["evidence"],
                "attempts": r["attempts"], "seconds": round((r["finished"] or 0) - (r["started"] or 0), 1) if r["finished"] and r["started"] else None}
        bucket = {"DONE": "done", "FAILED": "failed", "TIMEOUT": "failed", "ESCALATED": "waiting_for_you", "PENDING": "pending",
                  "RUNNING": "running"}.get(r["status"], "failed")
        item["status"] = r["status"]
        rep[bucket].append(item)
    rep["counts"] = {k: len(rep[k]) for k in ("done", "failed", "waiting_for_you", "pending", "running")}
    rep["capsule"] = capsule_text(model, run_id)
    rep["total"] = len(rows)
    rep["complete"] = rep["counts"]["pending"] == 0 and rep["counts"]["running"] == 0
    return rep


def write_report(model, run_id: str) -> str:
    rep = day_report(model, run_id)
    os.makedirs(REPORT_DIR, exist_ok=True)
    base = os.path.join(REPORT_DIR, re.sub(r"[^A-Za-z0-9_.-]", "_", run_id))
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, default=str)
    lines = [f"# Day report {run_id}", "", f"**{rep['capsule']}**  ({rep['total']} ticket(s); complete={rep['complete']})", ""]
    for title, key in (("Done (independently verified)", "done"), ("Failed", "failed"), ("Waiting for you", "waiting_for_you"),
                       ("Not run yet", "pending"), ("Interrupted", "running")):
        if rep[key]:
            lines += [f"## {title}", ""]
            for it in rep[key]:
                lines.append(f"- #{it['idx']} `{it['id']}` {it['task'][:90]} - {it['status']}: {it['reason'][:160]}"
                             + (f"\n  - evidence: {it['evidence'][:240]}" if it["evidence"] else ""))
            lines.append("")
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return base + ".md"


# ------------------------------------------------------------------------------------------------ one ticket under a watchdog

def _default_executor(task: Dict[str, Any]) -> Dict[str, Any]:
    """The real thing: the full lifecycle (intake, risk gate, template-first or verified loop, checkpoints)."""
    from core_organs import task_lifecycle as tl
    r = tl.run_lifecycle(task["task"], allow_destructive=bool(task.get("allow_destructive")), unattended=True)
    return {"status": r.get("status", "FAILED"), "evidence": "; ".join(f"{t.get('status')}: {str(t.get('evidence') or t.get('error') or '')[:120]}"
                                                                         for t in r.get("tickets", []))[:600], "raw": r}


def _run_with_watchdog(fn: Callable[[], Any], budget_s: float) -> Tuple[str, Any]:
    """(state, value): state is 'ok' | 'error' | 'timeout'. The worker is a daemon thread: a hung ticket cannot hold the process."""
    box: Dict[str, Any] = {}

    def _w() -> None:
        try:
            box["v"] = fn()
            box["s"] = "ok"
        except BaseException as exc:                                  # noqa: BLE001 - a ticket may raise anything; the queue must live
            box["v"], box["s"] = f"{type(exc).__name__}: {str(exc)[:200]}", "error"
    th = threading.Thread(target=_w, daemon=True, name="day-ticket")
    th.start()
    th.join(budget_s)
    if th.is_alive():
        return "timeout", f"no result within {budget_s:.0f}s"
    return box.get("s", "error"), box.get("v")


def run_day(tasks: Optional[List[Dict[str, Any]]] = None, *, run_id: Optional[str] = None, model=None,
            executor: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
            verify: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Tuple[bool, str]]] = None,
            per_task_budget_s: float = 240.0, capsule_cb: Optional[Callable[[str, str], None]] = None,
            cleanup: Optional[Callable[[Dict[str, Any]], None]] = None, stale_s: float = 0.0) -> Dict[str, Any]:
    """Run (or RESUME) a day. Returns day_report(). Safe to call again with the same run_id at any time."""
    from core_organs import organ_48_app_behavior_model as bm
    model = model or bm.get_model()
    _ensure(model)
    run_id = run_id or "day_" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
    created = register(model, run_id, tasks or []) if tasks is not None else 0
    notes = recover(model, run_id, stale_s=stale_s)
    executor = executor or _default_executor
    cap = capsule_cb or _default_capsule

    def _signal() -> None:
        try:
            cap("working", capsule_text(model, run_id))
        except Exception:
            pass
    _signal()
    while True:
        r = model._conn.execute("SELECT * FROM bm_day_tickets WHERE run_id=? AND status='PENDING' ORDER BY idx LIMIT 1", (run_id,)).fetchone()
        if r is None:
            break
        task = {"id": r["task_id"], "task": r["task"], "app": r["app"], "params": json.loads(r["params_json"] or "{}"),
                "allow_destructive": bool(r["allow_destructive"])}
        idx = r["idx"]
        # RISK GATE: destructive tickets wait for a human; the day goes on
        if r["risk"] == "E2" and not r["allow_destructive"]:
            model._conn.execute("UPDATE bm_day_tickets SET status='ESCALATED', reason=?, finished=? WHERE run_id=? AND idx=?",
                                ("destructive/irreversible class (E2): queued for a human, not executed", time.time(), run_id, idx))
            model._conn.commit()
            model.audit(run_id, bm._app_key(task["app"] or "?"), "task", task["task"], "ESCALATED", "E2 queued", "")
            _signal()
            continue
        now = time.time()
        model._conn.execute("UPDATE bm_day_tickets SET status='RUNNING', attempts=attempts+1, started=?, heartbeat=? WHERE run_id=? AND idx=?",
                            (now, now, run_id, idx))
        model._conn.commit()
        state, val = _run_with_watchdog(lambda: executor(task), per_task_budget_s)
        status, reason, evidence = "FAILED", "", ""
        if state == "timeout":
            status, reason = "TIMEOUT", f"watchdog: {val}; the queue moved on"
            if cleanup:
                try:
                    cleanup(task)
                except Exception:
                    pass
        elif state == "error":
            status, reason = "FAILED", f"executor raised {val}"
        else:
            res = val if isinstance(val, dict) else {"status": str(val)}
            claimed = str(res.get("status", "")).upper()
            evidence = str(res.get("evidence", ""))[:600]
            if claimed in ("DONE", "PARTIAL", "COMPLETED"):
                ok, why = verify(task, res) if verify else (claimed == "DONE", "no independent verifier supplied" if claimed == "DONE" else "only partially verified")
                if ok:
                    status, reason = "DONE", "verified" if verify else "executor reports DONE (no independent verifier supplied)"
                else:
                    status, reason = "FAILED", f"executor claimed {claimed} but the independent check failed: {why}"
                evidence = (evidence + " | " if evidence else "") + str(why)[:200]
            elif claimed in ("ESCALATED", "NEEDS_INPUT", "NEEDS_HUMAN"):
                status, reason = "ESCALATED", f"executor needs a human ({claimed})"
            else:
                status, reason = "FAILED", f"executor ended {claimed or 'without a status'}"
        model._conn.execute("UPDATE bm_day_tickets SET status=?, reason=?, evidence=?, finished=?, heartbeat=? WHERE run_id=? AND idx=?",
                            (status, reason, evidence, time.time(), time.time(), run_id, idx))
        model._conn.commit()
        model.audit(run_id, bm._app_key(task["app"] or "?"), "task", task["task"],
                    {"DONE": "DONE", "ESCALATED": "ESCALATED"}.get(status, "FAILED"), reason, evidence)
        _signal()
    path = write_report(model, run_id)
    rep = day_report(model, run_id)
    rep.update(created=created, recovered=notes, report_file=path)
    return rep


def _default_capsule(state: str, text: str) -> None:
    """The floating capsule (visual_cursor) when it is running; harmless otherwise."""
    try:
        from core_organs.visual_cursor import get_cursor
        get_cursor().set_label(text[:60], state)
    except Exception:
        pass


# ------------------------------------------------------------------------------------------------ CLI

def _load_callable(spec: str):
    mod, _, fn = spec.partition(":")
    import importlib
    return getattr(importlib.import_module(mod), fn)


def main(argv: List[str]) -> int:
    sys.path[:0] = [r"D:\new_automation", r"D:\new_automation\All codes"]
    if len(argv) < 2 or argv[0] != "run":
        print("usage: day_runner.py run <tasks.json> [--run-id X] [--budget SECONDS] [--executor module:function] [--verify module:function] [--db PATH]")
        return 2
    opt = lambda f, d: argv[argv.index(f) + 1] if f in argv else d
    from core_organs import organ_48_app_behavior_model as bm
    model = bm.BehaviorModel(opt("--db", bm.DB_PATH))
    tasks = json.load(open(argv[1], encoding="utf-8"))
    rep = run_day(tasks, run_id=opt("--run-id", None), model=model, per_task_budget_s=float(opt("--budget", 240)),
                  executor=_load_callable(opt("--executor", "")) if "--executor" in argv else None,
                  verify=_load_callable(opt("--verify", "")) if "--verify" in argv else None, capsule_cb=lambda s, t: print("[capsule]", t, flush=True))
    print(json.dumps({k: rep[k] for k in ("run_id", "counts", "capsule", "complete", "report_file")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
