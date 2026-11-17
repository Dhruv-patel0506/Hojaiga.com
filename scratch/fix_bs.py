import io
P = "D:/new_automation/All codes/core_organs/professor/adapters/chromium.py"
s = io.open(P, "r", encoding="utf-8").read()
n = s.count("\x08")
s = s.replace("\x08", "")
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("removed", n)
