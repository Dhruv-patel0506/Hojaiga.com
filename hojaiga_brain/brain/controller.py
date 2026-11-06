# brain/controller.py
"""
Natural-intelligence controller: the always-on layer a company plugs its automations into.

  request ─▶ router (learned) ─▶ skill ─▶ (approval gate for risky skills) ─▶ result ─▶ audit log
                                   │                                             │
                                   └──── outcomes train the router and the brain ◀┘

* Skills are registered at runtime: built-ins (answer, learn_dataset, classify, scan_screen, render,
  consolidate) and any external automation (`register_skill`) — e.g. Hojaiga's desktop organs,
  an RPA bot, an ERP connector.
* Routing has no keyword rules: cold start = similarity between the request and each skill's
  description; then an online Naive Bayes model learns from which skill actually succeeded.
* Skills marked `requires_approval` never run until a human approves the pending request.
* Always on: `serve()` exposes an HTTP API and a background loop that learns every dataset dropped
  into an inbox folder and periodically consolidates (inner-brain distillation + main LLM training).
"""
import json
import math
import re
import shutil
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from brain.conveyor.belt import ConveyorBelt, classify_text
from brain.inner_brain import DualBrain


@dataclass
class Skill:
    name: str
    description: str
    run: Callable[[Dict[str, Any]], Any]
    requires_approval: bool = False


class SkillRouter:
    """Description-similarity prior + online multinomial Naive Bayes over request words."""

    def __init__(self, embed: Callable[[str], np.ndarray], state_path: Path):
        self.embed = embed
        self.path = state_path
        self.counts: Dict[str, Counter] = defaultdict(Counter)
        self.totals: Counter = Counter()
        if state_path.exists():
            st = json.loads(state_path.read_text(encoding="utf-8"))
            self.counts = defaultdict(Counter, {k: Counter(v) for k, v in st["counts"].items()})
            self.totals = Counter(st["totals"])

    @staticmethod
    def _words(text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def scores(self, text: str, skills: Dict[str, Skill]) -> Dict[str, float]:
        q = self.embed(text)
        prior = {n: float(np.dot(q, self.embed(f"{n.replace('_', ' ')} {s.description}"))) for n, s in skills.items()}
        words = self._words(text)
        # Laplace smoothing over an open vocabulary: a word a person has taught for a skill must count
        # as strong evidence even when the router has only seen a handful of words so far
        vocab = len({w for c in self.counts.values() for w in c}) + 1000
        learned_n = sum(self.totals.values())
        out = {}
        for n in skills:
            if learned_n:
                ll = sum(math.log((self.counts[n][w] + 1) / (self.totals[n] + vocab)) for w in words) / max(len(words), 1)
                uni = sum(math.log(1 / vocab) for _ in words) / max(len(words), 1)
                out[n] = prior[n] + 0.5 * (ll - uni)          # evidence on top of the description prior
            else:
                out[n] = prior[n]
        return out

    def learn(self, text: str, skill: str) -> None:
        for w in self._words(text):
            self.counts[skill][w] += 1
            self.totals[skill] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"counts": {k: dict(v) for k, v in self.counts.items()},
                                         "totals": dict(self.totals)}), encoding="utf-8")


