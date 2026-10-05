"""
Session Cookie Management for Web Applications

Manages session cookies for web services like Gmail, etc.
Stores cookies after first login and reuses them for subsequent visits.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger("hojaiga.session_cookie_manager")


class SessionCookieManager:
    """
    Manages session cookies for web applications.
    
    Features:
    - Store cookies after login
    - Reuse cookies for subsequent visits
    - Validate cookie freshness
    - Detect expired cookies
    - Support multiple profiles
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = r"D:\new_automation\storage\session_cookies.sqlite"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
    
    def _init_db(self):
        """Initialize the cookie database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_name TEXT NOT NULL,
                    profile_name TEXT DEFAULT 'default',
                    cookies TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    UNIQUE(service_name, profile_name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cookie_usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            conn.commit()
        
        logger.info(f"[SessionCookieManager] Initialized database at {self.db_path}")
    
    def store_cookies(self, service_name: str, cookies: List[Dict[str, Any]], 
                     profile_name: str = "default", expires_in_hours: int = 24) -> int:
        """
        Store cookies for a service.
        
        Args:
            service_name: Name of the service (e.g., "gmail", "github")
            cookies: List of cookie dictionaries
            profile_name: Profile name (default "default")
            expires_in_hours: Hours until cookies expire
        
        Returns:
            Session ID
        """
        cookies_json = json.dumps(cookies)
        expires_at = datetime.now() + timedelta(hours=expires_in_hours)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Insert or replace
            cursor.execute("""
                INSERT OR REPLACE INTO sessions 
                (service_name, profile_name, cookies, expires_at, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (service_name, profile_name, cookies_json, expires_at.isoformat()))
            
            session_id = cursor.lastrowid
            conn.commit()
        
        logger.info(f"[SessionCookieManager] Stored {len(cookies)} cookies for {service_name} (profile: {profile_name})")
        return session_id

    def store_cookie(self, service_name: str, cookies: List[Dict[str, Any]],
                     profile_name: str = "default", expires_in_hours: int = 24) -> int:
        """Singular alias for store_cookies() — kept for callers using the old name."""
        return self.store_cookies(service_name, cookies, profile_name, expires_in_hours)
    
    def get_cookies(self, service_name: str, profile_name: str = "default") -> Optional[List[Dict[str, Any]]]:
        """
        Retrieve cookies for a service.
        
        Args:
            service_name: Name of the service
            profile_name: Profile name
        
        Returns:
            List of cookies or None if not found/expired
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, cookies, expires_at, is_active
                FROM sessions
                WHERE service_name = ? AND profile_name = ? AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            """, (service_name, profile_name))
            
            row = cursor.fetchone()
            
            if not row:
                logger.info(f"[SessionCookieManager] No active session found for {service_name}")
                return None
            
            session_id, cookies_json, expires_at_str, is_active = row
            
            # Check if expired
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                logger.info(f"[SessionCookieManager] Session expired for {service_name}")
                self._deactivate_session(session_id)
                return None
            
            # Log usage
            cursor.execute("""
                INSERT INTO cookie_usage_log (session_id, success)
                VALUES (?, 1)
            """, (session_id,))
            conn.commit()
            
            cookies = json.loads(cookies_json)
            logger.info(f"[SessionCookieManager] Retrieved {len(cookies)} cookies for {service_name}")
            
            return cookies
    
    def _deactivate_session(self, session_id: int):
        """Deactivate a session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE sessions SET is_active = 0 WHERE id = ?", (session_id,))
            conn.commit()
    
    def invalidate_cookies(self, service_name: str, profile_name: str = "default"):
        """Invalidate cookies for a service (e.g., after logout)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE sessions SET is_active = 0
                WHERE service_name = ? AND profile_name = ?
            """, (service_name, profile_name))
            conn.commit()
        
        logger.info(f"[SessionCookieManager] Invalidated cookies for {service_name}")
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT service_name, profile_name, created_at, expires_at
                FROM sessions
                WHERE is_active = 1
                ORDER BY created_at DESC
            """)
            
            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    "service_name": row[0],
                    "profile_name": row[1],
                    "created_at": row[2],
                    "expires_at": row[3]
                })
        
        return sessions
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE sessions SET is_active = 0
                WHERE expires_at < datetime('now')
            """)
            
            affected = cursor.rowcount
            conn.commit()
        
        if affected > 0:
            logger.info(f"[SessionCookieManager] Cleaned up {affected} expired sessions")


# Singleton instance
_cookie_manager = None


def get_cookie_manager() -> SessionCookieManager:
    """Get the singleton cookie manager instance."""
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = SessionCookieManager()
    return _cookie_manager


if __name__ == "__main__":
    # Test the cookie manager
    print("Testing Session Cookie Manager")
    print("=" * 60)
    
    manager = get_cookie_manager()
    
    # Test storing cookies
    test_cookies = [
        {"name": "SID", "value": "test_value_123", "domain": ".google.com"},
        {"name": "HSID", "value": "test_value_456", "domain": ".google.com"},
        {"name": "SSID", "value": "test_value_789", "domain": ".google.com"}
    ]
    
    session_id = manager.store_cookies("gmail", test_cookies, expires_in_hours=24)
    print(f"Stored session ID: {session_id}")
    
    # Test retrieving cookies
    retrieved = manager.get_cookies("gmail")
    print(f"Retrieved {len(retrieved) if retrieved else 0} cookies")
    
    # Test getting active sessions
    sessions = manager.get_active_sessions()
    print(f"Active sessions: {len(sessions)}")
    for session in sessions:
        print(f"  - {session['service_name']} ({session['profile_name']})")
    
    # Test cleanup
    manager.cleanup_expired_sessions()
    print("Cleanup completed")
