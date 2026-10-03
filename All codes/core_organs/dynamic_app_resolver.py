"""
DynamicAppResolver — Universal Host Application & Document Launcher for Hojaiga OS.

Eliminates hardcoded app dictionaries by leveraging:
1. Direct file association (opening .xlsx, .csv, .pdf, .txt, etc. with registered system viewers)
2. Organ 40's AppCatalog (Start Menu shortcuts, winget packages, installed apps)
3. Windows Registry (App Paths key)
4. System PATH resolution (shutil.which)
5. Windows Shell fallback (cmd.exe /c start "" "<target>")
"""

from __future__ import annotations

import os
import glob
import shutil
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("dynamic_app_resolver")


class DynamicAppResolver:
    @staticmethod
    def resolve_launch_command(
        target_str: str = "",
        parameters: Optional[dict] = None,
        workspace_dir: str = r"D:\new_automation"
    ) -> Tuple[List[str], str]:
        """
        Dynamically determine the exact Windows command to launch any app, file, or document.
        Returns: (command_list, resolved_description)
        """
        params = parameters or {}

        # Guard: sanitize target_str — reject empty, backslash-only, or garbage inputs
        if target_str:
            cleaned = target_str.strip().strip('"').strip("'")
            if not cleaned or cleaned.replace("\\", "").replace("/", "").strip() == "":
                target_str = "excel"
            else:
                target_str = cleaned

        explicit_cmd = params.get("command")
        if explicit_cmd:
            if isinstance(explicit_cmd, list):
                return explicit_cmd, "explicit_command"
            return ["cmd.exe", "/c", str(explicit_cmd)], "explicit_command_string"

        # 1. Check if a specific file path is requested
        file_candidate = params.get("file_path") or params.get("file") or params.get("output_file")
        if not file_candidate and target_str:
            cleaned_target = target_str.strip().strip('"').strip("'")
            if os.path.exists(cleaned_target) or cleaned_target.endswith((".xlsx", ".csv", ".docx", ".pdf", ".txt")):
                file_candidate = cleaned_target

        if file_candidate:
            # Check direct or relative in workspace
            abs_path = os.path.abspath(file_candidate)
            if not os.path.exists(abs_path) and os.path.exists(os.path.join(workspace_dir, file_candidate)):
                abs_path = os.path.abspath(os.path.join(workspace_dir, file_candidate))
            
            if os.path.exists(abs_path):
                logger.info("DynamicAppResolver: Launching document by association (minimized): %s", abs_path)
                return ["cmd.exe", "/c", "start", "/min", "", abs_path], f"document:{abs_path}"
            elif file_candidate.endswith((".xlsx", ".csv")):
                # Fall back to most recent .xlsx spreadsheet (never .csv — triggers Windows dialog)
                recent_files = sorted(
                    glob.glob(os.path.join(workspace_dir, "*.xlsx")),
                    key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
                    reverse=True
                )
                if recent_files:
                    latest = os.path.abspath(recent_files[0])
                    return ["cmd.exe", "/c", "start", "/min", "", latest], f"recent_excel:{latest}"
        # 2. Check if an Excel spreadsheet is requested without explicit path
        search_context = f"{target_str} {params.get('app_name', '')}".lower()
        if any(w in search_context for w in ["excel", "sheet", "spreadsheet", ".xlsx", ".csv"]):
            recent_files = sorted(
                glob.glob(os.path.join(workspace_dir, "*.xlsx")),
                key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
                reverse=True
            )
            if recent_files:
                latest = os.path.abspath(recent_files[0])
                logger.info("DynamicAppResolver: Auto-opening most recent spreadsheet (minimized): %s", latest)
                return ["cmd.exe", "/c", "start", "/min", "", latest], f"recent_excel:{latest}"
            return ["cmd.exe", "/c", "start", "excel"], "excel_app"

        # 3. Extract pure app name from target_str or parameters
        app_name = params.get("app_name") or params.get("target") or ""
        if not app_name and target_str:
            # Clean common words like 'launch', 'open', 'start'
            app_name = target_str
            for prefix in ["launch", "open", "start", "run", "app", "desktop"]:
                app_name = re_sub_word(prefix, "", app_name)
            app_name = app_name.strip().strip('"').strip("'")

        if not app_name:
            app_name = "notepad"

        if app_name.lower() in ["calculator", "calc"]:
            app_name = "calc"

        # 4. Search Organ 40's AppCatalog (Start Menu, Program Files, Winget)
        try:
            from core_organs.organ_40_app_launcher import AppCatalog
            catalog = AppCatalog()
            display_name, launcher_path = catalog.find(app_name)
            if launcher_path and os.path.exists(launcher_path):
                logger.info("DynamicAppResolver: AppCatalog match: '%s' -> %s", display_name, launcher_path)
                return ["cmd.exe", "/c", "start", "", launcher_path], f"catalog:{display_name}"
        except Exception as e:
            logger.debug("AppCatalog search error: %s", e)

        # 5. Search system PATH via shutil.which
        which_path = shutil.which(app_name) or shutil.which(f"{app_name}.exe")
        if which_path:
            logger.info("DynamicAppResolver: System PATH match: %s", which_path)
            return ["cmd.exe", "/c", "start", "", which_path], f"path:{app_name}"

        # 6. Search Windows Registry (App Paths)
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app_name}.exe") as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        if val and os.path.exists(val):
                            logger.info("DynamicAppResolver: Windows Registry App Paths match: %s", val)
                            return ["cmd.exe", "/c", "start", "", val], f"registry:{app_name}"
                except Exception:
                    pass
        except Exception:
            pass

        # 7. Default Windows Shell Execution — guard against empty/garbage app_name
        if not app_name or len(app_name) < 2 or app_name.replace("\\", "").replace("/", "").strip() == "":
            app_name = "excel"
        logger.info("DynamicAppResolver: Defaulting to Windows shell association: '%s'", app_name)
        return ["cmd.exe", "/c", "start", "", app_name], f"shell:{app_name}"


def re_sub_word(word: str, repl: str, text: str) -> str:
    import re
    return re.sub(rf"\b{re.escape(word)}\b", repl, text, flags=re.IGNORECASE)
