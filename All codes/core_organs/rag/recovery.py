"""
rag.recovery -- Sub-RAG 5: Error & Recovery Playbooks (DESIGN.md section 5.5).

popup_policy stays the decision engine; this is its knowledge store. A failure is recognised by (1) its exact signature (popup_policy.fingerprint), (2) (app, failure_code), (3) FTS +
vector over the masked message (app rows first, then global '*' rows), and answered with an ordered resolution or an honest escalation.

HARD RULE (hojaiga-popup-defense law): class elevation / destructive / payment is needs_human=True whatever the success history says. It is enforced when a playbook is written AND when it
is read, so no stored row, imported pack or learned outcome can lift it.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import config as C
from . import lt
from .types import Evidence, Outcome, UpsertReport

HUMAN_CLASSES = {"elevation", "destructive", "payment"}
_CLASS_RULES = [
    ("elevation", r"administrator|elevat|uac|run as|requires? (?:admin|elevation)|user account control"),
    ("payment", r"purchase|subscription|payment|billing|credit card|checkout|upgrade to (?:pro|premium)|buy now"),
    ("destructive", r"permanently (?:delete|remove|erase)|cannot be undone|erase|format|factory reset|are you sure you want to delete|overwrite"),
    ("file_locked", r"in use|being used by another|locked|sharing violation|cannot access the file"),
    ("unsaved_changes", r"save changes|do you want to save|unsaved|not been saved"),
    ("permission", r"access (?:is )?denied|permission|not allowed|not authorized|blocked by"),
    ("missing_dependency", r"missing|could not (?:find|load)|not installed|dll|runtime|redistributable"),
    ("network", r"network|connection|offline|timed out|server|proxy|certificate"),
    ("crash", r"stopped working|not responding|has crashed|fatal|unhandled exception"),
    ("automation_blocked", r"automation|blocked|bot|captcha|unusual activity"),
]
_NUM = re.compile(r"\d+")
_PATHY = re.compile(r"(?:[A-Za-z]:[\\/][^\s\"']*|\\\\[^\s\"']+|/[\w.-]+(?:/[\w.-]+)+)")
_MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_QUOTED = re.compile(r"[\"'“‘][^\"'”’]{1,60}[\"'”’]")

# strategy playbooks for failures that are not popups. Phantom-alpha capture is deliberately NOT here (decision 2026-10-16).
SEEDS = [
    {"failure_code": "uia_blocked", "message_template": "accessibility tree is empty or blocked for this application", "class_": "automation_blocked",
     "resolution": [{"action": "perceive", "mode": "visual_som"}, {"action": "input", "mode": "posted_or_os_level"}]},
    {"failure_code": "capture_blank", "message_template": "window capture returned a blank frame", "class_": "app_specific",
     "resolution": [{"action": "capture", "mode": "restore_capture_ladder"}]},
    {"failure_code": "no_effect", "message_template": "the step produced no observable change", "class_": "app_specific",
     "resolution": [{"action": "route", "mode": "next_in_route_order"}]},
    {"failure_code": "state_mismatch", "message_template": "the screen is not the state the plan expected", "class_": "app_specific",
     "resolution": [{"action": "localize"}, {"action": "replan"}]},
    {"failure_code": "timeout", "message_template": "the application did not respond within the step budget", "class_": "app_specific",
     "resolution": [{"action": "wait", "seconds": 2}, {"action": "localize"}, {"action": "retry_once"}]},
    {"failure_code": "script_error", "message_template": "the injected script raised an error", "class_": "app_specific",
     "resolution": [{"action": "read_error"}, {"action": "fallback", "mode": "hotkey_or_ui_route"}]},
    {"failure_code": "popup:elevation", "message_template": "this action requires administrator permission", "class_": "elevation", "resolution": []},
    {"failure_code": "popup:payment", "message_template": "this action requires a purchase or subscription", "class_": "payment", "resolution": []},
    {"failure_code": "popup:unsaved_changes", "message_template": "do you want to save changes", "class_": "unsaved_changes",
     "resolution": [{"action": "click_button", "target_role": "cancel"}]},
]


def mask(text: str) -> str:
    s = _MAIL.sub("<email>", text or "")
    s = _PATHY.sub("<path>", s)
    s = _QUOTED.sub("<name>", s)
    s = _NUM.sub("#", s)
    return re.sub(r"\s+", " ", s).strip().lower()[:400]


def classify_text(text: str) -> str:
    low = (text or "").lower()
    for cls, rx in _CLASS_RULES:
        if re.search(rx, low):
            return cls
    return "app_specific"


def signature_of(popup: Any) -> str:
    """popup_policy.fingerprint for a PopupView; the same md5(class|kind|title|buttons) construction for a plain dict."""
    if popup is None:
        return ""
    try:
        if hasattr(popup, "class_name") and hasattr(popup, "kind"):
            from core_organs import popup_policy as PP
            return PP.fingerprint(popup)
    except Exception:
        pass
    d = popup if isinstance(popup, dict) else {}
    title = re.sub(r"\d+", "#", str(d.get("title", "")).lower())
    key = "|".join([str(d.get("class_name", "")).lower(), str(d.get("kind", "modal_window")), title, ",".join(d.get("buttons", []))])
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def sig_id(app_key: str, signature: str, failure_code: str = "") -> str:
    return hashlib.sha1(f"{app_key or '*'}|{signature}|{failure_code}".encode("utf-8")).hexdigest()


def _p(r: Dict[str, Any]) -> float:
    a, b = C.PRIORS.get(r.get("trust", "seed"), (1, 1))
    return (r.get("n_ok", 0) + a) / (r.get("n_ok", 0) + r.get("n_fail", 0) + a + b)


class Recovery:
    name = "recovery"

    def __init__(self, st):
        self.st = st

    def seed(self) -> int:
        recs = [{"app_key": "*", "toolkit": "", "signature": "", "failure_code": s["failure_code"], "message_template": s["message_template"], "class_": s["class_"],
                 "resolution": s["resolution"], "source": "seed", "trust": "seed"} for s in SEEDS]
        return self.upsert(recs).inserted + 0

    def upsert(self, records: Iterable[Dict[str, Any]]) -> UpsertReport:
        rows = []
        for r in records:
            r = dict(r)
            r["app_key"] = r.get("app_key") or "*"
            r["message_template"] = mask(r.get("message_template", ""))
            r["class_"] = r.get("class_") or r.get("class") or classify_text(r["message_template"])
            r.pop("class", None)
            res = r.pop("resolution", None)
            if res is not None:
                r["resolution_json"] = json.dumps(res, sort_keys=True)
            r["needs_human"] = bool(r.get("needs_human", False)) or r["class_"] in HUMAN_CLASSES          # the hard rule, at write time
            r["sig_id"] = r.get("sig_id") or sig_id(r["app_key"], r.get("signature", ""), r.get("failure_code", ""))
            rows.append(r)
        ins, upd, deg = lt.upsert(self.st, "error_playbooks", rows, "message_template", lambda x: x["message_template"])
        for a in {r["app_key"] for r in rows}:
            self.st.bump(f"recovery:{a}")
        return UpsertReport(self.name, ins, upd, 0, deg)

    def _overlay(self, r: Dict[str, Any]) -> Dict[str, Any]:
        s = self.st.sql("learn").one("SELECT n_ok, n_fail FROM playbook_stats WHERE sig_id=?", (r["sig_id"],))
        if s:
            r["n_ok"], r["n_fail"] = int(r["n_ok"]) + s["n_ok"], int(r["n_fail"]) + s["n_fail"]
        return r

    def _evidence(self, r: Dict[str, Any], app_key: str, score: float = 0.0) -> Evidence:
        r = self._overlay(dict(r))
        human = bool(r["needs_human"]) or r["class_"] in HUMAN_CLASSES               # ... and again at read time
        res = json.loads(r["resolution_json"] or "[]")
        return Evidence("recovery", app_key or r["app_key"], "playbook", r["message_template"], [], {"sig_id": r["sig_id"], "failure_code": r["failure_code"], "class": r["class_"],
                        "resolution": [] if human and r["class_"] in HUMAN_CLASSES else res, "needs_human": human, "global": r["app_key"] == "*"},
                        r["trust"], round(_p(r), 4), 0.0, "allow", f"playbook:{r['sig_id'][:10]}:{r['source']}", "", score)

    def lookup(self, app_key: str, popup: Any = None, failure_code: str = "", message: str = "", toolkit: str = "", limit: int = 3) -> List[Evidence]:
        out: List[Evidence] = []
        seen = set()

        def add(rows: Sequence[Dict[str, Any]], score: float = 1.0) -> None:
            for r in rows:
                if r["sig_id"] not in seen:
                    seen.add(r["sig_id"])
                    out.append(self._evidence(r, app_key, score))
        sig = signature_of(popup) if popup is not None else ""
        if sig:
            for a in (app_key, "*"):
                add(lt.fetch(self.st, "error_playbooks", f"app_key = {lt.q(a)} AND signature = {lt.q(sig)}", 5), 1.0)
        code = failure_code or ("popup:" + classify_text(message) if popup is not None else "")
        if code:
            for a in (app_key, "*"):
                add(lt.fetch(self.st, "error_playbooks", f"app_key = {lt.q(a)} AND failure_code = {lt.q(code)}", 5), 0.8)
        if message and len(out) < limit:
            m = mask(message)
            for r in lt.search(self.st, "error_playbooks", m, [app_key, "*"], limit=limit):
                add([r], r["_rrf"])
        out.sort(key=lambda e: (e.payload["global"], -e.confidence))
        return out[:limit]

    def observe(self, o: Outcome) -> Optional[str]:
        """A tried resolution reports back: success strengthens the playbook; failure weakens it; an unseen popup resolved by a human-approved action becomes a new playbook."""
        res = o.resolution
        if not res:
            return None
        sid = res.get("sig_id")
        if sid:
            rows = lt.fetch(self.st, "error_playbooks", f"sig_id = {lt.q(sid)}", 1, ["sig_id", "app_key"])
            if rows:
                db = self.st.sql("learn")
                with db.lock:
                    db.execute("INSERT OR IGNORE INTO playbook_stats(sig_id) VALUES(?)", (sid,))
                    db.execute("UPDATE playbook_stats SET n_ok=n_ok+?, n_fail=n_fail+? WHERE sig_id=?", (1 if res.get("ok") else 0, 0 if res.get("ok") else 1, sid))
                    db.commit()
                self.st.bump(f"recovery:{rows[0]['app_key']}")
                return sid
        if res.get("ok") and res.get("actions") and o.popup is not None:
            msg = str(res.get("message", ""))
            self.upsert([{"app_key": o.app_key, "signature": signature_of(o.popup), "failure_code": o.failure_code or "popup:" + classify_text(msg), "message_template": msg,
                          "resolution": res["actions"], "source": "observed", "trust": "learned", "n_ok": 1}])
            return sig_id(o.app_key, signature_of(o.popup), o.failure_code or "popup:" + classify_text(msg))
        return None

    def stats(self, app_key: str = "") -> Dict[str, Any]:
        return {"playbooks": int(self.st.table("error_playbooks").count_rows(lt.where_app(app_key))) if self.st.count("error_playbooks") else 0}

    def forget_app(self, app_key: str) -> int:
        return lt.drop_app(self.st, "error_playbooks", app_key) if app_key != "*" else 0
