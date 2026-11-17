"""
harvest.fact_cleaner -- clean and compress what the OCR read, with a vocabulary the POOL TEACHES ITSELF.

OCR of a menu returns things like 'CopytoclipboardasPNG' (spaces lost), 'Canvas Shape properties' (two lines glued), the same shortcut named three ways by three authors. Before such a
fact is written into the RAG it goes through here:

    vocabulary()        word frequencies learned from what the pool already knows: every command name in the RAG lexicon (2,600+ across 150+ apps), the archetypes' signal words, and the
                        transcripts of the videos already harvested. The more apps the pool has met, the better it cleans the next one.
    segment(word)       dynamic-programming word segmentation (maximum likelihood under the unigram frequencies): 'copytoclipboardas' -> 'copy to clipboard as'. A run-together token is only
                        split when EVERY piece is a known word; otherwise it is left alone (no invented words).
    clean_action(text)  camel / digit boundaries split, segmentation of unknown long tokens, acronyms kept ('PNG'), sentence case.
    clean_facts(facts)  cleaned names, junk dropped (too short, not mostly known words), and facts that are the same shortcut collapsed into one (the better-supported, better-spelled name wins).

Pure functions over the facts that `consolidate.ocr_edges` produces; no model, no network. `export_facts_rag` calls `clean_facts` before anything is written.
"""
from __future__ import annotations

import contextlib
import glob
import json
import math
import os
import re
import sqlite3
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DATA = os.environ.get("HOJAIGA_DATA", os.path.join("D:" + os.sep, "new_automation", "data"))
LEXICON_DB = os.path.join(DATA, "ai_root", "rag", "lexicon.db")
MAX_WORD = 24
SMALL_WORDS = {"to", "as", "in", "on", "of", "or", "an", "at", "by", "is", "it", "up", "no", "do", "go", "us", "my", "we", "me", "he", "be", "if", "so", "id", "ui", "ok"}
_CACHE: Dict[str, Counter] = {}


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z]{2,}", (text or "").lower())


def vocabulary(extra: Iterable[str] = (), refresh: bool = False) -> Counter:
    """Word counts from the pool: lexicon command names, archetype signal words, harvested transcripts, plus anything passed in."""
    if "v" in _CACHE and not refresh and not extra:
        return _CACHE["v"]
    c: Counter = Counter()
    with contextlib.suppress(Exception):
        db = sqlite3.connect(f"file:{LEXICON_DB}?mode=ro", uri=True)
        for (label,) in db.execute("SELECT label FROM commands"):
            c.update(_words(label))
        db.close()
    with contextlib.suppress(Exception):
        from core_organs.rag import archetypes as A
        for a in A.ARCHETYPES:
            for w in a["signals"] + a["roles"]:
                c.update(_words(w))
            for ph in list(a.get("grammar", [])) + list(a.get("templates", [])) + list(a.get("keys", {})) + list(a.get("traps", [])):
                c.update(_words(ph))
        for ph in list(getattr(A, "_STD_KEYS", {})) + list(getattr(A, "_UNIVERSAL_TRAPS", [])):
            c.update(_words(ph))
    with contextlib.suppress(Exception):
        for p in glob.glob(os.path.join(DATA, "video_graph", "_downloads", "*", "*.transcript.json")):
            for seg in json.load(open(p, encoding="utf-8")).get("segments", []):
                c.update(_words(seg.get("text", "")))
    for t in extra:
        c.update(_words(t))
    for w in ("a", "i"):                                                  # one-letter words the tokenizer drops
        c[w] += 1
    if not extra:
        _CACHE["v"] = c
    return c


def segment(token: str, vocab: Counter) -> Optional[List[str]]:
    """Most likely split of a lowercase run-together token into KNOWN words, or None if no split uses only known words."""
    s = token.lower()
    n = len(s)
    if n < 4 or s in vocab:
        return None
    total = float(sum(vocab.values()) + 1)
    best: List[float] = [0.0] + [math.inf] * n
    back = [0] * (n + 1)
    for i in range(1, n + 1):
        for j in range(max(0, i - MAX_WORD), i):
            w = s[j:i]
            f = vocab.get(w, 0)
            if f == 0 and len(w) > 1:
                continue
            if len(w) == 1 and w not in ("a", "i"):
                continue
            if len(w) == 2 and w not in SMALL_WORDS:                       # two-letter pieces only from genuine small words: 'wibble' must not become 'wi bb le'
                continue
            cost = best[j] - math.log((f + 0.5) / total) + (0.0 if len(w) > 2 else 1.5)          # short pieces are cheap to find anywhere: charge them a little
            if cost < best[i]:
                best[i], back[i] = cost, j
    if math.isinf(best[n]):
        return None
    out, i = [], n
    while i > 0:
        out.append(s[back[i]:i])
        i = back[i]
    out.reverse()
    return out if len(out) >= 2 else None


