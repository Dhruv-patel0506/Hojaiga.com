p = r"D:\new_automation\All codes\core_organs\hojaiga_run.py"
s = open(p, encoding="utf-8").read()

# 1 split_parts: a fragment that is not a command belongs to the previous part
a = s.index("def split_parts(")
b = s.index("# ---- 3 route")
new_split = '''_CMD_START = re.compile(r"^(open|click|press|go|navigate|type|enter|fill|search|select|add|create|draw|save|close|run|launch|start|delete|remove|send|submit|book|buy|order|download|upload|post|publish|write|draft|compose|"
                        r"prepare|reply|respond|find|show|what|how|where|which|who|why|when|can|could|does|do|is|are|explain|tell|teach|list|give|take|make|set|change|rename|copy|paste|move|check|read|summari[sz]e|"
                        r"translate|schedule|call|email|mail|message|text|play|stop|pause|turn|switch|log|sign|visit|use|apply|install|update|export|import|print|scroll|zoom|rotate|scan|learn|reverse|in|on|at|from|"
                        r"please|then|also|and)\\b", re.I)


def split_parts(text: str) -> List[str]:
    """A task with several parts becomes several tickets: ';', a new line, 'then', 'and then', 'after that', 'next', 'finally'. The intake's own splitting only handles lists, and a part that is not split
    off is a part that is silently never done. A piece that does not start like a command ('helps people use it') is the rest of the previous sentence, not a new task."""
    pieces = re.split(r"(\\s*(?:;|\\n|\\band then\\b|\\bthen\\b|\\bafter that\\b|\\bnext\\b,?|\\bfinally\\b,?|\\balso\\b,?)\\s*)", text or "", flags=re.I)
    parts: List[str] = []
    glue = ""
    for i, piece in enumerate(pieces):
        if i % 2 == 1:
            glue = piece
            continue
        pc = piece.strip(" ,.")
        if len(pc) <= 2:
            continue
        if parts and not _CMD_START.match(pc):
            parts[-1] = parts[-1] + (glue if glue.strip() else " ") + pc
        else:
            parts.append(pc)
    return parts or ([text.strip()] if (text or "").strip() else [])


'''
s = s[:a] + new_split + s[b:]

# 2 a WRITE ticket is gated only when the task itself says to send / publish the result
old = '        th = BR.think(r_["text"], app=r_.get("host", ""))'
assert old in s
new = '''        gate_text = r_["text"]
        if r_["kind"] == "write" and not re.search(r"\\b(?:send|publish|post|tweet|share|email)\\s+(?:it|this|that|them|the\\s+(?:email|message|post|draft))\\b|\\band\\s+(?:send|publish|post)\\s+it\\b", r_["text"], re.I):
            gate_text = "draft a text"                                                                # drafting is not publishing: the draft is shown, nothing is sent
        th = BR.think(gate_text, app=r_.get("host", ""))'''
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
import ast
ast.parse(s)
print("ok; control chars:", sum(1 for c in s if c == "\x08"))
