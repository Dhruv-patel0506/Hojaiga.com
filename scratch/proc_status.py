"""Read-only status probe: python processes (cmdline + RSS + age) and suite log tails.

Why a script: PowerShell quoting inside `powershell -Command "..."` keeps eating $_ and
nested quotes, which wastes turns on syntax errors instead of answering the question.
"""
import os
import sys
import time
import glob

import psutil


def main() -> int:
    now = time.time()
    print("=== python processes ===")
    for p in psutil.process_iter(["pid", "name", "username"]):
        try:
            if "python" not in (p.info["name"] or "").lower():
                continue
            rss = p.memory_info().rss / 1e6
            age = now - p.create_time()
            try:
                cmd = " ".join(p.cmdline())
            except Exception:
                cmd = "?"
            print(f"{p.pid:>7}  {rss:8.0f} MB  age={age:7.0f}s  {cmd[-150:]}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print()
    print("=== log files (mtime age, size) ===")
    for pat in sys.argv[1:] or ["_sck*.out", "_sck*.err", "_full*.out", "_full*.err"]:
        for f in sorted(glob.glob(os.path.join(r"D:\new_automation", pat))):
            st = os.stat(f)
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
            print(f"{os.path.basename(f):<16} {len(lines):>5} lines  "
                  f"{st.st_size / 1e6:7.2f} MB  wrote {now - st.st_mtime:7.0f}s ago")
    return 0


if __name__ == "__main__":
    sys.exit(main())
