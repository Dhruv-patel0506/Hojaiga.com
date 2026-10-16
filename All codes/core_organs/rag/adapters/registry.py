"""command_registry.build() rows -> Lexicon (names, menu paths, help leads) + Sub-RAG 4 (shortcuts as hotkeys, menu ids as WM_COMMAND, automation ids stay in the lexicon)."""
from __future__ import annotations

from typing import Any, Dict, Sequence

from ..lexicon import canon

_RISK = {"E2": "destructive"}


def from_registry(rag, app_key: str, registry: Sequence[Dict[str, Any]], archetype: str = "") -> Dict[str, int]:
    n_cmd = rag.lex.ingest_registry(app_key, registry, archetype)
    rows = []
    for g in registry:
        name = (g.get("name") or "").strip()
        if not name or not canon(name):
            continue
        cid = f"{app_key}:{canon(name)}"
        trust = "verified" if g.get("verified") else {4: "learned", 3: "catalog", 2: "seed", 1: "llm"}.get(int(g.get("trust", 2) or 2), "seed")
        for sc in ([g["shortcut"]] if g.get("shortcut") else []) + list(g.get("alt_shortcuts") or []):
            rows.append({"app_key": app_key, "kind": "hotkey", "command_id": cid, "task_pattern": name, "payload": str(sc).lower().replace(" ", ""), "source": "registry",
                         "trust": trust, "verified": bool(g.get("verified")), "safety": _RISK.get(g.get("risk", "EU"), "")})
        for mid in g.get("menu_ids") or []:
            rows.append({"app_key": app_key, "kind": "wm_command", "command_id": cid, "task_pattern": name, "payload": str(int(mid)), "source": "registry", "trust": trust,
                         "verified": bool(g.get("verified")), "safety": _RISK.get(g.get("risk", "EU"), "")})
    rep = rag.fast.upsert(rows) if rows else None
    return {"commands": n_cmd, "fast_paths": (rep.inserted + rep.updated) if rep else 0}
