"""professor.symbol_eval -- CAN THE VISION SIDE READ THE APPLICATION'S SYMBOLS? Measured, not assumed.

Icon-only controls (a ribbon's B / I / U, a paint bucket, a brush) carry a NAME in the accessibility tree when the application publishes one. That name is the ground truth: each
icon-only control's picture is cut out of the window and the vision side (icon memory first, then the vision model, exactly the path a blind application gets) is asked to name it
WITHOUT seeing the tree's name. Agreement is scored per control, and the result tells how far a blind application's symbols can be trusted.

Every icon whose tree name is known is also LEARNED into the icon memory under that name (source 'uia'), so the symbol database grows with every application the run can read -
the same pictures in a blind application are then named from memory.

    evaluate(img, nodes, origin, labeler, app, max_icons) -> {"icons", "named", "correct", "accuracy", "by_source", "ribbon": {...}, "misses": [...], "learned"}"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .schema import Box, fold

ICON_ROLES = ("button", "splitbutton", "toggle", "menuitem", "checkbox", "radiobutton")
_STOP = {"the", "a", "an", "and", "of", "to", "on", "in", "for", "with", "button", "menu", "more", "options", "option"}

SYNONYM_GROUPS = [
    {"menu", "nav", "navigation", "drawer", "sidebar", "hamburger"},
    {"find", "search", "lookup", "magnifier", "glass"},
    {"settings", "gear", "options", "preferences", "config", "setup", "customize"},
    {"add", "new", "plus", "create", "zoom in", "enlarge", "bigger"},
    {"close", "dismiss", "cancel", "exit", "cross", "multiply", "x"},
    {"minus", "subtract", "collapse", "minimize", "dash", "zoom out", "smaller"},
    {"maximize", "restore", "expand", "fullscreen", "square", "box", "window"},
    {"redo", "repeat"},
    {"undo", "revert"},
    {"bullet", "bulleted", "list", "bullets"},
    {"number", "numbered", "numbering"},
    {"indent", "indentation", "align", "alignment", "left", "right", "center", "justify"},
    {"paragraph", "pilcrow", "showall", "formatting", "mark"},
    {"case", "capital", "uppercase", "lowercase", "font"},
    {"grow", "increase", "size", "bigger", "enlarge", "zoom"},
    {"shrink", "decrease", "smaller", "reduce"},
    {"highlight", "highlighter", "color", "colour", "fill", "shading"},
    {"paste", "clipboard"},
    {"cut", "scissors"},
    {"copy", "duplicate"},
    {"save", "floppy", "disk"},
    {"trash", "delete", "remove", "bin", "recycle"},
    {"dropdown", "chevron", "arrow", "down", "more", "expand", "options", "launcher"},
    {"border", "borders", "grid", "table", "cell"},
]


def _stem(w: str) -> str:
    for sfx in ("ing", "ed", "es", "s", "ly"):
        if w.endswith(sfx) and len(w) > len(sfx) + 2:
            return w[:-len(sfx)]
    return w


def _words(t: str) -> set:
    raw = [w for w in re.findall(r"[a-z0-9]+", fold(t))]
    out = set()
    for w in raw:
        if len(raw) > 1 and w in _STOP:
            continue
        if len(w) < 2:
            continue
        out.add(_stem(w))
    if not out and raw:
        out = {_stem(w) for w in raw if len(w) >= 2} or {raw[0]}
    return out


def agree(truth: str, guess: str) -> bool:
    """Does the vision name mean the tree's name? Same words (plural-insensitive), or every content word of the shorter one is in the longer one ('Bold' ~ 'Bold (Ctrl+B)')."""
    clean_truth = re.sub(r"\(.*?\)", "", truth).strip()
    clean_guess = guess.strip()
    fa, fb = fold(clean_truth), fold(clean_guess)
    if fa and fb and (fa == fb or fa in fb or fb in fa):
        return True
    a, b = _words(clean_truth), _words(clean_guess)
    if not a or not b:
        return False
    if a == b:
        return True
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    if len(small & big) >= max(1, len(small)):
        return True
    for grp in SYNONYM_GROUPS:
        grp_stem = {_stem(w) for w in grp}
        if bool(a & grp or a & grp_stem) and bool(b & grp or b & grp_stem):
            return True
    return False


