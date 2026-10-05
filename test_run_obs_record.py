"""TEST RUN — task: 'open OBS Studio and record for 30 sec and stop it and
find the file where the recording was saved'.

Runs the real pipeline with timestamped, real-time logs so you can see exactly
what the automation is doing at each step. Controlled entirely through the
host app catalog + aliasing (organ_40) and OBS's own UI (pywinauto).

Usage:
  python test_run_obs_record.py            # real 30s recording run
  python test_run_obs_record.py --dry-run # log the flow without recording
  python test_run_obs_record.py --seconds 10
"""
from __future__ import annotations
import argparse, configparser, logging, os, subprocess, sys, time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("test_run")

sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.organ_40_app_launcher import AppCatalog, VerbAliasEngine, AppLauncher
from core_organs.organ_29_popup_handler import resolve_dialog_via_catalog

REC_BUTTON = "Start Recording"
STOP_BUTTON = "Stop Recording"


def obs_pids():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process obs64 -EA SilentlyContinue).Id"],
        capture_output=True, text=True)
    return [int(x) for x in out.stdout.split() if x.strip().isdigit()]


def kill_all_obs():
    subprocess.run(["taskkill", "/IM", "obs64.exe", "/F"], capture_output=True)
    time.sleep(5)


def connect_obs_main(pid=None, timeout: float = 70):
    """Track a single OBS pid; auto-dismiss crash dialog (Run in Normal Mode).
    Returns (Application, main_window_title) or (None, None)."""
    from pywinauto import Application
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pid is None:
            pids = obs_pids()
            if not pids:
                time.sleep(1)
                continue
            pid = pids[0]
        try:
            app = Application(backend="uia").connect(process=pid, timeout=2)
        except Exception:
            pid = None
            time.sleep(1)
            continue
        try:
            wins = app.windows()
        except Exception:
            pid = None
            time.sleep(1)
            continue
        titles = [w.window_text() for w in wins]
        if any("Crash" in t or "Error" in t for t in titles):
            resolve_obstructions(app)
            log.info("Resolved blocking dialog via error_catalog; waiting for OBS to settle...")
            time.sleep(15)
            pid = None  # re-resolve after restart
            continue
        for w in wins:
            t = w.window_text()
            if "OBS" in t and w.is_visible() and "Crash" not in t and "Error" not in t:
                log.info("OBS main window ready: %r", t)
                return app, t
        time.sleep(1)
    return None, None


def obs_record_dirs():
    dirs = []
    for cfg in (os.path.expandvars(r"%APPDATA%\obs-studio\basic.ini"),
                r"D:\obs-studio\config\obs-studio\basic.ini"):
        if os.path.isfile(cfg):
            cp = configparser.ConfigParser()
            try:
                cp.read(cfg)
            except Exception:
                continue
            for sec in ("AdvOut", "SimpleOutput"):
                for key in ("RecFilePath", "FilePath"):
                    if cp.has_option(sec, key):
                        v = cp.get(sec, key).strip()
                        if v:
                            dirs.append(v)
    for u in (os.path.expandvars(r"%USERPROFILE%\Videos"),
              r"C:\Users\dhruv\Videos", r"D:\Users\dhruv\Videos"):
        dirs.append(u)
    return dirs


def find_recording(start_time, dirs):
    exts = (".mkv", ".mp4", ".flv", ".mov", ".ts", ".mxf")
    cands = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith(exts):
                    p = os.path.join(root, f)
                    try:
                        m = os.path.getmtime(p)
                    except Exception:
                        continue
                    if m >= start_time - 5:
                        cands.append((m, p))
    cands.sort()
    return cands[-1][1] if cands else None


UPDATE_LABELS = {"Update Now", "Skip Version", "Remind me Later", "Not Now", "Later", "Skip"}


def _win_buttons(win):
    try:
        return [el.window_text() for el in win.descendants(control_type="Button")
                if el.window_text()]
    except Exception:
        return []


def _click_button_in(win, label):
    if not label:
        return False
    for el in win.descendants(control_type="Button"):
        if el.window_text() == label:
            try:
                el.click_input()
                return True
            except Exception as e:
                log.warning("error_db: click '%s' failed: %s", label, e)
                return False
    return False


def resolve_obstructions(app):
    """Solve any blocking popups through the shared error_catalog DB.

    Handles separate modal dialogs (crash / error) and update/version prompts
    nested inside the main window. Each is looked up in the error database;
    if unknown, a resolution is decided and recorded for next time.
    """
    for w in app.windows():
        try:
            t = w.window_text()
        except Exception:
            continue
        btns = _win_buttons(w)
        if not btns:
            continue
        tl = t.lower()
        if "crash" in tl or "error" in tl:
            plan = resolve_dialog_via_catalog(t, btns)
            if plan.get("action") == "click_button":
                log.info("error_db: dialog %r -> click '%s' (source=%s)",
                         t, plan.get("label"), plan.get("_source"))
                _click_button_in(w, plan.get("label"))
            continue
        if any(b in UPDATE_LABELS for b in btns):
            plan = resolve_dialog_via_catalog(t, btns)
            if plan.get("action") == "click_button":
                log.info("error_db: update prompt -> click '%s' (source=%s)",
                         plan.get("label"), plan.get("_source"))
                _click_button_in(w, plan.get("label"))


