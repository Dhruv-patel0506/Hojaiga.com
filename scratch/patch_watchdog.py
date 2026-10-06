p = r"D:\new_automation\All codes\core_organs\run_system_intelligence_tests.py"
s = open(p, encoding="utf-8").read()
HEAD = 'def run_test(test_id: str, group: str, func: Callable[[], TestOutcome]) -> None:\n    print(f"\\n{\'=\' * 80}\\nTEST {test_id} [{group}]: {func.__doc__}\\n{\'=\' * 80}")\n    start = time.perf_counter()\n'
assert HEAD in s, "header"
NEW = '''class TestHang(Exception):
    def __str__(self) -> str:
        return "the test exceeded its per-test time limit (HOJAIGA_TEST_TIMEOUT_S): a hang is a FAIL, never a pass; thread stacks were written to scratch/hang_<id>.txt"


def _arm_watchdog(test_id: str):
    """Bounded time everywhere (L6): a test that never returns used to stall the whole overnight run (SCK1, 16+ minutes). At the limit the stacks of every
    thread are written out and TestHang is raised in the main thread (it lands as soon as the thread is back in Python; a thread stuck inside a COM call only
    gets it when the call returns, so a second, harder deadline ends the process with the partial results already printed)."""
    import faulthandler
    import threading
    limit = float(os.environ.get("HOJAIGA_TEST_TIMEOUT_S", "1200"))
    main_tid = threading.main_thread().ident

    def _fire():
        try:
            d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scratch")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, f"hang_{test_id}.txt"), "w") as fh:
                faulthandler.dump_traceback(file=fh, all_threads=True)
        except Exception:  # noqa: BLE001
            pass
        print(f"\\n[watchdog] {test_id} exceeded {limit:.0f}s: raising TestHang in the main thread", flush=True)
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(main_tid), ctypes.py_object(TestHang))
        hard = threading.Timer(180.0, lambda: (print(f"[watchdog] {test_id} still stuck 180 s later: ending the run (results so far are above)", flush=True), os._exit(3)))
        hard.daemon = True
        hard.start()
    t = threading.Timer(limit, _fire)
    t.daemon = True
    t.start()
    return t


'''
s = s.replace(HEAD, NEW + HEAD + "    _wd = _arm_watchdog(test_id)\n", 1)
A = "        try:\n            outcome = func()\n        finally:\n            g1 = _gui_counts()\n"
assert A in s, "finally"
s = s.replace(A, "        try:\n            outcome = func()\n        finally:\n            _wd.cancel()\n            g1 = _gui_counts()\n", 1)
open(p, "w", encoding="utf-8").write(s)
print("ok, chr8:", s.count(chr(8)))
