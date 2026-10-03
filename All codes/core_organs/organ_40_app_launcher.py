"""Organ 40 — App Launcher & Aliasing (the "which app?" brain for the host).

How app searching/launching works (per system design):

  1. HOST CATALOG (one-time / on-demand scan)
     We scan the Windows file explorer / Start Menu / winget to learn which
     apps are actually installed on this host (e.g. "OBS Studio"). This is the
     knowledge the rest of the system needs so it does not have to be told the
     app name on every task.

  2. ALIASING BY FUNCTIONALITY (verbs -> app)
     A task rarely names the app ("record the session for 30 seconds"). We map
     the task's *functionality* (verbs like record/screenshot/browse) to an
     installed app via the catalog. If nothing matches, we fall back to Chrome
     ("other use chrome"). The small LLM (HOJAIGA_SMALL_MODEL) helps when a
     keyword is not in the dictionary.

  3. LAUNCH — primary: WINDOWS SEARCH BAR
     Open the search bar, type the FULL app name, pick the top suggestion and
     open it. This matches how a human would launch OBS.

  4. LAUNCH — fallback: FILE-EXPLORER CRAWL
     Only if (a) the catalog said the app exists but (b) the search bar could
     not grasp it: crawl the file explorer to locate the actual app launcher
     (.exe — not the uninstaller/wizard) and start it directly.

This organ is intentionally non-destructive for read operations; actual
launches are explicit and guarded.
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("organ_40")

KNOWLEDGE_DB = Path(r"D:\new_automation\storage\hojaiga_knowledge.sqlite")

# Verb / keyword -> desired app (display name as it appears in Windows search).
# The value is the *desired* app; resolution checks it against the host catalog.
# Supports both exact phrase and word-level matching.
# Enhanced with more comprehensive verb mapping for better task understanding.
_ALIASES = {
    # Recording & Media
    "obs studio": ["record", "recording", "record the session", "capture screen",
                   "screen record", "screenrecord", "stream", "streaming", "cast",
                   "capture", "obs", "video capture", "filming", "live stream",
                   "broadcast", "screen capture", "video recording"],
    
    # Browsing & Web + Web Email (Gmail etc. always route through Chrome).
    # NOTE: keep ALL "google chrome" verbs inside this single entry — a second
    # "google chrome" key further down silently overwrites this list in the dict.
    "google chrome": ["browse", "browser", "website", "web ", "search the internet",
                      "open site", "open website", "go to", "url", "http",
                      "chrome", "google", "internet", "online", "web page",
                      "search", "web search", "open browser", "navigate to",
                      "visit website", "load webpage", "open link",
                      "gmail", "gmail account", "open gmail", "gmail web",
                      "check gmail", "gmail inbox", "gmail spam", "delete gmail",
                      "remove spam", "gmail emails", "webmail", "web mail",
                      "mail.google.com", "google mail"],
    
    # Text Editing
    "notepad": ["note", "notes", "text file", "write text", "document", "txt",
                "notepad", "memo", "write a note", "jot down", "scratchpad",
                "write down", "open notepad", "text editor", "edit text",
                "create document", "write file", "edit file"],
    
    # Screenshots
    "snipping tool": ["screenshot", "snip", "capture image", "screen shot",
                      "take a picture of screen", "capture screen region",
                      "snippingtool", "screen clip", "grab screen", "take screenshot",
                      "screen capture", "capture window"],
    
    # Math & Calculation
    "calculator": ["calculate", "calc", "math", "sum", "compute", "arithmetic",
                   "do math", "add numbers", "subtract", "multiply", "divide",
                   "equation", "solve", "total", "addition", "subtraction",
                   "mathematics", "number", "calculator", "calculate the",
                   "percentage", "square root", "power"],
    
    # Drawing & Image Editing
    "paint": ["draw", "paint", "edit image", "image editor", "mspaint",
              "drawing", "sketch", "color", "brush", "create image",
              "edit photo", "crop image", "resize image"],
    
    # File Management
    "file explorer": ["open folder", "show files", "file explorer", "my files",
                      "browse files", "file manager", "explorer", "folder",
                      "open file", "file manager", "navigate files",
                      "open directory", "browse directory"],
    
    # Email & Communication
    "mail": ["email", "send mail", "outlook", "mail", "compose email",
             "write email", "send message", "check email", "open email",
             "email client", "inbox", "send message", "read email"],
    
    # (Web Email verbs are merged into the single "google chrome" entry above.
    #  The former duplicate "google chrome" key here silently erased the
    #  browsing verbs from the alias tables — do not reintroduce it.)

    # Spreadsheets
    "excel": ["spreadsheet", "excel", "csv export", "table data", "xlsx",
              "workbook", "data table", "pivot", "chart", "spreadsheet application",
              "open spreadsheet", "edit spreadsheet", "data analysis"],
    
    # Word Processing
    "word": ["word document", "docx", "letter", "write a letter", "document",
             "word processor", "write document", "microsoft word", "text document",
             "open word", "edit document", "create document"],
    
    # Media Playback
    "windows media player": ["play video", "play music", "media player",
                             "watch video", "video player", "music player",
                             "audio player", "play audio", "play media"],
    
    # System Monitoring
    "task manager": ["task manager", "processes", "performance", "system monitor",
                     "cpu usage", "memory usage", "monitor performance",
                     "check processes", "kill process", "system resources"],
    
    # System Settings
    "settings": ["settings", "preferences", "configuration", "system settings",
                 "control panel", "options", "system configuration",
                 "open settings", "change settings"],
    
    # Development Tools
    "visual studio code": ["code", "vscode", "editor", "ide", "code editor",
                          "open code", "edit code", "programming", "development"],
    
    # Terminal
    "terminal": ["terminal", "command prompt", "cmd", "powershell", "shell",
                 "command line", "open terminal", "run command"],
    
    # Social Media
    "discord": ["discord", "chat", "voice chat", "gaming chat", "open discord"],
    "slack": ["slack", "team chat", "work chat", "open slack"],
    
    # Productivity
    "onenote": ["onenote", "notes", "note taking", "organize notes", "open onenote"],
    "teams": ["teams", "microsoft teams", "video call", "meeting", "teams meeting"],
}

# Word-level index: individual words -> apps (for fuzzy matching)
# Generic launch/transport verbs are EXCLUDED: they mean "bring an app up",
# not a functionality, so leaving them in makes "open blender" fuzzy-match some
# known app via the bare word "open" and skips the dynamic app-NAME crawl tier.
_ACTION_NOISE_WORDS = {
    "open", "close", "launch", "start", "stop", "run", "switch", "bring",
    "fire", "boot", "load", "go", "goto", "please", "now", "show", "hide",
}
_WORD_INDEX = {}
for _app, _verbs in _ALIASES.items():
    for _v in _verbs:
        for _word in _v.lower().split():
            if len(_word) > 2 and _word not in _ACTION_NOISE_WORDS:  # Skip tiny/noise words
                if _word not in _WORD_INDEX:
                    _WORD_INDEX[_word] = set()
                _WORD_INDEX[_word].add(_app)

# Reverse index: verb/keyword (lowercased) -> desired app name.
VERB_TO_APP = {}
for _app, _verbs in _ALIASES.items():
    for _v in _verbs:
        VERB_TO_APP[_v.strip()] = _app


def _phrase_in_text(phrase: str, text: str) -> bool:
    """Whole-word/phrase containment test with letter/digit boundaries.

    "mail" matches "open mail" but NOT "gmail" -- substring matching is the
    bug class that previously forced app-specific special cases into resolve().
    """
    p = (phrase or "").strip()
    if not p:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", text) is not None

DEFAULT_APP = "google chrome"  # per design: "other use chrome"

# Verbs that signal the user is naming a SPECIFIC app to bring up ("open
# blender", "launch vlc"). Used only for the dynamic app-NAME detection tier --
# when no alias/verb matched a known app, but the task clearly points at an app
# by name, we search / crawl for that literal name. Generic verbs, not app names.
_LAUNCH_HINTS = ("open", "launch", "start", "run", "bring up", "switch to",
                 "fire up", "boot up", "load")
_LAUNCH_HINT_WORDS = set()
for _h in _LAUNCH_HINTS:
    _LAUNCH_HINT_WORDS.update(_h.split())
# Non-app noise stripped when we try to recover a literal app name from a task.
_NAME_FILLER_WORDS = {
    "the", "a", "an", "app", "apps", "application", "applications", "for",
    "me", "my", "pc", "computer", "desktop", "laptop", "please", "now",
    "on", "to", "and", "of", "in", "up", "it", "this", "that", "some",
    "program", "software", "installed",
}


class AppCatalog:
    """Learns which apps are installed on the host and stores them in SQLite."""

    def __init__(self, db: Path = KNOWLEDGE_DB):
        self.db = db
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db) as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS app_catalog (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       name TEXT UNIQUE,
                       launcher_path TEXT,
                       source TEXT,
                       last_seen TEXT,
                       version TEXT,
                       ui_hash TEXT
                   )"""
            )
            # Add version/ui_hash columns if missing (migration)
            try:
                c.execute("SELECT version FROM app_catalog LIMIT 1")
            except Exception:
                c.execute("ALTER TABLE app_catalog ADD COLUMN version TEXT")
            try:
                c.execute("SELECT ui_hash FROM app_catalog LIMIT 1")
            except Exception:
                c.execute("ALTER TABLE app_catalog ADD COLUMN ui_hash TEXT")
            c.commit()

    # ── scanning ──────────────────────────────────────────────────────────
    def scan_host(self) -> list[str]:
        """Scan Start Menu shortcuts + winget and cache the installed-app list."""
        rows: list[tuple[str, str, str]] = []
        for root in self._shortcut_roots():
            rows.extend(self._iter_shortcuts(root))
        rows.extend(self._winget_list())
        # Deduplicate by (normalized) name, keeping any launcher path found.
        seen: dict[str, tuple[str, str, str]] = {}
        for name, path, source in rows:
            key = name.lower().strip()
            if not key:
                continue
            if key not in seen or (not seen[key][1] and path):
                seen[key] = (name.strip(), path, source)
        with sqlite3.connect(self.db) as c:
            c.execute("DELETE FROM app_catalog")
            for name, path, source in seen.values():
                c.execute(
                    "INSERT OR REPLACE INTO app_catalog(name, launcher_path, source, last_seen) "
                    "VALUES (?,?,?, datetime('now'))",
                    (name, path, source),
                )
            c.commit()
        logger.info("AppCatalog: scanned host, cached %d installed apps", len(seen))
        return sorted(v[0] for v in seen.values())

    def _shortcut_roots(self) -> list[str]:
        return [
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        ]

    def _iter_shortcuts(self, root: str) -> list[tuple[str, str, str]]:
        if not os.path.isdir(root):
            return []
        out: list[tuple[str, str, str]] = []
        for dirpath, _, files in os.walk(root):
            for f in files:
                if not f.lower().endswith(".lnk"):
                    continue
                full = os.path.join(dirpath, f)
                target = self._resolve_lnk(full)
                out.append((os.path.splitext(f)[0], target or full, "start_menu"))
        return out

    @staticmethod
    def _resolve_lnk(path: str) -> str | None:
        try:
            from win32com.client import Dispatch
            return Dispatch("WScript.Shell").CreateShortCut(path).TargetPath
        except Exception:
            return None

    def _winget_list(self) -> list[tuple[str, str, str]]:
        try:
            out = subprocess.run(["winget", "list"], capture_output=True,
                                 text=True, timeout=40)
        except Exception:
            return []
        rows: list[tuple[str, str, str]] = []
        for line in out.stdout.splitlines()[2:]:
            m = re.match(r"^([^\s].*?)\s{2,}", line)
            if m:
                rows.append((m.group(1).strip(), "", "winget"))
        return rows

    # ── lookup ────────────────────────────────────────────────────────────
    def ensure_scanned(self) -> None:
        """Scan the host once if the catalog is empty (lazy first use)."""
        try:
            with sqlite3.connect(self.db) as c:
                n = c.execute("SELECT COUNT(*) FROM app_catalog").fetchone()[0]
        except Exception:
            n = 0
        if n == 0:
            logger.info("AppCatalog: empty, performing first host scan...")
            self.scan_host()

    def find(self, name: str, fuzzy: bool = True):
        """Return (display_name, launcher_path) or (None, None)."""
        name_l = (name or "").lower().strip()
        with sqlite3.connect(self.db) as c:
            items = c.execute("SELECT name, launcher_path FROM app_catalog").fetchall()
        for n, p in items:
            if n.lower() == name_l:
                return n, p
        if fuzzy:
            for n, p in items:
                nl = n.lower()
                if name_l in nl or nl in name_l:
                    return n, p
        return None, None

    def get_version(self, app_name: str) -> str | None:
        """Get stored version for an app."""
        with sqlite3.connect(self.db) as c:
            row = c.execute("SELECT version FROM app_catalog WHERE name=?", (app_name,)).fetchone()
            return row[0] if row and row[0] else None

    def set_version(self, app_name: str, version: str) -> None:
        """Store version for an app."""
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE app_catalog SET version=? WHERE name=?", (version, app_name))
            c.commit()

    def get_ui_hash(self, app_name: str) -> str | None:
        """Get stored UI layout hash for an app."""
        with sqlite3.connect(self.db) as c:
            row = c.execute("SELECT ui_hash FROM app_catalog WHERE name=?", (app_name,)).fetchone()
            return row[0] if row and row[0] else None

    def set_ui_hash(self, app_name: str, ui_hash: str) -> None:
        """Store UI layout hash for an app."""
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE app_catalog SET ui_hash=? WHERE name=?", (ui_hash, app_name))
            c.commit()

    def check_version_changed(self, app_name: str, current_version: str) -> bool:
        """Check if app version changed since last scan. Returns True if changed."""
        stored = self.get_version(app_name)
        if stored is None:
            # First time seeing this app — store version
            self.set_version(app_name, current_version)
            return False
        if stored != current_version:
            logger.info("AppCatalog: version changed for '%s': %s -> %s", app_name, stored, current_version)
            self.set_version(app_name, current_version)
            return True
        return False

    def check_ui_changed(self, app_name: str, current_hash: str) -> bool:
        """Check if UI layout hash changed. Returns True if changed."""
        stored = self.get_ui_hash(app_name)
        if stored is None:
            self.set_ui_hash(app_name, current_hash)
            return False
        if stored != current_hash:
            logger.info("AppCatalog: UI layout changed for '%s'", app_name)
            self.set_ui_hash(app_name, current_hash)
            return True
        return False

    def crawl_for_exe(self, app_name: str) -> str | None:
        """Fallback: crawl the file explorer for the app's real launcher (.exe)."""
        keywords = re.findall(r"[a-z0-9]+", app_name.lower())
        roots = [
            r"C:\Program Files", r"C:\Program Files (x86)",
            r"C:\ProgramData", os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
            os.path.expandvars(r"%APPDATA%"),
        ]
        for root in roots:
            if not os.path.isdir(root):
                continue
            for dirpath, _, files in os.walk(root):
                depth = dirpath[len(root):].count(os.sep)
                if depth > 4:
                    continue
                for f in files:
                    fl = f.lower()
                    if not fl.endswith(".exe"):
                        continue
                    if any(k in fl for k in keywords):
                        # Exclude uninstallers / setup / wizard helpers.
                        if any(x in fl for x in ("uninst", "setup", "helper",
                                                  "crashpad", "update", "installer",
                                                  "wizard")):
                            continue
                        return os.path.join(dirpath, f)
        return None


