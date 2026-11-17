"""One-off correction: the first shortcut export filed its hotkeys under app key 'excalidraw' (the bridge rewrote the name). That key held 0 rows before (checked against the backup),
so every row under it is ours. Remove them, then export under the real key 'webapp:excalidraw.com' with the fixed exporter (no second procedure)."""
import sys, json
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs import rag as R
from core_organs.harvest import consolidate as C

r = R.get_rag()
wrong, right = "excalidraw", "webapp:excalidraw.com"
print("before: wrong key fast/commands", r.fast.count(wrong), r.lex.n_commands(wrong), "| right key fast/commands", r.fast.count(right), r.lex.n_commands(right))
assert r.fast.count(wrong) == 18, "unexpected row count under the wrong key: refusing to delete"
print("removed fast:", r.fast.forget_app(wrong), "lexicon:", r.lex.forget_app(wrong))
g = C.AppGraph.load(right)
print(json.dumps(C.export_facts_rag(g, r, "Excalidraw", write_procedure=False), indent=1))
print("after: wrong key fast/commands", r.fast.count(wrong), r.lex.n_commands(wrong), "| right key fast/commands", r.fast.count(right), r.lex.n_commands(right))
for q in ["zen mode", "snap to objects", "flip horizontal", "select all", "bring forward"]:
    ev = r.fast.by_goal(right, q)
    print(q, "->", [(e.payload.get("payload"), e.trust, e.payload.get("verified")) for e in ev[:2]])
