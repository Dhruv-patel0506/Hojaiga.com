"""
One-time migration: Polish-automation SQL Server (AutomationMemory) -> Hojaiga SQLite.

Polish stores TASK STRATEGIES + TASK FAILURES (error + how-it-was-handled history)
in SQL Server (DHRUV_PATEL\\SQLEXPRESS / AutomationMemory). Hojaiga's App Scanner
now persists its UI knowledge into the SAME unified SQLite DB, so the automation
can "scan a barcode" — i.e. look up prior strategy / error-fix knowledge for any
app, page, or error without re-querying the brain.

Target DB: D:\\new_automation\\storage\\hojaiga_knowledge.sqlite
(populated by core_organs/organ_30_app_scanner.py)

Run:  python migrate_polish_to_hojaiga.py
Optional: python migrate_polish_to_hojaiga.py --server DHRUV_PATEL\\SQLEXPRESS
"""
import argparse
import sqlite3
import sys
from pathlib import Path

TARGET_DB = Path(__file__).resolve().parent / "storage" / "hojaiga_knowledge.sqlite"

DEFAULT_CONN = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=DHRUV_PATEL\SQLEXPRESS;"
    "DATABASE=AutomationMemory;"
    "Trusted_Connection=yes;"
)


def init_sqlite(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS polish_task_types (
            task_name TEXT PRIMARY KEY,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS polish_task_strategies (
            id INTEGER PRIMARY KEY,
            task_name TEXT,
            version INTEGER,
            strategy_json TEXT,
            requirement_json TEXT,
            success_count INTEGER,
            fail_count INTEGER,
            avg_satisfaction REAL,
            is_active INTEGER,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS polish_task_runs (
            id INTEGER PRIMARY KEY,
            task_name TEXT,
            success_score INTEGER,
            fields_resolved INTEGER,
            fields_target INTEGER,
            duration_seconds REAL,
            run_strategy_json TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS polish_task_failures (
            id INTEGER PRIMARY KEY,
            task_name TEXT,
            input_query TEXT,
            failure_reason TEXT,
            fingerprint_json TEXT,
            strategy_version_attempted INTEGER,
            status TEXT,
            resolved_by_version INTEGER,
            resolved_at TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS polish_strategy_promotions (
            id INTEGER PRIMARY KEY,
            task_name TEXT,
            from_version INTEGER,
            to_version INTEGER,
            reason TEXT,
            created_at TEXT
        );
    """)
    conn.commit()


def migrate(conn: sqlite3.Connection, sql_conn) -> dict:
    cur = sql_conn.cursor()
    counts = {}

    # task_types
    cur.execute("SELECT task_name, description FROM task_types")
    rows = cur.fetchall()
    conn.executemany(
        "INSERT OR IGNORE INTO polish_task_types (task_name, description) VALUES (?, ?)",
        [(r.task_name, r.description) for r in rows])
    counts["task_types"] = len(rows)

    # task_strategies (join to get task_name)
    cur.execute("""
        SELECT s.id, t.task_name, s.version, s.strategy_json, s.requirement_json,
               s.success_count, s.fail_count, s.avg_satisfaction, s.is_active, s.created_at
        FROM task_strategies s JOIN task_types t ON t.id = s.task_type_id
    """)
    rows = cur.fetchall()
    conn.executemany(
        """INSERT OR IGNORE INTO polish_task_strategies
           (id, task_name, version, strategy_json, requirement_json, success_count,
            fail_count, avg_satisfaction, is_active, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [(r.id, r.task_name, r.version, r.strategy_json, r.requirement_json,
          r.success_count, r.fail_count, r.avg_satisfaction, r.is_active, str(r.created_at))
         for r in rows])
    counts["task_strategies"] = len(rows)

    # task_runs
    cur.execute("""
        SELECT r.id, t.task_name, r.success_score, r.fields_resolved, r.fields_target,
               r.duration_seconds, r.run_strategy_json, r.created_at
        FROM task_runs r JOIN task_types t ON t.id = r.task_type_id
    """)
    rows = cur.fetchall()
    conn.executemany(
        """INSERT OR IGNORE INTO polish_task_runs
           (id, task_name, success_score, fields_resolved, fields_target,
            duration_seconds, run_strategy_json, created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        [(r.id, r.task_name, r.success_score, r.fields_resolved, r.fields_target,
          r.duration_seconds, r.run_strategy_json, str(r.created_at)) for r in rows])
    counts["task_runs"] = len(rows)

    # task_failures (the valuable "error + how-it-was-handled" memory)
    cur.execute("""
        SELECT f.id, t.task_name, f.input_query, f.failure_reason, f.fingerprint_json,
               f.strategy_version_attempted, f.status, f.resolved_by_version, f.resolved_at, f.created_at
        FROM task_failures f JOIN task_types t ON t.id = f.task_type_id
    """)
    rows = cur.fetchall()
    conn.executemany(
        """INSERT OR IGNORE INTO polish_task_failures
           (id, task_name, input_query, failure_reason, fingerprint_json,
            strategy_version_attempted, status, resolved_by_version, resolved_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [(r.id, r.task_name, r.input_query, r.failure_reason, r.fingerprint_json,
          r.strategy_version_attempted, r.status, r.resolved_by_version,
          str(r.resolved_at) if r.resolved_at else None, str(r.created_at)) for r in rows])
    counts["task_failures"] = len(rows)

    # strategy_promotions
    cur.execute("""
        SELECT p.id, t.task_name, p.from_version, p.to_version, p.reason, p.created_at
        FROM strategy_promotions p JOIN task_types t ON t.id = p.task_type_id
    """)
    rows = cur.fetchall()
    conn.executemany(
        """INSERT OR IGNORE INTO polish_strategy_promotions
           (id, task_name, from_version, to_version, reason, created_at)
           VALUES (?,?,?,?,?,?)""",
        [(r.id, r.task_name, r.from_version, r.to_version, r.reason, str(r.created_at)) for r in rows])
    counts["strategy_promotions"] = len(rows)

    conn.commit()
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=None, help="Override SQL Server instance")
    args = ap.parse_args()

    TARGET_DB.parent.mkdir(parents=True, exist_ok=True)
    sqlite_conn = sqlite3.connect(str(TARGET_DB))
    init_sqlite(sqlite_conn)
    print(f"[migrate] Target SQLite ready: {TARGET_DB}")

    try:
        import pyodbc  # type: ignore
    except ImportError:
        print("[migrate] pyodbc not installed -> cannot read SQL Server.")
        print("[migrate] Install with: pip install pyodbc  (and 'ODBC Driver 17 for SQL Server').")
        print("[migrate] SQLite tables created (empty). Re-run this script once SQL Server is reachable.")
        return 0

    conn_str = DEFAULT_CONN
    if args.server:
        conn_str = conn_str.replace(r"SERVER=DHRUV_PATEL\SQLEXPRESS", f"SERVER={args.server}")

    try:
        sql_conn = pyodbc.connect(conn_str, timeout=10)
    except Exception as e:
        print(f"[migrate] Could not connect to SQL Server ({e}).")
        print("[migrate] SQLite tables created (empty). Re-run once SQL Server is running.")
        return 0

    try:
        counts = migrate(sqlite_conn, sql_conn)
    finally:
        sql_conn.close()

    print("[migrate] Done. Rows imported into Hojaiga SQLite:")
    for k, v in counts.items():
        print(f"   - {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
