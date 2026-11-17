"""
professor.teach_run -- ONE COMMAND: ask -> find the workflow -> run it on a VISIBLE window -> narrate every step -> report the verified result.

    python hojaiga_professor.py teach-run "how do I change the margins" --app winword
    python hojaiga_professor.py teach-run "add a new slide"                       (the application is found from the question when it names one, else the best workflow anywhere)

  1 find      the workflow library (professor.workflows) is searched for the request; runnable / best-grounded workflows first; the application comes from --app, from a name in the
              question, or from the best match across every library
  2 run       an OWNED instance (never the person's own window), left visible, the virtual cursor shown; every step through the executor (verified against its stated expectation:
              professor.verify), the person's supervision policy in force (professor.supervision)
  3 narrate   before each step the manual's own words are spoken (Piper, local; silent with --mute) and shown in the overlay bubble; after it, what happened ('done - a dialog opened',
              'that did not work: ...')
  4 report    steps done / verified / contradicted, the final verdict, the report file; the workflow library records the run
--dry plans and narrates without starting the application.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional

from .schema import fold


def _clean(text: str) -> str:
    t = re.sub(r"\*\*", "", text or "")
    t = re.sub(r"^\s*\d+[.)]\s*", "", t)
    t = re.sub(r"\s+\d+[.)]?\s*$", "", t)
    return re.sub(r"\s+", " ", t).strip()


def find_workflow(question: str, app: str = "") -> Optional[Dict[str, Any]]:
    """The workflow that answers the question: in the named application, else in the application the question names, else the best match in any library."""
    from . import workflows as WF
    apps: List[str] = []
    if app:
        apps = [app]
    else:
        idx = WF.WF_DIR
        names = [fn[:-5] for fn in sorted(os.listdir(idx)) if fn.endswith(".json") and fn != "INDEX.json"] if os.path.isdir(idx) else []
        q = fold(question)
        try:
            from .knowledge import guide_corpus as GCP
            for a in GCP.load_catalog():
                if any(re.search(r"\b" + re.escape(fold(n)) + r"\b", q) for n in [a.get("name", ""), a.get("key", "")] if n and len(n) > 2):
                    apps.append(a["key"])
        except Exception:
            pass
        apps = apps or names
    best, best_s = None, -1.0
    order = {"runnable": 3.0, "needs-file-dialog": 2.0, "partial": 1.0}
    for ak in apps:
        for w in WF.fetch(ak, question, 5):
            sc = order.get(w.get("status", ""), 0.0) + float(w.get("grounded_share", 0.0)) + (2.0 if fold(w["goal"]) in fold(question) or fold(question) in fold(w["goal"]) else 0.0)
            if sc > best_s:
                best, best_s = w, sc
    return best


class Narrator:
    """Speaks and shows each step. Silent when muted or when no voice is installed (the text is still printed and shown)."""

    def __init__(self, mute: bool = False, overlay: Any = None, echo: bool = True):
        self.overlay, self.echo = overlay, echo
        self.lines: List[str] = []
        self.speaker: Any = None
        if not mute:
            try:
                from .voice_out import Speaker
                self.speaker = Speaker()
            except Exception:
                self.speaker = None

    def say(self, text: str, wait: bool = True) -> None:
        self.lines.append(text)
        if self.echo:
            print("  >> " + text, flush=True)
        if self.speaker is not None:
            try:
                self.speaker.speak(text)
                if wait:
                    self.speaker.wait(40.0)
            except Exception:
                pass

    def on_step(self, phase: str, st: Any, res: Any) -> None:
        if phase == "before":
            if getattr(st, "kind", "") == "skip":
                self.say(f"Step {st.index + 1}: {_clean(st.goal)} - {st.note or 'nothing to do here'}.")
                return
            where = " > ".join(list(getattr(st, "path", []) or []) + ([st.verb] if getattr(st, "verb", None) else []))
            self.say(f"Step {st.index + 1}: {_clean(st.goal)}" + (f" - that is {where}" if where and fold(where) not in fold(st.goal) else "") + ".")
        else:
            if res is None:
                return
            if res.status == "done":
                v = "" if res.verified is None else (" and that is what the guide said would happen" if res.verified else f" - but not what was expected ({res.expected})")
                self.say(f"Done{': ' + res.evidence if res.evidence and res.verified else ''}{v}.", wait=False)
            elif res.status == "needs_human":
                self.say(f"I stop here: {res.summary}. This step needs your yes.")
            else:
                self.say(f"That did not work: {res.summary[:140]}.")

    def close(self) -> None:
        if self.speaker is not None:
            try:
                self.speaker.wait(30.0)
                self.speaker.close()
            except Exception:
                pass


def teach(question: str, app: str = "", mute: bool = False, cursor: bool = True, vision: bool = True, dry: bool = False, echo: bool = True) -> Dict[str, Any]:
    from . import workflows as WF, apprun as AR
    wf = find_workflow(question, app)
    if wf is None:
        return {"question": question, "error": "no workflow in the guide library answers this (try `workflow find` with other words, or `guide` to fetch the application's guide)"}
    app_key = wf["app"]
    narr = Narrator(mute=mute, echo=echo)
    out: Dict[str, Any] = {"question": question, "app": app_key, "workflow": wf["id"], "goal": wf["goal"], "source": wf["source"], "status_in_library": wf["status"]}
    narr.say(f"For '{question}', the {app_key} guide has: {wf['goal']}. {wf['step_count']} steps, from {wf['source']}.")
    if dry:
        for s in wf["steps"]:
            ctl = " > ".join((s["verb_path"] + [s["verb"]]) if s["verb"] else [])
            narr.say(f"Step {s['n']}: {_clean(s['text'])}" + (f" - the control is {ctl}" if ctl else f" - ({s['how']}: {s['note'][:80]})" if s["note"] else ""), wait=False)
        narr.close()
        out.update({"dry_run": True, "narration": narr.lines})
        return out
    os.environ.setdefault("HOJAIGA_REVEAL", "0")                       # a lesson does not explore every dialog first: the catalog from earlier scans + the manifest is enough, paths are opened live
    os.environ.setdefault("HOJAIGA_RIBBON_BUDGET", "1")
    spec = AR.spec_for(app_key)
    r = AR.AppRun(spec, vision=vision, overlay_visible=cursor, visible=cursor, phases=(), echo=echo)
    from .dialogs import paths_in
    r.user_files = paths_in(question)                                      # a file / folder the person named: the dialogs may choose it (and only it)
    if r.user_files:
        out["user_files"] = r.user_files
    try:
        if not r.start():
            narr.say("I could not start the application.")
            out["error"] = "could not start an owned instance"
            return out
        r.perceive()
        r.ex.on_step = narr.on_step
        try:
            from .knowledge.guide_finder import settings
            from .supervision import Supervisor
            r.ex.supervisor = Supervisor.from_settings(settings(), owned=True, sandboxed=bool(r.ex.sandboxed), navigate=spec.mode == "navigate", sandbox_dir=getattr(r.sandbox, "root", "") or "")
        except Exception:
            pass
        tr = r.run_task(WF.to_task(wf))
        res = (tr.attempts[-1].results if tr.attempts else [])
        steps = [x for x in res if isinstance(x, dict) and "step" in x]
        verified = sum(1 for x in steps if x.get("verified") is True)
        contradicted = sum(1 for x in steps if x.get("verified") is False)
        out.update({"final": tr.final, "steps_done": sum(1 for x in steps if x.get("status") == "done"), "steps": len(steps), "verified": verified, "contradicted": contradicted,
                    "why": tr.attempts[-1].why if tr.attempts else "", "attempts": len(tr.attempts), "verify_log": list(r.ex.verify_log)[-20:],
                    "supervision": r.ex.supervisor.summary() if r.ex.supervisor is not None else {}})
        if tr.final == "ok":
            narr.say(f"Finished: {wf['goal']} - {out['steps_done']} steps done, {verified} confirmed on screen.")
        elif tr.final == "blocked":
            narr.say(f"Stopped on purpose: {out['why'][:160]}.")
        else:
            narr.say(f"It did not finish: {out['why'][:160]}.")
    finally:
        rep = r.finish()
        out["report"] = rep.get("html") or rep.get("path")
        narr.close()
    out["narration"] = narr.lines
    return out
