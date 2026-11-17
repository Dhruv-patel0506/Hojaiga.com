"""
professor.lesson_runner -- teaching as it happens: point, speak, WAIT for the learner to do it, look again, go on. Like a tutorial that watches you.

For every step:
  1 ground     the step's control must be on screen: use the measured box; if the step names a control that was not visible when the lesson was
               planned (it lives in a menu the learner has not opened yet), look again and find it; last resort one vision-model locate on a fresh picture
  2 present    overlay: pointer flies to it, outline pulses, bubble shows the step; voice says the step at the same moment
  3 wait       until the learner CLICKS the control (physical mouse polled, nothing hooked), or the picture changes at/near it, or says next/skip/back/repeat/stop,
               or the step times out (then the Professor offers help instead of racing ahead)
  4 look       rescan only what changed (sweeper.rescan) so the next step finds its control, even inside the menu that just opened
  5 verify     does what the step said to expect appear? (label overlap with the new scan) -- reported, never blocking
The runner NEVER clicks, types or presses anything for the learner. It only points and talks.
"""

from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

from . import config as CFG
from .capture import Frame, changed_boxes, cursor_pos, mouse_down
from .schema import Box, Lesson, LessonStep, ScreenModel, UIElement, fold
from .teacher import Teacher, speakable

Looker = Callable[[Optional[ScreenModel], Optional[Image.Image]], Tuple[Optional[ScreenModel], Optional[Image.Image], Dict[str, Any]]]


@dataclass
class StepResult:
    n: int
    outcome: str                  # clicked | changed | next | skipped | timeout | auto | failed | stopped
    seconds: float = 0.0
    grounded_by: str = ""
    expect_met: Optional[bool] = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def _expect_met(expect: str, sm: ScreenModel) -> Optional[bool]:
    words = [w for w in fold(expect).split() if len(w) > 3]
    if not words:
        return None
    have = set()
    for e in sm.elements:
        have.update(fold(e.label).split())
    for r in sm.regions:
        have.update(fold(r.label).split())
    hit = sum(1 for w in words if w in have)
    return hit / len(words) >= 0.4


