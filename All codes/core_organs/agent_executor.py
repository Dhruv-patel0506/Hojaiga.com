"""
agent_executor -- Checkpoint 5: the closed loop  observe -> retrieve -> ground -> guard -> act -> verify -> learn,  and its teaching twin (advise).

    observe   a picture of the app + its numbered Set-of-Marks (professor.sweeper through harvest.video_pipeline.som_of_frame: the SAME map the adapter was trained on)
    retrieve  rag.retrieve(Query(...)): the 5 sub-RAGs under the Master Router -> a verified shortcut (hotkey) when one exists, evidence, gaps, safety flags
    ground    the trained QLoRA adapter (Qwen3-VL-2B + LoRA) reads picture + elements + goal and answers with ONE action (click target_id / hotkey / type), in exactly the training prompt format
    guard     safety_guard on the goal AND the target's name (destructive / financial / commit never run; an unnamed icon is judged by the goal that asked for it) + a short list of chords that close,
              lock or erase; an invalid or unknown-target answer is not executed
    act       injected: LiveSession (an owned, parked app; professor.effectors.Effector: posted messages / UIA, never the person's pointer) in real use, a fake in tests
    verify    the picture really changed or the screen's state moved; "delivered" is not "worked"
    learn     rag.observe(Outcome(...)) after EVERY step: the UI topology graph gets/credits the edge src_state -(command)-> dst_state, hotkey reliability and procedures learn too

Everything with a side effect or a model is injected, so the loop is testable without a GPU or a window; `LiveSession` and `AdapterGrounder` are the real ones.
`universal_scan.scan(target)` is the cold start (an app the RAG knows nothing about): `ensure_known` calls it only when asked, because it is a whole-app scan, not a per-step observer.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_organs import safety_guard as SG

# chords that close the window, lock or sign out, erase, or force-quit: never sent by the loop whoever asked
DANGEROUS_CHORDS = {"alt+f4", "ctrl+alt+delete", "ctrl+shift+escape", "win+l", "ctrl+w", "ctrl+shift+delete", "shift+delete", "ctrl+q", "alt+f4+alt"}


def som_to_snapshot(som: Dict[str, Any]) -> Dict[str, Any]:
    """The screen as the RAG's state key reads a frame with no UIA tree: its on-screen labels (a 'blind' snapshot: OCR landmarks)."""
    return {"nodes": [], "ocr": [e["label"] for e in som.get("elements", []) if e.get("label")], "role": "main"}


def _norm_chord(c: Any) -> str:
    return re.sub(r"\s+", "", str(c or "")).lower()


def element_by_id(som: Dict[str, Any], tid: Any) -> Optional[Dict[str, Any]]:
    for e in som.get("elements", []):
        if e.get("id") == tid:
            return e
    return None


def guard_action(goal: str, action: Optional[Dict[str, Any]], som: Dict[str, Any], allow: Sequence[str] = ()) -> Dict[str, Any]:
    """{allowed, why}. The goal is checked as the person's request; the target's own name is checked as what the click would hit."""
    if not isinstance(action, dict) or action.get("action") not in ("click", "hotkey", "type"):
        return {"allowed": False, "why": "no valid action"}
    d = SG.check(goal, allow=allow)
    if not d.allowed:
        return {"allowed": False, "why": d.why()}
    kind = action["action"]
    if kind == "click":
        el = element_by_id(som, action.get("target_id"))
        if el is None:
            return {"allowed": False, "why": f"target #{action.get('target_id')} is not on the screen"}
        label = (el.get("label") or "").strip()
        if label:
            dl = SG.check(label, allow=allow)
            if not dl.allowed:
                return {"allowed": False, "why": dl.why()}
    elif kind == "hotkey":
        chord = _norm_chord(action.get("hotkey"))
        if not chord:
            return {"allowed": False, "why": "hotkey action without keys"}
        if chord in DANGEROUS_CHORDS:
            return {"allowed": False, "why": f"blocked chord {chord!r} (closes, locks or erases)"}
    elif kind == "type" and not str(action.get("text") or ""):
        return {"allowed": False, "why": "type action without text"}
    return {"allowed": True, "why": ""}


def new_on_screen(pre_som: Dict[str, Any], post_som: Dict[str, Any], limit: int = 4) -> List[str]:
    before = {(e.get("label") or "").lower() for e in pre_som.get("elements", [])}
    out: List[str] = []
    for e in post_som.get("elements", []):
        lab = (e.get("label") or "").strip()
        if lab and lab.lower() not in before and lab not in out:
            out.append(lab)
        if len(out) >= limit:
            break
    return out


