p = r"D:\new_automation\All codes\core_organs\atlas\comlib.py"
s = open(p, encoding="utf-8").read()
old = '''            methods[t["name"]] = sorted(set(names))'''
new = '''            methods[t["name"]] = sorted(set(names))
            # signatures (parameter names) of the verbs that DO things: enough to write a call without opening the documentation
            for j in range(min(t["funcs"], 1500)):
                try:
                    fd = ti.GetFuncDesc(j)
                    nm_all = ti.GetNames(fd[0])
                except Exception:
                    continue
                if nm_all and fd[4] == 1 and VERB_RX.match(nm_all[0]) and len(sigs.setdefault(t["name"], {})) < 120:
                    sigs[t["name"]][nm_all[0]] = list(nm_all[1:9])'''
assert old in s
s = s.replace(old, new, 1)
s = s.replace('''    methods: Dict[str, List[str]] = {}
    for t in types[:keep_methods]:''','''    methods: Dict[str, List[str]] = {}
    sigs: Dict[str, Dict[str, List[str]]] = {}
    for t in types[:keep_methods]:''',1)
s = s.replace("               methods=methods, seconds=round(time.time() - t0, 2))", "               methods=methods, sigs=sigs, seconds=round(time.time() - t0, 2))",1)
s = s.replace("def enumerate_typelib(", 'VERB_RX = re.compile(r"^(Add|Insert|Create|New|Open|Save|SaveAs|Export|Import|Apply|Set|Delete|Remove|Run|Print|Close|Copy|Paste|Cut|Select|Find|Replace|Merge|Split|Sort|Filter|Group|Format|Convert|Refresh|Update)", re.I)\n\n\ndef enumerate_typelib(',1)
open(p, "w", encoding="utf-8").write(s)
print("ok")
