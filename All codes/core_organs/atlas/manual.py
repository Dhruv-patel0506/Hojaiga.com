"""
atlas.manual -- the full USER MANUAL of an application, generated from what the cartographer saw. Nothing is written that was not read from the live window.

    # PowerPoint
    ## Insert tab
    ### Images group
    - **Pictures** (drop-down): This Device..., Stock Images..., Online Pictures...
        - **This Device...** opens the dialog "Insert Picture" (fields: File name, Files of type; Open / Cancel)

Sections: how the window is organised (surfaces), every tab / menu with its groups and controls, every dialog that was opened with its fields, controls that need a
selection first (disabled when scanned), shortcuts, and the things the scanner deliberately did NOT open (capture / share / account / destructive).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from . import common as C
from . import teach


def _items_line(lt: Dict[str, Any], limit: int = 14) -> str:
    items = lt.get("items") if isinstance(lt.get("items"), list) else []
    names = [i["name"] if isinstance(i, dict) else str(i) for i in items]
    if not names:
        return ""
    return ", ".join(names[:limit]) + (f", ... ({len(names)} in total)" if len(names) > limit else "")


def render(key: str, title: str = "") -> str:
    m = teach.load_map(key)
    if not m:
        return f"# {title or key}\n\n_No UI map yet. Run: `python hojaiga_atlas.py learn {key} --tier full`._\n"
    L: List[str] = [f"# {title or key} - how it works (generated from the live application)", ""]
    st = m.get("stats", {})
    L.append(f"_Scanned in {m.get('seconds', '?')} s: {st.get('tabs', 0)} tabs, {st.get('groups', 0)} groups, {st.get('controls', 0)} controls, {st.get('expanded', 0)} drop-downs expanded "
             f"({st.get('items', 0)} items read), {st.get('dialogs', 0)} dialogs opened and cancelled._")
    if m.get("workspace", {}).get("state") == "created":
        L.append(f"_The program opened on a start screen; the scan created an empty working document through '{m['workspace'].get('via')}'._")
    L += ["", "## Layout", ""]
    for s in m.get("surfaces", []):
        n = sum(len(g.get("controls", [])) for g in s.get("groups", []))
        L.append(f"- **{s['name']}** ({s['kind'].replace('-', ' ')}): {len(s.get('groups', []))} groups, {n} controls")
    dialogs: Dict[str, Dict[str, Any]] = {}
    needs_selection: List[str] = []
    not_opened: List[str] = []
    shortcuts: List[str] = []
    for s in m.get("surfaces", []):
        L += ["", f"## {s['name']}" + (" tab" if s["kind"] == "ribbon-tab" else ""), ""]
        for g in s.get("groups", []):
            if g.get("name") and g["name"] not in ("(ungrouped)",):
                L += [f"### {g['name']}", ""]
            for c in g.get("controls", []):
                lt = c.get("leads_to") or {}
                typ = lt.get("type", "")
                tags = []
                if c.get("kind") in ("split", "dropdown") and typ in ("menu", "gallery"):
                    tags.append("drop-down")
                elif c.get("kind") in ("toggle", "checkbox"):
                    tags.append("toggle" + (f", {c['state']}" if c.get("state") else ""))
                elif c.get("kind") in ("combobox", "edit", "spinner", "slider"):
                    tags.append("value")
                if c.get("accel"):
                    tags.append(c["accel"])
                    shortcuts.append(f"{c['accel']} - {c['name']} ({s['name']})")
                line = f"- **{c['name']}**" + (f" ({'; '.join(tags)})" if tags else "")
                if not c.get("enabled", True):
                    line += " - needs a selection first"
                    needs_selection.append(f"{c['name']} ({s['name']}" + (f" > {g['name']}" if g.get("name") else "") + ")")
                il = _items_line(lt)
                if il:
                    line += f": {il}"
                if typ == "dialog" and lt.get("dialog"):
                    line += f" -> opens dialog \"{lt['dialog']}\""
                    dialogs[lt["dialog"]] = lt
                if typ == "pane":
                    line += " -> opens a side pane"
                if typ == "not-opened":
                    not_opened.append(f"{c['name']} ({s['name']})")
                L.append(line)
                for it in (lt.get("items") or []) if isinstance(lt.get("items"), list) else []:
                    if isinstance(it, dict) and it.get("leads_to", {}).get("type") == "dialog":
                        ilt = it["leads_to"]
                        dialogs[ilt.get("dialog", it["name"])] = ilt
                        L.append(f"    - **{it['name']}** opens dialog \"{ilt.get('dialog')}\"")
                    if isinstance(it, dict) and isinstance(it.get("items"), list) and it["items"]:
                        L.append(f"    - **{it['name']}** > " + ", ".join(i["name"] for i in it["items"][:10] if isinstance(i, dict)))
            L.append("")
    if dialogs:
        L += ["## Dialogs that were opened (and cancelled)", ""]
        for t, lt in sorted(dialogs.items()):
            fields = [f["name"] for f in (lt.get("fields") or []) if isinstance(f, dict) and f.get("name")]
            L.append(f"### {t}")
            if fields:
                L.append("Fields and buttons: " + ", ".join(fields[:40]) + (" ..." if len(fields) > 40 else ""))
            if lt.get("pages"):
                L.append(f"{lt['pages']} additional page(s) behind the list on the left.")
            if lt.get("commit") or lt.get("cancel"):
                L.append(f"Confirm: {lt.get('commit') or '?'}; back out: {lt.get('cancel') or '?'}.")
            L.append("")
    if needs_selection:
        L += ["## Controls that need something selected first", "", "These were disabled in the empty document that was scanned (select text, a shape, a table... to enable them):", ""]
        L.append(", ".join(sorted(set(needs_selection))[:120]))
        L.append("")
    if shortcuts:
        L += ["## Keyboard shortcuts seen", ""]
        L += [f"- {s}" for s in sorted(set(shortcuts))[:100]]
        L.append("")
    if not_opened:
        L += ["## Named but never opened by the scan", "", "Capture, share, account, playback and destructive controls are listed but deliberately not triggered:", "", ", ".join(sorted(set(not_opened))[:80]), ""]
    if m.get("incidents"):
        L += ["## Scan incidents", ""] + [f"- {i['class']} appeared during '{i['during']}' and was {i['handled']}" for i in m["incidents"]] + [""]
    return "\n".join(L)


def write(key: str, title: str = "") -> str:
    d = os.path.join(C.ATLAS_DIR, "reports", key)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "manual.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(render(key, title))
    return p
