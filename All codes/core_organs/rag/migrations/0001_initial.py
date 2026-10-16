"""0001: the five LanceDB tables (+ their FTS / scalar indexes) and the SQLite schemas of lexicon, graph, cache and telemetry."""
from __future__ import annotations

from .. import schemas as S

LEXICON = """
CREATE TABLE IF NOT EXISTS aliases(app_key TEXT, surface_norm TEXT, command_id TEXT, kind TEXT, source TEXT, trust TEXT, n_seen INTEGER DEFAULT 1,
    PRIMARY KEY(app_key, surface_norm, command_id));
CREATE INDEX IF NOT EXISTS ix_alias_cmd ON aliases(app_key, command_id);
CREATE TABLE IF NOT EXISTS commands(command_id TEXT PRIMARY KEY, app_key TEXT, label TEXT, archetype TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_cmd_app ON commands(app_key);
CREATE TABLE IF NOT EXISTS apps(app_key TEXT PRIMARY KEY, tier INTEGER DEFAULT -1, archetype TEXT DEFAULT '', version TEXT DEFAULT '', toolkit TEXT DEFAULT '');
"""

GRAPH = """
CREATE TABLE IF NOT EXISTS nodes(state_id TEXT PRIMARY KEY, app_key TEXT, app_version TEXT DEFAULT '', window_kind TEXT, modal_stack_json TEXT, landmarks_json TEXT,
    variants_json TEXT DEFAULT '[]', exact_sig TEXT, tier INTEGER DEFAULT 0, visits INTEGER DEFAULT 1, first_seen REAL, last_seen REAL, screenshot_ref TEXT DEFAULT '',
    description TEXT DEFAULT '', schema_v INTEGER DEFAULT 1, extra_json TEXT DEFAULT '{}');
CREATE INDEX IF NOT EXISTS ix_nodes_app ON nodes(app_key, window_kind);
CREATE INDEX IF NOT EXISTS ix_nodes_sig ON nodes(app_key, exact_sig);
CREATE TABLE IF NOT EXISTS edges(edge_id INTEGER PRIMARY KEY AUTOINCREMENT, app_key TEXT, src TEXT, dst TEXT, command_id TEXT, action_type TEXT, route TEXT, args_json TEXT DEFAULT '{}',
    n_ok INTEGER DEFAULT 0, n_fail INTEGER DEFAULT 0, n_noeffect INTEGER DEFAULT 0, ewma_latency_ms REAL DEFAULT 0, last_ok_ts REAL DEFAULT 0, last_seen_ts REAL DEFAULT 0,
    source TEXT DEFAULT 'observed', trust TEXT DEFAULT 'seed', safety TEXT DEFAULT 'allow', dst_hist_json TEXT DEFAULT '{}', schema_v INTEGER DEFAULT 1, extra_json TEXT DEFAULT '{}',
    UNIQUE(app_key, src, command_id, route, dst));
CREATE INDEX IF NOT EXISTS ix_edges_src ON edges(app_key, src);
CREATE INDEX IF NOT EXISTS ix_edges_cmd ON edges(app_key, command_id);
CREATE TABLE IF NOT EXISTS observations(obs_id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, run_id TEXT, app_key TEXT, src TEXT, command_id TEXT, route TEXT, args_json TEXT,
    expected_dst TEXT, observed_dst TEXT, ok INTEGER, effect TEXT, latency_ms REAL, verify_note TEXT, source TEXT);
CREATE INDEX IF NOT EXISTS ix_obs_app ON observations(app_key, obs_id);
CREATE TABLE IF NOT EXISTS aliases(state_id TEXT PRIMARY KEY, canonical_id TEXT);
CREATE TABLE IF NOT EXISTS sigs(app_key TEXT, sig TEXT, state_id TEXT, PRIMARY KEY(app_key, sig));
CREATE INDEX IF NOT EXISTS ix_sigs_state ON sigs(state_id);
CREATE TABLE IF NOT EXISTS landmark_df(app_key TEXT, landmark TEXT, df INTEGER DEFAULT 0, PRIMARY KEY(app_key, landmark));
"""

CACHE = """
CREATE TABLE IF NOT EXISTS router_cache(k TEXT PRIMARY KEY, v TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS rewrite_cache(k TEXT PRIMARY KEY, v TEXT, ts REAL);
"""

LEARN = """
CREATE TABLE IF NOT EXISTS fast_stats(fast_id TEXT PRIMARY KEY, n_ok INTEGER DEFAULT 0, n_fail INTEGER DEFAULT 0, consecutive_fail INTEGER DEFAULT 0, ok_runs_json TEXT DEFAULT '[]',
    last_ok_ts REAL DEFAULT 0, trust_override TEXT DEFAULT '', verified INTEGER DEFAULT -1);
CREATE TABLE IF NOT EXISTS proc_stats(procedure_id TEXT PRIMARY KEY, n_runs INTEGER DEFAULT 0, n_ok INTEGER DEFAULT 0, last_run_ts REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS playbook_stats(sig_id TEXT PRIMARY KEY, n_ok INTEGER DEFAULT 0, n_fail INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS fts_dirty(tbl TEXT, id TEXT, PRIMARY KEY(tbl, id));
"""

TELEMETRY = """
CREATE TABLE IF NOT EXISTS router_calls(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, app_key TEXT, intent TEXT, tier INTEGER, ms_total REAL, ms_by_probe_json TEXT,
    n_plans INTEGER, best_p REAL, grounded_ratio REAL, llm_used INTEGER, degraded TEXT);
CREATE TABLE IF NOT EXISTS outcomes(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, run_id TEXT, app_key TEXT, command_id TEXT, route TEXT, ok INTEGER, effect TEXT, failure_code TEXT);
"""


def up(st) -> None:
    import pyarrow as pa
    have = set(st.table_names())
    for name, sch in S.SCHEMAS.items():
        if name not in have:
            st.lance.create_table(name, schema=sch)
    st.sql("lexicon").script(LEXICON)
    st.sql("graph").script(GRAPH)
    st.sql("cache").script(CACHE)
    st.sql("telemetry").script(TELEMETRY)
    st.sql("learn").script(LEARN)
    for name in ("lexicon", "graph", "cache", "telemetry", "learn"):
        st.sql(name).commit()
