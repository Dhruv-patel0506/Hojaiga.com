"""
HOJAIGA SPRINT: Knowledge Builder & Query Engine
What the app is, what it can do, and how to make it do it.

Storage is JSON now so the sprint can run with zero setup; the shape mirrors
DATABASE_SCHEMA.md (app / element / interaction / capability) so the same rows
can be pushed into SQLite or organ_63's store without a rewrite.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict

SCHEMA_VERSION = 2

# Verbs users ask about -> words that appear in labels, effect and dialog titles.
# Keep every term >= 3 characters and specific: "x" matched "exponent", "change"
# matched every effect name, and the whole vocabulary lit up.
SYNONYMS = {
    "save": ["save", "saving", "save as", "save_or_confirm"],
    "create": ["new", "create", "blank", "insert", "creates_or_opens"],
    "new": ["new", "create", "blank", "ctrl+n"],
    "open": ["open", "load", "browse", "ctrl+o"],
    "close": ["close", "dismiss", "quit", "exit", "close_or_cancel"],
    "copy": ["copy", "duplicate"],
    "paste": ["paste"],
    "cut": ["cut"],
    "undo": ["undo", "revert"],
    "redo": ["redo"],
    "find": ["find", "search", "look up", "ctrl+f"],
    "replace": ["replace", "substitute"],
    "print": ["print", "pdf"],
    "delete": ["delete", "remove", "clear"],
    "settings": ["settings", "options", "preferences", "config"],
    "help": ["help", "about", "documentation"],
    "menu": ["menu", "navigation", "more options", "hamburger", "opens_menu"],
    "dialog": ["dialog", "opens_dialog", "panel"],
    "text": ["text", "type", "document", "accepts_text_input"],
    "write": ["text", "type", "document", "accepts_text_input"],
    "type": ["text", "type", "document", "accepts_text_input"],
    "format": ["format", "bold", "italic", "font", "theme"],
    "zoom": ["zoom", "magnify", "scale"],
    "share": ["share", "export"],
    "select": ["select", "choose", "uia-select", "selection"],
    "toggle": ["toggle", "switch", "toggles_state", "uia-toggle"],
    "expand": ["expand", "dropdown", "collapse", "uia-expand"],
    "navigate": ["navigate", "navigation", "tab", "jump"],
    "calculate": ["equals", "plus", "minus", "multiply", "divide", "calculate", "sum"],
    "edit": ["edit", "modify", "document", "text"],
    "clipboard": ["copy", "paste", "cut", "clipboard_action"],
}

ACTIONABLE_EFFECTS = {
    "opens_dialog", "opens_menu", "save_or_confirm", "close_or_cancel", "creates_or_opens",
    "clipboard_action", "replaces_view", "ui_changed", "local_change", "accepts_text_input",
    "keyboard_action", "highlight", "toggles_state", "selection_changed", "offers_command",
}


def _words(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


@dataclass
class Interaction:
    label: str
    effect_type: str
    id: str
    x: int = 0
    y: int = 0
    method: str = ""
    source: str = "uia"
    control_type: str = ""
    change_magnitude: float = 0.0
    detail: str = ""
    dialog: str = ""


@dataclass
class Capability:
    verb: str
    confidence: float
    evidence: list = field(default_factory=list)  # list[dict]


class HOJAIGAKnowledge:
    """Store and describe what one app can do."""

    def __init__(self, app_name):
        self.app_name = app_name
        self.interactions = []
        self.elements = []
        self.properties: Dict[str, Any] = {
            "total_interactions": 0,
            "total_elements": 0,
            "scan_time": 0,
            "probe_time": 0,
            "scanned_at": "",
        }

    def add_interaction(self, interaction_dict):
        fields = Interaction.__dataclass_fields__
        # Probers speak in probe-vocabulary (element_label/element_x); store in Interaction fields.
        aliased = dict(interaction_dict)
        aliased["label"] = interaction_dict.get("element_label") or interaction_dict.get("label") or "unnamed"
        aliased["x"] = int(interaction_dict.get("element_x", interaction_dict.get("x", 0)) or 0)
        aliased["y"] = int(interaction_dict.get("element_y", interaction_dict.get("y", 0)) or 0)
        clean = {k: v for k, v in aliased.items() if k in fields}
        clean["effect_type"] = clean.get("effect_type") or "unknown"
        inter = Interaction(
            id=f"int_{len(self.interactions)}",
            **{k: v for k, v in clean.items() if k != "id"}
        )
        self.interactions.append(inter)
        return inter

    def add_elements(self, uia_elements):
        keep = ("label", "control_type", "action", "enabled", "offscreen", "depth")
        self.elements = [{**{k: e.get(k) for k in keep},
                          "x": e.get("x", 0), "y": e.get("y", 0),
                          "width": e.get("width", 0), "height": e.get("height", 0)}
                         for e in uia_elements]
        self.properties["total_elements"] = len(self.elements)

    def capabilities(self):
        """Derive the verb list users can ask about, with the evidence behind each.

        Matching is split in two: our own structural fields (effect_type, method) are
        matched as substrings so "replace" fires on the replaces_view effect and "text"
        on accepts_text_input - but a control's LABEL is matched on whole words only,
        because otherwise "text" matches "Texture Paint" and every vocabulary verb lights
        up on an unrelated control.
        """
        caps = {}
        for inter in self.interactions:
            if inter.effect_type not in ACTIONABLE_EFFECTS:
                continue
            structural = (inter.effect_type + " " + inter.method).lower()
            label_words = _words(inter.label + " " + inter.dialog)
            label_text = (inter.label + " " + inter.dialog).lower()
            for verb, terms in SYNONYMS.items():
                matched = any(
                    t in structural                       # snake_case effect/method token
                    or t in label_words                   # a whole word in the label
                    or (" " in t and t in label_text)     # a multi-word phrase in the label
                    for t in terms
                )
                if not matched:
                    continue
                caps.setdefault(verb, []).append(inter)

        out = {}
        for verb, hits in caps.items():
            strength = min(1.0, 0.4 + 0.15 * len(hits) +
                           max((h.change_magnitude for h in hits), default=0.0))
            out[verb] = Capability(
                verb=verb,
                confidence=round(strength, 3),
                evidence=[{"label": h.label, "effect": h.effect_type, "method": h.method,
                           "dialog": h.dialog} for h in hits[:5]]
            )
        return sorted(out.values(), key=lambda c: -c.confidence)

    def to_dict(self):
        return {
            "schema_version": SCHEMA_VERSION,
            "app_name": self.app_name,
            "properties": self.properties,
            "capabilities": [asdict(c) for c in self.capabilities()],
            "interactions": [asdict(i) for i in self.interactions],
            "elements": self.elements,
        }

    def save_json(self, filepath):
        directory = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(directory, exist_ok=True)
        self.properties["total_interactions"] = len(self.interactions)
        self.properties["scanned_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(filepath, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False)
        print(f"[SAVE] Knowledge saved to {filepath}")
        return filepath

    @staticmethod
    def load_json(filepath):
        with open(filepath, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        knowledge = HOJAIGAKnowledge(data.get("app_name", "unknown"))
        fields = set(Interaction.__dataclass_fields__)
        for inter_dict in data.get("interactions", []):
            knowledge.interactions.append(
                Interaction(**{k: v for k, v in inter_dict.items() if k in fields}))
        knowledge.elements = data.get("elements", [])
        knowledge.properties = data.get("properties", knowledge.properties)
        return knowledge


class HOJAIGAQuery:
    """Ask the knowledge base questions."""

    def __init__(self, knowledge):
        self.knowledge = knowledge
        self._caps = None

    @property
    def caps(self):
        if self._caps is None:
            self._caps = {c.verb: c for c in self.knowledge.capabilities()}
        return self._caps

    def _expand(self, action):
        low = _words(action)
        terms = {action.lower().strip()}
        for verb, syns in SYNONYMS.items():
            if low & _words(verb) or verb in action.lower():
                terms.update(syns)
        return {t for t in terms if t}

    def matches(self, action):
        wanted = self._expand(action)
        scored = []
        for inter in self.knowledge.interactions:
            if inter.effect_type not in ACTIONABLE_EFFECTS:
                continue
            # Same split as capabilities(): our structural fields are matched as
            # substrings ("replace" fires on replaces_view, "text" on accepts_text_input),
            # but a control's LABEL/dialog is matched on whole words only - otherwise
            # "text" matches "Texture Paint" and unrelated apps light up on every verb.
            # control_type is excluded from the substring side so "text" never matches
            # the literal "OCRText" tag.
            structural = (inter.effect_type + " " + inter.method).lower()
            label_words = _words(inter.label + " " + inter.dialog)
            label_text = (inter.label + " " + inter.dialog).lower()
            score = sum(
                1 for t in wanted
                if t in structural or t in label_words or (" " in t and t in label_text)
            )
            if score:
                scored.append((score, inter))
        scored.sort(key=lambda p: (-p[0], -p[1].change_magnitude))
        return [inter for _, inter in scored]

    def can_do(self, action):
        return bool(self.matches(action)) or action.lower().strip() in self.caps

    def how_to_do(self, action):
        return self.matches(action)

    def find_by_label(self, keyword):
        low = keyword.lower()
        return [i for i in self.knowledge.interactions if low in i.label.lower()]

    def find_by_effect(self, effect_type):
        return [i for i in self.knowledge.interactions if effect_type in i.effect_type]

    def list_all(self):
        return self.knowledge.interactions

    def get_summary(self) -> Dict[str, Any]:
        distribution = {}
        for inter in self.knowledge.interactions:
            distribution[inter.effect_type] = distribution.get(inter.effect_type, 0) + 1
        return {
            "app_name": self.knowledge.app_name,
            "total_interactions": len(self.knowledge.interactions),
            "total_elements": len(self.knowledge.elements),
            "effect_distribution": distribution,
            "capabilities": [c.verb for c in self.knowledge.capabilities()],
            "properties": self.knowledge.properties,
        }

    def print_report(self):
        summary = self.get_summary()
        print(f"\n{'=' * 66}")
        print(f"HOJAIGA KNOWLEDGE REPORT: {summary['app_name']}")
        print(f"{'=' * 66}")
        print(f"UIA elements seen : {summary['total_elements']}")
        print(f"Interactions lived: {summary['total_interactions']}")
        props = summary["properties"]
        print(f"Scan / probe time : {props.get('scan_time', 0):.1f}s / {props.get('probe_time', 0):.1f}s")

        caps = self.knowledge.capabilities()
        print(f"\nCapabilities ({len(caps)}):")
        for cap in caps[:14]:
            first = cap.evidence[0] if cap.evidence else {}
            hint = first.get("dialog") or first.get("label") or first.get("method") or ""
            print(f"  * {cap.verb:<12} conf {cap.confidence:<5} via {hint[:42]}")

        print(f"\nEffect mix:")
        for effect, count in sorted(summary["effect_distribution"].items(), key=lambda x: -x[1]):
            print(f"  - {effect}: {count}")
        print(f"\n{'=' * 66}\n")
