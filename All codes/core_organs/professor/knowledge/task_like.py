"""
professor.knowledge.task_like -- IS THIS PASSAGE OF A GUIDE A TASK (do this, then this, and you get that) OR REFERENCE MATERIAL (what a menu entry / panel / option means)?

A guide's index is mostly reference: the Blender manual lists what every menu item, region and option IS. The step parser reads such a passage as 'steps' too ('File Menu: Open - Allows opening an
existing file' = click Open), and a run that attempts it measures nothing about what the person asked for: an explanation is not a thing that can be done and checked. A task has a shape:

  * its steps are written as instructions to the reader (imperative verbs, 'you' / 'then' / 'next', numbered), not as definitions in the third person ('Allows', 'Displays', 'Toggles', ...)
  * the steps change something that can be seen afterwards (an object, a value, a mode, a selection) and the passage often says what you get ('the object is now ...')
  * the heading names a goal ('Create a ...', 'Adding ...', 'Using ...', 'Parenting') rather than a part of the interface ('Header', 'Interactive Region', 'File Menu', 'Options')

`task_score(procedure)` is 0..1 from those features and `explain(procedure)` says why, so a run can prefer real tasks and report the reason a passage was set aside. Nothing here names an
application: the cues are the way instructions are written.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# a heading that names a part of the interface / a reference section
REFERENCE_HEAD_RX = re.compile(
    r"^(?:the\s+)?(?:header|footer|toolbar|tool\s?bar|sidebar|side\s?bar|menus?|options?|settings|properties|panels?|regions?|interactive region|interface|editors?|overview|introduction|"
    r"reference|usage|common|general|display|preferences|operators?|tools?|modes?|hotkeys?|shortcuts?|keymap|navigation|splash screen|workspaces?|areas?|windows?|file menu|edit menu|"
    r"[a-z ]+ menu|[a-z ]+ panel|[a-z ]+ options|[a-z ]+ settings|[a-z ]+ properties|[a-z ]+ node|[a-z ]+ modifier|[a-z ]+ constraint|[a-z ]+ tool|[a-z ]+ editor)\W*$", re.I)
# a heading that names a goal
GOAL_HEAD_RX = re.compile(r"^(?:how to |tutorial|quick start|quickstart|getting started|workflow|example|exercise|walk-?through|create|creating|add|adding|using|use|make|making|build|building|set up|setting up|"
                          r"configur|install|change|changing|apply|applying|move|moving|rotate|rotating|scale|scaling|extrud|insert|assign|connect|join|merge|split|separate|duplicat|delete|remov|"
                          r"parent|parenting|animat|render|export|import|save|saving|open|opening)", re.I)
# a definition written in the third person: 'Open Allows opening a file', 'Wireframe Displays the object as ...', 'Show Toggles ...'
DEFINITION_RX = re.compile(r"\b(?:allows?|lets?|enables?|displays?|shows?|toggles?|controls?|determines?|defines?|specifies|sets|selects the|opens the|used to|is used|are used|indicates?|represents?)\b", re.I)
# the reader is addressed: an instruction
INSTRUCT_RX = re.compile(r"^\W*(?:\d+[.)]\s*)?(?:then,?\s+|now,?\s+|next,?\s+|first,?\s+|finally,?\s+|after that,?\s+)?(?:go to|open|select|click|press|choose|set|enable|disable|check|uncheck|type|enter|drag|move|rotate|scale|"
                         r"add|create|extrude|delete|duplicate|hold|use|switch|change|activate|turn|toggle|navigate|expand|collapse|apply|assign|connect|name|rename|save|export|import|insert|pick|tick)\b", re.I)
SEQUENCE_RX = re.compile(r"\b(?:then|next|after that|afterwards|first|finally|now|once you|when you|you (?:can|should|will|may)|your)\b", re.I)
RESULT_RX = re.compile(r"\b(?:will (?:be|now|appear|show|become)|is now|are now|now (?:be|have|shows?)|you (?:will )?(?:see|get|have)|results? in|appears?|should (?:now )?(?:see|look))\b", re.I)


TASK_THRESHOLD = 0.4


def _step_lines(p: Dict[str, Any]) -> List[str]:
    return [getattr(s, "raw", "") or "" for s in p.get("steps", [])]


def features(p: Dict[str, Any]) -> Dict[str, float]:
    steps = p.get("steps", [])
    n = len(steps)
    raw = _step_lines(p)
    text = p.get("text", "") or ""
    goal = (p.get("goal") or "").replace("¶", "").strip()
    imperative = sum(1 for r in raw if INSTRUCT_RX.search(r)) / max(1, n)
    definitions = sum(1 for r in raw if DEFINITION_RX.search(r) and not INSTRUCT_RX.search(r)) / max(1, n)
    numbered = sum(1 for r in raw if re.match(r"^\W*\d+[.)]", r)) / max(1, n)
    concrete = sum(1 for s in steps if (getattr(s, "path", None) or getattr(s, "chord", "") or getattr(s, "text", "") or getattr(s, "target", ""))) / max(1, n)
    return {
        "n": float(n),
        "imperative": imperative,
        "definitions": definitions,
        "numbered": numbered,
        "concrete": concrete,
        "sequence": min(1.0, len(SEQUENCE_RX.findall(text)) / 3.0),
        "result": min(1.0, len(RESULT_RX.findall(text)) / 2.0),
        "reference_head": 1.0 if REFERENCE_HEAD_RX.match(goal) else 0.0,
        "goal_head": 1.0 if GOAL_HEAD_RX.match(goal) else 0.0,
        "second_person": 1.0 if re.search(r"\byou(?:r)?\b", text, re.I) else 0.0,
    }


def task_score(p: Dict[str, Any]) -> float:
    f = features(p)
    n = f["n"]
    s = 0.0
    s += 0.30 * f["imperative"]
    s += 0.10 * f["numbered"]
    s += 0.10 * f["sequence"]
    s += 0.10 * f["result"]
    s += 0.08 * f["second_person"]
    s += 0.07 * f["concrete"]
    s += 0.15 * f["goal_head"]
    s -= 0.30 * f["definitions"]
    s -= 0.20 * f["reference_head"]
    if n < 2:
        s -= 0.15                                                                       # one line is a reference entry far more often than a task
    elif 3 <= n <= 10:
        s += 0.10
    return max(0.0, min(1.0, s))


def explain(p: Dict[str, Any]) -> str:
    f = features(p)
    bits = []
    if f["reference_head"]:
        bits.append(f"the heading '{(p.get('goal') or '')[:40]}' names a part of the interface")
    if f["definitions"] >= 0.5:
        bits.append("its lines describe what things do (reference), not what to do")
    if f["imperative"] < 0.4:
        bits.append("few lines are instructions")
    if f["n"] < 2:
        bits.append("a single line")
    return "; ".join(bits) or "reads as reference"


def is_task(p: Dict[str, Any], threshold: float = TASK_THRESHOLD) -> Tuple[bool, float]:
    sc = task_score(p)
    return sc >= threshold, sc
