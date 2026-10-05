import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


def is_port_open(ip: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect((ip, port))
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    finally:
        sock.close()


def clean_and_launch_profile(
    profile_name: str = "Profile 1",
    user_data_base: str | None = None,
    port: int = 9222,
    ip: str = "127.0.0.1",
) -> bool:
    """
    Launch Chrome against a pre-authenticated profile directory.
    """
    if user_data_base is None:
        user_data_base = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")

    print("Step 1: Terminating conflicting Chrome background tasks...")
    subprocess.run(
        ["taskkill", "/F", "/IM", "chrome.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        check=False,
    )
    time.sleep(1.5)

    print(f"Step 2: Checking profile lock status for '{profile_name}'...")
    lock_file = Path(user_data_base) / profile_name / "SingletonLock"
    if lock_file.exists():
        try:
            lock_file.unlink()
            print("  Cleared legacy process lock file.")
        except Exception:
            print("  Warning: Could not remove lock file. It may still be held by a system process.")

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not Path(chrome_path).exists():
        chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    if not Path(chrome_path).exists():
        chrome_path = "chrome.exe"

    flags = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--remote-debugging-address={ip}",
        f"--user-data-dir={user_data_base}",
        f"--profile-directory={profile_name}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]

    print(f"Step 3: Launching Chrome with your saved sessions on port {port}...")
    subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("Step 4: Verifying port availability...")
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


if __name__ == "__main__":
    clean_and_launch_profile()
