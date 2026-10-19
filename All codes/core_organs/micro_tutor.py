"""
micro_tutor -- the interactive, visible tutor: ONE conversation over ONE engine, with the red overlay, a voice and the person's own hands.

    t = MicroTutor()
    t.open("Notepad")                         # the real program, on screen, its controls read from the accessibility tree
    t.teach("how do I find a word?")          # beat by beat: the tutor says one sentence, marks ONE thing, waits for the person to do it, then goes on
    t.session()                               # the conversation: typed lines or spoken words - questions are taught, 'next' / 'back' / 'repeat' steer, 'do it for me' hands over

What happens in a beat (micro_beats.Beat): the red box + badge + tiny pointer appear on the control (or a row / a grid cell), the sentence is spoken, then the tutor waits for a real click inside the box, the
key named, or a line ('next'). The moment the person does it the marks move on. 'do it for me' turns the same beats into actions on the same window: the tiny pointer glides to each control and the engine
operates it (UIA first, verified), saying what it is doing - teaching and doing share one plan.

Where the beats come from (nothing here knows an application):
    1. what the RAG holds for this question and program (procedures learned from scans, tutorials, datasets),
    2. when that does not speak to the question: the question put to the search engine's own summary in a browser (app_teaching_automation.AppIntelligenceEngine.ask_web), filed into the RAG,
    3. when a control on screen is simply named in the question: that control.
Everything the person sees comes from the live window: control boxes from UI Automation, cells of repeated-cell panels from OpenCV, never from a table of known programs.
"""
from __future__ import annotations

import contextlib
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_organs import micro_beats as MB, tutor_voice as TV


def best_plan(pw: Dict[str, Any], goal: str, app: str = "") -> Optional[Dict[str, Any]]:
    """The pathway that speaks most about the question: the one covering the most of the question's own words (not the program's name, not question words)."""
    from core_organs import app_teaching_automation as ATA
    skip = set(ATA._tokens(app)) | ATA.AppIntelligenceEngine.GENERIC
    want = [w for w in ATA._tokens(goal) if w not in skip]
    best, score = None, -1.0
    for pl in pw.get("plans") or []:
        have = ATA._tokens(" ".join(pl.get("steps", [])))
        cover = len({w for w in want if any(w == h or (len(w) >= 4 and len(h) >= 4 and (w.startswith(h[:4]) or h.startswith(w[:4]))) for h in have)})
        sc = cover + 0.1 * float(pl.get("reliability", 0))
        if sc > score:
            best, score = pl, sc
    return best


def relevant_steps(steps: List[Dict[str, Any]], goal: str, app: str = "") -> List[Dict[str, Any]]:
    """Only the steps whose own ACTION part speaks about the question (a stored chain keeps the NEXT step's words in its 'then' part: those are not this step's action)."""
    from core_organs import app_teaching_automation as ATA
    skip = set(ATA._tokens(app)) | ATA.AppIntelligenceEngine.GENERIC
    want = [w for w in ATA._tokens(goal) if w not in skip]
    out: List[Dict[str, Any]] = []
    for st in steps:
        action = st["text"].split(" -> then:")[0]
        have = ATA._tokens(action)
        if any(w == h or (len(w) >= 4 and len(h) >= 4 and (w.startswith(h[:4]) or h.startswith(w[:4]))) for w in want for h in have):
            out.append(st)
    return out


def steps_from_pathways(pw: Dict[str, Any], limit: int = 10, goal: str = "", app: str = "") -> List[Dict[str, Any]]:
    """The RAG's pathway steps (readable strings) as step dicts: the control names in quotes, the key combinations."""
    from core_organs.rag import logic_chains as LC
    out: List[Dict[str, Any]] = []
    plan0 = best_plan(pw, goal, app) if goal else ((pw.get("plans") or [None])[0])
    for plan in ([plan0] if plan0 else []):
        for s in plan.get("steps", [])[:limit]:
            names = [a or b for a, b in re.findall(r"['\"‘“]([^'\"’”]{2,32})['\"’”]|\*\*([^*]{2,32})\*\*", s)]
            keys = [k if isinstance(k, str) else k[0] for k in LC.KEY_RX.findall(s)][:2]
            out.append({"text": re.sub(r"\s+", " ", s)[:200], "names": names[:2], "keys": keys})
    return out


