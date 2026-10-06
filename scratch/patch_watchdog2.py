p = r"D:\new_automation\All codes\core_organs\run_system_intelligence_tests.py"
s = open(p, encoding="utf-8").read()
s = s.replace("class TestHang(Exception):", "class TestHang(BaseException):      # BaseException: a test's own broad `except Exception` must not swallow the watchdog", 1)
A = "        try:\n            outcome = func()\n        finally:\n            _wd.cancel()\n"
assert A in s
s = s.replace(A, "        try:\n            outcome = func()\n        except TestHang as _th:\n            outcome = TestOutcome(passed=False, evidence=str(_th), metrics={\"hang\": \"timeout\"})\n        finally:\n            _wd.cancel()\n", 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
