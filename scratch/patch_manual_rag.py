import ast
import io

P = "D:/new_automation/All codes/core_organs/professor/knowledge/manual_rag.py"
s = io.open(P, "r", encoding="utf-8").read()

start = s.index("class _Strip(HTMLParser):")
end = s.index("def read_text(path: str)")
new_cls = '''class _Strip(HTMLParser):
    """HTML -> text that KEEPS what a procedure needs: headings as '#', ordered / unordered list items as '1.' / '-', table cells as ' | ', and the words a manual marks as interface
    terms (<b> <strong> <kbd> <code> <samp>) as **bold** - those are the control names the steps refer to."""
    _SKIP = ("script", "style", "nav", "footer", "noscript", "aside", "form", "svg", "template")
    _EMPH = ("b", "strong", "kbd", "samp", "code")

    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self._skip = 0
        self._lists: List[List[Any]] = []
        self._emph = 0
        self._head = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\\n" + "#" * min(4, int(tag[1])) + " ")
            self._head += 1
        elif tag in ("ol", "ul"):
            self._lists.append([tag, 0])
            self.parts.append("\\n")
        elif tag == "li":
            if self._lists:
                self._lists[-1][1] += 1
                self.parts.append("\\n" + (f"{self._lists[-1][1]}. " if self._lists[-1][0] == "ol" else "- "))
            else:
                self.parts.append("\\n- ")
        elif tag in ("p", "div", "br", "tr", "section", "article", "pre", "table", "dt", "dd"):
            self.parts.append("\\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag in self._EMPH and not self._head:
            if self._emph == 0:
                self.parts.append("**")
            self._emph += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.parts.append("\\n")
            self._head = max(0, self._head - 1)
        elif tag in ("ol", "ul"):
            if self._lists:
                self._lists.pop()
            self.parts.append("\\n")
        elif tag in ("p", "li", "tr", "div", "pre", "table"):
            self.parts.append("\\n")
        elif tag in self._EMPH and self._emph:
            self._emph -= 1
            if self._emph == 0:
                self.parts.append("**")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(re.sub(r"\\s+", " ", data))


'''
s = s[:start] + new_cls + s[end:]
old_fn = s[s.index("def _html_to_text(raw: str) -> str:"):s.index("# -------------------------------------------------------------------------------------------------------------- chunks")]
new_fn = '''def _html_to_text(raw: str) -> str:
    p = _Strip()
    p.feed(raw)
    t = _html.unescape("".join(p.parts))
    t = re.sub(r"\\*\\*\\s*\\*\\*", "", t)                                   # empty emphasis
    t = re.sub(r"\\*\\*\\s+([^*\\n]+?)\\s*\\*\\*", r"**\\1**", t)                  # '** Save **' -> '**Save**'
    t = re.sub(r"[ \\t]+", " ", t)
    t = "\\n".join(line.strip() for line in t.splitlines())
    return re.sub(r"\\n{3,}", "\\n\\n", t).strip() + "\\n"


'''
s = s.replace(old_fn, new_fn, 1)
ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("manual_rag patched")
