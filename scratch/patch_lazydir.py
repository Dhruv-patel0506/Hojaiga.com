import ast, io
P = "D:/new_automation/All codes/core_organs/professor/apprun.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''        self.run_dir = os.path.join(OUT_DIR, f"{spec.key}_{self.stamp}")
        os.makedirs(os.path.join(self.run_dir, "evidence"), exist_ok=True)
'''
new = '''        self.run_dir = os.path.join(OUT_DIR, f"{spec.key}_{self.stamp}")                       # created when the first picture / report is written
'''
assert old in s
s = s.replace(old, new, 1)
s = s.replace('''    def _save(self, tag: str, img: Any) -> str:
        try:
            p = os.path.join(self.run_dir, tag + ".png")''', '''    def _save(self, tag: str, img: Any) -> str:
        try:
            os.makedirs(self.run_dir, exist_ok=True)
            p = os.path.join(self.run_dir, tag + ".png")''', 1)
s = s.replace('''            base = os.path.join(self.run_dir, "evidence", re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)[:60])''', '''            os.makedirs(os.path.join(self.run_dir, "evidence"), exist_ok=True)
            base = os.path.join(self.run_dir, "evidence", re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)[:60])''', 1)
s = s.replace('''        path = os.path.join(self.run_dir, "report.json")
        with open(path, "w", encoding="utf-8") as fh:''', '''        os.makedirs(os.path.join(self.run_dir, "evidence"), exist_ok=True)
        path = os.path.join(self.run_dir, "report.json")
        with open(path, "w", encoding="utf-8") as fh:''', 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
