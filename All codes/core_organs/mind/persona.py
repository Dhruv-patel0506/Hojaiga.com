"""
persona -- who is this for, in which language, in what register, how long? And does a draft fit that?

    read_message(text)                      -> language, register, urgency, mood, addressee, how they sign off   (from THEIR words, by measurement)
    style_brief(incoming, channel, relationship, intent, language)  -> the brief a writer (the local Qwen) is given
    compose_prompt(brief, facts)            -> the prompt text for that writer
    check_draft(draft, brief)               -> what is wrong with a draft (wrong language, too long, placeholders, tone off, clichés)

No model call in here and no app names: a channel is a set of conventions (length, greeting, hashtags, emoji), a relationship is a register, and the incoming message is measured.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---- language: script first, then stop-words for Latin-script text (Hinglish is its own thing: Hindi written in English letters) -----------------------------
_SCRIPTS: List[Tuple[str, str]] = [("hi", r"[ऀ-ॿ]"), ("bn", r"[ঀ-৿]"), ("ta", r"[஀-௿]"), ("te", r"[ఀ-౿]"), ("gu", r"[઀-૿]"), ("pa", r"[਀-੿]"),
                                    ("ar", r"[؀-ۿ]"), ("he", r"[֐-׿]"), ("ru", r"[Ѐ-ӿ]"), ("el", r"[Ͱ-Ͽ]"), ("th", r"[฀-๿]"),
                                    ("ja", r"[぀-ヿ]"), ("ko", r"[가-힯]"), ("zh", r"[一-鿿]")]
_STOP: Dict[str, str] = {
    "en": "the and to of in is that it for you with on this are be have not as at your we i will can from or by was if so but they my our please thanks thank",
    "hinglish": "hai hain nahi nahin kya aap tum mujhe mera meri hum kar karo karna kaise kyun kyu bhai yaar acha accha theek thik abhi bhej bhejo dena do mai main aur ya toh to se ko ka ke ki",
    "es": "el la los las de que y en un una es por con para no se su al lo como mas pero sus le ya o este si porque esta entre cuando muy sin sobre tambien me hasta hay donde",
    "fr": "le la les de des du un une et est en que qui dans pour pas sur au avec ce il elle nous vous ils sont mais ou comme je tu ne se plus par bien tout",
    "de": "der die das und ist in den von zu mit sich des auf fur nicht ein eine als auch es an werden aus er hat dass sie nach wird bei einer um am sind noch wie",
    "pt": "o a os as de que e do da em um uma para com nao e por mais se na no dos das como mas foi ao ele ela tambem voce ja mesmo",
    "it": "il lo la i gli le di che e un una in per con non si da del della come ma sono anche piu al suo",
}
_STOPSETS = {k: set(v.split()) for k, v in _STOP.items()}
_LANG_NAME = {"en": "English", "hinglish": "Hinglish (Hindi in English letters)", "hi": "Hindi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "gu": "Gujarati", "pa": "Punjabi", "ar": "Arabic", "he": "Hebrew",
              "ru": "Russian", "el": "Greek", "th": "Thai", "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese", "it": "Italian", "und": "unknown"}


def detect_language(text: str) -> Dict[str, Any]:
    t = text or ""
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return {"code": "und", "name": _LANG_NAME["und"], "confidence": 0.0, "basis": "no letters"}
    for code, rx in _SCRIPTS:
        n = len(re.findall(rx, t))
        if n / len(letters) > 0.3:
            return {"code": code, "name": _LANG_NAME[code], "confidence": round(min(1.0, n / len(letters)), 2), "basis": "script"}
    words = re.findall(r"[a-zà-ÿ']+", t.lower())
    words = [re.sub(r"[àáâãä]", "a", re.sub(r"[èéêë]", "e", re.sub(r"[ìíîï]", "i", re.sub(r"[òóôõö]", "o", re.sub(r"[ùúûü]", "u", w))))) for w in words]
    if not words:
        return {"code": "und", "name": _LANG_NAME["und"], "confidence": 0.0, "basis": "no words"}
    scores = {k: sum(1 for w in words if w in s) / len(words) for k, s in _STOPSETS.items()}
    code = max(scores, key=lambda k: scores[k])
    if scores[code] < 0.12:
        return {"code": "und", "name": _LANG_NAME["und"], "confidence": round(scores[code], 2), "basis": "too few function words"}
    second = sorted(scores.values())[-2]
    return {"code": code, "name": _LANG_NAME[code], "confidence": round(min(1.0, scores[code] / max(second + 1e-6, 0.05) / 3 + scores[code]), 2), "basis": "function words"}


# ---- register ---------------------------------------------------------------------------------------------------------------------------------------------------
_FORMAL = re.compile(r"\b(dear|sincerely|regards|respectfully|kindly|please find|attached|pursuant|hereby|would you be so kind|i would like to|i am writing to|thank you for your|best regards|yours faithfully|sir|madam|mr\.|ms\.|dr\.|prof\.)\b", re.I)
_CASUAL = re.compile(r"\b(hey|hiya|yo|sup|gonna|wanna|gotta|lol|lmao|haha|btw|bro|dude|bhai|yaar|ok|okay|cool|thx|pls|plz|omg|nope|yeah|yep|cheers)\b", re.I)
_URGENT = re.compile(r"\b(asap|urgent|urgently|immediately|right away|today|by eod|end of day|deadline|as soon as possible|time[\s-]*sensitive|now)\b|!!+", re.I)
_UPSET = re.compile(r"\b(unacceptable|disappointed|frustrated|angry|furious|terrible|worst|complain\w*|refund|never again|ridiculous|still waiting|no response|not happy|upset|disgusted)\b", re.I)
_THANKS = re.compile(r"\b(thanks|thank you|appreciate|grateful|cheers|thx)\b", re.I)
_QUESTION = re.compile(r"\?")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_GREET = re.compile(r"^\s*(dear|hi|hello|hey|hiya|good\s+(?:morning|afternoon|evening)|namaste|greetings)\b[ ,]*([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*)?)?", re.I)
_SIGNOFF = re.compile(r"(?:^|\n)\s*(best regards|kind regards|warm regards|regards|sincerely|yours sincerely|yours faithfully|thanks|thank you|cheers|best|thanks and regards|many thanks|take care|ttyl)\b[ ,.!]*", re.I)
_CLICHE = re.compile(r"\b(i hope this (?:email|message) finds you well|circle back|synergy|touch base|per my last email|going forward|at the end of the day|think outside the box|low[\s-]hanging fruit|leverage|game[\s-]changer|delve|in today's fast[\s-]paced world|unlock the power)\b", re.I)
_PLACEHOLDER = re.compile(r"(\[[A-Za-z ]{2,30}\]|\{\{.*?\}\}|<[A-Za-z ]{2,30}>|lorem ipsum|insert .{1,20} here|your name here|xxx+)", re.I)


def _sender(text: str) -> str:
    """The name under the sign-off ('Regards,\nPriya Shah'): who to greet in the reply."""
    lines = [l.strip() for l in (text or "").strip().splitlines() if l.strip()]
    for i, l in enumerate(lines):
        if _SIGNOFF.match("\n" + l) and i + 1 < len(lines):
            cand = lines[i + 1]
            if 1 <= len(cand.split()) <= 3 and re.fullmatch(r"[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,2}", cand):
                return cand
    m = re.search(r"(?:^|\n)\s*(?:best regards|kind regards|regards|sincerely|thanks|cheers|best)[ ,.!]+([A-Z][\w.'-]*)\s*$", (text or "").strip(), re.I)
    return m.group(1) if m and m.group(1)[:1].isupper() else ""


def read_message(text: str) -> Dict[str, Any]:
    """Measure an incoming message. Everything returned is evidence from the text, not a guess about the person."""
    t = text or ""
    words = re.findall(r"\w+", t)
    formal = len(_FORMAL.findall(t))
    casual = len(_CASUAL.findall(t)) + len(_EMOJI.findall(t)) + (1 if re.search(r"\b[a-z]+\b", t) and not re.search(r"[A-Z]", t[:1] or "A") else 0)
    contractions = len(re.findall(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", t))
    caps = sum(1 for w in words if len(w) > 3 and w.isupper())
    score = (formal * 2.0 - casual * 1.6 - contractions * 0.4 + (0.5 if len(words) > 60 else 0) - (0.4 if len(words) < 12 else 0)) / max(1.0, len(words) ** 0.35)
    register = "formal" if score > 0.55 else "casual" if score < -0.35 else "neutral"
    if score < -1.0:
        register = "very casual"
    lang = detect_language(t)
    return {"language": lang, "register": register, "register_score": round(score, 2), "urgent": bool(_URGENT.search(t)), "upset": bool(_UPSET.search(t) or caps >= 3),
            "grateful": bool(_THANKS.search(t)), "asks": len(_QUESTION.findall(t)), "words": len(words), "emoji": len(_EMOJI.findall(t)), "sender": _sender(t),
            "greeting": (_GREET.match(t).group(1).lower() if _GREET.match(t) else ""), "signoff": (_SIGNOFF.findall(t)[-1].lower() if _SIGNOFF.findall(t) else "")}


# ---- channels and relationships: conventions, as data ---------------------------------------------------------------------------------------------------------
CHANNELS: Dict[str, Dict[str, Any]] = {
    "email": {"max_words": 220, "greeting": True, "signoff": True, "emoji": False, "hashtags": 0, "exclaim": 1, "shape": "subject line, greeting, the point in the first two sentences, one clear ask, sign-off with name"},
    "email_reply": {"max_words": 150, "greeting": True, "signoff": True, "emoji": False, "hashtags": 0, "exclaim": 1, "shape": "answer the questions in the order asked, then the next step, short"},
    "linkedin_post": {"max_words": 260, "greeting": False, "signoff": False, "emoji": False, "hashtags": 3, "exclaim": 1, "shape": "a first line that stands alone as the hook, short paragraphs, one concrete example or number, a closing question or takeaway, up to 3 hashtags at the end"},
    "linkedin_dm": {"max_words": 90, "greeting": True, "signoff": False, "emoji": False, "hashtags": 0, "exclaim": 0, "shape": "who you are in one line, why them, one specific ask, easy to say no to"},
    "chat": {"max_words": 60, "greeting": False, "signoff": False, "emoji": True, "hashtags": 0, "exclaim": 2, "shape": "short lines, answer first"},
    "team_chat": {"max_words": 90, "greeting": False, "signoff": False, "emoji": True, "hashtags": 0, "exclaim": 2, "shape": "the update or ask first, then details; name an owner and a date for any ask"},
    "sms": {"max_words": 35, "greeting": False, "signoff": False, "emoji": True, "hashtags": 0, "exclaim": 1, "shape": "one idea per message"},
    "support_ticket": {"max_words": 180, "greeting": True, "signoff": True, "emoji": False, "hashtags": 0, "exclaim": 0, "shape": "what happened, what you expected, steps to reproduce, what you already tried, what you need"},
    "cover_letter": {"max_words": 320, "greeting": True, "signoff": True, "emoji": False, "hashtags": 0, "exclaim": 0, "shape": "why this role, two matching achievements with numbers, why this company, a close"},
    "tweet": {"max_words": 45, "greeting": False, "signoff": False, "emoji": True, "hashtags": 2, "exclaim": 1, "shape": "one idea, no filler"},
    "blog_post": {"max_words": 900, "greeting": False, "signoff": False, "emoji": False, "hashtags": 0, "exclaim": 2, "shape": "title, a lead that states the payoff, headed sections, an example in each, a short conclusion"},
    "document": {"max_words": 1200, "greeting": False, "signoff": False, "emoji": False, "hashtags": 0, "exclaim": 0, "shape": "title, purpose, headed sections, tables for comparisons, numbered steps for procedures, a summary on top"},
}
_REL_REGISTER = {"boss": "formal", "manager": "formal", "client": "formal", "customer": "formal", "recruiter": "formal", "professor": "formal", "teacher": "formal", "stranger": "formal", "unknown": "formal", "public": "neutral",
                 "investor": "formal", "interviewer": "formal", "colleague": "neutral", "teammate": "neutral", "vendor": "neutral", "friend": "casual", "family": "casual", "partner": "casual"}


def style_brief(incoming: str = "", channel: str = "email", relationship: str = "unknown", intent: str = "", language: str = "") -> Dict[str, Any]:
    """The brief the writer works from. The register mirrors the other person's, but never drops below what the relationship and the channel need."""
    ch = CHANNELS.get(channel) or CHANNELS["email"]
    rel = (relationship or "unknown").lower()
    seen = read_message(incoming) if incoming else {}
    want = _REL_REGISTER.get(rel, "neutral")
    their = seen.get("register") if seen else ""
    order = ["very casual", "casual", "neutral", "formal"]
    register = want
    if their and want != "formal":
        register = order[max(order.index(want) if want in order else 2, 0)]
        if their in order and order.index(their) < order.index(register):
            register = order[max(order.index(their), order.index(register) - 1)]             # mirror, at most one step more relaxed than the relationship allows
    if channel in ("linkedin_post", "linkedin_dm", "cover_letter", "support_ticket", "document") and register in ("casual", "very casual"):
        register = "neutral"
    lang_code = language or (seen.get("language", {}).get("code") if seen else "") or "en"
    if lang_code == "und":
        lang_code = "en"
    mood = "calm"
    do: List[str] = []
    dont: List[str] = ["no placeholders such as [Name]", "no filler openers", "no invented facts, numbers or names that were not given"]
    if seen.get("upset"):
        mood = "upset"
        do += ["open by acknowledging the problem in one sentence", "say what will happen next and by when", "keep it calm: no exclamation marks, no blame"]
        dont += ["no defensiveness", "no jokes"]
    if seen.get("urgent"):
        do += ["lead with the answer or the action", "keep it short"]
    if seen.get("grateful"):
        do += ["acknowledge the thanks briefly"]
    if seen.get("asks"):
        do += [f"answer all {seen['asks']} question(s) in the order asked"]
    if register == "formal":
        dont += ["no slang or emoji", "no contractions"]
    elif register in ("casual", "very casual"):
        dont += ["no stiff phrases like 'I am writing to inform you'"]
    max_words = ch["max_words"] if not seen.get("urgent") else int(ch["max_words"] * 0.7)
    if seen and seen.get("words") and channel in ("email_reply", "chat", "team_chat", "sms"):
        max_words = min(max_words, max(25, int(seen["words"] * 1.6)))                      # a reply is not longer than twice what it answers
    return {"channel": channel, "relationship": rel, "language": lang_code, "language_name": _LANG_NAME.get(lang_code, lang_code), "register": register, "mood": mood, "max_words": max_words,
            "greeting": ch["greeting"], "signoff": ch["signoff"], "emoji_ok": ch["emoji"] and register != "formal", "hashtags_max": ch["hashtags"], "exclaim_max": 0 if mood == "upset" else ch["exclaim"],
            "shape": ch["shape"], "intent": intent, "do": do, "dont": dont, "mirrors": their or "", "greet_name": seen.get("sender", "") if seen else ""}


