p = r"D:\new_automation\All codes\core_organs\hojaiga_run.py"
s = open(p, encoding="utf-8").read()

# resume: re-run only the tickets of the last run that were not finished
old = 'def run(task: str, yes: bool = False, dry: bool = False, say=print, rag: Any = None, boot_first: bool = True, executors: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:'
assert old in s
new = '''GOOD = {"DONE", "ANSWERED", "DRAFTED"}


def unfinished_from_last(runs_dir: str = "") -> Tuple[str, List[str]]:
    """(the last run's id, the texts of its tickets that did not finish): a job left half done is continued, not started again."""
    folder = runs_dir or RUNS
    try:
        last = json.load(open(os.path.join(folder, "last_run.json"), encoding="utf-8"))
    except Exception:
        return "", []
    return last.get("run_id", ""), [t["text"] for t in last.get("tickets", []) if (t.get("result") or {}).get("status") not in GOOD]


def run(task: str, yes: bool = False, dry: bool = False, say=print, rag: Any = None, boot_first: bool = True, executors: Optional[Dict[str, Any]] = None, resume: bool = False) -> Dict[str, Any]:'''
s = s.replace(old, new, 1)

old = '''    ex = executors or {}
    rep: Dict[str, Any] = {"run_id": run_id, "task": task, "status": "FAILED", "tickets": []}'''
assert old in s
new = '''    ex = executors or {}
    if resume:
        prev, left = unfinished_from_last()
        if not left:
            say("RESUME: the last run has nothing unfinished" if prev else "RESUME: there is no earlier run")
            return {"run_id": run_id, "task": task, "status": "NOTHING_TO_RESUME", "tickets": [], "resumed_from": prev}
        task = "; ".join(left)
        say(f"RESUME: continuing run {prev}: {len(left)} unfinished ticket(s)")
    rep: Dict[str, Any] = {"run_id": run_id, "task": task, "status": "FAILED", "tickets": []}'''
s = s.replace(old, new, 1)

old = '''    with contextlib.suppress(Exception):
        json.dump(rep, open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)'''
assert old in s
new = '''    with contextlib.suppress(Exception):
        json.dump(rep, open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)
        if rep.get("tickets"):
            json.dump(rep, open(os.path.join(os.path.dirname(out_dir), "last_run.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)'''
s = s.replace(old, new, 1)

old = '    ap.add_argument("--dry", action="store_true"'
assert old in s
s = s.replace(old, '    ap.add_argument("--resume", action="store_true", help="continue the last run: only its unfinished tickets are done again")\n' + old, 1)
old = "    task = \" \".join(a.task).strip()\n    if not task:"
assert old in s
s = s.replace(old, "    task = \" \".join(a.task).strip()\n    if not task and not a.resume:", 1)
old = "    r = run(task, yes=a.yes, dry=a.dry)"
assert old in s
s = s.replace(old, "    r = run(task, yes=a.yes, dry=a.dry, resume=a.resume)", 1)
s = s.replace('return 0 if r["status"] in ("DONE", "PARTIAL", "NEEDS_CONFIRM", "NEEDS_INPUT") else 1', 'return 0 if r["status"] in ("DONE", "PARTIAL", "NEEDS_CONFIRM", "NEEDS_INPUT", "NOTHING_TO_RESUME") else 1')
# docstring: say what resume really is
s = s.replace("4 THINK     mind.brain: is the plan itself risky (delete all, send, pay)? then it stops and asks BEFORE anything runs; the job's professional order; resume of a job left half done",
              "4 THINK     mind.brain: is the plan itself risky (delete all, send, pay)? then it stops and asks BEFORE anything runs. --resume continues the last run's unfinished tickets (finished ones are not redone)")
open(p, "w", encoding="utf-8").write(s)
import ast
ast.parse(s)
print("ok")