def close_obs_cleanly(app, main_title):
    try:
        app.window(title=main_title).type_keys("%{F4}")  # Alt+F4
        time.sleep(3)
    except Exception:
        pass
    subprocess.run(["taskkill", "/IM", "obs64.exe", "/F"], capture_output=True)


def main_run(seconds: int, dry_run: bool):
    log.info("=== TASK: open OBS Studio and record for %d sec, stop, find file ===")

    # 0) Clean any stale OBS so we start from one known instance
    if not dry_run:
        kill_all_obs()

    # 1) Resolve task -> app via catalog + verb aliasing
    cat = AppCatalog()
    cat.ensure_scanned()
    engine = VerbAliasEngine(cat, gateway=None)
    name, path, used_default = engine.resolve_installed(
        "open OBS Studio and record for 30 sec and stop it and find the file")
    if used_default or not name:
        log.error("Could not resolve OBS Studio from host catalog; aborting.")
        return
    log.info("Aliasing resolved target app: %r (launcher=%s)", name, path)

    # 2) Launch the app (Windows search bar -> full name -> open)
    if dry_run:
        log.info("[DRY-RUN] would launch %r via Windows search bar", name)
    else:
        log.info("Launching %r via Windows search bar...", name)
        AppLauncher(cat).launch(name)
        time.sleep(8)

    # 3) Connect to OBS main window
    if dry_run:
        log.info("[DRY-RUN] OBS main window would be connected here")
        log.info("[DRY-RUN] would click '%s'", REC_BUTTON)
        log.info("[DRY-RUN] recording for %d sec (heartbeat every 5s)...", seconds)
        log.info("[DRY-RUN] would click '%s'", STOP_BUTTON)
        log.info("[DRY-RUN] would search recording dirs: %s", obs_record_dirs())
        log.info("[DRY-RUN] DONE. (no real recording performed)")
        return

    pid = obs_pids()[0] if obs_pids() else None
    app, main_title = connect_obs_main(pid)
    if app is None:
        log.error("Could not reach OBS main window; aborting.")
        return

    def get_main():
        for w in app.windows():
            t = w.window_text()
            if "OBS" in t and w.is_visible() and "Crash" not in t and "Error" not in t:
                return w
        return None

    def click_btn(label):
        w = get_main()
        if w is None:
            raise RuntimeError("OBS main window not found for click")
        try:
            w.set_focus()
        except Exception:
            pass
        kw = label.lower()  # 'start recording' / 'stop recording'
        hits = [el for el in w.descendants()
                if kw in (el.element_info.name or "").lower()]
        hits = [h for h in hits if h.element_info.control_type == "Button"] or hits
        if not hits:
            raise RuntimeError(f"button {label!r} not found")
        hits[0].click_input()

    # 4) Start recording (clear any pending update prompt first, via error db)
    resolve_obstructions(app)
    start_time = time.time()
    try:
        click_btn(REC_BUTTON)
        time.sleep(2)
        # Verify recording actually began (button label flips to Stop Recording)
        if any("stop recording" in (e.element_info.name or "").lower()
               for e in get_main().descendants(control_type="Button")):
            log.info("Clicked '%s' -- recording STARTED (confirmed)", REC_BUTTON)
        else:
            log.warning("Clicked '%s' but record state not confirmed; proceeding", REC_BUTTON)
    except Exception as e:
        log.error("Failed to click '%s': %s", REC_BUTTON, e)
        close_obs_cleanly(app, main_title)
        return

    # 5) Heartbeat during recording
    while (time.time() - start_time) < seconds:
        time.sleep(5)
        elapsed = time.time() - start_time
        log.info("recording... %.0f/%ds", min(elapsed, seconds), seconds)

    # 6) Stop recording
    try:
        click_btn(STOP_BUTTON)
        log.info("Clicked '%s' -- recording STOPPED", STOP_BUTTON)
    except Exception as e:
        log.error("Failed to click '%s': %s", STOP_BUTTON, e)

    time.sleep(3)  # let OBS flush the file

    # 7) Find the saved file
    f = find_recording(start_time, obs_record_dirs())
    if f:
        size = os.path.getsize(f)
        log.info("RECORDING FILE FOUND: %s (%d bytes)", f, size)
    else:
        log.warning("No new recording file detected in: %s", obs_record_dirs())

    # 8) Clean shutdown to avoid leaving a crash flag for next time.
    close_obs_cleanly(app, main_title)
    log.info("=== TASK COMPLETE ===")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    main_run(args.seconds, args.dry_run)