def default_verify(pre: Dict[str, Any], post: Dict[str, Any], src_state: Optional[str], dst_state: Optional[str]) -> Tuple[bool, str]:
    """(worked, effect): the picture changed (>= 60 pixels moved) or the screen's state key moved. No change at all = 'no_effect'."""
    from core_organs.harvest.local_recorder import changed
    moved = False
    try:
        moved = bool(changed(pre["image"], post["image"])[0])
    except Exception:
        moved = False
    if src_state and dst_state and src_state != dst_state:
        moved = True
    if not moved:
        return False, "no_effect"
    new = new_on_screen(pre["som"], post["som"])
    return True, ("new on screen: " + ", ".join(new)) if new else "the screen changed"


class AdapterGrounder:
    """The trained adapter: Qwen3-VL-2B (4-bit) + LoRA, in-process (~3-5 GB of VRAM). Prompt = the training format, byte for byte (build_messages)."""

    def __init__(self, adapter_dir: str, base: str = "Qwen/Qwen3-VL-2B-Instruct", max_pixels: int = 448 * 448, max_new_tokens: int = 256):
        self.adapter_dir, self.base, self.max_pixels, self.max_new_tokens = adapter_dir, base, max_pixels, max_new_tokens
        self._model = None
        self._proc = None

    @staticmethod
    def build_messages(image: Any, som: Dict[str, Any], app_key: str, goal: str) -> List[Dict[str, Any]]:
        from core_organs.harvest import video_explain as VE, video_pipeline as VP
        return [{"role": "system", "content": [{"type": "text", "text": VE._SYSTEM_HINT}]},
                {"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": f"Application: {app_key}\nElements:\n{VP.som_text(som)}\nGoal: {goal}"}]}]

    def _load(self) -> None:
        import torch
        from peft import PeftModel
        from transformers import AutoProcessor, BitsAndBytesConfig, Qwen3VLForConditionalGeneration
        bf16 = torch.cuda.is_bf16_supported()
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16 if bf16 else torch.float16,
                                 llm_int8_skip_modules=["visual", "lm_head"])
        m = Qwen3VLForConditionalGeneration.from_pretrained(self.base, quantization_config=bnb, device_map={"": 0}, dtype=torch.bfloat16 if bf16 else torch.float16)
        self._model = PeftModel.from_pretrained(m, self.adapter_dir).eval()
        self._proc = AutoProcessor.from_pretrained(self.base)

    def unload(self) -> None:
        self._model = self._proc = None
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    def __call__(self, image: Any, som: Dict[str, Any], app_key: str, goal: str) -> Tuple[Optional[Dict[str, Any]], str]:
        import torch
        from PIL import Image
        from core_organs.train_qlora import parse_action, shrink
        if self._model is None:
            self._load()
        img = Image.open(image).convert("RGB") if isinstance(image, (str, os.PathLike)) else image.convert("RGB")
        msgs = self.build_messages(shrink(img, self.max_pixels), som, app_key, goal)
        enc = self._proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
        enc = {k: (v.to(self._model.device) if hasattr(v, "to") else v) for k, v in enc.items()}
        with torch.no_grad():
            out = self._model.generate(**enc, max_new_tokens=self.max_new_tokens, do_sample=False)
        text = self._proc.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        return parse_action(text), text


@dataclass
class StepRecord:
    goal: str
    status: str                                   # done | no_effect | blocked | no_action | not_delivered | no_observation | advised
    source: str = ""                              # rag | model
    action: Optional[Dict[str, Any]] = None
    label: str = ""
    why: str = ""
    effect: str = ""
    src_state: Optional[str] = None
    dst_state: Optional[str] = None
    learned: bool = False
    ms: float = 0.0
    evidence: List[str] = field(default_factory=list)
    reply: str = ""


