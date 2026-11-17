p = r"D:\new_automation\All codes\core_organs\atlas\teach.py"
s = open(p, encoding="utf-8").read()
old = "                if (tname, m) in seen:\n                    continue"
new = "                if (tname, m) in seen or m in NOISE_MEMBERS or tname.startswith(\"E\") and tname.endswith((\"Application\", \"Events\")) or tname.endswith(\"Events\"):\n                    continue"
assert old in s
s = s.replace(old, new, 1)
s = s.replace("_W = re.compile(", 'NOISE_MEMBERS = {"AddRef", "Release", "QueryInterface", "GetTypeInfo", "GetTypeInfoCount", "GetIDsOfNames", "Invoke", "Dispose", "Finalize", "ToString", "Equals", "GetHashCode"}\n_W = re.compile(', 1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