class LessonRunner:
    def __init__(self, overlay: Any, speaker: Any, looker: Optional[Looker] = None, teacher: Optional[Teacher] = None, vlm: Any = None,
                 step_wait_s: Optional[float] = None, poll_s: float = 0.15, spotlight: bool = False, watcher: Any = None):
        self.overlay, self.speaker, self.looker, self.teacher, self.vlm = overlay, speaker, looker, teacher or Teacher(), vlm
        self.spotlight = spotlight                              # dim everything except the target (the 'professor lamp')
        self.watcher = watcher                                  # professor.pedagogy.StateWatcher: the learner's action is recognised by a STRUCTURAL change (tree / text / state), not only pixels
        self.last_delta = ""
        self.step_wait_s = step_wait_s if step_wait_s is not None else CFG.BUDGETS.step_wait_s
        self.poll_s = poll_s
        self.commands: "queue.Queue[str]" = queue.Queue()       # fed by voice or UI: next | back | repeat | skip | stop
        self.events: List[Tuple[float, str]] = []

    def command(self, name: str) -> None:
        self.commands.put(name)

    def _log(self, what: str) -> None:
        self.events.append((time.time(), what))

    # ---------------------------------------------------------------------------------------------- grounding
    def _ground(self, st: LessonStep, sm: ScreenModel, img: Optional[Image.Image]) -> Tuple[Optional[Box], str]:
        if st.box is not None and st.element_id is not None and sm.element(st.element_id) is not None:
            return sm.element(st.element_id).bbox, "scan"        # fresh box from the newest scan wins over the planned one
        if st.box is not None and st.grounded_by:
            return st.box, st.grounded_by
        q = st.find or st.label
        if q:
            hits = sm.find(q, limit=2)
            if hits:
                st.element_id = hits[0].id
                return hits[0].bbox, "scan"
            if self.vlm is not None and img is not None and self.vlm.available():
                b, _meta = self.vlm.ground_refined(img, q, timeout=90.0)
                if b is not None:
                    return b.shift(sm.origin[0], sm.origin[1]), "vlm_locate"
        return None, "none"

    # --------------------------------------------------------------------------------------------- waiting
    def _wait_for_learner(self, st: LessonStep, box: Box, sm: ScreenModel, img: Optional[Image.Image]) -> Tuple[str, str]:
        t0 = time.time()
        was_down = mouse_down(1)
        region = box.expand(40)
        base: Optional[Image.Image] = None
        try:
            from .capture import grab_box
            f = grab_box(region)
            base = f.image if f is not None else None
        except Exception:
            base = None
        last_check = 0.0
        last_struct = time.time()
        while time.time() - t0 < self.step_wait_s:
            try:
                cmd = self.commands.get_nowait()
                return cmd, ""
            except queue.Empty:
                pass
            down = mouse_down(1)
            if down and not was_down:
                x, y = cursor_pos()
                if box.expand(8).contains_point(x, y):
                    return "clicked", ""
            was_down = down
            if base is not None and time.time() - last_check > 0.45:
                last_check = time.time()
                try:
                    from .capture import grab_box
                    f2 = grab_box(region)
                    if f2 is not None and f2.image.size == base.size and changed_boxes(base, f2.image, cell=16, thresh=10.0):
                        return "changed", ""
                except Exception:
                    pass
            if self.watcher is not None and time.time() - last_struct > 0.8:
                last_struct = time.time()
                d = self.watcher.poll()
                if d is not None:
                    self.last_delta = d.summary()
                    return "changed", self.last_delta
            time.sleep(self.poll_s)
        return "timeout", ""

    # ------------------------------------------------------------------------------------------------- run
    def run(self, lesson: Lesson, sm: ScreenModel, image: Optional[Image.Image], interactive: bool = True, pace_s: float = 0.6) -> Dict[str, Any]:
        results: List[StepResult] = []
        t_start = time.time()
        if lesson.speech:
            self.speaker.speak(lesson.speech)
        steps = lesson.steps
        i = 0
        guard = 0
        while i < len(steps) and guard < 4 * max(1, len(steps)) + 8:
            guard += 1
            st = steps[i]
            ts = time.time()
            box, how = self._ground(st, sm, image)
            st.grounded_by = how
            narration = st.say or (lesson.speech if i == 0 and not lesson.speech else "")
            if st.hotkey and narration and not any(w in narration.lower() for w in ("press", "shortcut", "control ", "alt ")):
                narration = narration.rstrip(". ") + ". " + speakable(f"The shortcut is {st.hotkey}.")
            if box is None:
                # nothing to point at: say it, and wait for the learner to open whatever hides it, then look again
                if narration:
                    self.speaker.speak(narration)
                self.overlay.clear()
                st.status = "shown"
                if not interactive:
                    results.append(StepResult(st.n, "auto", time.time() - ts, "none", None, "control not visible yet; described only"))
                    i += 1
                    continue
                self.speaker.wait(40)
                what, _ = self._wait_cmd_or_change(sm)
                if what == "stop":
                    results.append(StepResult(st.n, "stopped", time.time() - ts))
                    break
                sm, image = self._look(sm, image)
                box2, how2 = self._ground(st, sm, image)
                if box2 is None:
                    results.append(StepResult(st.n, "failed", time.time() - ts, "none", None, "control still not visible"))
                    i += 1
                    continue
                box, how = box2, how2
            if self.watcher is not None:
                self.watcher.rebase()                                   # what the interface looks like BEFORE the learner acts
                self.last_delta = ""
            self.overlay.point(box, st.label or st.find, st.n, st.action, True, _bubble_text(st), self.spotlight, True, st.hotkey)
            if narration:
                self.speaker.speak(narration)
            st.status = "shown"
            if not interactive:
                self.speaker.wait(40)
                time.sleep(pace_s)
                results.append(StepResult(st.n, "auto", time.time() - ts, how))
                i += 1
                continue
            outcome, _ = self._wait_for_learner(st, box, sm, image)
            if outcome == "stop":
                results.append(StepResult(st.n, "stopped", time.time() - ts, how))
                break
            if outcome == "repeat":
                self.speaker.stop()
                continue
            if outcome == "back":
                i = max(0, i - 1)
                continue
            if outcome == "timeout":
                self.speaker.speak("Take your time. Say next when you're ready, or tell me if you're stuck.")
                outcome2, _ = self._wait_for_learner(st, box, sm, image)
                outcome = outcome2 if outcome2 != "timeout" else "timeout"
                if outcome == "stop":
                    results.append(StepResult(st.n, "stopped", time.time() - ts, how))
                    break
            st.status = "skipped" if outcome in ("skip",) else "done"
            time.sleep(0.45)                                           # let the interface settle (menus animate)
            sm, image = self._look(sm, image)
            met = _expect_met(st.expect, sm) if st.expect else None
            results.append(StepResult(st.n, "next" if outcome == "next" else ("skipped" if outcome == "skip" else outcome), time.time() - ts, how, met, self.last_delta))
            i += 1
        self.overlay.clear()
        done = all(s.status in ("done", "skipped", "shown") for s in steps) if steps else True
        return {"steps": [r.to_dict() for r in results], "completed": done and len(results) >= len(steps), "seconds": round(time.time() - t_start, 1),
                "events": len(self.events)}

    def _wait_cmd_or_change(self, sm: ScreenModel) -> Tuple[str, str]:
        t0 = time.time()
        while time.time() - t0 < self.step_wait_s:
            try:
                return self.commands.get(timeout=0.4), ""
            except queue.Empty:
                pass
            if mouse_down(1):
                time.sleep(0.5)
                return "clicked", ""
        return "timeout", ""

    def _look(self, sm: ScreenModel, image: Optional[Image.Image]) -> Tuple[ScreenModel, Optional[Image.Image]]:
        if self.looker is None:
            return sm, image
        try:
            sm2, img2, info = self.looker(sm, image)
            self._log("look:" + str(info.get("path", "")))
            return (sm2 or sm), (img2 if img2 is not None else image)
        except Exception as exc:
            self._log(f"look failed: {type(exc).__name__}")
            return sm, image


def _bubble_text(st: LessonStep) -> str:
    t = (st.say or st.label or "").strip()
    return t if len(t) <= 140 else t[:137].rsplit(" ", 1)[0] + "..."