class Agent:
    def __init__(self, app_key: str, observe: Callable[[], Dict[str, Any]], ground: Callable[..., Tuple[Optional[Dict[str, Any]], str]], act: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Tuple[bool, str]]] = None,
                 rag: Any = None, run_id: str = "", prefer_rag: bool = True, allow: Sequence[str] = (), settle_s: float = 0.6, verify: Optional[Callable[..., Tuple[bool, str]]] = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.app_key, self.observe, self.ground, self.act, self.rag = app_key, observe, ground, act, rag
        self.run_id = run_id or f"agent-{int(time.time())}"
        self.prefer_rag, self.allow, self.settle_s, self.verify, self.sleep = prefer_rag, tuple(allow), settle_s, verify or default_verify, sleep
        self.history: List[StepRecord] = []

    # ---------------------------------------------------------------------------------------------------- retrieve + ground
    def _retrieve(self, goal: str, snap: Dict[str, Any]) -> Any:
        if self.rag is None:
            return None
        try:
            from core_organs.rag import Query
            return self.rag.retrieve(Query(text=goal, app_key=self.app_key, snapshot=snap, mode="auto"))
        except Exception:
            return None

    @staticmethod
    def _rag_hotkey(ret: Any) -> str:
        """A verified (not a probe), reliable hotkey step at the head of the best plan, or ''."""
        try:
            for plan in ret.plans[:1]:
                for st in plan.steps[:1]:
                    if st.route == "hotkey" and not st.probe and st.reliability >= 0.8 and st.safety == "allow":
                        return _norm_chord(st.args.get("keys") or st.args.get("payload"))
        except Exception:
            pass
        return ""

    def _decide(self, goal: str, pre: Dict[str, Any], ret: Any) -> Tuple[Optional[Dict[str, Any]], str, str]:
        chord = self._rag_hotkey(ret) if self.prefer_rag else ""
        if chord:
            return {"step": 1, "action": "hotkey", "target_id": None, "hotkey": chord, "text": None, "verify_expectation": "the screen changes"}, "rag", f"RAG fast path: {chord}"
        action, reply = self.ground(pre["image"], pre["som"], self.app_key, goal)
        return action, "model", reply

    # ---------------------------------------------------------------------------------------------------- the teaching twin
    def advise(self, goal: str) -> Dict[str, Any]:
        """What to do next, WITHOUT doing it: the grounded action, where it is on the screen, what to say, and any keyboard alternative the RAG knows. Nothing is clicked and nothing is learned."""
        t0 = time.perf_counter()
        try:
            pre = self.observe()
        except Exception as exc:
            say = f"I can't see the application right now ({type(exc).__name__})."
            return {"say": say, "point": None, "action": None, "source": "", "alternatives": [], "allowed": False, "record": StepRecord(goal, "no_observation", why=say)}
        snap = som_to_snapshot(pre["som"])
        ret = self._retrieve(goal, snap)
        action, source, reply = self._decide(goal, pre, ret)
        g = guard_action(goal, action, pre["som"], self.allow)
        alt = []
        try:
            alt = [e.text for e in (ret.evidence if ret else []) if e.kind == "hotkey" and e.safety == "allow"][:2]
        except Exception:
            pass
        if not g["allowed"]:
            say, point = f"I won't do that: {g['why']}.", None
        elif action["action"] == "click":
            el = element_by_id(pre["som"], action["target_id"])
            lab = (el.get("label") or "").strip() or "the highlighted control"
            say, point = f"Click {lab}.", list(el["box"])
        elif action["action"] == "hotkey":
            say, point = f"Press {action['hotkey']}.", None
        else:
            say, point = f"Type \"{action['text']}\".", None
        if alt and g["allowed"] and action and action.get("action") != "hotkey":
            say += " Keyboard alternative: " + "; ".join(alt) + "."
        rec = StepRecord(goal, "advised" if g["allowed"] else "blocked", source, action, say, "" if g["allowed"] else g["why"], ms=round((time.perf_counter() - t0) * 1000, 1), reply=reply,
                         evidence=[e.text[:80] for e in (ret.evidence[:3] if ret else [])])
        return {"say": say, "point": point, "action": action if g["allowed"] else None, "source": source, "alternatives": alt, "allowed": g["allowed"], "record": rec}

    # ---------------------------------------------------------------------------------------------------- the loop
    def step(self, goal: str) -> StepRecord:
        t0 = time.perf_counter()
        try:
            pre = self.observe()
        except Exception as exc:                                   # no picture = no step: nothing is guessed, nothing is learned
            rec = StepRecord(goal, "no_observation", why=f"could not observe the application ({type(exc).__name__}: {str(exc)[:60]})")
            self.history.append(rec)
            return rec
        snap = som_to_snapshot(pre["som"])
        loc = self.rag.localize(self.app_key, snap) if self.rag is not None else None
        src = getattr(loc, "state_id", None)
        ret = self._retrieve(goal, snap)
        action, source, reply = self._decide(goal, pre, ret)
        evid = [e.text[:80] for e in (ret.evidence[:3] if ret else [])]
        rec = StepRecord(goal, "no_action", source, action, src_state=src, reply=reply, evidence=evid)
        g = guard_action(goal, action, pre["som"], self.allow)
        if action is None:
            rec.why = "the model gave no valid action"
        elif not g["allowed"]:
            rec.status, rec.why = "blocked", g["why"]
        elif self.act is None:
            rec.status, rec.why = "advised", "no actor attached"
        else:
            el = element_by_id(pre["som"], action.get("target_id")) if action["action"] == "click" else None
            rec.label = (el.get("label") if el else "") or goal
            ok_sent, note = self.act(action, pre["som"])
            if not ok_sent:
                rec.status, rec.why = "not_delivered", note
            else:
                self.sleep(self.settle_s)
                post = self.observe()
                dst = self.rag.localize(self.app_key, som_to_snapshot(post["som"])) if self.rag is not None else None
                dst_id = getattr(dst, "state_id", None)
                worked, effect = self.verify(pre, post, src, dst_id)
                rec.status, rec.effect, rec.dst_state = ("done" if worked else "no_effect"), effect, dst_id
                rec.learned = self._learn(goal, action, rec, post, worked, effect, (time.perf_counter() - t0) * 1000)
        rec.ms = round((time.perf_counter() - t0) * 1000, 1)
        self.history.append(rec)
        return rec

    def _learn(self, goal: str, action: Dict[str, Any], rec: StepRecord, post: Dict[str, Any], worked: bool, effect: str, ms: float) -> bool:
        """Report the step to the RAG: the topology graph learns the edge src_state -(command)-> dst_state (and an unverified one is credited as a failure)."""
        if self.rag is None:
            return False
        try:
            from core_organs.rag import Outcome, PlanStep
            from core_organs.rag.lexicon import command_id
            kind = action["action"]
            if kind == "click":
                label = rec.label
                cid, route, args = command_id(self.app_key, label), "control_click", {"label": label}
            elif kind == "hotkey":
                chord = _norm_chord(action.get("hotkey"))
                cid, route, args = command_id(self.app_key, goal), "hotkey", {"label": goal, "keys": chord}
            else:
                cid, route, args = f"{self.app_key}:type", "type", {"label": "type"}
            if kind != "type":
                self.rag.lex.add_command(self.app_key, rec.label if kind == "click" else goal, source="executor", trust="learned")
            self.rag.observe(Outcome(self.run_id, self.app_key, PlanStep(cid, route, args, None, effect[:60], 0.5, "allow"), src_state=rec.src_state, observed_snapshot=som_to_snapshot(post["som"]),
                                     ok=bool(worked), effect=effect if worked else "no_effect", latency_ms=float(ms), failure_code="" if worked else "no_effect", observed_dst=rec.dst_state))
            return True
        except Exception:
            return False

    def run(self, goals: Sequence[str], stop_on_fail: bool = True) -> List[StepRecord]:
        out: List[StepRecord] = []
        for g in goals:
            r = self.step(g)
            out.append(r)
            if stop_on_fail and r.status != "done":
                break
        return out

    def ensure_known(self, target: str, scan: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
        """Cold start: when the RAG knows nothing about this app, learn it once with universal_scan.scan(target). Explicit and opt-in (a whole-app scan, not a per-step observer)."""
        if self.rag is not None:
            try:
                if self.rag.proc.chunk_count(self.app_key) or self.rag.graph.stats(self.app_key).get("nodes", 0):
                    return {"scanned": False, "why": "already known"}
            except Exception:
                pass
        if scan is None:
            from core_organs import universal_scan
            scan = universal_scan.scan
        return {"scanned": True, "result": scan(target)}


# ---------------------------------------------------------------------------------------------------- the real hands and eyes (an owned, parked app)
class LiveSession:
    """`with LiveSession('notepad') as s: Agent('notepad', s.observe, grounder, s.act, rag).step('Click the Bold button')`.
    The app is OWNED (started by this process, state-guarded, parked off-screen, never the person's focus); input goes through professor.effectors (posted messages / UIA)."""

    def __init__(self, launch_name: str):
        from core_organs.harvest.local_recorder import OwnedApp
        self.app = OwnedApp(launch_name)
        self.eff = None
        self.origin = (0, 0)

    def __enter__(self) -> "LiveSession":
        self.app.__enter__()
        from core_organs.professor.effectors import Effector
        self.eff = Effector(self.app.hwnd, allow_input=True, owned=True)
        return self

    def __exit__(self, *exc) -> bool:
        return self.app.__exit__(*exc)

    def observe(self) -> Dict[str, Any]:
        from core_organs.harvest import video_pipeline as VP
        img, origin = None, (0, 0)
        for _ in range(3):                                         # a frame can fail to render for a moment (measured: the first grab after a window settles)
            img, origin = self.app.grab(popups=True)
            if img is not None:
                break
            time.sleep(0.8)
        if img is None:
            raise RuntimeError("no picture of the window")
        self.origin = origin
        return {"image": img, "som": VP.som_of_frame(img)}

    def act(self, action: Dict[str, Any], som: Dict[str, Any]) -> Tuple[bool, str]:
        kind = action["action"]
        if kind == "click":
            el = element_by_id(som, action.get("target_id"))
            x, y, w, h = el["box"]
            return self.eff.click_xy(int(self.origin[0] + x + w / 2), int(self.origin[1] + y + h / 2))
        if kind == "hotkey":
            return self.eff.key(str(action["hotkey"]))
        return self.eff.insert_text(str(action.get("text") or ""))
