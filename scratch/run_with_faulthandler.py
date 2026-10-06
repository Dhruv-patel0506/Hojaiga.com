import faulthandler, sys, runpy, os
faulthandler.dump_traceback_later(int(os.environ.get("FH_S", "150")), exit=True, file=open(r"D:\new_automation\scratch\fh_stacks.txt", "w"))
sys.argv = ["run_system_intelligence_tests.py"] + sys.argv[1:]
runpy.run_path("run_system_intelligence_tests.py", run_name="__main__")