class VerbAliasEngine:
    """Maps a task's functionality to an installed app via aliasing."""

    def __init__(self, catalog: AppCatalog, gateway=None):
        self.catalog = catalog
        self.gateway = gateway

    def _semantic_match(self, task_text: str) -> Optional[str]:
        """Perform semantic matching using partial phrases and synonyms."""
        t = task_text.lower().strip()
        
        # Common semantic mappings
        semantic_map = {
            "video": ["record", "stream", "play", "watch", "media"],
            "text": ["write", "edit", "document", "note", "file"],
            "image": ["screenshot", "capture", "picture", "photo", "draw"],
            "math": ["calculate", "compute", "number", "calc"],
            "web": ["browse", "internet", "site", "url", "link"],
            "email": ["mail", "message", "compose", "send"],
            "file": ["folder", "directory", "browse", "explore"],
            "code": ["programming", "develop", "script", "edit code"],
        }
        
        # Check for semantic category matches
        for category, related in semantic_map.items():
            if category in t:
                # Check which app has the most related verbs
                app_counts = {}
                for verb in related:
                    if verb in t:
                        for app, verbs in _ALIASES.items():
                            if verb in verbs:
                                app_counts[app] = app_counts.get(app, 0) + 1
                
                if app_counts:
                    best_app = max(app_counts, key=app_counts.get)
                    return best_app
        
        return None

    def resolve(self, task_text: str) -> str:
        """Return the desired app NAME for a task (not yet validated as installed)."""
        return self.resolve_detailed(task_text)[0]

    def resolve_detailed(self, task_text: str):
        """Return (desired_app_name, source) where source is one of
        'alias' / 'word' / 'semantic' / 'llm' / 'default'.

        'default' means NOTHING concrete matched (so the caller may still try the
        dynamic app-NAME tier). Crucially a web cue like 'gmail' matches Tier 1
        -> ('google chrome', 'alias'), which lets the planner tell a genuine web
        task apart from an unknown desktop app that merely lacks an alias."""
        t = (task_text or "").lower().strip()

        # Tier 1: Exact phrase match (fastest)
        for verb, app in VERB_TO_APP.items():
            if _phrase_in_text(verb, t):
                logger.info("VerbAlias: exact phrase match: '%s' -> '%s'", t, app)
                return app, "alias"

        # Tier 2: Word-level match -- score apps by how many matching words
        words = set(w for w in re.findall(r'[a-z]+', t) if len(w) > 2)
        app_scores: dict[str, int] = {}
        for word in words:
            if word in _WORD_INDEX:
                for app in _WORD_INDEX[word]:
                    app_scores[app] = app_scores.get(app, 0) + 1

        if app_scores:
            best_app = max(app_scores, key=app_scores.get)
            best_score = app_scores[best_app]
            if best_score >= 1:
                logger.info("VerbAlias: word-level match: '%s' -> '%s' (score=%d)", t, best_app, best_score)
                return best_app, "word"

        # Tier 3: Semantic similarity - match partial phrases and synonyms
        semantic_match = self._semantic_match(t)
        if semantic_match:
            logger.info("VerbAlias: semantic match: '%s' -> '%s'", t, semantic_match)
            return semantic_match, "semantic"

        # Tier 4: Small-LLM intent detection for phrases not in the dictionary.
        if self.gateway:
            try:
                known = ", ".join(sorted(set(_ALIASES.keys()))) + ", chrome"
                prompt = (
                    f'Task: "{task_text}"\n'
                    f"Which installed-style app best fits this task?\n"
                    f"Choose from: {known}.\n"
                    f'Reply with ONLY the app name, or "chrome" if none fits. No explanation.'
                )
                resp = self.gateway.execute_small_inference(
                    "You map task verbs to the right desktop app.", prompt,
                    temperature=0.0, timeout=30.0,
                )
                app = (resp or "").strip().strip('"').lower()
                if app and app != "chrome" and app in _ALIASES:
                    return app, "llm"
            except Exception as exc:
                logger.warning("alias LLM failed: %s", exc)

        return DEFAULT_APP, "default"

    def detect_named_app(self, task_text: str) -> Optional[str]:
        """Dynamic app-NAME tier: if the task contains a launch hint
        ('open'/'launch'/...) but NO alias matched, recover the literal app name
        the user pointed at (e.g. 'open blender' -> 'blender'). Strips launch
        hints + filler words; returns None when no launch hint is present (so
        genuine web tasks like 'browse ...' never trigger a name crawl)."""
        raw = (task_text or "").lower()
        # Need at least one launch-hint phrase present.
        if not any(_phrase_in_text(h, raw) for h in _LAUNCH_HINTS):
            return None
        cleaned = re.sub(r"[^a-z0-9 ]", " ", raw)
        tokens = [w for w in cleaned.split()
                  if w not in _LAUNCH_HINT_WORDS and w not in _NAME_FILLER_WORDS
                  and len(w) > 1]
        if not tokens:
            return None
        name = " ".join(tokens)
        logger.info("VerbAlias: dynamic app-name tier: %r -> '%s'", task_text, name)
        return name

    def resolve_installed(self, task_text: str):
        """Return (display_name_or_None, launcher_path_or_None, used_default: bool)."""
        desired = self.resolve(task_text)
        logger.info("VerbAlias: task %r -> desired app '%s'", task_text, desired)
        if desired == DEFAULT_APP:
            return None, None, True
        name, path = self.catalog.find(desired)
        if name:
            logger.info("VerbAlias: matched installed app '%s' (launcher=%s)", name, path)
            return name, path, False
        # Desired app not present on this host -> fall back to Chrome.
        logger.info("VerbAlias: desired app '%s' not in host catalog -> default (Chrome)", desired)
        return None, None, True


