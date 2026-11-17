import ast
import io

D = "D:/new_automation/All codes/core_organs/professor/dialogs.py"
s = io.open(D, "r", encoding="utf-8").read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep('''    def pick(*names: str) -> str:
        for nme in names:
            if nme in labels:
                return labels[nme]
        return ""''', '''    def pick(*names: str) -> str:
        for nme in names:
            k = fold(nme)                                                          # 'Don't save' is 'don t save' once folded: both sides are folded
            if k in labels:
                return labels[k]
        return ""''')
rep('''"try again", "replace", "skip", "stop", "keep", "exit")''', '''"try again", "replace", "skip", "stop", "keep", "exit", "don t save", "don t allow")''')
ast.parse(s)
io.open(D, "w", encoding="utf-8", newline="\n").write(s)

t = io.open("D:/new_automation/scratch/pr61.txt", "r", encoding="utf-8").read()
t = t.replace("store: Dict[str, Any] = {}", "store = {}")
t = t.replace('rx_ok = (bool(DG.COPY_RX.search("Copy Ctrl+C")) and bool(DG.PASTE_RX.search("Paste Ctrl+V")) and not DG.PASTE_RX.search("Pasteboard settings") is None)',
              'rx_ok = bool(DG.COPY_RX.search("Copy Ctrl+C")) and bool(DG.PASTE_RX.search("Paste Ctrl+V")) and DG.PASTE_RX.search("Pasteboard settings") is None')
t = t.replace("        drv.windows = lambda: []\n", "        drv.windows = lambda: []\n        drv._exists_soon = lambda p, max_s=3.0: True\n")
T = "D:/new_automation/All codes/core_organs/si_tests_apprun.py"
f = io.open(T, "r", encoding="utf-8").read()
assert "run_pr61" not in f
f = f.replace('\nTESTS = [("PR49"', "\n" + t + '\nTESTS = [("PR49"', 1)
f = f.replace('("PR60", run_pr60)]', '("PR60", run_pr60), ("PR61", run_pr61)]', 1)
ast.parse(f)
io.open(T, "w", encoding="utf-8", newline="\n").write(f)
print("ok")
