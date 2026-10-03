"""
AppKnowledgeManager — Cross-Run Learning Engine for Hojaiga OS.

Bridges the gap between Organ 30 (App Scanner / Vision Discovery) and
Organ 01 (Brain Reasoning) + Organ 10 (Agents).

Capabilities:
1. Discovers and catalogs learned apps/domains from var/hojaiga/app_knowledge/
2. Provides fuzzy search & exact lookup for target apps or websites
3. Formats learned knowledge into contextual prompt injections for the LLM
4. Records action successes/failures to incrementally improve reliability across runs
"""

from __future__ import annotations

import os
import re
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("organ_knowledge_manager")


class AppKnowledgeManager:
    """Manages persistent cross-run knowledge about desktop applications and websites."""

    _instance: Optional["AppKnowledgeManager"] = None

    @classmethod
    def get_instance(cls) -> "AppKnowledgeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, storage_dirs: Optional[List[str]] = None) -> None:
        self.storage_dirs: List[Path] = []
        if storage_dirs:
            self.storage_dirs = [Path(d) for d in storage_dirs]
        else:
            # Default search paths across workspace
            base_dir = Path(os.path.dirname(__file__)).parent
            candidates = [
                base_dir / "var" / "hojaiga" / "app_knowledge",
                Path(r"D:\new_automation\All codes\var\hojaiga\app_knowledge"),
                Path(r"D:\new_automation\var\hojaiga\app_knowledge"),
            ]
            for c in candidates:
                if c.exists() or str(c) not in [str(p) for p in self.storage_dirs]:
                    self.storage_dirs.append(c)

        # Ensure primary storage directory exists
        self.primary_dir = self.storage_dirs[0] if self.storage_dirs else Path(r"D:\new_automation\var\hojaiga\app_knowledge")
        try:
            self.primary_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.debug("Failed to create primary storage dir: %s", e)

        self._cache: Dict[str, Dict[str, Any]] = {}
        self.reload_cache()

    def reload_cache(self) -> int:
        """Scan all storage directories and load knowledge files into memory."""
        count = 0
        for sdir in self.storage_dirs:
            if not sdir.exists():
                continue
            for fpath in sdir.glob("*.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    app_name = data.get("app_name") or fpath.stem
                    safe_key = self._normalize_key(app_name)
                    data["_filepath"] = str(fpath)
                    self._cache[safe_key] = data
                    count += 1
                except Exception as e:
                    logger.debug("Error loading knowledge file %s: %s", fpath, e)
        logger.info("AppKnowledgeManager: Loaded %d learned profiles from disk", count)
        return count

    @staticmethod
    def _normalize_key(text: str) -> str:
        """Normalize app name or domain to a clean search key."""
        clean = re.sub(r"[^a-zA-Z0-9]", "_", text.lower()).strip("_")
        return clean

    def get_knowledge(self, app_or_domain: str) -> Optional[Dict[str, Any]]:
        """Exact or direct lookup for an app or website domain."""
        if not app_or_domain:
            return None
        key = self._normalize_key(app_or_domain)
        if key in self._cache:
            return self._cache[key]

        # Check partial match in keys
        for k, v in self._cache.items():
            if k in key or key in k:
                return v

        return None

    def search_knowledge_for_context(self, context_text: str) -> List[Dict[str, Any]]:
        """Search cached knowledge for any apps, domains, or controls mentioned in context_text."""
        if not context_text:
            return []
        text_lower = context_text.lower()
        matches = []
        for k, data in self._cache.items():
            app_name = (data.get("app_name") or "").lower()
            if app_name and app_name in text_lower:
                matches.append(data)
                continue
            # Check individual tokens
            tokens = [t for t in k.split("_") if len(t) > 3]
            if any(t in text_lower for t in tokens):
                matches.append(data)
        return matches

    def save_knowledge(self, app_name: str, scan_data: Dict[str, Any]) -> str:
        """Store or update discovered app knowledge."""
        safe_key = self._normalize_key(app_name)
        filepath = self.primary_dir / f"{safe_key}.json"
        scan_data["app_name"] = app_name
        scan_data["last_updated"] = time.time()
        
        # Ensure directory
        self.primary_dir.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(scan_data, f, indent=2, default=str)

        scan_data["_filepath"] = str(filepath)
        self._cache[safe_key] = scan_data
        logger.info("AppKnowledgeManager: Saved knowledge for '%s' -> %s", app_name, filepath)
        return str(filepath)

    def record_action_success(self, app_name: str, action: str, target: str) -> None:
        """Record a successful interaction with a specific element or app."""
        k = self.get_knowledge(app_name)
        if not k:
            return
        stats = k.setdefault("action_stats", {})
        key = f"{action}:{target}".strip(":")
        entry = stats.setdefault(key, {"success_count": 0, "fail_count": 0})
        entry["success_count"] += 1
        entry["last_success"] = time.time()
        self._persist_cached_profile(k)

    def record_action_failure(self, app_name: str, action: str, target: str, error: str) -> None:
        """Record a failure trap so future planning avoids repeated errors."""
        k = self.get_knowledge(app_name)
        if not k:
            return
        stats = k.setdefault("action_stats", {})
        key = f"{action}:{target}".strip(":")
        entry = stats.setdefault(key, {"success_count": 0, "fail_count": 0, "last_errors": []})
        entry["fail_count"] += 1
        entry["last_fail"] = time.time()
        if "last_errors" not in entry:
            entry["last_errors"] = []
        entry["last_errors"] = (entry["last_errors"] + [str(error)[:100]])[-3:]
        self._persist_cached_profile(k)

    def _persist_cached_profile(self, profile: Dict[str, Any]) -> None:
        fpath = profile.get("_filepath")
        if fpath:
            try:
                # Make clean copy without internal keys
                to_save = {k: v for k, v in profile.items() if not k.startswith("_")}
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(to_save, f, indent=2, default=str)
            except Exception as e:
                logger.debug("Failed to persist updated profile: %s", e)

    def format_knowledge_for_prompt(self, context_text: str) -> str:
        """
        Generate a concise, high-value prompt injection for the Brain/LLM
        describing UI elements, proven actions, and known blockers.
        """
        matches = self.search_knowledge_for_context(context_text)
        if not matches:
            return ""

        lines = ["\n--- LEARNED APPLICATION & UI KNOWLEDGE (FROM PAST RUNS) ---"]
        for data in matches[:3]:  # Top 3 relevant apps
            app = data.get("app_name", "Unknown")
            app_type = data.get("app_type", "desktop")
            first_action = data.get("suggested_first_action", "")
            notes = data.get("automation_notes", "")
            elements = data.get("ui_elements", [])
            blockers = data.get("blocking_elements", [])

            lines.append(f"Target: {app} ({app_type})")
            if first_action:
                lines.append(f"- Recommended first action: {first_action}")
            if notes:
                lines.append(f"- Automation tip: {notes}")
            if blockers and blockers != ["none"]:
                lines.append(f"- Warning (Known blockers/popups): {', '.join(blockers)}")

            # List key interactable elements
            interactive = [e.get("name") for e in elements if e.get("interactable", True) and e.get("name")]
            if interactive:
                lines.append(f"- Known UI controls: {', '.join(interactive[:10])}")

            # Include high-confidence actions
            stats = data.get("action_stats", {})
            proven = [k for k, s in stats.items() if s.get("success_count", 0) > s.get("fail_count", 0)]
            if proven:
                lines.append(f"- Proven reliable actions: {', '.join(proven[:5])}")

        lines.append("--- END OF LEARNED KNOWLEDGE ---\n")
        return "\n".join(lines)