def compose_prompt(brief: Dict[str, Any], facts: Sequence[str] = (), incoming: str = "") -> str:
    """Text for the local writer. The facts are the ONLY content it may use."""
    lines = [f"Write a {brief['channel'].replace('_', ' ')} for a {brief['relationship']}.",
             f"Language: {brief['language_name']}. Register: {brief['register']}. Maximum {brief['max_words']} words.",
             f"Shape: {brief['shape']}."]
    if brief.get("intent"):
        lines.append(f"Purpose: {brief['intent']}")
    if brief["do"]:
        lines.append("Do: " + "; ".join(brief["do"]) + ".")
    lines.append("Do not: " + "; ".join(brief["dont"]) + ".")
    if brief["hashtags_max"]:
        lines.append(f"At most {brief['hashtags_max']} hashtags, at the end.")
    if incoming:
        lines.append("They wrote:\n\"\"\"\n" + incoming.strip()[:1500] + "\n\"\"\"")
    lines.append("Use only these facts:\n" + "\n".join(f"- {f}" for f in facts) if facts else "No facts were given: ask for the missing details instead of inventing them.")
    return "\n".join(lines)


def check_draft(draft: str, brief: Dict[str, Any]) -> Dict[str, Any]:
    """Problems with a draft against its brief. An empty list = fits."""
    d = draft or ""
    problems: List[str] = []
    words = len(re.findall(r"\w+", d))
    if words > brief["max_words"] * 1.1:
        problems.append(f"too long: {words} words, brief says at most {brief['max_words']}")
    lang = detect_language(d)
    if lang["code"] not in ("und", brief["language"]) and words >= 8:
        problems.append(f"wrong language: wrote {lang['name']}, brief says {brief['language_name']}")
    if _PLACEHOLDER.search(d):
        problems.append("contains a placeholder: " + _PLACEHOLDER.search(d).group(0))
    if brief["greeting"] and not _GREET.match(d):
        problems.append("no greeting")
    if brief["signoff"] and not _SIGNOFF.search(d):
        problems.append("no sign-off")
    if not brief["greeting"] and brief["channel"] in ("linkedin_post", "tweet", "blog_post", "document") and _GREET.match(d):
        problems.append("starts with a greeting; this channel starts with the point")
    if not brief["emoji_ok"] and _EMOJI.search(d):
        problems.append("emoji where the register does not allow it")
    if d.count("!") > brief["exclaim_max"]:
        problems.append(f"{d.count('!')} exclamation marks, at most {brief['exclaim_max']}")
    tags = len(re.findall(r"#\w+", d))
    if tags > brief["hashtags_max"]:
        problems.append(f"{tags} hashtags, at most {brief['hashtags_max']}")
    if _CLICHE.search(d):
        problems.append("filler phrase: " + _CLICHE.search(d).group(0))
    if brief["register"] == "formal" and (_CASUAL.search(d) or re.search(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", d) and len(re.findall(r"\b\w+'(?:t|re|ve|ll|d|m)\b", d)) >= 2):
        problems.append("too casual for a formal reader")
    if brief["register"] in ("casual", "very casual") and len(_FORMAL.findall(d)) >= 2:
        problems.append("too stiff for a casual reader")
    if brief["mood"] == "upset" and not re.search(r"\b(sorry|apolog\w+|understand|i can see|that must|frustrat\w+|thank you for (?:letting|telling|raising|flagging))\b", d, re.I):
        problems.append("the reader is upset and the draft never acknowledges it")
    return {"fits": not problems, "problems": problems, "words": words, "language": lang["code"]}