class NaturalIntelligenceController:
    def __init__(self, brain, inbox: Optional[Path] = None):
        self.brain = brain
        self.dual = DualBrain(brain)
        self.ws = brain.cfg.workspace_dir
        self.inbox = Path(inbox) if inbox else self.ws / "inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        (self.ws / "inbox_done").mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.skills: Dict[str, Skill] = {}
        self.pending: Dict[str, Dict[str, Any]] = {}
        self.router = SkillRouter(brain.l2.compute_embedding, self.ws / "controller" / "router.json")
        self.audit_path = self.ws / "controller" / "audit.jsonl"
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_consolidation = time.time()
        self._register_builtins()

    # ------------------------------------------------------------------ skills
    def register_skill(self, name: str, description: str, run: Callable[[Dict[str, Any]], Any],
                       requires_approval: bool = False) -> None:
        self.skills[name] = Skill(name, description, run, requires_approval)

    def _register_builtins(self) -> None:
        self.register_skill("answer", "answer a question explain what why how from knowledge memory",
                            lambda p: self.dual.ask(p["text"]))
        self.register_skill("learn_dataset", "learn ingest train on a dataset folder files data path",
                            lambda p: ConveyorBelt(self.brain, train_llm=p.get("train_llm", False)).run(
                                [p["path"]]))
        self.register_skill("classify", "classify categorize label tag sort this text ticket message",
                            lambda p: classify_text(self.ws, p.get("content") or p["text"]))
        self.register_skill("scan_screen", "scan screenshot screen image interface app ui layout look at",
                            lambda p: self._scan(p["image"]))
        self.register_skill("render", "render draw animate visualize diagram 3d hologram view",
                            lambda p: self._render(p))
        self.register_skill("consolidate", "consolidate sleep train distill improve model memory overnight",
                            lambda p: self.consolidate(epochs=int(p.get("epochs", 1))))

    def _scan(self, image_path: str) -> Dict[str, Any]:
        from PIL import Image
        arr = np.array(Image.open(image_path).convert("RGB"))
        r = self.brain.vlm.deep_scan_ui_screen(arr, context_hint=Path(image_path).stem)
        return {k: r[k] for k in ("interface_id", "recognized_from_memory", "label_hint", "epistemic_surprise",
                                  "discovered_regions_count", "layout")}

    def _render(self, p: Dict[str, Any]) -> Dict[str, Any]:
        from brain.universal_renderer import HojaigaUniversalRenderer
        out = Path(p.get("out") or self.ws / "renders" / f"render_{int(time.time())}.html")
        return {"html": str(HojaigaUniversalRenderer().render_to_html(p.get("content") or p["text"], out))}

    # ------------------------------------------------------------------ requests
    def _audit(self, entry: Dict[str, Any]) -> None:
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), **entry}, default=str) + "\n")

    def route(self, text: str) -> Dict[str, Any]:
        sc = self.router.scores(text, self.skills)
        ranked = sorted(sc.items(), key=lambda kv: -kv[1])
        return {"skill": ranked[0][0], "scores": {k: round(v, 3) for k, v in ranked[:3]}}

    def handle(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """request: {"text": ..., optional "skill", payload fields (path, image, content, out ...)}."""
        rid = uuid.uuid4().hex[:10]
        text = request.get("text", "")
        routed = {"skill": request["skill"], "scores": {}} if request.get("skill") else self.route(text)
        skill = self.skills.get(routed["skill"])
        if skill is None:
            return {"id": rid, "error": f"unknown skill {routed['skill']}"}
        if skill.requires_approval and not request.get("_approved"):
            self.pending[rid] = {**request, "skill": skill.name}
            self._audit({"id": rid, "event": "awaiting_approval", "skill": skill.name, "text": text})
            return {"id": rid, "status": "awaiting_approval", "skill": skill.name}
        t0 = time.time()
        try:
            with self.lock:
                result = skill.run(request)
            status = "done"
        except Exception as exc:
            result, status = {"error": f"{type(exc).__name__}: {exc}"}, "failed"
        out = {"id": rid, "status": status, "skill": skill.name, "routing": routed["scores"], "result": result,
               "ms": round((time.time() - t0) * 1000, 1)}
        self._audit({"id": rid, "event": status, "skill": skill.name, "text": text, "ms": out["ms"]})
        if status == "done" and not request.get("skill"):
            self.router.learn(text, skill.name)          # successful routing is evidence for the router
        return out

    def approve(self, rid: str, approver: str = "human") -> Dict[str, Any]:
        req = self.pending.pop(rid, None)
        if req is None:
            return {"id": rid, "error": "no pending request with this id"}
        self._audit({"id": rid, "event": "approved", "by": approver})
        return self.handle({**req, "_approved": True})

    def correct_routing(self, text: str, right_skill: str) -> None:
        """A person says which skill should have handled a request; the router learns it."""
        for _ in range(3):
            self.router.learn(text, right_skill)
        self._audit({"event": "routing_corrected", "text": text, "skill": right_skill})

    # ------------------------------------------------------------------ always-on loop
    def consolidate(self, epochs: int = 1) -> Dict[str, Any]:
        """'Sleep': distill the inner brain's LLM and train the main LLM on the replay buffer."""
        from brain_cli import run_overnight_consolidation
        with self.lock:
            inner = self.dual.inner.distill_llm(self.brain.tokenizer, epochs=epochs)
            main = run_overnight_consolidation(self.brain, epochs=epochs)
        self.last_consolidation = time.time()
        self._audit({"event": "consolidated", "inner": inner, "main": main})
        return {"inner_llm": inner, "main_llm": main}

    def tick(self, consolidate_every_s: float = 3600.0) -> Dict[str, Any]:
        """One pass of the background loop: learn new inbox data, consolidate when due."""
        done: List[str] = []
        for entry in sorted(self.inbox.iterdir()):
            if entry.name.startswith("."):
                continue
            rep = self.handle({"skill": "learn_dataset", "text": f"learn {entry.name}", "path": str(entry)})
            target = self.ws / "inbox_done" / f"{int(time.time())}_{entry.name}"
            shutil.move(str(entry), str(target))
            done.append(entry.name if rep["status"] == "done" else f"{entry.name} (failed)")
        consolidated = None
        if consolidate_every_s and time.time() - self.last_consolidation >= consolidate_every_s:
            consolidated = self.consolidate()
        return {"learned": done, "consolidated": consolidated is not None}

    def status(self) -> Dict[str, Any]:
        return {"skills": {n: {"description": s.description, "requires_approval": s.requires_approval}
                           for n, s in self.skills.items()},
                "pending_approvals": list(self.pending), "self_reliance": self.dual.self_reliance(),
                "inner_memory": len(self.dual.inner.memory), "main_memory": len(self.brain.l2.episodes),
                "failures_remembered": len(self.brain.l8.failure_memory),
                "known_interfaces": len(self.brain.vlm.known_interfaces), "llm_trained": self.brain.llm_trained}

    def serve(self, host: str = "127.0.0.1", port: int = 8765, consolidate_every_s: float = 3600.0,
              poll_s: float = 10.0, block: bool = True):
        ctrl = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, body: Dict[str, Any]) -> None:
                data = json.dumps(body, default=str).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):          # quiet console; everything is in audit.jsonl
                pass

            def do_GET(self):
                if self.path == "/status":
                    return self._send(200, ctrl.status())
                self._send(404, {"error": "GET /status, POST /ask /task /feedback /approve /route-correction"})

            def do_POST(self):
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                except json.JSONDecodeError:
                    return self._send(400, {"error": "body must be JSON"})
                if self.path == "/ask":
                    return self._send(200, ctrl.handle({"skill": "answer", "text": body.get("question", "")}))
                if self.path == "/task":
                    return self._send(200, ctrl.handle(body))
                if self.path == "/feedback":
                    return self._send(200, ctrl.dual.feedback(body["question"], bool(body.get("good", False)),
                                                              body.get("correction")))
                if self.path == "/approve":
                    return self._send(200, ctrl.approve(body["id"], body.get("by", "human")))
                if self.path == "/route-correction":
                    ctrl.correct_routing(body["text"], body["skill"])
                    return self._send(200, {"recorded": True})
                self._send(404, {"error": "unknown endpoint"})

        server = ThreadingHTTPServer((host, port), Handler)
        stop = threading.Event()

        def loop():
            while not stop.wait(poll_s):
                try:
                    ctrl.tick(consolidate_every_s)
                except Exception as exc:
                    ctrl._audit({"event": "loop_error", "error": str(exc)})

        threading.Thread(target=loop, daemon=True).start()
        if block:
            try:
                server.serve_forever()
            finally:
                stop.set()
        else:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        return server, stop
