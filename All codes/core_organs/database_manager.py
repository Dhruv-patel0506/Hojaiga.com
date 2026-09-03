"""
Database Manager — SSMS Logger for UI Knowledge
Tracks layout fingerprints, popup history, and resolution pathways.

Tables:
  - ui_knowledge: Layout tree snapshots with hash fingerprints
  - ui_scanned: Individual control records with bounding boxes
  - popup_history: Cached popup resolutions for instant replay
"""

import hashlib
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import pyodbc

logger = logging.getLogger("hojaiga.database_manager")


class DatabaseManager:
    _SQL_CONN = (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=DHRUV_PATEL\\SQLEXPRESS;"
        "DATABASE=hojaiga_knowledge;"
        "UID=Hojaiga.com;"
        "PWD=DhPa@3396$;"
    )

    def __init__(self, conn_str: str = None):
        self.conn_str = conn_str or self._SQL_CONN
        self._lock = threading.Lock()
        self._conn = pyodbc.connect(self.conn_str, timeout=10, autocommit=True)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create tables if they don't exist."""
        with self._lock:
            c = self._conn.cursor()
            c.execute("""
                IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='popup_history')
                CREATE TABLE popup_history (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    popup_title NVARCHAR(500),
                    layout_hash NVARCHAR(64),
                    popup_type NVARCHAR(100),
                    target_x INT DEFAULT 0,
                    target_y INT DEFAULT 0,
                    resolution_action NVARCHAR(MAX),
                    parent_path NVARCHAR(1000),
                    occurrences INT DEFAULT 1,
                    last_seen DATETIME2 DEFAULT GETDATE(),
                    created_at DATETIME2 DEFAULT GETDATE()
                )
            """)
            c.execute("""
                IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='ui_scanned')
                CREATE TABLE ui_scanned (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    app_id NVARCHAR(255),
                    version NVARCHAR(50),
                    sig NVARCHAR(64),
                    info NVARCHAR(MAX),
                    last_scanned FLOAT
                )
            """)
            c.execute("""
                IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name='ui_knowledge')
                CREATE TABLE ui_knowledge (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    app_id NVARCHAR(255),
                    version NVARCHAR(50),
                    page_key NVARCHAR(255),
                    tree_hash NVARCHAR(64),
                    ui_tree NVARCHAR(MAX),
                    interactive_elements NVARCHAR(MAX),
                    last_scanned DATETIME2
                )
            """)

    @staticmethod
    def generate_layout_hash(control_tree_string: str) -> str:
        """Creates a unique MD5 fingerprint of the current UI element tree."""
        return hashlib.md5(control_tree_string.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_popup_fingerprint(title: str, button_names: List[str]) -> str:
        """Generate a fingerprint from popup title + visible buttons."""
        key = f"{title.lower().strip()}|{'|'.join(sorted(b.lower().strip() for b in button_names))}"
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def check_popup_history(self, window_title: str, layout_hash: str = None) -> Optional[Dict[str, Any]]:
        """Queries the database to see if we already know how to handle this popup.
        Returns {x, y, action, parent_path} or None if unknown."""
        with self._lock:
            c = self._conn.cursor()
            if layout_hash:
                c.execute(
                    "SELECT TOP 1 target_x, target_y, resolution_action, parent_path FROM popup_history "
                    "WHERE popup_title LIKE ? OR layout_hash = ? ORDER BY last_seen DESC",
                    (f"%{window_title}%", layout_hash),
                )
            else:
                c.execute(
                    "SELECT TOP 1 target_x, target_y, resolution_action, parent_path FROM popup_history "
                    "WHERE popup_title LIKE ? ORDER BY last_seen DESC",
                    (f"%{window_title}%",),
                )
            row = c.fetchone()
            if row:
                return {"x": row[0], "y": row[1], "action": row[2], "parent_path": row[3]}
            return None

    def log_new_pathway(self, layout_hash: str, element_name: str, x: int, y: int,
                        action_type: str, parent_path: str, popup_type: str = "") -> None:
        """Insert newly discovered pathway into the database."""
        with self._lock:
            c = self._conn.cursor()
            # Check if this exact pathway exists
            c.execute(
                "SELECT id, occurrences FROM popup_history WHERE layout_hash = ? AND resolution_action = ?",
                (layout_hash, action_type),
            )
            row = c.fetchone()
            if row:
                c.execute(
                    "UPDATE popup_history SET occurrences=?, last_seen=GETDATE() WHERE id=?",
                    (row[1] + 1, row[0]),
                )
            else:
                c.execute(
                    "INSERT INTO popup_history (popup_title, layout_hash, popup_type, target_x, target_y, "
                    "resolution_action, parent_path) VALUES (?,?,?,?,?,?,?)",
                    (element_name, layout_hash, popup_type, x, y, action_type, parent_path),
                )
            logger.info("[DB] Pathway cached: [%s -> %s]", parent_path, element_name)

    def update_popup_seen(self, popup_title: str) -> None:
        """Increment occurrence count and update last_seen for a known popup."""
        with self._lock:
            c = self._conn.cursor()
            c.execute(
                "UPDATE popup_history SET occurrences=occurrences+1, last_seen=GETDATE() WHERE popup_title LIKE ?",
                (f"%{popup_title}%",),
            )

    def get_all_cached_popups(self) -> List[Dict[str, Any]]:
        """Return all cached popup resolutions for analysis."""
        with self._lock:
            c = self._conn.cursor()
            c.execute(
                "SELECT popup_title, layout_hash, resolution_action, occurrences, last_seen "
                "FROM popup_history ORDER BY occurrences DESC"
            )
            results = []
            for row in c.fetchall():
                results.append({
                    "title": row[0],
                    "hash": row[1],
                    "action": row[2],
                    "occurrences": row[3],
                    "last_seen": row[4],
                })
            return results

    def get_layout_by_hash(self, app_id: str, version: str, tree_hash: str) -> Optional[Dict]:
        """Retrieve a stored layout by its hash."""
        with self._lock:
            c = self._conn.cursor()
            c.execute(
                "SELECT ui_tree, interactive_elements FROM ui_knowledge "
                "WHERE app_id=? AND version=? AND tree_hash=?",
                (app_id, version, tree_hash),
            )
            row = c.fetchone()
            if row:
                return {"ui_tree": row[0], "interactive_elements": row[1]}
            return None

    def store_layout(self, app_id: str, version: str, page_key: str,
                     tree_hash: str, ui_tree: str, interactive_elements: str) -> None:
        """Store a layout snapshot."""
        from datetime import datetime
        with self._lock:
            c = self._conn.cursor()
            c.execute(
                "SELECT id FROM ui_knowledge WHERE app_id=? AND version=? AND page_key=?",
                (app_id, version, page_key),
            )
            row = c.fetchone()
            now = datetime.now()
            if row:
                c.execute(
                    "UPDATE ui_knowledge SET tree_hash=?, ui_tree=?, interactive_elements=?, "
                    "last_scanned=? WHERE id=?",
                    (tree_hash, ui_tree, interactive_elements, now, row[0]),
                )
            else:
                c.execute(
                    "INSERT INTO ui_knowledge (app_id, version, page_key, tree_hash, ui_tree, "
                    "interactive_elements, last_scanned) VALUES (?,?,?,?,?,?,?)",
                    (app_id, version, page_key, tree_hash, ui_tree, interactive_elements, now),
                )

    def close(self):
        """Close the database connection."""
        try:
            self._conn.close()
        except Exception:
            pass
