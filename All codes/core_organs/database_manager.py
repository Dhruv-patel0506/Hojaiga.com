"""
Database Manager — SSMS Logger for UI Knowledge
Tracks layout fingerprints, popup history, and resolution pathways.

Tables:
  - ui_scanned: Individual control records (app_id, version, sig, info, last_scanned)
  - ui_knowledge: Layout tree snapshots with hash fingerprints
  - popup_history: Cached popup resolutions for instant replay
"""

import hashlib
import json
import logging
import pyodbc
import os
import time
from typing import Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("hojaiga.database_manager")

DB_DRIVER = os.environ.get("HOJAIGA_DB_DRIVER", "{ODBC Driver 17 for SQL Server}")
DB_SERVER = os.environ.get("HOJAIGA_DB_SERVER", "DHRUV_PATEL\\SQLEXPRESS")
DB_NAME = os.environ.get("HOJAIGA_DB_NAME", "hojaiga_knowledge")
DB_USER = os.environ.get("HOJAIGA_DB_USER", "Hojaiga.com")
DB_PWD = os.environ.get("HOJAIGA_DB_PWD", "DhPa@3396$")

DB_CONN = (
    f"DRIVER={DB_DRIVER};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};PWD={DB_PWD}"
)

# Fixed-width SQL Server columns on the UIA scanning write path. Values longer
# than the column make pyodbc raise 'String or binary data would be truncated',
# which aborts the whole write — every value is clipped before it reaches SQL.
PROFILE_NAME_MAX = 400           # element_profiles.element_name (migrated from 200)
PROFILE_APP_MAX = 200
PROFILE_TYPE_MAX = 50
PROFILE_CONTROL_TYPE_MAX = 100
PROFILE_LOCATION_MAX = 100


def _clip_text(value, limit):
    """Clip a value to a fixed NVARCHAR column width (None passes through)."""
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[:limit]


def _clip_element_name(name, limit=PROFILE_NAME_MAX):
    """Deterministically truncate an element name to the column width.

    UIA names can exceed NVARCHAR limits. Instead of letting SQL Server raise a
    truncation error (or blindly slicing, which would merge distinct long names
    into one profile row), keep the informative prefix and append a digest of
    the FULL name. The same name always clips to the same key across scans.
    """
    text = (name or "").strip()
    if len(text) <= limit:
        return text
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return text[: max(limit - 9, 0)] + "~" + digest