class AppLauncher:
    """Launches an app, primarily via the Windows search bar."""

    def __init__(self, catalog: AppCatalog):
        self.catalog = catalog
        # Get current user for Chrome profile
        import getpass
        self.username = getpass.getuser()
        self.chrome_user_data = os.path.expandvars(rf"%LOCALAPPDATA%\Google\Chrome\User Data")

    # Chrome/Edge/Chromium automation must launch DIRECTLY against a dedicated
    # isolated profile so Chrome NEVER shows the "Who's using Chrome?" profile
    # picker. The Windows search bar is forbidden for browsers because it opens
    # the user's REAL multi-profile Chrome with none of these flags.
    _BROWSER_TOKENS = ("chrome", "msedge", "chromium", "edge", "firefox", "browser")
    _CDP_PORTS = (9222, 9223, 9224)

    def _automation_profile_dir(self) -> str:
        return os.path.join(os.environ.get("TEMP", os.getcwd()), "chrome_automation_9222")

    def _looks_like_browser(self, app_name: str) -> bool:
        name = (app_name or "").lower()
        if any(tok in name for tok in self._BROWSER_TOKENS):
            return True
        try:
            _, path = self.catalog.find(app_name)
            if path and any(tok in os.path.basename(path).lower()
                            for tok in ("chrome", "msedge", "chromium", "firefox")):
                return True
        except Exception:
            pass
        return False

    def _automation_cdp_alive(self) -> Optional[int]:
        """Return the CDP port of an already-running automation Chrome, else None."""
        import urllib.request
        for port in self._CDP_PORTS:
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/json/version", timeout=1) as resp:
                    if resp.status == 200:
                        return port
            except Exception:
                continue
        return None

    def _spawn_isolated_chrome(self, exe_path: str) -> bool:
        """Deterministic, picker-free Chrome launch on an isolated single profile."""
        iso_dir = self._automation_profile_dir()
        try:
            os.makedirs(iso_dir, exist_ok=True)
        except Exception:
            pass
        cmd = [
            exe_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={iso_dir}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            "about:blank",
        ]
        logger.info("Launch: Chrome direct on isolated automation profile '%s' (no picker)", iso_dir)
        subprocess.Popen(cmd)
        time.sleep(1.5)
        return True

    def launch_browser_direct(self, app_name: str) -> bool:
        """Launch a browser the way automation needs it: reuse the single running
        CDP Chrome if present, otherwise start a dedicated isolated-profile Chrome
        with an explicit --profile-directory (never the profile picker, never the
        Windows search bar)."""
        alive = self._automation_cdp_alive()
        if alive:
            logger.info("Launch: browser '%s' reusing running automation Chrome on CDP port %d (direct, no picker)", app_name, alive)
            return True
        # Prefer the shared launcher helper (waits for the CDP port to open).
        try:
            import chrome_launcher
            if chrome_launcher.launch_safe_chrome(port=9222):
                logger.info("Launch: browser '%s' direct-launched via chrome_launcher (no picker)", app_name)
                return True
        except Exception as exc:
            logger.debug("Launch: chrome_launcher unavailable (%s); inline isolated launch", exc)
        # Inline fallback: resolve the browser exe and launch it deterministically.
        exe_path = None
        try:
            _, exe_path = self.catalog.find(app_name)
        except Exception:
            exe_path = None
        if not exe_path:
            exe_path = self.catalog.crawl_for_exe(app_name)
        if exe_path and exe_path.lower().endswith(".lnk"):
            exe_path = AppCatalog._resolve_lnk(exe_path) or exe_path
        if exe_path and exe_path.lower().endswith(".exe"):
            return self._spawn_isolated_chrome(exe_path)
        logger.error("Launch: could not directly launch browser '%s' without the profile picker", app_name)
        return False

    def launch(self, app_name: str) -> bool:
        # Browsers must NEVER go through the Windows search bar: that opens the
        # user's real multi-profile Chrome and triggers the "Who's using Chrome?"
        # profile picker. Route them to a direct, isolated automation launch.
        if self._looks_like_browser(app_name):
            return self.launch_browser_direct(app_name)
        # Primary: Windows search bar (type full name, open top suggestion).
        logger.info("Launch: attempting Windows search-bar launch for '%s'", app_name)
        if self.launch_via_search(app_name):
            logger.info("Launch: '%s' opened via Windows search bar", app_name)
            return True
        # Fallback: catalog launcher path (Start Menu .lnk -> .exe).
        logger.info("Launch: search-bar failed for '%s'; trying catalog launcher path", app_name)
        _, path = self.catalog.find(app_name)
        if path and self.launch_via_path(path):
            logger.info("Launch: '%s' opened via catalog launcher path", app_name)
            return True
        # Fallback 2: crawl the file explorer for the actual launcher .exe.
        logger.info("Launch: catalog path missing; crawling file explorer for '%s' launcher", app_name)
        exe = self.catalog.crawl_for_exe(app_name)
        if exe and self.launch_via_path(exe):
            logger.info("Launch: '%s' opened via crawled launcher %s", app_name, exe)
            return True
        logger.error("Launch: could not open '%s' by any method", app_name)
        return False

    def launch_via_search(self, app_name: str) -> bool:
        try:
            import pyautogui
            pyautogui.press("win")
            time.sleep(0.6)
            pyautogui.write(app_name)
            time.sleep(1.2)
            pyautogui.press("enter")
            time.sleep(2.0)
            return True
        except Exception:
            try:
                from pywinauto.keyboard import send_keys
                send_keys("{VK_LWIN}")
                time.sleep(0.6)
                send_keys(app_name)
                time.sleep(1.2)
                send_keys("{ENTER}")
                time.sleep(2.0)
                return True
            except Exception:
                return False

    def launch_via_path(self, path: str) -> bool:
        try:
            if path.lower().endswith(".lnk"):
                path = AppCatalog._resolve_lnk(path) or path
            if path.lower().endswith(".exe"):
                # Special handling for Chrome: launch with user profile for session persistence
                if any(tok in path.lower() for tok in ("chrome", "msedge", "chromium", "edge")):
                    # Reuse the running automation Chrome if present; otherwise a
                    # direct, picker-free isolated-profile launch. The real
                    # multi-profile User Data is intentionally NOT opened here.
                    alive = self._automation_cdp_alive()
                    if alive:
                        logger.info("Launch_via_path: reusing automation Chrome on CDP port %d (no picker)", alive)
                    else:
                        self._spawn_isolated_chrome(path)
                else:
                    subprocess.Popen([path])
            else:
                os.startfile(path)  # type: ignore[attr-defined]
            time.sleep(1.5)
            return True
        except Exception:
            return False