class MicroTutor:
    def __init__(self, engine: Any = None, overlay: Any = None, voice: Optional[TV.Voice] = None, watcher: Optional[TV.Watcher] = None, bar: bool = True, mic: bool = False,
                 log: Callable[[str], None] = print, shot: Optional[Callable[[], Any]] = None, vision: bool = True) -> None:
        self.engine = engine
        self.overlay = overlay
        self.voice = voice or TV.Voice(enabled=True)
        self.watcher = watcher or TV.Watcher(TV.Listener() if mic else None)
        self.watcher._speaking = lambda: not self.voice.idle()
        self.want_bar, self.want_mic, self.log = bar, mic, log
        self.shot = shot
        self.bar: Optional[TV.ControlBar] = None
        self.ts: Any = None                              # live_tutor.TutorSession: opens the window and reads its controls
        self.app = ""
        self.key = ""
        self.controls: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []         # what was shown / said / done, for the report and the tests
        self.stop = threading.Event()
        self.want_vision = vision
        self._vision: Any = None

    # ------------------------------------------------------------------------------------------------------------------------------- pieces
    def vision_fn(self) -> Optional[Callable[[str], Any]]:
        """`ground(name) -> box`: the trained Qwen3-VL-2B reading a fresh screenshot, used by the planner only when the accessibility tree and the grid finder have nothing (loaded on first use)."""
        if not self.want_vision:
            return None
        if self._vision is None:
            from core_organs import vision_ground as VG
            self._vision = VG.VisionGrounder(self._engine(), self.key or "screen")
        vg = self._vision

        def ground(name: str) -> Any:
            box = vg.ground_fn(self.screenshot, self.controls)(name)
            self.history.append({"vision": name, "box": box, "info": dict(vg.last)})
            return box
        return ground

    def growth(self) -> Any:
        """The self-growing memory (rag.self_growth): a beat whose click changed the screen as expected is kept as a fast path for next time."""
        if getattr(self, "_growth", None) is None:
            from core_organs.rag import self_growth as SG
            self._growth = SG.SelfGrowth()
        return self._growth

    def _labels(self) -> List[str]:
        return [str(c.get("name") or c.get("label") or "") for c in self.controls if (c.get("name") or c.get("label"))][:60]

    def remember(self, b: MB.Beat, before: List[str]) -> None:
        """After a beat's action and the rescan: if the set of control labels changed, the step worked -- keep (parent screen, control, action, post screen)."""
        if b.primitive != "box_pointer" or not b.target or not b.box:
            return
        after = self._labels()
        from core_organs.rag import self_growth as SG
        if not before or not after or SG.jaccard(SG.signature(before), SG.signature(after)) >= 0.95:
            return                                                                   # nothing changed: not a verified step
        x, y, w, h = b.box
        with contextlib.suppress(Exception):
            crop = None
            with contextlib.suppress(Exception):
                crop = self.screenshot().crop((int(x), int(y), int(x + w), int(y + h)))
            k = self.growth().learn(self.key or self.app or "screen", before, {"name": b.target, "type": "button", "center": (int(x + w / 2), int(y + h / 2)), "box": (int(x), int(y), int(w), int(h))}, "click", after, crop, True)
            self.history.append({"grew": b.target, "key": k})

    def _engine(self) -> Any:
        if self.engine is None:
            from core_organs import app_teaching_automation as ATA
            self.engine = ATA.AppIntelligenceEngine(log=self.log)
        return self.engine

    def _overlay(self) -> Any:
        if self.overlay is None:
            from core_organs.tutor_overlay import make_red_overlay
            self.overlay = make_red_overlay("auto")
        return self.overlay

    def state(self, text: str) -> None:
        with contextlib.suppress(Exception):
            self._overlay().status(text)

    def say(self, text: str) -> None:
        self.history.append({"say": text})
        self.log(f"[say] {text}")
        self.state("Speaking")
        self.voice.speak(text, wait=True)

    # ------------------------------------------------------------------------------------------------------------------------------- the window
    def open(self, app: str) -> None:
        """The real program on screen (owned, un-parked) and its controls. The overlay and the control bar come up with it."""
        from core_organs import live_tutor as LT
        self.app = app
        self._engine()
        self.key = self.engine.key_of(app)
        self.state("Scanning")
        self.ts = LT.TutorSession(self.engine, voice=False)
        self.ts.app_name, self.ts.app_key = app, self.key
        self.ts._open_visible(app)
        self.refresh()
        if self.want_bar:
            self.bar = TV.ControlBar(self.watcher.push, self.watcher.toggle_voice)
            self.bar.start()
        if self.want_mic and not self.watcher.voice_in:
            self.watcher.toggle_voice()
        self.state("Idle")

    def refresh(self) -> None:
        if self.ts is not None:
            self.controls = [dict(c) for c in self.ts._controls()]

    def screenshot(self) -> Any:
        if self.shot is not None:
            return self.shot()
        with contextlib.suppress(Exception):
            import mss
            from PIL import Image
            with mss.mss() as m:
                raw = m.grab(m.monitors[1])
                return Image.frombytes("RGB", raw.size, raw.rgb)
        return None

    # ------------------------------------------------------------------------------------------------------------------------------- the plan
    def steps_for(self, question: str) -> Tuple[List[Dict[str, Any]], str]:
        """(steps, where they came from)."""
        E = self._engine()
        pw = E.pathways(question, self.key)
        if not E.weak(pw, question, self.app):
            steps = relevant_steps(steps_from_pathways(pw, goal=question, app=self.app), question, self.app)
            if len(steps) >= 2:                                           # the learned pathway really does the asked thing in at least two steps; otherwise the question goes to the web
                return steps, "rag"
        ctl = MB.find_in_text(self.controls, question) if self.controls else None
        if ctl is not None and not MB.UNSAFE.search(ctl["name"]):
            return [{"text": f"Use {ctl['name']}.", "names": [ctl["name"]], "keys": [k for k in [ctl.get("key")] if k]}], "screen"
        self.state("Thinking")
        web = E.ask_web(question, self.app, self.key)
        if web.get("found"):
            return web.get("step_dicts") or [{"text": t, "names": [], "keys": []} for t in web["steps"]], "web"
        return [], "none"

    def teach(self, question: str) -> Dict[str, Any]:
        self.refresh()
        steps, src = self.steps_for(question)
        beats = MB.plan_beats(steps, self.controls, image=self.screenshot(), app=self.app, ground=self.vision_fn())
        self.log(f"[tutor] {len(steps)} step(s) from {src} -> {len(beats)} beat(s)")
        if not beats:
            self.say("I could not find the steps for that on this window. Tell me what you want done and I will do it for you.")
            self.state("Idle")
            return {"beats": 0, "source": src}
        moves = sum(1 for b in beats if b.wait in ("click",) or b.wait.startswith("key"))
        if moves:
            self.say(f"Here is how, in {moves} move{'s' if moves != 1 else ''}.")
        out = self.run(beats)
        out["source"] = src
        return out

    # ------------------------------------------------------------------------------------------------------------------------------- the beats
    def draw(self, b: MB.Beat) -> None:
        ov = self._overlay()
        from core_organs.professor.schema import Box
        if b.primitive in ("box_pointer", "region") and b.box:
            ov.box(Box(*b.box), b.pill, pointer=(b.primitive == "box_pointer"))
        elif b.primitive == "shape" and b.points:
            ov.shape(b.shape or "polygon", b.points, b.pill)
        elif b.pill and hasattr(ov, "badge"):                                   # a step with no control on screen (a key to press): its badge, near the top of the program's window
            wx, wy, ww, wh = (self.ts.window if self.ts is not None and getattr(self.ts, "window", None) else (200, 60, 800, 600))
            ov.badge(b.pill, wx + ww / 2.0, wy + 70)
        else:
            ov.wipe()
        self.history.append({"draw": b.primitive, "box": b.box, "pill": b.pill})

    def run(self, beats: List[MB.Beat], start: int = 0) -> Dict[str, Any]:
        i, done, delegated = start, 0, False
        while 0 <= i < len(beats) and not self.stop.is_set():
            b = beats[i]
            if b.late and b.box is None:                                          # its control may exist NOW (the dialog the last beat opened): look again before drawing
                with contextlib.suppress(Exception):
                    self.refresh()
                    got = [x for x in MB.plan_beats([b.late], self.controls, app=self.app, ground=self.vision_fn()) if x.primitive == "box_pointer"]
                    if got:
                        beats[i] = b = got[0]
                        self.history.append({"relocated": b.target})
            self.draw(b)
            self.say(b.speech)
            if b.wait == "none":
                time.sleep(0.4)
                i += 1
                continue
            if b.wait == "next" and b.primitive == "none":                         # nothing to point at: say it, then give the person a few seconds to do it / say 'next'
                self.state("Listening")
                ev = self.watcher.wait(timeout=9.0)
                self.history.append({"event": ev})
                if ev["kind"] == "line":
                    cmd = ev.get("command", "")
                    if cmd == "stop":
                        break
                    if cmd == "back":
                        i = max(0, i - 1)
                        continue
                    if cmd == "repeat":
                        continue
                    if cmd == "delegate":
                        self.delegate(beats, i)
                        delegated = True
                        break
                    if not cmd:
                        self.teach(ev["text"])
                        return {"beats": len(beats), "done": done, "interrupted_by": ev["text"]}
                i += 1
                continue
            self.state("Listening")
            before_labels = self._labels()
            keys: List[str] = []
            if b.wait.startswith("key:"):
                keys = [b.wait[4:]]
            elif b.keys:
                keys = [MB.last_key(b.keys)]
            ev = self.watcher.wait(box=b.box if b.wait == "click" else None, keys=keys, timeout=180.0)
            self.history.append({"event": ev})
            if ev["kind"] in ("click", "key"):
                done += 1
                time.sleep(0.7)                                                   # let a dialog / flyout / composer the action opened appear ...
                with contextlib.suppress(Exception):
                    self.refresh()                                                # ... then read the live window again: the next beat is located on what is there NOW
                    self.history.append({"rescan": len(self.controls)})
                    self.remember(b, before_labels)
                i += 1
            elif ev["kind"] == "line":
                cmd = ev.get("command", "")
                if cmd == "stop":
                    break
                if cmd == "back":
                    i = max(0, i - 1)
                elif cmd == "repeat":
                    pass
                elif cmd in ("next", "skip"):
                    i += 1
                elif cmd == "delegate":
                    self.delegate(beats, i)
                    delegated = True
                    break
                else:                                                             # a question in the middle of a lesson: answer it, then come back
                    self.teach(ev["text"])
                    return {"beats": len(beats), "done": done, "interrupted_by": ev["text"]}
            else:
                self.say("I'm still here. Say next, or ask me anything.")
        self._overlay().wipe()
        if not delegated:
            self.say("That is all of it." if i >= len(beats) else "Okay, stopping here.")
        self.state("Idle")
        return {"beats": len(beats), "done": done, "delegated": delegated, "reached": i}

    # ------------------------------------------------------------------------------------------------------------------------------- drawing a concept
    def explain(self, request: str, region: Optional[Tuple[float, float, float, float]] = None, hold_s: float = 25.0) -> Dict[str, Any]:
        """Explain something by DRAWING it on the screen (no drawing program): the brain plans the diagram, the red overlay draws each part while its sentence is spoken, the labels appear beside the strokes."""
        import ctypes
        from core_organs import diagram_teach as DT
        self.state("Thinking")
        shot = self.screenshot()
        look: Dict[str, Any] = {}
        if shot is not None and self.want_vision:                                    # LOOK first: is the concept already drawn on this screen? what is on it?
            from core_organs import vision_ground as VG
            look = VG.look_at(shot, request)
            self.history.append({"looked": look})
        if shot is not None:
            sp = DT.plan_on_screen(self._engine().get_brain(), request, shot, look)
            if sp["mode"] == "annotate":
                x0, y0, x1, y1 = sp["box"]
                from core_organs.professor.schema import Box
                self._overlay().box(Box(x0, y0, x1, y1), "the diagram", pointer=True)
                self.say("That diagram on your screen is the one to look at. " + str(look.get("description", ""))[:120])
                self.state("Idle")
                return {"mode": "annotate", "look": look}
            if sp["mode"] == "none":
                self.say("I could not work out a clear drawing for that. Try asking it another way.")
                self.state("Idle")
                return {"parts": 0, "problems": sp["plan"]["problems"]}
            plan, parts, card = sp["plan"], sp["parts"], sp["card"]
        else:
            plan = DT.plan_diagram(self._engine().get_brain(), request)
            if not plan["parts"]:
                self.say("I could not work out a clear drawing for that. Try asking it another way.")
                self.state("Idle")
                return {"parts": 0, "problems": plan["problems"]}
            if region is None:
                u = ctypes.windll.user32
                sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
                region = (sw * 0.12, sh * 0.14, sw * 0.88, sh * 0.9)
            parts, card = DT.to_screen(plan["parts"], region), None
        self.log(f"[tutor] diagram: {len(parts)} part(s) planned in {plan['seconds']}s ({plan.get('mode', 'freeform')})")
        ov = self._overlay()
        if card:
            ov.shape("card", card, "", seconds=0.1)
        for k, part in enumerate(parts):
            self.history.append({"shape": part["kind"], "label": part["label"], "say": part["say"]})
            self.state("Speaking")
            ov.shape(part["kind"], part["points"], part["label"], seconds=1.0)
            if part["say"]:
                self.log(f"[say] {part['say']}")
                self.voice.speak(part["say"], wait=True)
            time.sleep(0.25)
        self.state("Listening")
        ev = self.watcher.wait(timeout=hold_s)                                    # the drawing stays until the person says something (or a while)
        ov.wipe()
        self.state("Idle")
        return {"parts": len(parts), "seconds": plan["seconds"], "ended_by": ev.get("kind")}

    # ------------------------------------------------------------------------------------------------------------------------------- doing
    def delegate(self, beats: List[MB.Beat], start: int = 0) -> Dict[str, Any]:
        """'do it for me': the remaining beats become actions on the same window. The tiny pointer glides to each control, the engine operates it (UIA first, verified), one sentence says what is happening."""
        from core_organs import agent_executor as AE
        from core_organs.professor.schema import Box
        done = 0
        self.say("All right, I will do the rest.")
        agent = None
        if self.ts is not None and self.ts.live is not None:
            agent = AE.Agent(self.key, self.ts.live.observe_lite, self._engine().grounder(), self.ts.live.act, rag=self._engine().get_rag(), recover=self.ts.live.recover, uia_first=True,
                             observe_full=self.ts.live.observe)
        for b in beats[start:]:
            if b.primitive == "box_pointer" and b.box:
                self._overlay().box(Box(*b.box), b.pill, pointer=True)
                self.state("Thinking")
                time.sleep(0.9)                                                  # the pointer arrives before the click
                ok = False
                if agent is not None and b.target and b.layer == "uia":
                    before_labels = self._labels()
                    rec = agent.step(f"Click the {b.target} button")
                    ok = rec.status == "done"
                    if ok:
                        with contextlib.suppress(Exception):
                            self.refresh()
                            self.remember(b, before_labels)
                    self.history.append({"did": b.target, "status": rec.status, "source": rec.source})
                if ok:
                    done += 1
                    self.say(f"Done: {b.target}.")
                else:
                    self.say(f"I could not operate {b.target or 'that'} by myself; you take that one.")
                    break
            elif b.wait.startswith("key:") and self.ts is not None and self.ts.live is not None:
                with contextlib.suppress(Exception):
                    from core_organs import headless_input as hin
                    hin.post_key_combo(self.ts.live.app.hwnd, b.keys.lower().replace(" ", ""))
                    done += 1
                    self.history.append({"did": b.keys, "status": "posted"})
                    self.say(f"Pressed {b.keys}.")
        self._overlay().wipe()
        self.state("Idle")
        return {"done": done}

    # ------------------------------------------------------------------------------------------------------------------------------- the conversation
    def session(self) -> None:
        """Typed lines and spoken words: a question is taught, a task is done, 'stop' ends it."""
        self.say("I'm ready. Ask me how to do something, or tell me what to do.")
        while not self.stop.is_set():
            self.state("Listening")
            ev = self.watcher.wait(timeout=600.0)
            if ev["kind"] != "line":
                if ev["kind"] == "timeout":
                    break
                continue
            text, cmd = ev["text"], ev.get("command", "")
            self.log(f"[heard] {text!r} -> {cmd or 'a question or task'}")
            if cmd == "stop":
                break
            try:
                from core_organs import diagram_teach as _DT
                if _DT.is_diagram_request(text):
                    self.explain(text)
                elif re.search(r"\b(for me|take over|automate)\b", text, re.I) or self._is_order(text):
                    self.do_task(text)
                else:
                    self.teach(text)
            except Exception as exc:                                               # one failed question must never end the conversation
                self.log(f"[tutor] failed: {type(exc).__name__}: {str(exc)[:160]}")
                self.say("Sorry, that one went wrong on my side. Ask me again, or ask it another way.")
                self.state("Idle")
        self.close()

    @staticmethod
    def _is_order(text: str) -> bool:
        from core_organs import brain_planner as BP
        return BP.classify_intent(text)["mode"] == "delegate"

    def do_task(self, text: str) -> None:
        """A task, done by the engine on this window (planned goals, UIA first, verified, rolled back)."""
        self.state("Thinking")
        self.say("On it.")
        if self.ts is not None:
            self.ts.delegate(re.sub(r"^(please\s+)?(can you\s+)?", "", text, flags=re.I))
        self.state("Idle")

    def close(self) -> None:
        self.stop.set()
        with contextlib.suppress(Exception):
            self._overlay().wipe()
            self._overlay().status("Idle")
        with contextlib.suppress(Exception):
            if self.bar:
                self.bar.close()
        with contextlib.suppress(Exception):
            if self.ts is not None:
                self.ts.close()
