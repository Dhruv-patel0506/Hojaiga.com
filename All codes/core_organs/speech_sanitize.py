"""
speech_sanitize -- what the voice may say: the answer, never the prompt machinery around it.

    clean_for_speech(text) -> str

Strips chat-template tokens (<|im_start|>, [INST], <<SYS>>), role headers ('user:' 'assistant:' 'system:' at the start of a line or of the text), the echoed prompt that precedes the last assistant turn,
the persona preamble ('You are HoJaiga Tutor ...'), Set-of-Marks markers ('● [12]'), markdown emphasis / code fences / bullets, and bare URLs. A text that is only machinery becomes ''.
"""
from __future__ import annotations

import re

_TOKENS = re.compile(r"<\|[^|>]{1,40}\|>|\[/?INST\]|<</?SYS>>|</?s>|<(?:start|end)_of_turn>", re.I)
_ROLE = re.compile(r"(?im)^\s*(?:user|assistant|system|human|ai|model)\s*:\s*")
_PREAMBLE = re.compile(r"(?is)\byou are (?:the )?hojaiga\b[^.!?\n]*[.!?]?")
_SOM = re.compile(r"[\u25CF\u2022]?\s*\[\s*\d{1,3}\s*\]")
_FENCE = re.compile(r"```.*?```", re.S)
_URL = re.compile(r"https?://\S+")


def clean_for_speech(text: str) -> str:
    t = str(text or "")
    t = _TOKENS.sub(" ", t)
    last = None
    for m in re.finditer(r"(?im)(?:^|\s)assistant\s*:\s*", t):                  # an echoed prompt: only what follows the LAST assistant header is the answer
        last = m
    if last is not None and re.search(r"(?im)(?:^|\s)(?:user|system)\s*:", t[:last.start()] or ""):
        t = t[last.end():]
    t = re.sub(r"(?im)^\s*(?:user|assistant|system|human|ai|model)\s*$", " ", t)                 # a role name alone on its line (what is left of a template token)
    t = _ROLE.sub("", t)
    t = _PREAMBLE.sub(" ", t)
    t = _FENCE.sub(" ", t)
    t = _SOM.sub(" ", t)
    t = _URL.sub(" ", t)
    t = re.sub(r"[*_`#>]+", "", t)
    t = re.sub(r"(?m)^\s*[-+]\s+", "", t)
    t = re.sub(r"\s+", " ", t).strip(" \t\r\n:-")
    return t