def plan_task_app(task_text: str, catalog: Optional["AppCatalog"] = None,
                  engine: Optional["VerbAliasEngine"] = None) -> dict:
    """Pure (dry-run) app-resolution: decide WHICH app a task wants and HOW it
    would be launched, WITHOUT touching the OS (no search-bar typing, no Popen).

    This is the single source of truth for the launcher decision, shared by the
    real :func:`resolve_and_launch` and the behavior tests. It encodes the four
    designer requirements:
      * a web cue ('gmail', 'browse ...') -> browser_web, NEVER typed into the
        Windows search bar as a literal app;
      * an aliased app ('open obs studio') -> find it, launch if available;
      * any verb -> functionality aliasing picks the best app;
      * any app NAME ('open blender') -> dynamic app-name tier -> catalog search
        then file-explorer crawl, launching only if actually present.
    """
    own_catalog = catalog is None
    if own_catalog:
        catalog = AppCatalog()
    if engine is None:
        engine = VerbAliasEngine(catalog)

    desired, source = engine.resolve_detailed(task_text)

    # A genuine web task: an alias explicitly resolved to the default browser
    # (e.g. gmail/browse -> chrome). The browser agent handles it; do not crawl.
    if desired == DEFAULT_APP and source in ("alias", "word", "semantic", "llm"):
        return {"task": task_text, "desired_app": DEFAULT_APP,
                "resolution_source": source, "target_app": None,
                "installed": False, "method": "none", "launcher_path": None,
                "action": "browser_web", "would_type_in_search_bar": False,
                "note": "web task handled by browser agent (Chrome)"}

    # Determine a concrete desktop-app target.
    target = None
    if source != "default":
        target = desired  # alias/word/semantic/llm named a real desktop app
    else:
        # Dynamic app-NAME tier: user pointed at an app by name we have no alias for.
        target = engine.detect_named_app(task_text)
        if target:
            source = "named"

    if not target:
        # No launch hint, no alias -> treat as generic/web fallback (no crawl).
        return {"task": task_text, "desired_app": DEFAULT_APP,
                "resolution_source": source or "default", "target_app": None,
                "installed": False, "method": "none", "launcher_path": None,
                "action": "browser_web", "would_type_in_search_bar": False,
                "note": "no app alias or name detected; web/browser fallback"}

    # Resolve the target against the host catalog, then the file-explorer crawl.
    name, path = catalog.find(target)
    installed = bool(name)
    method = "none"
    launcher_path = path or None
    if installed:
        method = "catalog" if launcher_path else "search"
    else:
        exe = catalog.crawl_for_exe(target)
        if exe:
            installed = True
            method = "crawl"
            launcher_path = exe
            name = name or target

    action = "launch_app" if installed else "not_found"
    return {"task": task_text, "desired_app": desired, "resolution_source": source,
            "target_app": (name or target), "installed": installed,
            "method": method, "launcher_path": launcher_path,
            "would_type_in_search_bar": method == "search",
            "action": action,
            "note": (f"{source} -> '{target}' via {method}" if installed
                     else f"'{target}' named but not found on host")}