def clean_action(text: str, vocab: Optional[Counter] = None) -> str:
    vocab = vocab if vocab is not None else vocabulary()
    t = re.sub(r"[^A-Za-z0-9 /+&'.-]+", " ", text or "")
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)                          # CamelCase / glued capitals: 'toclipboardasPNG' -> 'toclipboardas PNG'
    t = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", t)
    words: List[str] = []
    for tok in t.split():
        if tok.isupper() and len(tok) <= 5 or not tok.isalpha() or tok.lower() in vocab:
            words.append(tok)
            continue
        seg = segment(tok, vocab)
        words.extend(seg if seg else [tok])
    out = " ".join(words).strip()
    if not out:
        return ""
    words = out.split()
    words = [w if w.isupper() and len(w) > 1 else w.lower() for w in words]
    words[0] = words[0] if words[0].isupper() and len(words[0]) > 1 else words[0].capitalize()
    return " ".join(words)


def plausible(word: str) -> bool:
    """Looks like a word: has a vowel, no run of 5 consonants, 2..14 letters."""
    w = word.lower()
    return 2 <= len(w) <= 14 and bool(re.search(r"[aeiouy]", w)) and not re.search(r"[^aeiouy]{5,}", w)


def mnemonic(action: str, windows_chord: str) -> bool:
    """The usual convention: the shortcut's letter is the action's first letter (Save = S, Quit = Q, Open = O, Find = F)."""
    key = windows_chord.split("+")[-1]
    w = re.findall(r"[A-Za-z]+", action or "")
    return bool(w) and len(key) == 1 and w[0][0].lower() == key and all(plausible(x) for x in w)


def known_ratio(text: str, vocab: Counter) -> float:
    ws = [w for w in re.findall(r"[A-Za-z]+", text or "")]
    if not ws:
        return 0.0
    return sum(1 for w in ws if w.lower() in vocab or (w.isupper() and len(w) <= 5)) / len(ws)


DISCOURSE = {"again", "here", "so", "okay", "ok", "yeah", "yes", "right", "actually", "like", "gonna", "going", "lets", "let", "um", "uh", "well", "just", "basically", "really", "very", "thing", "things",
             "something", "guys", "everyone", "welcome", "video", "today"}


def command_verbs(refresh: bool = False) -> Counter:
    """First words of the command names the pool knows ('Save as', 'Copy', 'Select all' -> save, copy, select), seen in >= 2 command names."""
    if "verbs" in _CACHE and not refresh:
        return _CACHE["verbs"]
    c: Counter = Counter()
    with contextlib.suppress(Exception):
        db = sqlite3.connect(f"file:{LEXICON_DB}?mode=ro", uri=True)
        for (label,) in db.execute("SELECT label FROM commands"):
            w = _words(label)
            if w:
                c[w[0]] += 1
        db.close()
    out = Counter({w: n for w, n in c.items() if n >= 2 and len(w) >= 3})
    _CACHE["verbs"] = out
    return out


def speech_ok(action: str, vocab: Optional[Counter] = None, verbs: Optional[Counter] = None) -> bool:
    """A spoken action name must look like a COMMAND: 1-7 words, no chit-chat words, (almost) all known words, and it starts with a verb the pool has seen starting command names
    ('undo any changes', 'select all', 'copy' pass; 'Gartam again so you' and 'Cutting into undo coefficient here find option here' do not). Speech recognition errs; a wrong NAME
    would attach a real chord to a nonsense label, so the stricter rule applies to what was only said."""
    vocab = vocab if vocab is not None else vocabulary()
    verbs = verbs if verbs is not None else command_verbs()
    ws = re.findall(r"[A-Za-z]+", action or "")
    if not 1 <= len(ws) <= 7 or any(w.lower() in DISCOURSE for w in ws):
        return False
    if known_ratio(action, vocab) < 0.85:
        return False
    head = ws[0].lower()
    return head in verbs or any(len(v) >= 3 and head.startswith(v) and len(head) - len(v) <= 3 for v in verbs)


def clean_facts(facts: Sequence[Dict[str, Any]], vocab: Optional[Counter] = None, min_known: float = 0.6) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """-> (cleaned facts, report). A fact keeps its chord and author count; its action is cleaned. Dropped: names with < 3 letters or mostly unknown words.
    Collapsed: several facts with the same Windows chord become one (more authors first, then the better-spelled, then the shorter name)."""
    vocab = vocab if vocab is not None else vocabulary()
    kept: Dict[str, Dict[str, Any]] = {}
    rep: Dict[str, Any] = {"renamed": [], "dropped": [], "merged": []}
    for f in facts:
        new = clean_action(f["action"], vocab)
        letters = sum(ch.isalpha() for ch in new)
        if letters < 3 or (known_ratio(new, vocab) < min_known and not mnemonic(new, f["windows"])):
            rep["dropped"].append((f["action"], new, round(known_ratio(new, vocab), 2)))
            continue
        if new != f["action"]:
            rep["renamed"].append((f["action"], new))
        g = dict(f, action=new)
        cur = kept.get(g["windows"])
        if cur is None:
            kept[g["windows"]] = g
            continue
        rank = lambda x: (x["videos"], known_ratio(x["action"], vocab), -len(x["action"]))
        win, lose = (g, cur) if rank(g) > rank(cur) else (cur, g)
        kept[g["windows"]] = win
        rep["merged"].append((lose["action"], win["action"], g["windows"]))
    return sorted(kept.values(), key=lambda f: (-f["videos"], f["windows"])), rep
