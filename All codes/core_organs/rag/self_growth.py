"""
rag.self_growth -- the memory that grows from what worked and repairs itself when what worked stops working.

GROW   after a step was done AND checked (the screen changed the way the step said it would), keep it as a fast path:
           (parent_state, control_locator, icon_hash, action, post_state)
       parent_state / post_state = the set of control labels on the screen before / after (order-free signature), control_locator = name + type + centre + box, icon_hash = dHash of the control's picture.
       The crop itself goes to data/experience_replay/ and a line to data/experience_replay.jsonl (the next training round reads it).

REUSE  lookup(app, parent_labels, name): the best stored fast path whose parent screen is >= 60% the same screen and whose control carries that name.

HEAL   run(app, name, parent_labels, perform, verify, rollback, fallbacks):
           1. try the stored locator; perform it; verify against the stored post_state (and any extra check the caller gives)
           2. fails -> rollback (Escape / undo, the caller's), count the failure, and walk the fallbacks IN ORDER -- UIA by name, DOM by name, the Qwen eye -- each returns a fresh locator
           3. the first fallback whose locator performs AND verifies PATCHES the stored row (new locator, new icon hash, healed_from = the old locator), resets the failure count and appends a 'healed' line to the replay
           4. nothing works -> the row loses trust after FAIL_LIMIT consecutive failures (demoted, never silently deleted) and the caller gets {'ok': False}
       A patched row is on disk before run() returns, so the next process starts healed.

Nothing here knows an application; the callbacks are the only contact with the screen.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

FAIL_LIMIT = 3
PARENT_MATCH = 0.6
_BASE = os.path.join("D:" + os.sep, "new_automation", "data")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def signature(labels: Sequence[str]) -> List[str]:
    return sorted({norm(l) for l in labels if norm(l)})[:40]


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(len(sa | sb), 1)


def icon_hash(crop: Any) -> str:
    """dHash64 of a PIL image as hex ('' when there is no picture)."""
    if crop is None:
        return ""
    try:
        from core_organs.rag.icons import dhash64
        return format(int(dhash64(crop)), "016x")
    except Exception:
        return ""


class SelfGrowth:
    def __init__(self, db_path: str = "", replay_path: str = "", replay_dir: str = "", rag: Any = None):
        self.db_path = db_path or os.path.join(_BASE, "self_growth.sqlite")
        self.replay_path = replay_path or os.path.join(_BASE, "experience_replay.jsonl")
        self.replay_dir = replay_dir or os.path.join(_BASE, "experience_replay")
        self.rag = rag
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS ui_fast(
            key TEXT PRIMARY KEY, app_key TEXT, name TEXT, parent_sig TEXT, locator TEXT, icon_hash TEXT, action TEXT, post_sig TEXT,
            n_ok INTEGER DEFAULT 0, n_fail INTEGER DEFAULT 0, trust TEXT DEFAULT 'learned', healed_from TEXT DEFAULT '', created REAL, last_ok REAL, last_fail REAL)""")
        self.db.commit()

    # ---- grow ---------------------------------------------------------------------------------------------------------------------------------------
    def key_of(self, app_key: str, parent_labels: Sequence[str], name: str, action: str) -> str:
        return hashlib.sha1("|".join([app_key, ",".join(signature(parent_labels)), norm(name), action]).encode()).hexdigest()

    def _replay(self, rec: Dict[str, Any], crop: Any = None) -> str:
        os.makedirs(os.path.dirname(self.replay_path) or ".", exist_ok=True)
        path = ""
        if crop is not None:
            try:
                os.makedirs(self.replay_dir, exist_ok=True)
                path = os.path.join(self.replay_dir, f"{int(time.time() * 1000)}_{hashlib.sha1(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()[:8]}.png")
                crop.save(path)
            except Exception:
                path = ""
        rec = dict(rec, ts=time.time(), crop=path)
        with open(self.replay_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return path

    def learn(self, app_key: str, parent_labels: Sequence[str], locator: Dict[str, Any], action: str, post_labels: Sequence[str], crop: Any = None, verified: bool = True) -> str:
        """Keep a step that was done and checked. Unverified steps are not kept (a guess must not become a fast path)."""
        if not verified:
            return ""
        name = str(locator.get("name", ""))
        k = self.key_of(app_key, parent_labels, name, action)
        ih = icon_hash(crop)
        with self._lock:
            row = self.db.execute("SELECT n_ok FROM ui_fast WHERE key=?", (k,)).fetchone()
            if row:
                self.db.execute("UPDATE ui_fast SET n_ok=n_ok+1, n_fail=0, last_ok=?, locator=?, icon_hash=?, post_sig=? WHERE key=?",
                                (time.time(), json.dumps(locator), ih, json.dumps(signature(post_labels)), k))
            else:
                self.db.execute("INSERT INTO ui_fast(key,app_key,name,parent_sig,locator,icon_hash,action,post_sig,n_ok,created,last_ok) VALUES(?,?,?,?,?,?,?,?,1,?,?)",
                                (k, app_key, norm(name), json.dumps(signature(parent_labels)), json.dumps(locator), ih, action, json.dumps(signature(post_labels)), time.time(), time.time()))
            self.db.commit()
        self._replay({"event": "learn", "app_key": app_key, "name": name, "action": action, "locator": locator, "icon_hash": ih, "parent": signature(parent_labels), "post": signature(post_labels)}, crop)
        if self.rag is not None:
            try:                                                           # the same step as a graph edge, so the router's prerequisite logic sees it too
                from core_organs.rag import Outcome, PlanStep
                from core_organs.rag.lexicon import command_id
                src = self.rag.localize(app_key, {"nodes": [{"name": l, "ctype": "button", "offscreen": False} for l in parent_labels][:60], "role": "main"}).state_id
                self.rag.observe(Outcome("self-growth", app_key, PlanStep(command_id(app_key, name), "control_click", {"label": name, "kind": "self_growth"}, None, "", 0.8, "allow"), src_state=src,
                                         observed_snapshot={"nodes": [{"name": l, "ctype": "button", "offscreen": False} for l in post_labels][:60], "role": "main"}, ok=True, effect=f"{action} {name}", latency_ms=0.0, failure_code=""))
            except Exception:
                pass
        return k

    # ---- reuse --------------------------------------------------------------------------------------------------------------------------------------
    def lookup(self, app_key: str, parent_labels: Sequence[str], name: str, action: str = "click") -> Optional[Dict[str, Any]]:
        sig = signature(parent_labels)
        best, bs = None, 0.0
        with self._lock:
            rows = self.db.execute("SELECT * FROM ui_fast WHERE app_key=? AND name=? AND action=? AND trust!='demoted'", (app_key, norm(name), action)).fetchall()
        for r in rows:
            s = jaccard(sig, json.loads(r["parent_sig"]))
            if s >= PARENT_MATCH and s + 0.01 * r["n_ok"] > bs:
                best, bs = dict(r), s + 0.01 * r["n_ok"]
        if best:
            best["locator"] = json.loads(best["locator"])
            best["post_sig"] = json.loads(best["post_sig"])
        return best

    def row(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self.db.execute("SELECT * FROM ui_fast WHERE key=?", (key,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["locator"], d["post_sig"] = json.loads(d["locator"]), json.loads(d["post_sig"])
        return d

    # ---- heal ---------------------------------------------------------------------------------------------------------------------------------------
    def _verified(self, row: Dict[str, Any], labels_now: Sequence[str], extra: Optional[Callable[[], bool]]) -> bool:
        if extra is not None:
            try:
                if not extra():
                    return False
            except Exception:
                return False
        post = row.get("post_sig") or []
        return not post or jaccard(signature(labels_now), post) >= 0.5

    def run(self, app_key: str, name: str, parent_labels: Sequence[str], perform: Callable[[Dict[str, Any]], Any], verify: Callable[[], Sequence[str]], rollback: Optional[Callable[[], Any]] = None,
            fallbacks: Sequence[Any] = (), action: str = "click", crop_fn: Optional[Callable[[Dict[str, Any]], Any]] = None, check: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
        """perform(locator) does the step; verify() returns the control labels on the screen NOW; fallbacks = [(label, fn(name) -> locator|None)]. Returns {ok, route, healed, locator, tried}."""
        tried: List[str] = []
        row = self.lookup(app_key, parent_labels, name, action)
        if row:
            tried.append("fast_path")
            ok = False
            try:
                perform(row["locator"])
                ok = self._verified(dict(row, parent_labels=parent_labels), verify(), check)
            except Exception:
                ok = False
            if ok:
                with self._lock:
                    self.db.execute("UPDATE ui_fast SET n_ok=n_ok+1, n_fail=0, last_ok=? WHERE key=?", (time.time(), row["key"]))
                    self.db.commit()
                return {"ok": True, "route": "fast_path", "healed": False, "locator": row["locator"], "tried": tried, "key": row["key"]}
            if rollback is not None:
                try:
                    rollback()
                except Exception:
                    pass
            with self._lock:
                self.db.execute("UPDATE ui_fast SET n_fail=n_fail+1, last_fail=? WHERE key=?", (time.time(), row["key"]))
                self.db.commit()
        for label, fn in fallbacks:
            tried.append(label)
            try:
                loc = fn(name)
            except Exception:
                loc = None
            if not loc:
                continue
            try:
                perform(loc)
                labels_now = list(verify())
                good = self._verified(dict(row or {"post_sig": []}, parent_labels=parent_labels), labels_now, check) if row else (bool(check()) if check else jaccard(signature(labels_now), signature(parent_labels)) < 0.9)
            except Exception:
                good = False
            if not good:
                if rollback is not None:
                    try:
                        rollback()
                    except Exception:
                        pass
                continue
            crop = None
            if crop_fn is not None:
                try:
                    crop = crop_fn(loc)
                except Exception:
                    crop = None
            if row:                                                         # patch the stored edge: the new locator is on disk before this returns
                with self._lock:
                    self.db.execute("UPDATE ui_fast SET locator=?, icon_hash=?, healed_from=?, n_ok=n_ok+1, n_fail=0, trust='verified', last_ok=? WHERE key=?",
                                    (json.dumps(loc), icon_hash(crop) or row.get("icon_hash", ""), json.dumps(row["locator"]), time.time(), row["key"]))
                    self.db.commit()
                self._replay({"event": "healed", "app_key": app_key, "name": name, "via": label, "from": row["locator"], "to": loc, "icon_hash": icon_hash(crop)}, crop)
                return {"ok": True, "route": label, "healed": True, "locator": loc, "tried": tried, "key": row["key"]}
            k = self.learn(app_key, parent_labels, dict(loc, name=loc.get("name", name)), action, labels_now, crop, True)
            return {"ok": True, "route": label, "healed": False, "grown": True, "locator": loc, "tried": tried, "key": k}
        if row:
            with self._lock:
                r = self.db.execute("SELECT n_fail FROM ui_fast WHERE key=?", (row["key"],)).fetchone()
                if r and r["n_fail"] >= FAIL_LIMIT:
                    self.db.execute("UPDATE ui_fast SET trust='demoted' WHERE key=?", (row["key"],))
                    self.db.commit()
        return {"ok": False, "route": "", "healed": False, "locator": None, "tried": tried}

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            r = self.db.execute("SELECT COUNT(*) n, SUM(n_ok) ok, SUM(n_fail) bad, SUM(healed_from!='') healed FROM ui_fast").fetchone()
        return {"paths": r["n"], "ok": r["ok"] or 0, "fail": r["bad"] or 0, "healed": r["healed"] or 0}

    def close(self) -> None:
        with self._lock:
            self.db.close()
