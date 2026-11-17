"""
professor.teacher -- the Professor's teaching mind: a question + what is on screen + what is known  ->  a spoken, pointed, step-by-step lesson.

Adapted from Clicky's idea (a voice companion that sees your screen and POINTS), with three deliberate changes:
  1. GROUNDED POINTING.  Clicky asks a cloud model for raw pixel coordinates. Here the model is shown a NUMBERED INVENTORY of controls whose boxes were
     measured (professor.sweeper) and answers with element ids; the overlay uses the measured box. A small local model can mis-number, so every id is
     checked against the label the model said it meant and repaired by label when they disagree. Coordinates are never invented.
  2. KNOWN ROUTES.  Measured menu paths from Atlas (which tab/group/menu leads where, shortcuts, what a control opens) go into the prompt as facts to
     TRUST OVER GUESSING, and become the deterministic fallback lesson when no model is running.
  3. LOCAL.  The text model is the same resident Qwen3-VL (or Ollama); no API key, no network.
A lesson step that names a control not on screen yet (inside a closed menu) carries `find`; the LessonRunner grounds it once the learner has opened the menu.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import config as CFG
from . import pointing
from .brain import Brain, brain as _brain
from .knowledge import app_knowledge, explain as EX
from .schema import ACTIONS, Box, Lesson, LessonStep, ScreenModel, UIElement, fold

PERSONA = """You are the Professor: a patient, warm, expert teacher who can SEE the learner's screen and POINT at things on it. The learner speaks to you; your reply is read aloud, so write for the ear.

How you teach:
- Answer the question directly first, in one or two plain sentences. Go deeper only when asked.
- For "how do I..." questions, give a short lesson: at most 7 small steps, one action per step, each step says WHAT to do and WHERE the control is ("the Insert tab, top row of the ribbon").
- Point at the control for every step where a visible control is involved: give its number from the INVENTORY as "element" and copy its label into "target".
- Use ONLY controls that appear in the INVENTORY. If a step needs a control that is not listed (it is inside a closed menu, another tab, or a dialog that is not open), set "element" to null, describe the control in "find", and tell the learner what to open first. Never invent a button, a menu item or a shortcut.
- Trust KNOWN ROUTES (measured from this application) and MANUAL EXCERPTS (quoted from its user manual) over your own memory of how the program works.
- Teach the idea before the clicks: the opening "speech" first says, in one plain sentence, what the whole task is for or how this kind of software thinks about it (use KIND OF SOFTWARE when it is given), then answers.
- Mention a keyboard shortcut ONLY if it is listed under HOTKEYS. The application printed those; never make one up.
- If you cannot tell what the learner wants, ask ONE short clarifying question (mode "clarify", no steps).
- Never say "simply" or "just". No lists, markdown, emojis or symbols in "say": spell out small numbers, write "control s" for Ctrl+S.
- Each "say" is at most 25 words. After the last step, "expect" says what the learner should now see."""

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["answer", "lesson", "clarify"]},
        "title": {"type": "string"},
        "speech": {"type": "string"},
        "steps": {"type": "array", "maxItems": 8, "items": {
            "type": "object",
            "properties": {
                "say": {"type": "string"},
                "action": {"type": "string", "enum": list(ACTIONS)},
                "element": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "target": {"type": "string"},
                "find": {"type": "string"},
                "text": {"type": "string"},
                "keys": {"type": "string"},
                "expect": {"type": "string"},
            },
            "required": ["say", "action", "element", "target"],
        }},
    },
    "required": ["mode", "title", "speech", "steps"],
}

_STOP = {"the", "a", "an", "to", "of", "in", "on", "and", "or", "how", "do", "i", "can", "you", "me", "my", "is", "it", "this", "that", "what", "where", "show", "please",
         "want", "need", "make", "with", "for", "from", "at", "by", "be", "are", "does", "should", "would", "could", "let", "us", "we"}


_UI_NOUNS = {"tab", "button", "menu", "icon", "dialog", "option", "item", "ribbon", "group", "bar", "box", "panel", "window", "field", "list"}


def _words(s: str) -> List[str]:
    return [w for w in fold(s).split() if w not in _STOP and len(w) > 1]


def _ui_words(s: str) -> List[str]:
    """Content words of a control's name or of a description of it, without the generic nouns people add ('the Insert tab' == 'Insert')."""
    return [w for w in _words(s) if w not in _UI_NOUNS]