class DatabaseManager:
    def __init__(self):
        self._conn = None
        # Effective element_name column width; refreshed by ensure_visual_memory_tables()
        self._element_name_max = PROFILE_NAME_MAX

    def _connect(self):
        if self._conn is None:
            self._conn = pyodbc.connect(DB_CONN)
        return self._conn

    def _safe_call(self, func, *args, **kwargs):
        """Execute a DB call with automatic reconnect on failure."""
        try:
            conn = self._connect()
            print(f"[DB] Connected OK", flush=True)
            result = func(conn, *args, **kwargs)
            print(f"[DB] Call OK", flush=True)
            return result
        except Exception as e:
            print(f"[DB] Call failed: {e}", flush=True)
            self._conn = None
            try:
                conn = self._connect()
                result = func(conn, *args, **kwargs)
                print(f"[DB] Reconnect OK", flush=True)
                return result
            except Exception as e2:
                print(f"[DB] Reconnect failed: {e2}", flush=True)
                return None

    def generate_layout_hash(self, title):
        return hashlib.md5(title.encode("utf-8")).hexdigest()

    def generate_popup_fingerprint(self, title, buttons):
        key = f"{title}|{'|'.join(sorted(buttons))}"
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def check_popup_history(self, title):
        def _query(conn):
            cursor = conn.cursor()
            # Search by title in the info JSON column
            cursor.execute(
                "SELECT TOP 1 info FROM ui_scanned WHERE info LIKE ? ORDER BY last_scanned DESC",
                (f'%"{title}"%',),
            )
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    data = json.loads(row[0])
                    return {"x": data.get("x", 0), "y": data.get("y", 0),
                            "action": data.get("detected_type", "click"),
                            "parent_path": data.get("parent_path", "")}
                except Exception:
                    return None
            return None
        return self._safe_call(_query)

    def log_new_pathway(self, layout_hash, element_name, x, y, action_type, parent_path=""):
        def _insert(conn):
            cursor = conn.cursor()
            info_json = json.dumps({
                "title": element_name,
                "detected_type": action_type,
                "x": x,
                "y": y,
                "parent_path": parent_path,
            })
            # Use unique sig to avoid constraint violation
            import hashlib as _hashlib
            unique_sig = _hashlib.md5(f"{element_name}_{time.time()}".encode()).hexdigest()[:16]
            cursor.execute(
                "INSERT INTO ui_scanned (app_id, version, sig, info, last_scanned) VALUES (?, ?, ?, ?, ?)",
                ("Gatekeeper", "live", unique_sig, info_json, time.time()),
            )
            conn.commit()
        return self._safe_call(_insert)

    def get_all_cached_popups(self):
        def _query(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT TOP 100 sig, info, last_scanned FROM ui_scanned ORDER BY last_scanned DESC")
            return [{"sig": r[0], "info": json.loads(r[1]) if r[1] else {}, "last_scanned": r[2]} for r in cursor.fetchall()]
        return self._safe_call(_query) or []

    # session_cookies vault — separate table, site -> cookies_json
    def ensure_session_table(self):
        def _ddl(conn):
            cur = conn.cursor()
            cur.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='session_cookies' AND xtype='U')
                CREATE TABLE session_cookies (
                    site NVARCHAR(255) PRIMARY KEY,
                    cookies_json NVARCHAR(MAX),
                    last_updated DATETIME DEFAULT GETDATE()
                )
            """)
            conn.commit()
        return self._safe_call(_ddl)

    def get_session_cookies(self, site: str):
        self.ensure_session_table()
        def _q(conn):
            cur = conn.cursor()
            cur.execute("SELECT cookies_json FROM session_cookies WHERE site=?", (site.lower(),))
            row = cur.fetchone()
            return json.loads(row[0]) if row and row[0] else None
        return self._safe_call(_q)

    def store_session_cookies(self, site: str, cookies: list):
        self.ensure_session_table()
        def _ins(conn):
            cur = conn.cursor()
            cur.execute("SELECT site FROM session_cookies WHERE site=?", (site.lower(),))
            if cur.fetchone():
                cur.execute("UPDATE session_cookies SET cookies_json=?, last_updated=GETDATE() WHERE site=?", (json.dumps(cookies), site.lower()))
            else:
                cur.execute("INSERT INTO session_cookies (site, cookies_json, last_updated) VALUES (?, ?, GETDATE())", (site.lower(), json.dumps(cookies)))
            conn.commit()
        return self._safe_call(_ins)

    # ── Modal / popup resolutions vault ─────────────────────────────────
    def ensure_modal_resolutions_table(self):
        def _ddl(conn):
            cur = conn.cursor()
            cur.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='modal_resolutions' AND xtype='U')
                CREATE TABLE modal_resolutions (
                    resolution_key NVARCHAR(255) PRIMARY KEY,
                    resolution NVARCHAR(100),
                    last_updated DATETIME DEFAULT GETDATE()
                )
            """)
            conn.commit()
        return self._safe_call(_ddl)

    def get_modal_resolution(self, key: str):
        self.ensure_modal_resolutions_table()
        def _q(conn):
            cur = conn.cursor()
            cur.execute("SELECT resolution FROM modal_resolutions WHERE resolution_key=?", (key.lower(),))
            row = cur.fetchone()
            return row[0] if row and row[0] else None
        return self._safe_call(_q)

    def store_modal_resolution(self, key: str, value: Any):
        self.ensure_modal_resolutions_table()
        def _ins(conn):
            cur = conn.cursor()
            cur.execute("SELECT resolution_key FROM modal_resolutions WHERE resolution_key=?", (key.lower(),))
            if cur.fetchone():
                cur.execute("UPDATE modal_resolutions SET resolution=?, last_updated=GETDATE() WHERE resolution_key=?", (str(value), key.lower()))
            else:
                cur.execute("INSERT INTO modal_resolutions (resolution_key, resolution, last_updated) VALUES (?, ?, GETDATE())", (key.lower(), str(value)))
            conn.commit()
        return self._safe_call(_ins)

    # ── App UI element knowledge ────────────────────────────────────────
    def ensure_app_ui_table(self):
        def _ddl(conn):
            cur = conn.cursor()
            cur.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='app_ui_elements' AND xtype='U')
                CREATE TABLE app_ui_elements (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    app_name NVARCHAR(100),
                    ribbon_tab NVARCHAR(100),
                    group_name NVARCHAR(100),
                    element_name NVARCHAR(200),
                    element_type NVARCHAR(50),
                    x INT, y INT, width INT, height INT,
                    description NVARCHAR(MAX),
                    last_scanned DATETIME DEFAULT GETDATE()
                )
            """)
            conn.commit()
        return self._safe_call(_ddl)

    # ── Visual UI Memory tables ──────────────────────────────────────────
    def ensure_visual_memory_tables(self):
        """Create the 4 tables for the Visual UI Memory system."""
        def _ddl(conn):
            cur = conn.cursor()
            # 1. Visual snapshots — one per deep scan encounter
            cur.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='visual_snapshots' AND xtype='U')
                CREATE TABLE visual_snapshots (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    app_name NVARCHAR(200) NOT NULL,
                    window_title NVARCHAR(500),
                    scan_number INT DEFAULT 1,
                    screenshot_path NVARCHAR(1000),
                    ui_state_hash NVARCHAR(64),
                    element_count INT DEFAULT 0,
                    scan_mode NVARCHAR(50) DEFAULT 'first_contact',
                    vlm_description NVARCHAR(MAX),
                    elements_json NVARCHAR(MAX),
                    created_at DATETIME DEFAULT GETDATE()
                )
            """)
            # 2. Element profiles — one per unique element, updated across scans
            cur.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='element_profiles' AND xtype='U')
                CREATE TABLE element_profiles (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    app_name NVARCHAR(200) NOT NULL,
                    element_name NVARCHAR(400) NOT NULL,
                    element_type NVARCHAR(50),
                    control_type NVARCHAR(100),
                    visual_description NVARCHAR(MAX),
                    typical_region_x INT,
                    typical_region_y INT,
                    typical_region_w INT,
                    typical_region_h INT,
                    tab_location NVARCHAR(100),
                    group_location NVARCHAR(100),
                    spatial_context NVARCHAR(MAX),
                    times_scanned INT DEFAULT 1,
                    times_found INT DEFAULT 0,
                    times_activated INT DEFAULT 0,
                    last_scanned DATETIME DEFAULT GETDATE(),
                    confidence_score FLOAT DEFAULT 0.0,
                    is_confirmed BIT DEFAULT 0
                )
            """)
            # 3. Training gate — tracks readiness per app
            cur.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='visual_training_gate' AND xtype='U')
                CREATE TABLE visual_training_gate (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    app_name NVARCHAR(200) NOT NULL UNIQUE,
                    total_scans INT DEFAULT 0,
                    successful_scans INT DEFAULT 0,
                    elements_confirmed INT DEFAULT 0,
                    elements_total INT DEFAULT 0,
                    gate_status NVARCHAR(20) DEFAULT 'learning',
                    min_scans_required INT DEFAULT 5,
                    min_confidence FLOAT DEFAULT 0.75,
                    last_scan_at DATETIME DEFAULT GETDATE(),
                    gate_opened_at DATETIME
                )
            """)
            # 4. Visual signatures — for fast drift detection
            cur.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='visual_signatures' AND xtype='U')
                CREATE TABLE visual_signatures (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    app_name NVARCHAR(200) NOT NULL,
                    signature_hash NVARCHAR(64) NOT NULL,
                    element_fingerprint NVARCHAR(MAX),
                    layout_hash NVARCHAR(64),
                    snapshot_id INT,
                    created_at DATETIME DEFAULT GETDATE()
                )
            """)
            # Widen element_profiles.element_name for databases created before the
            # 400-char schema (200 -> 400). If ALTER is not permitted we fall back
            # to clipping by the width the column actually has.
            width = PROFILE_NAME_MAX
            try:
                cur.execute(
                    "SELECT CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_NAME = 'element_profiles' AND COLUMN_NAME = 'element_name'"
                )
                row = cur.fetchone()
                width = int(row[0]) if row and row[0] else PROFILE_NAME_MAX
                if width < PROFILE_NAME_MAX:
                    cur.execute(
                        f"ALTER TABLE element_profiles ALTER COLUMN element_name NVARCHAR({PROFILE_NAME_MAX}) NOT NULL"
                    )
                    width = PROFILE_NAME_MAX
            except Exception as widen_err:
                logger.warning(
                    "element_profiles.element_name widen skipped (%s); clipping names to %d chars",
                    widen_err, width,
                )
            self._element_name_max = max(int(width or PROFILE_NAME_MAX), 64)
            conn.commit()
        return self._safe_call(_ddl)

    def log_visual_snapshot(self, app_name, window_title, scan_number, screenshot_path,
                            ui_state_hash, element_count, scan_mode, vlm_description, elements_json):
        """Store a visual snapshot from a deep scan."""
        app_name = _clip_text(app_name, PROFILE_APP_MAX) or "unknown"
        window_title = _clip_text(window_title, 500)
        screenshot_path = _clip_text(screenshot_path, 1000)
        scan_mode = _clip_text(scan_mode, 50)
        ui_state_hash = _clip_text(ui_state_hash, 64)

        def _ins(conn):
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO visual_snapshots
                (app_name, window_title, scan_number, screenshot_path, ui_state_hash,
                 element_count, scan_mode, vlm_description, elements_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (app_name, window_title, scan_number, screenshot_path, ui_state_hash,
                  element_count, scan_mode, vlm_description, elements_json))
            conn.commit()
            return cur.rowcount
        return self._safe_call(_ins)

    def upsert_element_profile(self, app_name, element_name, element_type, control_type,
                                visual_description, region_x, region_y, region_w, region_h,
                                tab_location, group_location, spatial_context=None):
        """Create or update an element profile across multiple scans."""
        app_name = _clip_text(app_name, PROFILE_APP_MAX) or "unknown"
        element_name = _clip_element_name(
            element_name or "", getattr(self, "_element_name_max", PROFILE_NAME_MAX)
        )
        element_type = _clip_text(element_type or "", PROFILE_TYPE_MAX)
        control_type = _clip_text(control_type or "", PROFILE_CONTROL_TYPE_MAX)
        tab_location = _clip_text(tab_location or "", PROFILE_LOCATION_MAX)
        group_location = _clip_text(group_location or "", PROFILE_LOCATION_MAX)

        def _upsert(conn):
            cur = conn.cursor()
            cur.execute("""
                SELECT id, times_scanned, times_found FROM element_profiles
                WHERE app_name = ? AND element_name = ?
            """, (app_name, element_name))
            row = cur.fetchone()
            if row:
                cur.execute("""
                    UPDATE element_profiles SET
                        element_type = ?, control_type = ?, visual_description = ?,
                        typical_region_x = ?, typical_region_y = ?,
                        typical_region_w = ?, typical_region_h = ?,
                        tab_location = ?, group_location = ?, spatial_context = ?,
                        times_scanned = times_scanned + 1,
                        last_scanned = GETDATE()
                    WHERE id = ?
                """, (element_type, control_type, visual_description,
                      region_x, region_y, region_w, region_h,
                      tab_location, group_location, spatial_context, row[0]))
            else:
                cur.execute("""
                    INSERT INTO element_profiles
                    (app_name, element_name, element_type, control_type, visual_description,
                     typical_region_x, typical_region_y, typical_region_w, typical_region_h,
                     tab_location, group_location, spatial_context, times_scanned, last_scanned)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, GETDATE())
                """, (app_name, element_name, element_type, control_type, visual_description,
                      region_x, region_y, region_w, region_h,
                      tab_location, group_location, spatial_context))
            conn.commit()
        return self._safe_call(_upsert)

    def upsert_element_profiles_batch(self, app_name, elements):
        """Batch upsert element profiles — the UIA scanning hot path.

        The per-element upsert costs a SELECT + INSERT/UPDATE + commit per
        element (144 elements -> ~432 round trips and ~288 log lines per scan).
        This version reads existing rows in ONE query, then writes with two
        executemany calls and a single commit, keeping a whole deep scan
        inside ~4 round trips.

        `elements` is a list of dicts with keys: element_name, element_type,
        control_type, visual_description, region_x, region_y, region_w,
        region_h, tab_location, group_location, spatial_context.
        Returns the number of profiles written (0 on DB failure).
        """
        if not elements:
            return 0
        name_max = getattr(self, "_element_name_max", PROFILE_NAME_MAX)

        def _batch(conn):
            cur = conn.cursor()
            app = _clip_text(app_name, PROFILE_APP_MAX) or "unknown"

            # Keyed by clipped name: duplicates within one scan collapse (last wins).
            rows = {}
            for el in elements:
                name = _clip_element_name(el.get("element_name") or "", name_max)
                if not name:
                    continue
                rows[name] = (
                    app, name,
                    _clip_text(el.get("element_type") or "", PROFILE_TYPE_MAX),
                    _clip_text(el.get("control_type") or "", PROFILE_CONTROL_TYPE_MAX),
                    el.get("visual_description") or "",
                    int(el.get("region_x") or 0), int(el.get("region_y") or 0),
                    int(el.get("region_w") or 0), int(el.get("region_h") or 0),
                    _clip_text(el.get("tab_location") or "", PROFILE_LOCATION_MAX),
                    _clip_text(el.get("group_location") or "", PROFILE_LOCATION_MAX),
                    el.get("spatial_context"),
                )
            if not rows:
                return 0

            cur.execute(
                "SELECT id, element_name FROM element_profiles WHERE app_name = ?",
                (app,),
            )
            existing = {r[1]: r[0] for r in cur.fetchall()}

            inserts, updates = [], []
            for name, row in rows.items():
                if name in existing:
                    updates.append(row[2:] + (existing[name],))
                else:
                    inserts.append(row)

            try:
                cur.fast_executemany = True
            except Exception:
                pass
            if inserts:
                cur.executemany("""
                    INSERT INTO element_profiles
                    (app_name, element_name, element_type, control_type, visual_description,
                     typical_region_x, typical_region_y, typical_region_w, typical_region_h,
                     tab_location, group_location, spatial_context, times_scanned, last_scanned)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, GETDATE())
                """, inserts)
            if updates:
                cur.executemany("""
                    UPDATE element_profiles SET
                        element_type = ?, control_type = ?, visual_description = ?,
                        typical_region_x = ?, typical_region_y = ?,
                        typical_region_w = ?, typical_region_h = ?,
                        tab_location = ?, group_location = ?, spatial_context = ?,
                        times_scanned = times_scanned + 1,
                        last_scanned = GETDATE()
                    WHERE id = ?
                """, updates)
            conn.commit()
            logger.debug("Batch element upsert for '%s': %d inserted, %d updated",
                         app, len(inserts), len(updates))
            return len(inserts) + len(updates)

        return self._safe_call(_batch) or 0

    def confirm_element_found(self, app_name, element_name):
        """Record that an element was successfully found and optionally activated."""
        def _upd(conn):
            cur = conn.cursor()
            cur.execute("""
                UPDATE element_profiles SET times_found = times_found + 1 WHERE app_name = ? AND element_name = ?
            """, (app_name, element_name))
            # Update confidence: ratio of times_found / times_scanned
            cur.execute("""
                UPDATE element_profiles SET confidence_score = CAST(times_found AS FLOAT) / NULLIF(times_scanned, 0)
                WHERE app_name = ? AND element_name = ? AND times_scanned > 0
            """, (app_name, element_name))
            conn.commit()
        return self._safe_call(_upd)

    def get_training_gate(self, app_name):
        """Get training gate status for an app."""
        def _q(conn):
            cur = conn.cursor()
            cur.execute("SELECT * FROM visual_training_gate WHERE app_name = ?", (app_name,))
            row = cur.fetchone()
            if row:
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
            return None
        return self._safe_call(_q)

    def update_training_gate(self, app_name, scan_success=True, elements_found=0, elements_total=0):
        """Update the training gate after a scan. Returns gate_status."""
        app_name = _clip_text(app_name, PROFILE_APP_MAX) or "unknown"

        def _upd(conn):
            cur = conn.cursor()
            # Upsert gate record
            cur.execute("SELECT id FROM visual_training_gate WHERE app_name = ?", (app_name,))
            row = cur.fetchone()
            if not row:
                cur.execute("""
                    INSERT INTO visual_training_gate (app_name, total_scans, successful_scans, elements_confirmed, elements_total, last_scan_at)
                    VALUES (?, 1, ?, ?, ?, GETDATE())
                """, (app_name, 1 if scan_success else 0, elements_found, elements_total))
            else:
                cur.execute("""
                    UPDATE visual_training_gate SET
                        total_scans = total_scans + 1,
                        successful_scans = successful_scans + ?,
                        elements_confirmed = elements_confirmed + ?,
                        elements_total = elements_total + ?,
                        last_scan_at = GETDATE()
                    WHERE app_name = ?
                """, (1 if scan_success else 0, elements_found, elements_total, app_name))

            # Check gate thresholds
            cur.execute("SELECT total_scans, successful_scans, min_scans_required, min_confidence FROM visual_training_gate WHERE app_name = ?", (app_name,))
            gate = cur.fetchone()
            if gate:
                total, success, min_scans, min_conf = gate
                success_rate = success / max(total, 1)
                if total >= min_scans and success_rate >= min_conf:
                    cur.execute("""
                        UPDATE visual_training_gate SET gate_status = 'ready', gate_opened_at = GETDATE()
                        WHERE app_name = ? AND gate_status != 'ready'
                    """, (app_name,))
                    conn.commit()
                    return 'ready'
            conn.commit()
            return 'learning'
        return self._safe_call(_upd)

    def get_element_profiles(self, app_name, confirmed_only=False):
        """Get all element profiles for an app."""
        def _q(conn):
            cur = conn.cursor()
            if confirmed_only:
                cur.execute("""
                    SELECT element_name, element_type, control_type, visual_description,
                           typical_region_x, typical_region_y, typical_region_w, typical_region_h,
                           tab_location, group_location, spatial_context,
                           times_scanned, times_found, confidence_score
                    FROM element_profiles WHERE app_name = ? AND confidence_score >= 0.75
                    ORDER BY confidence_score DESC
                """, (app_name,))
            else:
                cur.execute("""
                    SELECT element_name, element_type, control_type, visual_description,
                           typical_region_x, typical_region_y, typical_region_w, typical_region_h,
                           tab_location, group_location, spatial_context,
                           times_scanned, times_found, confidence_score
                    FROM element_profiles WHERE app_name = ?
                    ORDER BY confidence_score DESC
                """, (app_name,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        return self._safe_call(_q) or []

    def get_visual_snapshot_count(self, app_name):
        """How many times has this app been scanned."""
        def _q(conn):
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM visual_snapshots WHERE app_name = ?", (app_name,))
            return cur.fetchone()[0]
        return self._safe_call(_q) or 0

    def lookup_ui_element(self, element_name: str, app: str = "Microsoft Word"):
        self.ensure_app_ui_table()
        def _q(conn):
            cur = conn.cursor()
            cur.execute("""
                SELECT TOP 1 element_name, ribbon_tab, group_name, x, y, width, height, element_type
                FROM app_ui_elements
                WHERE app_name = ? AND element_name LIKE ?
                ORDER BY CASE WHEN element_name = ? THEN 0 ELSE 1 END
            """, (app, f"%{element_name}%", element_name))
            row = cur.fetchone()
            if row:
                return {"name": row[0], "tab": row[1], "group": row[2],
                        "x": row[3], "y": row[4], "width": row[5], "height": row[6],
                        "type": row[7]}
            return None
        return self._safe_call(_q)

    def get_app_ui_elements(self, app: str = "Microsoft Word"):
        self.ensure_app_ui_table()
        def _q(conn):
            cur = conn.cursor()
            cur.execute("""
                SELECT element_name, ribbon_tab, group_name, x, y, width, height, element_type
                FROM app_ui_elements WHERE app_name = ?
                ORDER BY ribbon_tab, group_name
            """, (app,))
            return [{"name": r[0], "tab": r[1], "group": r[2], "x": r[3], "y": r[4],
                     "width": r[5], "height": r[6], "type": r[7]} for r in cur.fetchall()]
        return self._safe_call(_q) or []
