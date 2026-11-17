import sys, time, threading, multiprocessing as mp


def burn(stop):
    x = 0
    while not stop.is_set():
        x = (x * 31 + 7) % 1000003


if __name__ == "__main__":
    sys.path[:0] = ["D:/new_automation", "D:/new_automation/All codes", "D:/new_automation/All codes/core_organs"]
    stop = mp.Event()
    procs = [mp.Process(target=burn, args=(stop,), daemon=True) for _ in range(max(2, (mp.cpu_count() or 8) - 1))]
    for p in procs:
        p.start()
    time.sleep(2)
    try:
        from core_organs import si_tests_professor as T
        n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
        for i in range(n):
            r = T.run_pl8()
            bad = [c.strip() for c in r.evidence.split("|")[0].split(";") if "FAIL" in c]
            print(f"loaded run {i + 1}: passed={r.passed} failed_checks={bad}", flush=True)
            if not r.passed:
                print("   ", r.evidence[:2500], flush=True)
    finally:
        stop.set()
        for p in procs:
            p.terminate()