def icon_nodes(nodes: Sequence[Any], win: Tuple[int, int, int, int], max_icons: int = 60) -> List[Any]:
    """Small, square-ish, named, visible controls inside the window: the controls a person recognises by their picture."""
    wl, wt, wr, wb = win
    out, seen = [], set()
    for n in nodes:
        l, t, r, b = tuple(n.rect)[:4]
        w, h = r - l, b - t
        if n.role not in ICON_ROLES or not (n.name or "").strip() or getattr(n, "offscreen", False):
            continue
        fn = fold(n.name)
        if any(fn == p or fn.startswith(f"{p} ") or fn.endswith(f" {p}") for p in ("minimize", "maximize", "restore", "close", "system menu", "system")):
            continue
        if "," in n.name or any(p in fn for p in ("account", "profile", "sign in", "signed in")):
            continue
        aid_lower = getattr(n, "aid", "").lower()
        if any(p in aid_lower for p in ("minimize", "maximize", "close", "restore", "titlebar", "account", "profile", "useravatar", "avatar")):
            continue
        if not (10 <= w <= 64 and 10 <= h <= 64 and max(w, h) <= 1.8 * min(w, h)):
            continue
        if not (wl <= l and r <= wr and wt <= t and b <= wb):
            continue
        key = (fold(n.name), l // 4, t // 4)
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    out.sort(key=lambda n: (n.rect[1], n.rect[0]))
    return out[:max_icons]


def _aid_truth(aid: str) -> str:
    """A control's automation id often carries its TRUE command name ('Redo', 'FontColor', 'IdQATCustomize'): split camel / snake / digits. Used as a SECOND ground truth when the tree's Name
    is something else entirely (a status text 'Can't Repeat', the signed-in person's name): vision is then right and the Name is the unreliable one."""
    if not aid:
        return ""
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(aid).replace("_", " "))
    words = [w for w in re.findall(r"[A-Za-z]{3,}", parts) if w.lower() not in ("id", "btn", "button", "ctrl", "control", "xaml", "win", "ms")]
    if not (1 <= len(words) <= 5):
        return ""
    return " ".join(words)


def evaluate(img: Any, nodes: Sequence[Any], win: Tuple[int, int, int, int], labeler: Any, app: str = "", max_icons: int = 60, budget_s: float = 90.0,
             band: Optional[Tuple[int, int]] = None, learn: bool = True, memory_first: bool = True) -> Dict[str, Any]:
    """`img`: the window's picture; `win`: the window's screen rectangle the picture shows; `band`: (top, bottom) screen rows of a ribbon / tool band, scored separately."""
    rep: Dict[str, Any] = {"icons": 0, "named": 0, "correct": 0, "accuracy": None, "by_source": {}, "misses": [], "learned": 0, "ribbon": {"icons": 0, "correct": 0, "accuracy": None}}
    if img is None or labeler is None:
        rep["skipped"] = "no picture or no labeler"
        return rep
    sx = img.width / max(1, (win[2] - win[0]))
    sy = img.height / max(1, (win[3] - win[1]))
    picks = icon_nodes(nodes, win, max_icons)
    boxes = [Box((n.rect[0] - win[0]) * sx, (n.rect[1] - win[1]) * sy, (n.rect[2] - win[0]) * sx, (n.rect[3] - win[1]) * sy) for n in picks]
    keep = [(n, b) for n, b in zip(picks, boxes) if b.w >= 6 and b.h >= 6 and b.x2 <= img.width + 2 and b.y2 <= img.height + 2]
    if not keep:
        rep["skipped"] = "no icon-only controls with a picture"
        return rep
    picks, boxes = [k[0] for k in keep], [k[1] for k in keep]
    mem = labeler.from_memory(img, boxes) if memory_first else [None] * len(boxes)
    todo = [i for i, m in enumerate(mem) if m is None]
    vis, meta = labeler.label_boxes(img, [boxes[i] for i in todo], budget_s=budget_s) if todo else ([], {})
    labels = list(mem)
    for k, i in enumerate(todo):
        labels[i] = vis[k] if k < len(vis) else None
    rep["vision_meta"] = {k: meta.get(k) for k in ("sheets", "asked", "named", "skipped")} if meta else {}
    for n, b, lab in zip(picks, boxes, labels):
        in_band = band is not None and band[0] <= n.rect[1] and n.rect[3] <= band[1]
        rep["icons"] += 1
        rep["ribbon"]["icons"] += 1 if in_band else 0
        guess = lab.text if lab is not None else ""
        src = lab.via if lab is not None else "none"
        rep["by_source"][src] = rep["by_source"].get(src, 0) + 1
        ok = bool(guess) and agree(n.name, guess)
        ok_aid = False
        if not ok and guess:
            aid_name = _aid_truth(getattr(n, "aid", ""))
            ok_aid = bool(aid_name) and (agree(aid_name, guess) or agree(guess, aid_name))
        if guess:
            rep["named"] += 1
        bs = rep.setdefault("by_source_correct", {})
        bs[src] = bs.get(src, 0) + (1 if (ok or ok_aid) else 0)
        if ok or ok_aid:
            rep["correct"] += 1
            rep["ribbon"]["correct"] += 1 if in_band else 0
            if ok_aid and not ok:
                rep["correct_by_aid"] = rep.get("correct_by_aid", 0) + 1         # the tree's Name disagreed but the id says vision was right
        elif len(rep["misses"]) < 25:
            rep["misses"].append({"truth": n.name[:40], "vision": guess[:40], "via": src, "aid": (getattr(n, "aid", "") or "")[:30]})
        if learn and getattr(labeler, "memory", None) is not None:
            try:
                from .icon_memory import fingerprint
                labeler.memory.learn(fingerprint(img.crop(b.clip(img.width, img.height).ituple())), n.name.strip()[:60], "uia", app)
                rep["learned"] += 1
            except Exception:
                pass
    rep["accuracy"] = round(100.0 * rep["correct"] / rep["icons"], 1) if rep["icons"] else None
    rep["accuracy_by_source"] = {k: round(100.0 * rep["by_source_correct"].get(k, 0) / v, 1) for k, v in rep["by_source"].items() if v}
    ri = rep["ribbon"]
    ri["accuracy"] = round(100.0 * ri["correct"] / ri["icons"], 1) if ri["icons"] else None
    return rep
