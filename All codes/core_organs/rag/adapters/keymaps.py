"""atlas.keymaps.extract() bindings ({kind:'key', input, action, context}) -> Sub-RAG 4 as shipped keymap rows (catalog trust, never verified) + lexicon keymap_action aliases."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Sequence

from ..lexicon import canon


def _human(action: str) -> str:
    """'mesh.extrude_region_move' -> 'extrude region move'"""
    return re.sub(r"[_.]+", " ", action.split(".")[-1]).strip()


def from_keymap(rag, app_key: str, bindings: Sequence[Dict[str, Any]], source_url: str = "") -> Dict[str, int]:
    rows, n_alias = [], 0
    for b in bindings:
        if b.get("kind") != "key" or not b.get("input") or not b.get("action"):
            continue
        label = _human(str(b["action"]))
        if not canon(label):
            continue
        hit = rag.lex.best(app_key, label)
        cid = hit.command_id if hit else f"{app_key}:{canon(label)}"
        if hit:
            n_alias += int(rag.lex.add_alias(app_key, str(b["action"]), cid, "keymap_action", "keymap", "catalog"))
        rows.append({"app_key": app_key, "kind": "hotkey", "command_id": cid, "task_pattern": label, "payload": str(b["input"]).lower().replace(" ", ""),
                     "context": str(b.get("context", "")), "preconditions_json": ({"editor": b["context"]} if b.get("context") else {}), "source": "keymap_file", "trust": "catalog",
                     "extra_json": json.dumps({"url": source_url})})
    rep = rag.fast.upsert(rows) if rows else None
    return {"fast_paths": (rep.inserted + rep.updated) if rep else 0, "aliases": n_alias}
