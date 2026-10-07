"""popup_mode: who may hold the machine in cancel-only mode? (truth table, real processes)

case A  our own live process       -> probe honoured   (the scanner and its handler, same pid)
case B  a DIFFERENT live process   -> probe honoured   (the documented CNS-bridge case; must not break)
case C  a process that has EXITED  -> task             (f5's failure: a dead writer held 4 tests)
case D  no pid at all (old format) -> task             (nobody is claiming it)
case E  dead writer, stale clock   -> task
case F  an expected-dialog fragment is honoured only while its step's process lives
case G  releasing OUR claim leaves another live claimant in probe
case H  releasing a token that is not ours cannot drop ours
case I  a bystander's set_policy('task') cannot silence a live claim   (f6's regression)
case J  a claimant that was killed is not honoured
case K  a scan that keeps working refreshes its claim past the TTL
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, r"D:\new_automation\All codes")
os.environ.setdefault("PYTHONPATH", r"D:\new_automation;D:\new_automation\All codes")
from core_organs import popup_mode as pm  # noqa: E402

FLAG = pm._FLAG_PATH


def write(pid, policy="probe", age=0.0):
    with open(FLAG, "w", encoding="utf-8") as fh:
        json.dump({"policy": policy, "ts": time.time() - age, "pid": pid, "expect": []}, fh)
    return pm.current_policy()


def expect_fragment_liveness():
    """The same rule for 'this step wants that dialog': a dead step must stop protecting it."""
    live = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"])
    dead = subprocess.Popen([sys.executable, "-c", "import os;print(os.getpid())"], stdout=subprocess.PIPE, text=True)
    dead_pid = int(dead.communicate()[0].strip())
    time.sleep(0.2)
    try:
        with open(FLAG, "w", encoding="utf-8") as fh:
            json.dump({"policy": "task", "ts": time.time(), "pid": os.getpid(),
                       "expect": [{"frag": "save as", "ts": time.time(), "pid": live.pid},
                                  {"frag": "overwrite", "ts": time.time(), "pid": dead_pid}]}, fh)
        return pm.is_expected("Confirm Save As"), pm.is_expected("Confirm Overwrite"), pm.expected_titles()
    finally:
        live.kill()
        live.wait()


ok = True
got_a = write(os.getpid())
print(f"A own live pid            -> {got_a!r}  (want 'probe')  {'OK' if got_a == 'probe' else 'WRONG'}")
ok &= got_a == "probe"

# a genuinely different live process writes it, we read it
holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
try:
    got_b = write(holder.pid)
    print(f"B other live pid          -> {got_b!r}  (want 'probe')  {'OK' if got_b == 'probe' else 'WRONG'}")
    ok &= got_b == "probe"
finally:
    holder.kill()
    holder.wait()
time.sleep(0.3)

child = subprocess.Popen([sys.executable, "-c", "import os;print(os.getpid())"], stdout=subprocess.PIPE, text=True)
dead_pid = int(child.communicate()[0].strip())
child.wait()
time.sleep(0.3)
got_c = write(dead_pid)
print(f"C pid of an exited process  -> {got_c!r}  (want 'task')   {'OK' if got_c == 'task' else 'WRONG'}")
ok &= got_c == "task"

got_d = write(0)
print(f"D no pid in the flag        -> {got_d!r}  (want 'task')   {'OK' if got_d == 'task' else 'WRONG'}")
ok &= got_d == "task"

got_e = write(dead_pid, age=200.0)
print(f"E dead + older than TTL     -> {got_e!r}  (want 'task')   {'OK' if got_e == 'task' else 'WRONG'}")
ok &= got_e == "task"

live_ok, dead_ok, titles = expect_fragment_liveness()
print(f"F expect from a LIVE writer honoured={live_ok} / a DEAD writer honoured={dead_ok}  "
      f"(want True / False)  titles={titles}  {'OK' if live_ok and not dead_ok else 'WRONG'}")
ok &= live_ok and not dead_ok


# ---------------------------------------------------------------- the other half: who may CLEAR it
def claims_of():
    return [c.get("token", "?") for c in pm._live_claims(pm._read(), time.time())]


def case_ghij():
    """G,H,I,J,K: probe is a SET of claims. One claimant finishing must not silence another, and a
    release must not write over a claim that is not its own (f6's regression: an abandoned scan being
    cleaned up answered 'task' while a live scan was mid-probe)."""
    results = []
    pm.set_policy("task")
    other = subprocess.Popen(
        [sys.executable, "-c",
         "import sys,time;sys.path.insert(0,r'D:\\new_automation\\All codes');"
         "from core_organs import popup_mode as p;"
         "p.claim('child-holds-it','probe');print('CLAIMED',flush=True);time.sleep(25)"],
        stdout=subprocess.PIPE, text=True)
    try:
        first = other.stdout.readline().strip()          # wait until the child really holds the claim
        results.append(("the child reported its own claim", first.startswith("CLAIMED"), first))

        tok = pm.claim("ours-G", "test")                 # ours on top of theirs
        pm.unclaim(tok)
        g = pm.current_policy()
        results.append(("G releasing OUR claim leaves another live claimant in probe",
                        g == "probe", f"-> {g!r}"))

        tok2 = pm.claim("ours-H", "test")
        pm.unclaim("someone-elses-token")                # a stray release of a token not ours
        h = pm.current_policy() == "probe" and "ours-H" in claims_of()
        results.append(("H releasing a FOREIGN token cannot drop ours",
                        h, f"claims={claims_of()}"))

        pm.set_policy("task")                            # the bystander's plain 'task'
        i = pm.current_policy()
        results.append(("I another process's set_policy('task') cannot silence a live claim",
                        i == "probe", f"-> {i!r}"))
        pm.unclaim(tok2)
    finally:
        other.kill()
        other.wait()
    time.sleep(0.4)
    pm.set_policy("task")                                # the child is gone now
    j = pm.current_policy()
    results.append(("J a killed claimant's claim is not honoured", j == "task", f"-> {j!r}"))

    with open(FLAG, "w", encoding="utf-8") as fh:
        json.dump({"policy": "task", "ts": time.time(), "pid": os.getpid(),      # the answer must come
                   "claims": [{"token": "stale-scan", "pid": os.getpid(),        # from the claim alone
                               "ts": time.time() - 400}], "expect": []}, fh)
    k_before = pm.current_policy()
    pm._HEARTBEAT.pop("stale-scan", None)
    pm.heartbeat("stale-scan")                           # a scan that is still working
    k_after = pm.current_policy()
    results.append(("K a long scan's heartbeat keeps its claim past the TTL",
                    k_before == "task" and k_after == "probe", f"{k_before!r} -> {k_after!r}"))
    pm.set_policy("task")
    return results


for _name, _cond, _detail in case_ghij():
    ok &= bool(_cond)
    print(f"{_name:<62} {'OK' if _cond else 'WRONG'}  {_detail}")

with open(FLAG, "w", encoding="utf-8") as fh:
    json.dump({"policy": "task", "ts": time.time(), "pid": os.getpid(), "expect": []}, fh)
print(f"\nflag restored to task; truth table {'ALL PASS' if ok else 'FAILURES PRESENT'}")
sys.exit(0 if ok else 1)
