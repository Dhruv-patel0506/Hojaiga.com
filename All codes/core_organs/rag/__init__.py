"""
rag -- the federated multi-RAG (design: DESIGN.md). Five sub-RAGs under one Master Router, on LanceDB + SQLite + a derived networkx view.

    from core_organs import rag
    r = rag.retrieve(rag.Query(text="how do I extrude the face", app_key="blender", snapshot=nodes, mode="tutor"))
    rag.observe(rag.Outcome(...))           # the executor reports every step: the graph, hotkey reliability, procedures and playbooks all learn
    rag.status()                            # root, degraded reasons, table sizes

get_rag() is the process-wide Rag; tests build their own Rag(Storage(tmp_root)).
"""
from __future__ import annotations

import os
import threading
from typing import Any, Optional

from .types import (Evidence, Outcome, Plan, PlanStep, Query, RagStatus, Retrieval, UpsertReport)   # noqa: F401
from .router import Rag, Router, classify_intent, infer_tier                                       # noqa: F401
from .storage import Storage, get_storage, reset_storage, resolve_root                              # noqa: F401

_RAG: Optional[Rag] = None
_LOCK = threading.Lock()


def get_rag() -> Rag:
    global _RAG
    with _LOCK:
        if _RAG is None:
            rewriter = None
            if os.environ.get("HOJAIGA_RAG_REWRITE", "on").lower() not in ("off", "0", "false", "no"):
                try:
                    from .adapters.llm_rewrite import rewriter as _rw
                    rewriter = _rw()                       # weak-recall fallback only (DESIGN 7.6); costs nothing while the model is down
                except Exception:
                    rewriter = None
            _RAG = Rag(rewriter=rewriter)
        return _RAG


def reset_rag() -> None:
    global _RAG
    with _LOCK:
        if _RAG is not None:
            try:
                _RAG.close()
            except Exception:
                pass
        _RAG = None
    reset_storage()


def retrieve(q: Query) -> Retrieval:
    return get_rag().retrieve(q)


def retrieve_workflow(app_key: str, user_goal: str, current_som_map: Any = None, mode: str = "auto", **kw) -> Retrieval:
    return get_rag().retrieve_workflow(app_key, user_goal, current_som_map, mode, **kw)


def localize(app_key: str, snapshot: Any, **kw):
    return get_rag().localize(app_key, snapshot, **kw)


def observe(o: Outcome):
    return get_rag().observe(o)


def ingest(sub_rag: str, records):
    return get_rag().ingest(sub_rag, records)


def status() -> RagStatus:
    return get_rag().status()