def resolve_and_launch(task_text: str, gateway=None) -> dict:
    """End-to-end: understand the task, find the app, and launch it.

    Delegates the decision to the pure :func:`plan_task_app`, then performs the
    physical launch only when the plan says a real desktop app was found. Web
    tasks and unknown-but-named-but-absent apps are never force-launched.
    """
    catalog = AppCatalog()
    catalog.ensure_scanned()
    engine = VerbAliasEngine(catalog, gateway)
    plan = plan_task_app(task_text, catalog=catalog, engine=engine)
    if plan["action"] != "launch_app":
        return {"task": task_text, "target_app": plan["target_app"] or DEFAULT_APP,
                "launched": False, "method": plan["method"], "note": plan["note"]}
    ok = AppLauncher(catalog).launch(plan["target_app"])
    return {"task": task_text, "target_app": plan["target_app"], "launched": ok,
            "method": plan["method"], "note": plan["note"]}


if __name__ == "__main__":
    import sys, json as _json
    logging_basic = None
    cat = AppCatalog()
    if "--scan" in sys.argv:
        print("Scanning host for installed apps...")
        apps = cat.scan_host()
        print(f"Found {len(apps)} apps. Sample: {apps[:15]}")
    elif len(sys.argv) > 1:
        task = sys.argv[1]
        print(_json.dumps(resolve_and_launch(task), indent=2))
    else:
        print("Usage:")
        print("  python organ_40_app_launcher.py --scan")
        print('  python organ_40_app_launcher.py "record the session for 30 seconds"')
