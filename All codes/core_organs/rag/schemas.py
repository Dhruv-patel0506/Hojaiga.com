"""rag.schemas -- the LanceDB table schemas (DESIGN.md section 5). One place, so migrations, upserts and tools.reembed agree. Every table: schema_v + extra_json."""
from __future__ import annotations

import pyarrow as pa

from . import config as C


def _vec():
    return pa.list_(pa.float32(), C.VEC_DIM)                   # nullable: a row written while the embedder was down has vector=NULL and embedder_id=""


def _common():
    return [("embedder_id", pa.string()), ("schema_v", pa.int32()), ("extra_json", pa.string())]


SCHEMAS = {
    "knowledge_chunks": pa.schema([
        ("chunk_id", pa.string()), ("app_key", pa.string()), ("app_version", pa.string()), ("source_kind", pa.string()), ("source_ref", pa.string()),
        ("heading_path", pa.string()), ("text", pa.string()), ("steps_json", pa.string()), ("mentions", pa.list_(pa.string())), ("unresolved", pa.list_(pa.string())),
        ("division", pa.string()), ("lang", pa.string()), ("trust", pa.string()), ("quality", pa.float32()), ("vector", _vec()),
        ("procedure_id", pa.string()), ("ingested_at", pa.float64())] + _common()),
    "procedures": pa.schema([
        ("procedure_id", pa.string()), ("app_key", pa.string()), ("app_version", pa.string()), ("goal", pa.string()), ("goal_norm", pa.string()),
        ("steps_json", pa.string()), ("sources", pa.list_(pa.string())), ("grounded_ratio", pa.float32()), ("n_runs", pa.int32()), ("n_ok", pa.int32()),
        ("last_run_ts", pa.float64()), ("trust", pa.string()), ("vector", _vec())] + _common()),
    "fast_paths": pa.schema([
        ("fast_id", pa.string()), ("app_key", pa.string()), ("app_version_min", pa.string()), ("app_version_max", pa.string()), ("kind", pa.string()),
        ("command_id", pa.string()), ("task_pattern", pa.string()), ("payload", pa.string()), ("params_schema_json", pa.string()), ("preconditions_json", pa.string()),
        ("context", pa.string()), ("source", pa.string()), ("trust", pa.string()), ("verified", pa.bool_()), ("n_ok", pa.int32()), ("n_fail", pa.int32()),
        ("consecutive_fail", pa.int32()), ("ok_runs", pa.list_(pa.string())), ("last_ok_ts", pa.float64()), ("safety", pa.string()), ("sandbox", pa.string()),
        ("vector", _vec())] + _common()),
    "error_playbooks": pa.schema([
        ("sig_id", pa.string()), ("app_key", pa.string()), ("toolkit", pa.string()), ("signature", pa.string()), ("failure_code", pa.string()),
        ("message_template", pa.string()), ("resolution_json", pa.string()), ("class_", pa.string()), ("needs_human", pa.bool_()), ("n_ok", pa.int32()),
        ("n_fail", pa.int32()), ("source", pa.string()), ("trust", pa.string()), ("vector", _vec())] + _common()),
    "ui_states": pa.schema([
        ("state_id", pa.string()), ("app_key", pa.string()), ("description", pa.string()), ("vector", _vec()), ("visual_vec", _vec()),
        ("screenshot_ref", pa.string())] + _common()),
}

# the text each table indexes lexically (SQLite FTS5, rag.textindex)
FTS_TEXT = {"knowledge_chunks": lambda r: f"{r.get('heading_path', '')} {r.get('text', '')}", "procedures": lambda r: r.get("goal", ""),
            "fast_paths": lambda r: f"{r.get('task_pattern', '')} {str(r.get('command_id', '')).split(':', 1)[-1]}", "error_playbooks": lambda r: f"{r.get('message_template', '')} {r.get('failure_code', '')}",
            "ui_states": lambda r: r.get("description", "")}

# the id column of each table (merge_insert key) and the text column its FTS index covers
KEYS = {"knowledge_chunks": "chunk_id", "procedures": "procedure_id", "fast_paths": "fast_id", "error_playbooks": "sig_id", "ui_states": "state_id"}
FTS = {"knowledge_chunks": "text", "procedures": "goal", "fast_paths": "task_pattern", "error_playbooks": "message_template", "ui_states": "description"}
