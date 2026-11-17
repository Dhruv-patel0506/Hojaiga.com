"""
professor.session -- the whole Professor, assembled:   hear -> look -> think -> speak + point -> watch -> go on.

    s = ProfessorSession()                    # real overlay + voice when available (each degrades honestly to a silent / recording twin)
    s.ask("how do I insert a picture?")       # looks at the foreground window, plans, speaks, points, waits for you, looks again
    s.serve()                                 # hold Ctrl+Alt and talk; Escape cancels; "next / back / repeat / skip / stop" steer a running lesson

Latency design for a local 8B model on a 6 GB GPU:
  * the FIRST look is `quick` (accessibility tree + shapes + text + remembered icons, seconds); a `standard` scan (vision-model naming of the remaining
    icons) then runs in the BACKGROUND and upgrades the cached model, and it yields the moment the next question arrives
  * the lesson's opening line is spoken as soon as the model has written it (streamed), not after the last step
  * after each step only the changed screen areas are analysed again
Nothing here ever clicks or types for the learner.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

from . import config as CFG
from . import sweeper
from .brain import Brain, brain as _brain
from .capture import Frame, cursor_pos, foreground_hwnd, pick_target_window, window_info
from .lesson_runner import LessonRunner
from .overlay import make_overlay
from .schema import Lesson, ScreenModel, UIElement
from .teacher import Conversation, Teacher, speakable
from .vlm import VisionClient, client as _client
from .voice_in import PushToTalk, Recorder, Transcriber, rms_level
from .voice_out import SilentSpeaker, Speaker

_CONTROL_WORDS = [
    ("stop", re.compile(r"^\s*(stop|cancel|never ?mind|quit|that's enough|enough)\b", re.I)),
    ("back", re.compile(r"^\s*(back|go back|previous)\b", re.I)),
    ("repeat", re.compile(r"^\s*(repeat|say (that )?again|again|what was that)\b", re.I)),
    ("skip", re.compile(r"^\s*skip\b", re.I)),
    ("next", re.compile(r"^\s*(next|go on|continue|done|okay|ok|got it|i did it|finished|ready)\b", re.I)),
]


def control_word(text: str) -> str:
    for name, rx in _CONTROL_WORDS:
        if rx.match(text or ""):
            return name
    return ""


class ProfessorSession:
    def __init__(self, *, mute: bool = False, overlay: str = "auto", first_mode: str = "quick", upgrade_mode: str = "standard", upgrade: bool = True,
                 vlm: Optional[VisionClient] = None, brain: Optional[Brain] = None, speaker: Any = None, overlay_obj: Any = None,
                 interactive: bool = True, use_catalog: bool = True, watch_state: bool = True, spotlight: bool = False, find_guide: bool = True, guide_web: Optional[bool] = None):
        self.vlm = vlm or _client()
        self.brain = brain or _brain()
        self.teacher = Teacher(self.brain)
        self.conv = Conversation()
        self.overlay = overlay_obj if overlay_obj is not None else make_overlay(overlay)
        self.speaker = speaker if speaker is not None else (SilentSpeaker() if mute else Speaker())
        self.first_mode, self.upgrade_mode, self.upgrade = first_mode, upgrade_mode, upgrade
        self.interactive = interactive
        self.use_catalog, self.watch_state, self.spotlight = use_catalog, watch_state, spotlight
        self.find_guide, self.guide_web = find_guide, guide_web                 # guide_web None = follow HOJAIGA_GUIDE_WEB (off unless you turned it on)
        self._guide_threads: Dict[str, threading.Thread] = {}
        self.guide_reports: Dict[str, Dict[str, Any]] = {}
        self.frames: Dict[str, Tuple[Any, Dict[str, Any]]] = {}      # app_key -> (Catalog, archetype): what the application is, learnt once
        self.state = "idle"
        self.cache: Dict[int, Tuple[ScreenModel, Image.Image]] = {}
        self._question_waiting = threading.Event()
        self._upgrade_thread: Optional[threading.Thread] = None
        self.runner: Optional[LessonRunner] = None
        self.last: Dict[str, Any] = {}
        self.recorder: Optional[Recorder] = None
        self.transcriber: Optional[Transcriber] = None
        self._ptt: Optional[PushToTalk] = None
        self._ptt_target = 0
        self._busy = threading.Lock()
        self.log: List[Tuple[float, str]] = []

    # ------------------------------------------------------------------------------------------------ status
    def _set(self, state: str) -> None:
        self.state = state
        self.log.append((time.time(), state))

    def components(self) -> Dict[str, Any]:
        vh = self.vlm.health(True)
        try:
            from .knowledge import manual_rag, divisions
            ix = manual_rag.index()
            manual = {"apps": ix.apps()} if ix is not None else "no manual ingested"
            frame = divisions.source_in_use() or "built-in"
        except Exception:
            manual, frame = "unavailable", "?"
        # WHO DOES WHAT: the heavy semantic work is text (the language model over the tree, the stored maps and the manual); the vision model only locates and
        # names pixels. Every control the accessibility tree or a native menu names never reaches the vision model at all.
        roles = {"reasoner (lesson planning, explanations)": self.brain.backend() or "none", "grounder (where is it / what area is this)": ("vision model" if vh.get("up") else "down: shapes + text only"),
                 "namer (icons with no tree name)": ("vision model, contact sheets" if vh.get("up") else "icon memory only"), "structure": "accessibility tree where it exists, else pixel layout tree",
                 "knowledge": {"manual": manual, "layer frame": frame}}
        return {"roles": roles, "vision_server": {"up": vh.get("up"), "model": vh.get("model")}, "brain": self.brain.backend() or "none", "overlay": getattr(self.overlay, "kind", "?"),
                "overlay_error": getattr(self.overlay, "error", ""), "voice_out": getattr(self.speaker, "backend", "?"), "voice_out_error": getattr(self.speaker, "error", ""),
                "voice_in": (self.transcriber.backend if self.transcriber else "not started"), "recorder": (self.recorder.backend if self.recorder else "not started")}

    # --------------------------------------------------------------------------------------------------- look
    def look(self, hwnd: int = 0, title_hint: str = "", image: Optional[Image.Image] = None, mode: Optional[str] = None, force: bool = False,
             origin: Tuple[int, int] = (0, 0)) -> Tuple[ScreenModel, Optional[Image.Image], Dict[str, Any]]:
        """(model, picture, info). A window seen before is re-scanned incrementally; a new one gets a `quick` scan and a background upgrade."""
        if image is None and not hwnd:
            w = pick_target_window(title_hint)
            hwnd = w.hwnd if w else 0
        key = hwnd or -1
        mode = mode or self.first_mode
        prev = self.cache.get(key)
        if prev is not None and not force and image is None:
            sm, fr, info = sweeper.rescan(prev[0], prev[1], hwnd=hwnd, mode=mode, vlm=self.vlm)
            if fr is not None:
                self.cache[key] = (sm, fr.image)
                return sm, fr.image, info
        sm, fr = sweeper.scan(hwnd=hwnd, image=image, mode=mode, vlm=self.vlm, origin=origin, title_hint=title_hint)
        if fr is None:
            return sm, None, {"path": "capture-failed"}
        self.cache[key] = (sm, fr.image)
        if self.upgrade and mode == "quick":
            self._start_upgrade(key, hwnd, fr)
        return sm, fr.image, {"path": f"full:{mode}", "seconds": sm.timings.get("total")}

    def _start_upgrade(self, key: int, hwnd: int, fr: Frame) -> None:
        if self._upgrade_thread and self._upgrade_thread.is_alive():
            return

        def work() -> None:
            try:
                if not self.vlm.available():
                    return
                opt = sweeper.ScanOptions.for_mode(self.upgrade_mode)
                opt.yolo = True                              # the background upgrade may use the icon detector where the app has no tree
                opt.cancel = self._question_waiting.is_set
                sm, _f = sweeper.scan(hwnd=hwnd, image=fr.image, origin=fr.origin, options=opt, vlm=self.vlm)
                cur = self.cache.get(key)
                if cur is not None and cur[0].frame_hash == sm.frame_hash and len(sm.named()) >= len(cur[0].named()):
                    self.cache[key] = (sm, cur[1])
            except Exception:
                pass

        self._upgrade_thread = threading.Thread(target=work, name="professor-upgrade", daemon=True)
        self._upgrade_thread.start()

    def frame(self, sm: ScreenModel, hwnd: int = 0) -> Tuple[Any, Dict[str, Any]]:
        """(catalog, archetype) of the application on screen -- harvested passively once per application, then cached. Never raises; (None, {}) when unavailable."""
        if not self.use_catalog or not sm.app_key:
            return None, {}
        hit = self.frames.get(sm.app_key)
        if hit is not None:
            return hit
        try:
            from .pedagogy import frame_for
            cat, arch = frame_for(sm, hwnd or sm.hwnd, self.brain, harvest=True)
            self.frames[sm.app_key] = (cat, arch)
            self._ensure_guide(sm, hwnd or sm.hwnd)
            return cat, arch
        except Exception as exc:
            self.log.append((time.time(), f"frame failed: {type(exc).__name__}"))
            return None, {}

    def _ensure_guide(self, sm: ScreenModel, hwnd: int) -> None:
        """Find + index the application's user guide in the BACKGROUND (install folder; the web only if you enabled it). The lesson never waits for it: whatever is indexed by the time a
        question is planned is used, with citations."""
        key = sm.app_key
        if not self.find_guide or not hwnd or not key or key == "unknown" or key in self._guide_threads:
            return

        def work() -> None:
            try:
                from .knowledge import guide_finder as GF
                ident = GF.identity_of(hwnd, app_key=key)
                self.guide_reports[key] = GF.discover(ident, web=self.guide_web, budget_s=90.0)
            except Exception as exc:
                self.guide_reports[key] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}

        th = threading.Thread(target=work, name=f"professor-guide-{key}", daemon=True)
        self._guide_threads[key] = th
        th.start()

    def element_under_cursor(self, sm: ScreenModel) -> Optional[UIElement]:
        x, y = cursor_pos()
        hits = [e for e in sm.elements if e.bbox.contains_point(x, y) and e.role != "text"]
        return min(hits, key=lambda e: e.bbox.area) if hits else None

    # ---------------------------------------------------------------------------------------------------- ask
    def ask(self, question: str, *, hwnd: int = 0, image: Optional[Image.Image] = None, origin: Tuple[int, int] = (0, 0), interactive: Optional[bool] = None,
            speak: bool = True, point: bool = True, title_hint: str = "") -> Dict[str, Any]:
        t0 = time.time()
        self._question_waiting.set()
        out: Dict[str, Any] = {"question": question}
        try:
            self._set("looking")
            self.overlay.thinking(True)
            sm, img, info = self.look(hwnd, title_hint, image, origin=origin)
            out["look"] = {**info, "elements": len(sm.elements), "named": len(sm.named()), "app": sm.app_key, "tiers_used": sm.tiers_used, "tiers_skipped": sm.tiers_skipped}
            self._set("thinking")
            early: List[str] = []

            def on_partial(ev: str, payload: Any) -> None:
                if ev == "speech" and speak and payload:
                    txt = speakable(str(payload))
                    early.append(txt)
                    self.speaker.speak(txt)

            focus = self.element_under_cursor(sm) if image is None else None
            cat, arch = self.frame(sm, hwnd)
            if cat is not None:
                out["frame"] = {"verbs": len(cat.verbs), "with_shortcut": sum(1 for v in cat.verbs if v.shortcut), "archetype": arch.get("id"), "by": arch.get("by")}
            lesson = self.teacher.plan(question, sm, self.conv, focus, on_partial=on_partial, catalog=cat, arch=arch)
            out["plan_seconds"] = round(time.time() - t0, 1)
            if early and lesson.speech:
                lesson.speech = ""                                       # already spoken while the steps were being written
            self.overlay.thinking(False)
            out["lesson"] = lesson.to_dict()
            self._question_waiting.clear()
            self.conv.last_lesson = lesson
            self._set("teaching")
            spoken_text = " ".join(early + [lesson.speech] + [s.say for s in lesson.steps if s.say])
            if point and lesson.steps:
                looker = (lambda s, i: sweeper.rescan(s, i, hwnd=hwnd or s.hwnd, mode=self.first_mode, vlm=self.vlm)) if image is None else None
                watcher = None
                target = hwnd or sm.hwnd
                if self.watch_state and image is None and target and (self.interactive if interactive is None else interactive):
                    from .pedagogy import StateWatcher
                    watcher = StateWatcher(target)
                self.runner = LessonRunner(self.overlay, self.speaker if speak else SilentSpeaker(), looker, self.teacher, self.vlm, spotlight=self.spotlight, watcher=watcher)
                out["run"] = self.runner.run(lesson, sm, img, interactive=self.interactive if interactive is None else interactive)
                self.runner = None
            elif lesson.speech and speak:
                self.speaker.speak(lesson.speech)
                self.speaker.wait(60)
            self.conv.add(question, spoken_text.strip() or lesson.title, sm.app_key)
            out["spoken"] = spoken_text.strip()
        except Exception as exc:
            out["error"] = f"{type(exc).__name__}: {exc}"
            self.overlay.thinking(False)
        finally:
            self._question_waiting.clear()
            self.overlay.clear()
            self._set("idle")
            out["seconds"] = round(time.time() - t0, 1)
            self.last = out
        return out

    def demonstrate(self, skill: Any, hwnd: int = 0, speak: bool = True, image: Optional[Image.Image] = None, model: Optional[Tuple[ScreenModel, Image.Image]] = None) -> Dict[str, Any]:
        """'Watch me do it': the overlay pointer glides through the skill's targets as ONE continuous Fitts's-law route (arriving at each control, naming it, showing its hotkey). It only
        DRAWS - nothing is clicked and the user's real mouse and keyboard are never touched or blocked. Controls that are not visible now are listed, not guessed."""
        from . import pointing
        sm, img = model if model is not None else self.look(hwnd, image=image)[:2]
        cat, _arch = self.frame(sm, hwnd)
        boxes, labels, hotkeys, missing = [], [], [], []
        for st in skill.steps:
            if st.kind != "verb":
                continue
            hit = sm.find(st.label, limit=1)
            if hit:
                boxes.append(hit[0].bbox)
                labels.append(st.label)
                hotkeys.append((cat.shortcut_for(st.label) if cat is not None else "") or "")
            else:
                missing.append(st.label)
        if not boxes:
            return {"ok": False, "error": "none of the skill's controls is visible right now", "missing": missing}
        start = cursor_pos()
        pts, ws = pointing.route_for(boxes, start, "click")
        traj = pointing.stitch(pts, ws)
        t0 = time.time()
        total = self.overlay.glide(pts[1:], ws[1:])
        sp = self.speaker if speak else SilentSpeaker()
        sp.speak(f"{skill.goals[0]}. Watch the pointer.")
        for i, arr in enumerate(traj.arrival[1:]):
            time.sleep(max(0.0, arr - (time.time() - t0)))
            self.overlay.point(boxes[i], labels[i], i + 1, "click", True, labels[i], False, False, hotkeys[i])
            sp.speak(f"{labels[i]}." + (f" Shortcut: {hotkeys[i]}." if hotkeys[i] else ""))
        sp.wait(30)
        time.sleep(0.6)
        self.overlay.clear()
        return {"ok": True, "steps": labels, "missing": missing, "route_seconds": round(traj.duration, 2), "planned": round(total, 2), "hotkeys": hotkeys}

    def explain_here(self, hwnd: int = 0) -> Dict[str, Any]:
        """'What is this?' -- the control under the mouse, explained from measured facts."""
        sm, img, info = self.look(hwnd)
        e = self.element_under_cursor(sm)
        if e is None:
            msg = "Move the mouse over a button and ask again."
            self.speaker.speak(msg)
            return {"error": "no control under the cursor", "spoken": msg}
        les = self.teacher.explain(e, sm)
        self.overlay.point(e.bbox, e.label, None, "look", True, e.label)
        self.speaker.speak(les.speech)
        self.speaker.wait(60)
        self.overlay.clear()
        return {"element": e.to_dict(), "lesson": les.to_dict(), "spoken": les.speech}

    # ------------------------------------------------------------------------------------------------ voice loop
    def _ensure_voice_in(self) -> None:
        if self.recorder is None:
            self.recorder = Recorder()
        if self.transcriber is None:
            self.transcriber = Transcriber()

    def serve(self, block: bool = True) -> None:
        """Push-to-talk loop. Hold Ctrl+Alt, speak, release. Escape while holding cancels."""
        self._ensure_voice_in()
        self._ptt = PushToTalk(self._ptt_start, self._ptt_end, self._ptt_cancel)
        self._ptt.start()
        self.speaker.speak("Professor ready. Hold control and alt, and ask me anything about what's on your screen.")
        if block:
            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.close()

    def _ptt_start(self) -> None:
        self._ptt_target = foreground_hwnd()
        self.speaker.stop()
        self._set("listening")
        self.overlay.thinking(True)
        self.recorder.start()                                           # type: ignore[union-attr]

    def _ptt_cancel(self) -> None:
        if self.recorder:
            self.recorder.stop()
        self.overlay.thinking(False)
        self._set("idle")

    def _ptt_end(self, dur: float) -> None:
        pcm = self.recorder.stop() if self.recorder else b""
        self.overlay.thinking(False)
        target = self._ptt_target
        threading.Thread(target=self._handle_utterance, args=(pcm, target), name="professor-utterance", daemon=True).start()

    def _handle_utterance(self, pcm: bytes, target: int) -> None:
        if rms_level(pcm) < 0.003:
            self._set("idle")
            return
        self._set("transcribing")
        r = self.transcriber.transcribe(pcm) if self.transcriber else {"ok": False}
        text = (r.get("text") or "").strip()
        self.log.append((time.time(), "heard: " + text))
        if not text:
            self._set("idle")
            return
        cw = control_word(text)
        if cw and self.runner is not None:
            self.runner.command(cw)
            return
        if cw == "stop":
            self.speaker.stop()
            self.overlay.clear()
            return
        if not self._busy.acquire(blocking=False):
            self.speaker.speak("One moment, I'm still working on the last one.")
            return
        try:
            self.ask(text, hwnd=target)
        finally:
            self._busy.release()

    def close(self) -> None:
        try:
            if self._ptt:
                self._ptt.stop()
            self.overlay.clear()
            self.overlay.stop()
            self.speaker.close()
        except Exception:
            pass