# ----------------------------------------------------------------------------------------------------- speech cleanup
_SHORTCUT = re.compile(r"\b(ctrl|control|alt|shift|win)\s*\+\s*([A-Za-z0-9]+|F\d+|Tab|Enter|Esc|Space|Del(?:ete)?)", re.I)


def speakable(text: str) -> str:
    """Make text safe and natural for text-to-speech: no markdown, no symbols that get read aloud, shortcuts spelled out."""
    t = text or ""
    t = re.sub(r"[*_`#>]+", "", t)
    t = _SHORTCUT.sub(lambda m: f"{m.group(1).lower().replace('ctrl', 'control')} {m.group(2).lower() if len(m.group(2)) == 1 else m.group(2)}", t)
    t = re.sub(r"\be\.g\.", "for example", t, flags=re.I)
    t = re.sub(r"\bi\.e\.", "that is", t, flags=re.I)
    t = re.sub(r"\s*(->|→|=>|>)\s*", ", then ", t)
    t = t.replace("&", " and ").replace("…", ".").replace("’", "'")
    t = re.sub(r"\(([^)]{0,60})\)", r", \1,", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r",\s*,", ",", t).strip(" ,")
    return t


# -------------------------------------------------------------------------------------------------- conversation memory
class Conversation:
    def __init__(self, keep: int = 5):
        self.keep = keep
        self.turns: List[Tuple[str, str]] = []
        self.app: str = ""
        self.last_lesson: Optional[Lesson] = None

    def add(self, question: str, answer: str, app: str = "") -> None:
        self.turns.append((question.strip(), answer.strip()))
        self.turns = self.turns[-self.keep:]
        self.app = app or self.app

    def history(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for q, a in self.turns:
            out.append({"role": "user", "content": q})
            out.append({"role": "assistant", "content": a})
        return out


# ----------------------------------------------------------------------------------------------------- inventory choice
NAV_REGIONS = {"menubar", "tab_strip", "ribbon", "toolbar", "titlebar"}


def select_inventory(sm: ScreenModel, question: str, hint_names: List[str], focus: Optional[UIElement], limit: int) -> List[UIElement]:
    """The controls shown to the model: everything the question or a known route mentions, the focused control and its neighbours, then navigation
    (menu bar, tabs, ribbon, toolbars) and dialog controls, trimmed to `limit`. Order stays reading order."""
    qw = set(_words(question))
    hint_fold = {fold(h) for h in hint_names if h}
    hint_words = {w for h in hint_names for w in _words(h)}
    reg = {r.id: r for r in sm.regions}
    scored: List[Tuple[float, UIElement]] = []
    for e in sm.elements:
        lab = fold(e.label)
        s = 0.0
        if lab:
            lw = set(lab.split())
            s += 3.0 * len(qw & lw)
            if lab in hint_fold:
                s += 6.0
            s += 1.5 * len(hint_words & lw)
        r = reg.get(e.region_id)
        kind = r.kind if r else ""
        if kind in NAV_REGIONS or e.role in ("tab", "menu_item"):
            s += 1.2
        if kind == "dialog":
            s += 1.5
        if focus is not None and (e.id == focus.id or e.bbox.expand(60).contains(focus.bbox)):
            s += 5.0
        if e.role == "text" and kind not in NAV_REGIONS and s < 3:
            s -= 1.0
        if not e.label:
            s -= 0.4
        if not e.enabled:
            s -= 0.3
        scored.append((s, e))
    scored.sort(key=lambda t: -t[0])
    pick = [e for s, e in scored[:limit] if s > -0.9 or len(sm.elements) <= limit]
    pick.sort(key=lambda e: e.id)
    return pick


def inventory_lines(sm: ScreenModel, els: List[UIElement]) -> str:
    reg = {r.id: r for r in sm.regions}
    lines: List[str] = []
    last = None
    for e in els:
        r = reg.get(e.region_id)
        head = f"{r.kind}: {r.label}" if r and r.label and r.label != r.kind else (r.kind if r else "window")
        if head != last:
            lines.append(f"== {head} ==")
            last = head
        lines.append(e.line())
    return "\n".join(lines)


def routes_text(routes: List[Dict[str, Any]]) -> str:
    out = []
    for i, r in enumerate(routes[:3], 1):
        t = re.sub(r"\*\*", "", r.get("text", ""))
        extra = []
        if r.get("outcome"):
            extra.append(re.sub(r"\*\*", "", r["outcome"]))
        if r.get("shortcut"):
            extra.append("shortcut " + r["shortcut"])
        for p in r.get("preconditions", [])[:1]:
            extra.append("note: " + p)
        out.append(f"{i}. {t}" + (" | " + "; ".join(extra) if extra else ""))
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------------- stream watcher
_SPEECH_RX = re.compile(r'"speech"\s*:\s*"((?:[^"\\]|\\.)*)"')


def stream_watcher(emit: Callable[[str, Any], None]) -> Callable[[str], None]:
    """Turn the growing JSON text of a lesson into events: the opening line as soon as it is complete, then each finished step."""
    from . import grounding as G
    state = {"speech": False, "steps": 0}

    def cb(text: str) -> None:
        if not state["speech"]:
            m = _SPEECH_RX.search(text)
            if m:
                state["speech"] = True
                try:
                    import json
                    emit("speech", json.loads('"' + m.group(1) + '"'))
                except Exception:
                    emit("speech", m.group(1))
        i = text.find('"steps"')
        if i >= 0:
            objs = G.salvage_objects(text[i:])
            while state["steps"] < len(objs):
                emit("step", objs[state["steps"]])
                state["steps"] += 1

    return cb


# ===================================================================================================== the teacher
class Teacher:
    def __init__(self, brain: Optional[Brain] = None):
        self.brain = brain or _brain()

    # ------------------------------------------------------------------------------------------------ intents
    _LOCATE = re.compile(r"^\s*(?:where(?:'s| is| are)|find|show me|point (?:to|at)|locate|which is)\s+(?:the\s+|my\s+)?(.+?)[\s\?\.!]*$", re.I)
    _WHAT = re.compile(r"\b(what(?:'s| is| does)|explain|tell me about|describe)\b.*\b(this|that|here|it)\b|\bwhat does (?:this|that|it) do\b", re.I)

    def intent(self, question: str) -> str:
        if self._LOCATE.match(question or ""):
            return "locate"
        if self._WHAT.search(question or ""):
            return "explain_here"
        return "plan"

    # --------------------------------------------------------------------------------------------------- plan
    def plan(self, question: str, sm: ScreenModel, conv: Optional[Conversation] = None, focus: Optional[UIElement] = None,
             allow_model: bool = True, on_partial: Optional[Callable[[str, Any], None]] = None, catalog: Any = None, arch: Optional[Dict[str, Any]] = None) -> Lesson:
        """`on_partial(event, payload)` fires while the model is still writing: ("speech", text) once the opening line is complete, ("step", dict) per finished step.
        `catalog` (professor.harvest.Catalog) supplies the application's own shortcuts; `arch` (professor.archetype.classify) the kind of software."""
        t0 = time.time()
        conv = conv or Conversation()
        intent = self.intent(question)
        ak = app_knowledge.for_model(sm)
        if intent == "locate":
            les = self._locate(question, sm)
            if les is not None:
                self._attach_hotkeys(les, catalog)
                return les
        if intent == "explain_here" and focus is not None:
            les = self.explain(focus, sm, allow_model=allow_model)
            self._attach_hotkeys(les, catalog)
            return les
        rt = ak.howto(question) if ak.ui_key else {"ok": False, "routes": []}
        routes = rt.get("routes", []) if rt.get("ok") else []
        hint_names = []
        for r in routes[:3]:
            hint_names += [p["name"] for p in r.get("path", []) if p.get("name")] + [r.get("control", "")]
        els = select_inventory(sm, question, hint_names, focus, CFG.BUDGETS.inventory_max)
        if allow_model and self.brain.available():
            les = self._llm_plan(question, sm, els, routes, conv, focus, on_partial, catalog, arch)
            if les is not None:
                les.app_key = sm.app_key
                self.resolve_steps(les, sm, catalog, [r.get("shortcut", "") for r in routes])
                self._frame(les, arch)
                les.notes.append(f"planned in {time.time() - t0:.1f}s via {les.source}")
                return les
        les = self._fallback_plan(question, sm, routes)
        les.app_key = sm.app_key
        self.resolve_steps(les, sm, catalog, [r.get("shortcut", "") for r in routes])
        self._frame(les, arch)
        return les

    @staticmethod
    def _frame(les: Lesson, arch: Optional[Dict[str, Any]]) -> None:
        """Record the macro idea (first sentence of the opening line) and the kind of software the lesson was framed for."""
        first = re.split(r"(?<=[.!?])\s+", (les.speech or "").strip(), maxsplit=1)[0] if les.speech else ""
        les.principle = first[:200]
        if arch and arch.get("id") not in (None, "unknown"):
            les.archetype = arch["id"]

    def _llm_plan(self, question: str, sm: ScreenModel, els: List[UIElement], routes: List[Dict[str, Any]], conv: Conversation,
                  focus: Optional[UIElement], on_partial: Optional[Callable[[str, Any], None]] = None, catalog: Any = None, arch: Optional[Dict[str, Any]] = None) -> Optional[Lesson]:
        parts = [f'APPLICATION: {sm.app_key or "unknown"}  WINDOW: "{sm.window_title}"  PICTURE: {sm.size[0]}x{sm.size[1]}']
        try:
            from .archetype import teaching_line
            line = teaching_line(arch or {})
            if line:
                parts.append(line)
        except Exception:
            pass
        parts += ["INVENTORY (the only controls you may point at; number = element id):", inventory_lines(sm, els)]
        if catalog is not None:
            try:
                hk = catalog.prompt_lines([question] + [e.label for e in els[:8] if e.label], limit=8)
                if hk:
                    parts += ["HOTKEYS (printed by this application itself):", hk]
            except Exception:
                pass
        try:
            from .pedagogy import behaviour_lines
            beh = behaviour_lines(sm.app_key)
            if beh:
                parts += ["OBSERVED BEHAVIOUR (tested on this application):", beh]
        except Exception:
            pass
        try:
            from . import skills as SK
            if os.path.isfile(SK.SKILL_DB):
                wf = SK.library().prompt_lines(question, sm.app_key)
                if wf:
                    parts += ["VERIFIED WORKFLOWS (these exact sequences worked on this application before):", wf]
        except Exception:
            pass
        if routes:
            parts += ["KNOWN ROUTES (measured from this application):", routes_text(routes)]
        try:
            from .knowledge import manual_rag
            block, manual = manual_rag.prompt_block(question, sm.app_key, self.brain)
            if block:
                parts.append(block)
        except Exception:
            manual = []
        if focus is not None:
            parts.append(f"The learner's mouse is over: {focus.line()}")
        parts.append(f'LEARNER SAYS: "{question}"')
        r = self.brain.generate(PERSONA, "\n".join(parts), schema=SCHEMA, max_tokens=700, temperature=0.2, history=conv.history(),
                                on_text=stream_watcher(on_partial) if on_partial else None)
        if not r.ok or not isinstance(r.json, dict):
            return None
        d = r.json
        steps: List[LessonStep] = []
        for i, s in enumerate((d.get("steps") or [])[:8], 1):
            if not isinstance(s, dict):
                continue
            act = s.get("action") if s.get("action") in ACTIONS else "look"
            eid = s.get("element")
            steps.append(LessonStep(i, speakable(str(s.get("say", ""))), act, int(eid) if isinstance(eid, int) else None, str(s.get("find") or ""),
                                    str(s.get("text") or ""), str(s.get("keys") or ""), "", str(s.get("expect") or ""), None, str(s.get("target") or "")))
        mode = d.get("mode") if d.get("mode") in ("answer", "lesson", "clarify") else ("lesson" if steps else "answer")
        les = Lesson(str(d.get("title") or question)[:80], speakable(str(d.get("speech") or "")), steps, mode, f"llm:{r.backend}", question)
        les.notes.append(f"{r.backend} {r.seconds:.1f}s")
        return les

    # ---------------------------------------------------------------------------------------- deterministic paths
    def _locate(self, question: str, sm: ScreenModel) -> Optional[Lesson]:
        m = self._LOCATE.match(question or "")
        if not m:
            return None
        phrase = m.group(1)
        hits = sm.find(phrase, limit=8)
        if not hits:
            words = _words(phrase)
            scored = []
            for e in sm.named():
                ew = set(fold(e.label).split())
                ov = len(set(words) & ew)
                if ov:
                    scored.append((ov / max(1, len(ew)) + ov, e))
            scored.sort(key=lambda t: -t[0])
            hits = [e for _s, e in scored[:3]]
        if not hits:
            return None
        e = hits[0]
        where = EX._where(e, sm)
        les = Lesson(f"Where is {e.label}", speakable(f"The {e.label} {e.role.replace('_', ' ')} is {where}. Here it is."),
                     [LessonStep(1, "", "look", e.id, "", "", "", "", "", e.bbox, e.label, "scan")], "answer", "scan", question, sm.app_key)
        if len(hits) > 1:
            les.notes.append("other matches: " + ", ".join(f"#{h.id} {h.label}" for h in hits[1:4]))
        return les

    def explain(self, e: UIElement, sm: ScreenModel, allow_model: bool = True) -> Lesson:
        sheet = EX.fact_sheet(e, sm)
        base = speakable(EX.spoken(sheet))
        text, src = base, "knowledge"
        if allow_model and self.brain.available():
            r = self.brain.generate(PERSONA.split("How you teach:")[0] + "Rephrase the FACTS below as a warm spoken explanation of at most 3 sentences. Add nothing that is not in the facts.",
                                    "FACTS: " + str({k: v for k, v in sheet.items() if v not in ("", [], {}, None)}), max_tokens=220, temperature=0.3)
            if r.ok and r.text.strip():
                text, src = speakable(r.text.strip()), f"llm:{r.backend}"
        step = LessonStep(1, "", "look", e.id, "", "", "", "", "", e.bbox, e.label, "scan")
        return Lesson(f"About {e.label or 'this control'}", text, [step], "answer", src, "", sm.app_key, [f"facts: {sheet.get('trust')}"])

    def _fallback_plan(self, question: str, sm: ScreenModel, routes: List[Dict[str, Any]]) -> Lesson:
        if not routes:
            return Lesson(question[:60], "I can see the screen, but I don't have a way to work that out right now. Try asking where a specific button is.", [], "clarify",
                          "fallback", question, sm.app_key, ["no language model and no stored route"])
        best = routes[0]
        steps: List[LessonStep] = []
        n = 0
        for p in best.get("path", []):
            if p["kind"] not in ("surface", "group", "control", "item", "dialog"):
                continue
            if p["kind"] == "group":
                continue
            n += 1
            verb = {"surface": "Open the {n} tab", "control": "Click {n}", "item": "Choose {n}", "dialog": "In the {n} dialog"}[p["kind"]].format(n=p["name"])
            steps.append(LessonStep(n, speakable(verb + "."), "click" if p["kind"] != "dialog" else "look", None, p["name"], "", "", "", "", None, p["name"]))
        if best.get("shortcut"):
            steps.append(LessonStep(n + 1, speakable(f"Or use the shortcut {best['shortcut']}."), "key", None, "", "", best["shortcut"]))
        if best.get("outcome"):
            steps[-1].expect = re.sub(r"\*\*", "", best["outcome"])[:160] if steps else ""
        intro = speakable(re.sub(r"\*\*", "", f"Here's how: {best.get('text', '')}."))
        return Lesson(question[:60], intro, steps, "lesson", "knowledge", question, sm.app_key, ["deterministic route from stored UI map"])

    # ---------------------------------------------------------------------------------------- step resolution
    @staticmethod
    def _attach_hotkeys(lesson: Lesson, catalog: Any, trusted: Any = ()) -> None:
        """Every step's hotkey comes from the application's own catalog (by the control it points at). A key chord the MODEL wrote that the application never printed
        (neither in the catalog nor in the measured routes) is dropped."""
        if catalog is None:
            return
        try:
            from .harvest import normalize_chord as _nc
            known = {c.lower() for c in catalog.shortcut_map()} | {_nc(t).lower() for t in trusted if t}
        except Exception:
            return
        for st in lesson.steps:
            hk = catalog.shortcut_for(st.label) if st.label else ""
            if not hk and st.find:
                hk = catalog.shortcut_for(st.find)
            if st.keys:
                from .harvest import normalize_chord
                ch = normalize_chord(st.keys)
                if ch.lower() in known:
                    hk = hk or ch
                elif ch and lesson.source.startswith("llm"):
                    lesson.notes.append(f"step {st.n}: shortcut '{st.keys}' is not printed by the application; not shown")
                    st.keys = ""
            if hk:
                st.hotkey = hk
                if not st.keys and st.action in ("key",):
                    st.keys = hk

    def resolve_steps(self, lesson: Lesson, sm: ScreenModel, catalog: Any = None, trusted: Any = ()) -> None:
        """Turn element ids / names into measured boxes. Repairs ids the model mis-numbered by checking the label it said it meant."""
        self._resolve_boxes(lesson, sm)
        self._attach_hotkeys(lesson, catalog, trusted)

    def _resolve_boxes(self, lesson: Lesson, sm: ScreenModel) -> None:
        for st in lesson.steps:
            e: Optional[UIElement] = sm.element(st.element_id) if st.element_id is not None else None
            tgt = st.label or ""
            if e is not None and tgt and e.label:
                a, b = fold(tgt), fold(e.label)
                if a and b and a != b and a not in b and b not in a:
                    alt = [x for x in sm.find(tgt, limit=5) if x.id != e.id]
                    if alt:
                        lesson.notes.append(f"step {st.n}: id #{e.id} '{e.label}' did not match '{tgt}'; used #{alt[0].id}")
                        e = alt[0]
                    else:
                        lesson.notes.append(f"step {st.n}: id #{e.id} '{e.label}' does not match '{tgt}' (kept, low trust)")
            if e is None and (st.find or tgt):
                q = st.find or tgt
                hits = sm.find(q, limit=3) if len(fold(q)) < 60 else []
                if not hits:
                    qw = set(_ui_words(q))
                    cand = []
                    for x in sm.named():
                        ew = set(_ui_words(x.label))
                        ov = len(qw & ew)
                        if ov and ov / max(1, len(qw)) >= 0.75 and ov / max(1, len(ew)) >= 0.6:    # the query must be (almost) fully explained, or 'Picture from file' becomes a bare 'Picture'
                            cand.append((ov / max(1, len(qw)) + ov / max(1, len(ew)), x))
                    cand.sort(key=lambda c: -c[0])
                    hits = [c[1] for c in cand[:1]]
                if hits:
                    e = hits[0]
            if e is not None:
                st.element_id, st.box, st.label, st.grounded_by = e.id, e.bbox, e.label or tgt, "scan"
            else:
                st.element_id, st.box, st.grounded_by = None, None, "none"
