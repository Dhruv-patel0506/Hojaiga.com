import os
import socket
import subprocess
import shutil
import sys
import time
import urllib.request
from pathlib import Path


def is_port_open(ip: str, port: int) -> bool:
    """Check whether a TCP port is actively accepting connections."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect((ip, port))
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        sock.close()


def _find_chrome_executable() -> str:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return "chrome.exe"


def _list_chrome_profiles(user_data_base: str) -> list[str]:
    base = Path(user_data_base)
    if not base.exists():
        return []
    profiles = []
    for entry in base.iterdir():
        if entry.is_dir() and entry.name.startswith("Profile "):
            profiles.append(entry.name)
    default_profile = base / "Default"
    if default_profile.exists():
        profiles.insert(0, "Default")
    return profiles


def _safe_profile_clone(source_profile: Path, clone_profile: Path) -> None:
    """
    Copy a Chrome profile while skipping volatile lock/session files that are
    often in use when the human browser is open.
    """
    skip_names = {
        "SingletonLock",
        "SingletonCookie",
        "SingletonSocket",
        "Cookies",
        "Cookies-journal",
        "History",
        "History-journal",
        "Current Session",
        "Current Tabs",
    }
    skip_dirs = {
        "Sessions",
        "Session Storage",
        "Service Worker",
        "Network",
    }

    def _ignore(_src: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name in skip_names or name in skip_dirs:
                ignored.add(name)
        return ignored

    if clone_profile.exists():
        shutil.rmtree(clone_profile, ignore_errors=True)
    shutil.copytree(source_profile, clone_profile, ignore=_ignore, dirs_exist_ok=True)


def choose_profile_interactively(user_data_base: str | None = None) -> str:
    if user_data_base is None:
        user_data_base = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")

    profiles = _list_chrome_profiles(user_data_base)
    if not profiles:
        return "Profile 1"

    cache_file = Path(user_data_base) / ".hojaiga_profile_cache"
    if cache_file.exists():
        try:
            cached_profile = cache_file.read_text().strip()
            if cached_profile in profiles:
                return cached_profile
        except Exception:
            pass

    if not sys.stdin or not sys.stdin.isatty():
        # Non-interactive (automation) run: never block on input(); open the
        # first profile deterministically instead of stalling on a prompt.
        return profiles[0]

    print("\nAvailable Chrome profiles:")
    for idx, profile in enumerate(profiles, start=1):
        print(f"  {idx}. {profile}")

    while True:
        choice = input("Choose a profile number: ").strip()
        try:
            idx = int(choice)
            if 1 <= idx <= len(profiles):
                selected = profiles[idx - 1]
                try:
                    cache_file.write_text(selected)
                except Exception:
                    pass
                return selected
        except ValueError:
            pass
        print("Invalid choice. Please enter a valid number.")


def launch_safe_chrome(port: int = 9222, ip: str = "127.0.0.1") -> bool:
    """
    Launch Chrome with a dedicated profile and wait for the CDP port to open.

    This is intended to avoid stale profile locks, IPv6 loopback surprises,
    and silent startup failures that leave the controller unable to connect.
    """
    profile_dir = os.path.join(os.environ.get("TEMP", os.getcwd()), f"chrome_automation_{port}")
    chrome_path = _find_chrome_executable()

    flags = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--remote-debugging-address={ip}",
        f"--user-data-dir={profile_dir}",
        # Deterministic profile open: omitting --profile-directory would let
        # Chrome show the "Who's using Chrome?" picker and block automation.
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "about:blank",
    ]

    print(f"[2/4] Launching Chrome on {ip}:{port}...")
    subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("[3/4] Waiting for CDP port to activate...")
    for attempt in range(10):
        if is_port_open(ip, port):
            print(f"[4/4] Success! Port {port} is open and listening.")
            try:
                with urllib.request.urlopen(f"http://{ip}:{port}/json/version", timeout=2) as response:
                    if response.status == 200:
                        print("CDP Endpoint is fully operational.")
                        return True
            except Exception:
                # Port is open; the JSON endpoint may come up a moment later.
                pass

        time.sleep(1)
        print(f"  Retrying connection... ({attempt + 1}/10)")

    raise RuntimeError("Chrome launched but refused to open the CDP port.")


def launch_authenticated_chrome(
    profile_name: str = "Profile 1",
    user_data_base: str | None = None,
    port: int = 9222,
    ip: str = "127.0.0.1",
) -> bool:
    """
    Launch Chrome using a pre-authenticated profile directory.

    Use this when the task depends on saved cookies/session data from a
    manual login. Chrome must be fully closed first or the profile lock will
    block the launch.
    """
    if user_data_base is None:
        user_data_base = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")

    source_profile = Path(user_data_base) / profile_name
    if not source_profile.exists():
        raise FileNotFoundError(f"Chrome profile folder not found: {source_profile}")

    print(f"Step 1: Preparing isolated automation copy for '{profile_name}'...")
    clone_root = Path(user_data_base).parent / "Hojaiga Automation Profiles" / profile_name.replace(" ", "_")
    clone_root.mkdir(parents=True, exist_ok=True)
    clone_profile = clone_root / profile_name

    try:
        if not clone_profile.exists():
            _safe_profile_clone(source_profile, clone_profile)
        print(f"  Cloned profile to {clone_profile}")
    except Exception as exc:
        print(f"  Warning: profile clone failed ({exc}); launching against persistent automation profile path.")

    chrome_path = _find_chrome_executable()
    flags = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--remote-debugging-address={ip}",
        f"--user-data-dir={clone_root}",
        f"--profile-directory={profile_name}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-minimized",
        "about:blank",
    ]

    print(f"Step 2: Launching Chrome with your saved sessions on port {port}...")
    subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("Step 3: Verifying port availability...")
    for i in range(10):
        if is_port_open(ip, port):
            try:
                with urllib.request.urlopen(f"http://{ip}:{port}/json/version", timeout=2) as response:
                    if response.status == 200:
                        print("Success! Chrome is running, profile is loaded, and port is open.")
                        return True
            except Exception:
                pass
        time.sleep(1)
        print(f"  Waiting for port to respond... ({i + 1}/10)")

    raise RuntimeError("Chrome started but the debugging port remains unreachable.")


def launch_chrome_for_trial(
    mode: str = "safe",
    port: int = 9222,
    ip: str = "127.0.0.1",
    profile_name: str = "Profile 1",
    user_data_base: str | None = None,
) -> bool:
    """
    Unified launcher for the trial harness.

    mode="safe" uses an isolated automation profile.
    mode="auth" uses an existing logged-in Chrome profile.
    mode="select" prompts you to pick a profile from the terminal.
    """
    if mode == "select":
        profile_name = choose_profile_interactively(user_data_base=user_data_base)
        return launch_authenticated_chrome(
            profile_name=profile_name,
            user_data_base=user_data_base,
            port=port,
            ip=ip,
        )
    if mode == "auth":
        return launch_authenticated_chrome(
            profile_name=profile_name,
            user_data_base=user_data_base,
            port=port,
            ip=ip,
        )
    return launch_safe_chrome(port=port, ip=ip)


if __name__ == "__main__":
    launch_safe_chrome(port=9222)
