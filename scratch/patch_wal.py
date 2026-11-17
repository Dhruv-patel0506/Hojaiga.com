import ast, io
P = "D:/new_automation/All codes/core_organs/professor/knowledge/manual_rag.py"
s = io.open(P, "r", encoding="utf-8").read()
old = '''        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS docs('''
new = '''        self.db = sqlite3.connect(self.path, timeout=120, check_same_thread=False)         # the corpus builder and a live run may share the file: wait for the lock, readers never block a writer (WAL)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA busy_timeout=120000")
        except Exception:
            pass
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS docs('''
assert old in s
s = s.replace(old, new, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
