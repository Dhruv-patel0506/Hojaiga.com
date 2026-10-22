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
import contextlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_organs import agent_verify as AV, chrome_filter as CF, picture_tier as PT, safety_guard as SG

# chords that close the window, lock or sign out, erase, or force-quit: never sent by the loop whoever asked
DANGEROUS_CHORDS = {"alt+f4", "ctrl+alt+delete", "ctrl+shift+escape", "win+l", "ctrl+w", "ctrl+shift+delete", "shift+delete", "ctrl+q", "alt+f4+alt"}


def som_to_snapshot(som: Dict[str, Any]) -> Dict[str, Any]:
    """The screen as the RAG's state key reads a frame with no UIA tree: its on-screen labels (a 'blind' snapshot: OCR landmarks)."""
    return {"nodes": [], "ocr": [e["label"] for e in som.get("elements", []) if e.get("label")], "role": "main"}


def _norm_chord(c: Any) -> str:
    return re.sub(r"\s+", "", str(c or "")).lower()


def som_from_controls(controls: Sequence[Dict[str, Any]], size: Tuple[int, int]) -> Dict[str, Any]:
    """A Set-of-Marks built from the UI Automation tree alone (Layer 1 of the design): one numbered element per named control, boxes and labels exact, no OCR and no model. Used when the application exposes
    enough of its tree; the OCR / icon scan stays the fallback for what UIA does not name."""
    els, seen = [], set()
    for c in controls:
        x, y, w, h = c["box"]
        key = (c["name"], round(x / 3), round(y / 3))
        if key in seen or w < 4 or h < 4:
            continue
        seen.add(key)
        els.append({"id": len(els) + 1, "label": c["name"], "role": str(c.get("type", "")).replace("Control", "").lower() or "control", "box": [int(x), int(y), int(w), int(h)]})
    return {"elements": els, "seconds": 0.0, "size": list(size), "tiers_used": ["uia"], "tiers_skipped": []}


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
    if not moved and (pre.get("doc") or post.get("doc")) and pre.get("doc") != post.get("doc"):
        return True, "the document's text changed"
    new = new_on_screen(pre["som"], post["som"])
    if not moved and len(new) >= 2:                                 # a flyout whose picture cannot be captured (WinUI): its items appeared in the accessibility tree
        return True, "new on screen (not in the picture): " + ", ".join(new)
    if not moved:
        return False, "no_effect"
    return True, ("new on screen: " + ", ".join(new)) if new else "the screen changed"


class AdapterGrounder:
    """The trained adapter: Qwen3-VL-2B (4-bit) + LoRA, in-process (~3-5 GB of VRAM). Prompt = the training format, byte for byte (build_messages)."""

    def __init__(self, adapter_dir: str, base: str = "Qwen/Qwen3-VL-2B-Instruct", max_pixels: int = 448 * 448, max_new_tokens: int = 72, prompt_version: int = 1, use_names: bool = True):
        """prompt_version 2 = the format of harvest.prompt_v2 (the picture + zoomed crops of dense toolbar strips + a `Names:` line from UI Automation when `use_names`); an adapter trained on v1 must not be given v2."""
        self.adapter_dir, self.base, self.max_pixels, self.max_new_tokens = adapter_dir, base, max_pixels, max_new_tokens
        self.prompt_version, self.use_names = prompt_version, use_names
        self._model = None
        self._proc = None

    def build_messages_v2(self, image: Any, som: Dict[str, Any], app_key: str, goal: str, controls: Optional[Sequence[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        from core_organs.harvest import prompt_v2 as P2, video_explain as VE
        from core_organs.train_qlora import shrink
        content, _info = P2.user_content(image, som, app_key, goal, controls=list(controls) if (controls and self.use_names) else None)
        content = [dict(c, image=shrink(c["image"], self.max_pixels)) if c.get("type") == "image" else c for c in content]
        return [{"role": "system", "content": [{"type": "text", "text": VE._SYSTEM_HINT}]}, {"role": "user", "content": content}]

    def build_messages_v3(self, image: Any, som: Dict[str, Any], app_key: str, goal: str, controls: Optional[Sequence[Dict[str, Any]]] = None, hint: str = "") -> List[Dict[str, Any]]:
        """Prompt format v3 (harvest.prompt_v3): the picture + zoomed strips as in v2, the Top-40 elements for THIS goal as centre points, the Names of those, and the RAG's hint when it has one."""
        from core_organs.harvest import prompt_v2 as P2, prompt_v3 as P3, video_explain as VE
        from core_organs.train_qlora import shrink
        els = som["elements"]
        nm = P2.name_elements(els, list(controls)) if (controls and self.use_names) else {}
        gtext = re.sub(r"^goal:\s*", "", goal, flags=re.I)
        kept = P3.trim(els, gtext, nm, P3.TOP_K, hint_words=P3.tokens(hint))               # the Mind's retrieved step names count as goal words (the parent menu of 'Replace' is 'Edit')
        content, info = P2.user_content(image, dict(som, elements=som.get("all_elements") or els), app_key, goal, controls=None)       # the strips were chosen on the whole scan in training
        imgs = [dict(c, image=shrink(c["image"], self.max_pixels)) for c in content if c.get("type") == "image"]
        text = P3.build_text(app_key, kept, {i: n for i, n in nm.items() if i in {e["id"] for e in kept}}, hint, info.get("n_crops", 0), gtext)
        return [{"role": "system", "content": [{"type": "text", "text": VE._SYSTEM_HINT}]}, {"role": "user", "content": imgs + [{"type": "text", "text": text}]}]

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

    def __call__(self, image: Any, som: Dict[str, Any], app_key: str, goal: str, controls: Optional[Sequence[Dict[str, Any]]] = None, hint: str = "") -> Tuple[Optional[Dict[str, Any]], str]:
        import torch
        from PIL import Image
        from core_organs.train_qlora import parse_action, shrink
        if self._model is None:
            self._load()
        img = Image.open(image).convert("RGB") if isinstance(image, (str, os.PathLike)) else image.convert("RGB")
        if self.prompt_version == 3:
            msgs = self.build_messages_v3(img, som, app_key, goal, controls, hint)
        else:
            msgs = self.build_messages_v2(img, som, app_key, goal, controls) if self.prompt_version == 2 else self.build_messages(shrink(img, self.max_pixels), som, app_key, goal)
        enc = self._proc.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt")
        enc = {k: (v.to(self._model.device) if hasattr(v, "to") else v) for k, v in enc.items()}
        with torch.no_grad():
            # the action fields come first in the reply and the free-text expectation after them: generation STOPS where the expectation starts (and is capped at ~72 tokens), parse_action reads the rest
            gen = self._model.generate(**enc, max_new_tokens=self.max_new_tokens, do_sample=False, stop_strings=['"verify_expectation"'], tokenizer=getattr(self._proc, "tokenizer", self._proc),
                                       return_dict_in_generate=True, output_scores=True)
        out = gen.sequences
        text = self._proc.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        self.last = {"conf": None}
        with contextlib.suppress(Exception):                      # how sure the model was: the geometric mean of its own token probabilities over the answer it gave (1.0 = certain)
            import math
            sc = self._model.compute_transition_scores(gen.sequences, gen.scores, normalize_logits=True)[0]
            vals = [float(x) for x in sc.float().cpu().tolist()]
            self.last = {"conf": round(math.exp(sum(vals) / max(len(vals), 1)), 4), "min_p": round(math.exp(min(vals)), 4) if vals else None, "tokens": len(vals)}
        return parse_action(text), text


@dataclass
class StepRecord:
    goal: str
    status: str                                   # done | no_effect | wrong_effect | blocked | no_action | not_delivered | no_observation | advised
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
    reason: str = ""                              # '' on success, else no_effect | wrong_control | unexpected_dialog | toggle_unchanged | no_dialog
    rolled_back: bool = False                     # a wrong effect was undone (dialog dismissed / toggle restored)
    assisted: str = ""                            # the UIA-name assist changed the model's target: what it did
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    timings: Dict[str, float] = field(default_factory=dict)


class Agent:
    def __init__(self, app_key: str, observe: Callable[[], Dict[str, Any]], ground: Callable[..., Tuple[Optional[Dict[str, Any]], str]], act: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Tuple[bool, str]]] = None,
                 rag: Any = None, run_id: str = "", prefer_rag: bool = True, allow: Sequence[str] = (), settle_s: float = 0.6, verify: Optional[Callable[..., Tuple[bool, str]]] = None,
                 sleep: Callable[[float], None] = time.sleep, recover: Optional[Callable[..., Dict[str, Any]]] = None, assist: bool = True, max_attempts: int = 2, reuse_post: bool = True,
                 reuse_max_age_s: float = 20.0, tools: Sequence[Any] = (), uia_first: bool = False, observe_full: Optional[Callable[[], Dict[str, Any]]] = None):
        """`verify` = a custom (pre, post, src, dst) -> (worked, effect); without one the base test is 'the picture / state moved' and, where the app exposes UIA, the goal-aware rules (agent_verify).
        `recover(pre, post, verdict, names)` undoes a wrong effect (dismiss the dialog, restore the toggle) and returns {restored: bool, how}; without one a wrong effect is reported, not undone.
        `assist`: the UIA-name correction of the model's target. `reuse_post`: the screen seen after one step is the screen the next step starts from (one Set-of-Marks scan saved per step)."""
        self.app_key, self.observe, self.ground, self.act, self.rag = app_key, observe, ground, act, rag
        self.run_id = run_id or f"agent-{int(time.time())}"
        self.prefer_rag, self.allow, self.settle_s, self.custom_verify, self.sleep = prefer_rag, tuple(allow), settle_s, verify, sleep
        self.recover, self.assist, self.max_attempts, self.reuse_post, self.reuse_max_age_s = recover, assist, max(1, int(max_attempts)), reuse_post, reuse_max_age_s
        self.uia_first, self.observe_full, self._pre_override = uia_first, observe_full, None      # uia_first: a goal that names ONE control UIA lists is done through that control, with no model call and no OCR scan
        self.tools = list(tools)                                  # tools take goals that are not one click (drawing: agent_artist.ArtistTools); each has matches(goal) and run(goal) -> StepRecord
        self.history: List[StepRecord] = []
        self._last_post: Optional[Tuple[Dict[str, Any], float]] = None

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

    def _uia_route(self, goal: str, pre: Dict[str, Any], exclude: Sequence[int]) -> Optional[Dict[str, Any]]:
        """The control a goal names, when exactly one control UIA lists carries that name: a click on the Set-of-Marks element inside it."""
        gname = AV.explicit_name(goal)
        controls = pre.get("controls") or []
        if not gname or not controls:
            return None
        named = [c for c in controls if AV.name_match(gname, c["name"])]
        if len(named) > 1:                                          # several controls carry the name: the one whose name IS the goal's, then the one that can be pressed (a menu / button / tab, not a text area)
            exact = [c for c in named if c["name"].strip().lower() == gname.strip().lower()]
            named = exact or named
        if len(named) > 1:
            presser = [c for c in named if str(c.get("type", "")) in ("ButtonControl", "MenuItemControl", "TabItemControl", "ListItemControl", "HyperlinkControl", "CheckBoxControl", "RadioButtonControl", "SplitButtonControl")]
            named = presser or named
        if len(named) != 1:
            return None
        from core_organs.harvest.local_recorder import element_at
        el = element_at(pre["som"], named[0]["box"])
        if el is None or el.get("id") in set(exclude):
            return None
        return {"step": 1, "action": "click", "target_id": el["id"], "hotkey": None, "text": None, "verify_expectation": "the screen changes"}

    def _decide(self, goal: str, pre: Dict[str, Any], ret: Any, exclude: Sequence[int] = ()) -> Tuple[Optional[Dict[str, Any]], str, str]:
        if self.uia_first:
            act_ = self._uia_route(goal, pre, exclude)
            if act_ is not None:
                return act_, "uia", f"UIA name '{AV.explicit_name(goal)}'"
            if self.observe_full is not None and "uia" in (pre["som"].get("tiers_used") or []):
                pre = self.observe_full()                      # the tree could not answer: the full scan (OCR + icons) is what the model was trained on
                self._pre_override = pre
        chord = self._rag_hotkey(ret) if self.prefer_rag else ""
        if chord:
            return {"step": 1, "action": "hotkey", "target_id": None, "hotkey": chord, "text": None, "verify_expectation": "the screen changes"}, "rag", f"RAG fast path: {chord}"
        som = pre["som"]
        if exclude:                                                # a target that was just undone is not offered again
            som = dict(som, elements=[e for e in som["elements"] if e.get("id") not in set(exclude)])
        action, reply = self.ground(pre["image"], som, self.app_key, goal)
        return action, "model", reply

    def _assist(self, goal: str, action: Optional[Dict[str, Any]], pre: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self.assist:
            return action, ""
        from core_organs.harvest.local_recorder import element_at
        fixed, note = AV.uia_assist(goal, action, pre, element_at)
        return (fixed, note) if fixed else (action, "")

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
        action, _assist_note = self._assist(goal, action, pre)
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
    def _verdict(self, goal: str, action: Dict[str, Any], pre: Dict[str, Any], post: Dict[str, Any], src: Optional[str], dst: Optional[str]) -> Dict[str, Any]:
        if self.custom_verify is not None:
            worked, effect = self.custom_verify(pre, post, src, dst)
            return {"worked": bool(worked), "effect": effect, "reason": "" if worked else "no_effect", "intent": "", "target": "", "checked": "custom", "new": []}
        base_worked, base_effect = default_verify(pre, post, src, dst)
        return AV.goal_verify(goal, action, pre, post, base_worked, base_effect)

    def _recovery_names(self, goal: str, post: Dict[str, Any], verdict: Dict[str, Any]) -> List[str]:
        """Buttons Sub-RAG 5 (recovery playbooks) names for this failure, else the safe dismissals. 'OK' / 'Yes' / 'Close' are never in the list: they confirm or close."""
        names: List[str] = []
        if self.rag is not None:
            try:
                from core_organs.rag import Query
                ret = self.rag.retrieve(Query(text=goal, app_key=self.app_key, snapshot=som_to_snapshot(post["som"]), mode="auto",
                                              failure={"code": verdict.get("reason", ""), "controls": verdict.get("new", [])}))
                for plan in ret.plans[:2]:
                    for st in plan.steps:
                        nm = str((st.args or {}).get("text") or (st.args or {}).get("label") or "")
                        if st.route == "control_click" and nm and SG.is_safe(nm) and nm.lower() not in ("ok", "yes", "close"):
                            names.append(nm)
            except Exception:
                pass
        return names + ["Cancel", "No"]

    def step(self, goal: str) -> StepRecord:
        for tool in self.tools:
            try:
                hit = tool.matches(goal)
            except Exception:
                hit = False
            if hit:
                rec = tool.run(goal)
                self.history.append(rec)
                return rec
        t_all = time.perf_counter()
        tm: Dict[str, float] = {}

        def timed(key: str, t0: float) -> None:
            tm[key] = round(tm.get(key, 0.0) + (time.perf_counter() - t0), 2)

        def look(fresh: bool = False) -> Dict[str, Any]:
            t0 = time.perf_counter()
            if self.reuse_post and not fresh and self._last_post is not None and time.time() - self._last_post[1] <= self.reuse_max_age_s:
                obs = self._last_post[0]                           # the screen seen after the last step IS the screen this one starts from
                tm["observe_reused"] = 1
            else:
                obs = self.observe()
            self._last_post = None
            timed("observe", t0)
            return obs
        try:
            pre = look()
        except Exception as exc:                                   # no picture = no step: nothing is guessed, nothing is learned
            rec = StepRecord(goal, "no_observation", why=f"could not observe the application ({type(exc).__name__}: {str(exc)[:60]})")
            self.history.append(rec)
            return rec
        exclude: List[int] = []
        rec = StepRecord(goal, "no_action")
        for attempt in range(self.max_attempts):
            snap = som_to_snapshot(pre["som"])
            loc = self.rag.localize(self.app_key, snap) if self.rag is not None else None
            src = getattr(loc, "state_id", None)
            t0 = time.perf_counter()
            ret = self._retrieve(goal, snap)
            timed("retrieve", t0)
            t0 = time.perf_counter()
            action, source, reply = self._decide(goal, pre, ret, exclude)
            if self._pre_override is not None:
                pre, self._pre_override = self._pre_override, None
            timed("ground", t0)
            note = ""
            if source == "model":
                fixed, fnote = self._assist(goal, action, pre)
                if fnote and fixed.get("target_id") in exclude:                  # the one control that carries this name was already tried and undone: not clicked a second time
                    rec.status, rec.why = "wrong_effect", "the only control with that name was already tried and its effect was not the goal's"
                    break
                action, note = fixed, fnote
            rec.action, rec.source, rec.src_state, rec.reply, rec.assisted = action, source, src, reply, note or rec.assisted
            rec.evidence = [e.text[:80] for e in (ret.evidence[:3] if ret else [])]
            g = guard_action(goal, action, pre["som"], self.allow)
            if action is None:
                rec.status, rec.why = "no_action", "the model gave no valid action"
                break
            if not g["allowed"]:
                rec.status, rec.why = "blocked", g["why"]
                break
            if self.act is None:
                rec.status, rec.why = "advised", "no actor attached"
                break
            el = element_by_id(pre["som"], action.get("target_id")) if action["action"] == "click" else None
            rec.label = (el.get("label") if el else "") or (AV.explicit_name(goal) or goal)
            t0 = time.perf_counter()
            ok_sent, why_sent = self.act(action, pre["som"])
            timed("act", t0)
            if not ok_sent:
                rec.status, rec.why = "not_delivered", why_sent
                break
            t0 = time.perf_counter()
            self.sleep(self.settle_s)
            timed("settle", t0)
            t0 = time.perf_counter()
            try:
                post = self.observe()
            except Exception as exc:                               # the click went out but the window can no longer be seen: say so; nothing is learned from a step nobody could check
                rec.status, rec.why, rec.reason = "no_observation", f"could not observe the application after the step ({type(exc).__name__}: {str(exc)[:60]})", "no_observation"
                rec.attempts.append({"attempt": attempt + 1, "target_id": action.get("target_id"), "worked": False, "reason": "no_observation", "operated": str(why_sent)[:80]})
                break
            timed("observe", t0)
            dst = self.rag.localize(self.app_key, som_to_snapshot(post["som"])) if self.rag is not None else None
            dst_id = getattr(dst, "state_id", None)
            t0 = time.perf_counter()
            verdict = self._verdict(goal, action, pre, post, src, dst_id)
            if not verdict["worked"] and verdict["reason"] == "no_effect":          # a slow effect (a replace over a long document, a dialog still painting): look once more before calling it nothing
                self.sleep(1.4)
                with contextlib.suppress(Exception):
                    post2 = self.observe()
                    v2 = self._verdict(goal, action, pre, post2, src, dst_id)
                    if v2["worked"]:
                        post, verdict = post2, v2
            timed("verify", t0)
            rec.effect, rec.dst_state, rec.reason = verdict["effect"], dst_id, verdict["reason"]
            rec.attempts.append({"attempt": attempt + 1, "target_id": action.get("target_id"), "hotkey": action.get("hotkey"), "worked": verdict["worked"], "reason": verdict["reason"], "effect": verdict["effect"][:90],
                                 "assisted": note, "operated": str(why_sent)[:80]})
            rec.learned = self._learn(goal, action, rec, post, verdict["worked"], verdict["effect"], (time.perf_counter() - t_all) * 1000, verdict["reason"]) or rec.learned
            if verdict["worked"]:
                rec.status, rec.why = "done", ""
                self._last_post = (post, time.time())
                break
            rec.status = "no_effect" if verdict["reason"] == "no_effect" else "wrong_effect"
            rec.why = verdict["effect"]
            if verdict["reason"] == "no_effect" or self.recover is None or attempt + 1 >= self.max_attempts:
                self._last_post = (post, time.time()) if verdict["reason"] == "no_effect" else None
                break
            t0 = time.perf_counter()
            back = self.recover(pre, post, verdict, self._recovery_names(goal, post, verdict))     # undo it before anything else is tried
            timed("recover", t0)
            rec.attempts[-1]["rollback"] = back
            if not (back or {}).get("restored"):
                break                                                                                  # could not get back to where we were: no second guess on a screen we do not understand
            rec.rolled_back = True
            if action.get("target_id") is not None:
                exclude.append(action["target_id"])
            try:
                pre = look(fresh=True)
            except Exception:
                break
        tm["total"] = round(time.perf_counter() - t_all, 2)
        rec.timings = tm
        rec.ms = round((time.perf_counter() - t_all) * 1000, 1)
        self.history.append(rec)
        return rec

    def _learn(self, goal: str, action: Dict[str, Any], rec: StepRecord, post: Dict[str, Any], worked: bool, effect: str, ms: float, reason: str = "") -> bool:
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
                                     ok=bool(worked), effect=effect if worked else (reason or "no_effect"), latency_ms=float(ms), failure_code="" if worked else (reason or "no_effect"), observed_dst=rec.dst_state))
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

    def __init__(self, launch_name: str, uia_first: bool = True):
        from core_organs.harvest.local_recorder import OwnedApp
        self.app = OwnedApp(launch_name)
        self.eff = None
        self.origin = (0, 0)
        self.size = (0, 0)
        self.uia_first = uia_first

    def __enter__(self) -> "LiveSession":
        self.app.__enter__()
        from core_organs.professor.effectors import Effector
        self.eff = Effector(self.app.hwnd, allow_input=True, owned=True)
        return self

    def __exit__(self, *exc) -> bool:
        return self.app.__exit__(*exc)

    def observe_lite(self, min_controls: int = 8) -> Dict[str, Any]:
        """The cheap observation: the picture and the UIA tree; the Set-of-Marks comes from the tree (no OCR). Falls back to the full scan when the app names fewer than `min_controls` controls."""
        self._repark()
        img, origin = None, (0, 0)
        for _ in range(3):
            img, origin = self.app.grab(popups=True, stable=False)
            if img is not None:
                break
            time.sleep(0.5)
        if img is None:
            raise RuntimeError("no picture of the window")
        self.origin, self.size = origin, img.size
        try:
            controls = [{"name": c["name"], "type": c["type"], "box": c["box"], "toggle": self._toggle(c["ctl"]), "ctl": c["ctl"]} for c in self.app.controls(origin, img.size)]
        except Exception:
            controls = []
        if len(controls) < min_controls:
            return self.observe()
        controls = CF.drop_chrome(controls, img.size)                  # the window frame is not part of the application: never a candidate
        controls, tier = PT.augment(img, controls)                     # a thin tree or an empty work area: the picture's OCR words and icons join the candidates
        som = som_from_controls(controls, img.size)
        if tier.get("added"):
            som["tiers_used"] = ["uia"] + [t for t in ("ocr", "icon") if tier.get({"ocr": "ocr", "icon": "icons"}[t])]
            som["picture_tier"] = tier
        return {"image": img, "som": som, "controls": controls, "doc": self._doc()}

    def observe(self) -> Dict[str, Any]:
        from core_organs.harvest import video_pipeline as VP
        self._repark()
        img, origin = None, (0, 0)
        for _ in range(3):                                         # a frame can fail to render for a moment (measured: the first grab after a window settles)
            img, origin = self.app.grab(popups=True)
            if img is not None:
                break
            time.sleep(0.8)
        if img is None:
            raise RuntimeError("no picture of the window")
        self.origin = origin
        self.size = img.size
        som = VP.som_of_frame(img)
        controls: List[Dict[str, Any]] = []
        for attempt in range(2):
            try:
                controls = [{"name": c["name"], "type": c["type"], "box": c["box"], "toggle": self._toggle(c["ctl"]), "ctl": c["ctl"]} for c in self.app.controls(origin, img.size)]
            except Exception:
                controls = []
            if len(controls) >= 5:
                break
            time.sleep(0.6)                                        # a half-read tree (measured: Strikethrough missing right after a toolbar click) is read again
        return {"image": img, "som": som, "controls": CF.drop_chrome(controls, img.size), "doc": self._doc()}

    def _doc(self) -> str:
        try:
            return self.app.doc_text()
        except Exception:
            return ""

    def _repark(self) -> None:
        """MEASURED: opening Notepad's Link dialog moved the PARKED window onto the real screen (rect -345,0 .. 755,760). It is put back to its off-screen sliver straight away."""
        try:
            if getattr(self.app, "bg", None) is not None and self.app.bg.mode == "parked":
                self.app.bg.lay_out(settle_s=0.0)
        except Exception:
            pass

    @staticmethod
    def _toggle(ctl: Any) -> Optional[int]:
        try:
            import uiautomation as auto
            pat = ctl.GetPattern(auto.PatternId.TogglePattern)
            return int(pat.ToggleState) if pat is not None else None
        except Exception:
            return None

    def recover(self, pre: Dict[str, Any], post: Dict[str, Any], verdict: Dict[str, Any], names: Sequence[str]) -> Dict[str, Any]:
        """Undo a wrong effect and check that the screen is back: a dialog is dismissed (Escape; then a button the recovery playbook / the safe list names), a toggle that flipped by mistake is flipped back.
        `restored` = the control names on screen are again those of the screen before the click."""
        from core_organs import headless_input as hin
        how: List[str] = []

        def same() -> bool:
            try:
                now = {(c["type"], c["name"].lower()) for c in self.app.controls(self.origin, self.size)}
            except Exception:
                return False
            before = {(c["type"], c["name"].lower()) for c in pre.get("controls") or []}
            return bool(before) and len(before & now) / max(len(before | now), 1) >= 0.9
        if verdict.get("reason") in ("unexpected_dialog", "wrong_control", "no_dialog"):
            for nm in names:                                       # a posted Escape is ignored by a XAML dialog (measured): the dismissal button the playbook / safe list names goes first
                ctl = next((c for c in self.app.controls(self.origin, self.size) if c["name"].lower() == nm.lower()), None)
                if ctl is not None and self.app.act(ctl["ctl"]):
                    how.append(f"clicked {nm}")
                    time.sleep(0.8)
                    break
            self._repark()
            if not same():
                hin.post_key_combo(self.app.hwnd, "esc")
                how.append("escape")
                time.sleep(0.8)
                self._repark()
        if not same() or verdict.get("reason") in ("wrong_control", "toggle_unchanged"):
            tname = verdict.get("target", "")
            before = next((c for c in pre.get("controls") or [] if c["name"] == tname), None)
            now = next((c for c in self.app.controls(self.origin, self.size) if c["name"] == tname), None)
            if before is not None and now is not None and before.get("toggle") is not None and self._toggle(now["ctl"]) != before.get("toggle"):
                try:
                    import uiautomation as auto
                    now["ctl"].GetPattern(auto.PatternId.TogglePattern).Toggle()
                    how.append(f"toggled {tname} back")
                    time.sleep(0.6)
                except Exception:
                    pass
        return {"restored": same(), "how": ", ".join(how) or "nothing to undo"}

    foreground_ok = os.environ.get("HOJAIGA_ALLOW_FOREGROUND") == "1"      # bringing the window to the front takes the person's focus: off unless they allowed it

    def ensure_ready(self, force: bool = False, win: Any = None) -> Dict[str, Any]:
        """Before an action is sent, the window must be able to receive it (measured: a second launch of a packaged app stayed on its splash / cloaked and the click was 'not delivered'; a PowerPoint title never got its text).
        A minimised window is restored WITHOUT being activated; a cloaked / zero-size frame is reported; the foreground is taken only when the person allowed it (`foreground_ok`) or the window already has it.
        `win` is the Win32 surface (tests pass a fake)."""
        notes: List[str] = []
        if win is None:
            import ctypes
            u = ctypes.windll.user32

            class _Win:
                IsIconic = staticmethod(lambda h: bool(u.IsIconic(h)))
                ShowNoActivate = staticmethod(lambda h: u.ShowWindow(h, 4))
                Foreground = staticmethod(lambda: u.GetForegroundWindow())
                SetForeground = staticmethod(lambda h: u.SetForegroundWindow(h))

                @staticmethod
                def cloaked(h: int) -> bool:
                    v = ctypes.c_int(0)
                    try:
                        ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(v), 4)
                    except Exception:
                        return False
                    return bool(v.value)
            win = _Win
        h = self.app.hwnd
        try:
            if win.IsIconic(h):
                win.ShowNoActivate(h)
                notes.append("restored from minimised (not activated)")
            if win.cloaked(h):
                notes.append("window is cloaked (splash / not drawn yet)")
            if win.Foreground() == h:
                notes.append("already in front")
            elif self.foreground_ok:
                win.SetForeground(h)
                notes.append("brought to the front (allowed)")
        except Exception as exc:
            notes.append(f"ready check failed: {type(exc).__name__}")
        return {"ready": not any("cloaked" in n for n in notes), "notes": notes}

    def fresh_box(self, el: Dict[str, Any]) -> Tuple[Tuple[int, int, int, int], str]:
        """The box a control has NOW (the layout may have moved since the picture was taken): the control with the element's name and type nearest to its old centre, else the old box."""
        x, y, w, h = el["box"]
        try:
            cx, cy = x + w / 2, y + h / 2
            same = [c for c in self.app.controls(self.origin, self.size) if c["name"] == el.get("label") and c["box"][2] > 3 and c["box"][3] > 3]
            if same:
                best = min(same, key=lambda c: (c["box"][0] + c["box"][2] / 2 - cx) ** 2 + (c["box"][1] + c["box"][3] / 2 - cy) ** 2)
                nb = tuple(int(v) for v in best["box"])
                if abs(nb[0] - x) > 3 or abs(nb[1] - y) > 3:
                    return nb, f"re-measured: moved ({nb[0] - int(x)},{nb[1] - int(y)})"
                return nb, ""
        except Exception:
            pass
        return (int(x), int(y), int(w), int(h)), ""

    def act(self, action: Dict[str, Any], som: Dict[str, Any]) -> Tuple[bool, str]:
        self.ensure_ready()
        res = self._act(action, som)
        if not res[0] and not str(res[1]).startswith("refused"):                   # not delivered: make the window ready again, measure again, send once more
            ready = self.ensure_ready(force=True)
            time.sleep(0.5)
            res2 = self._act(action, som)
            res = (res2[0], res2[1] + (" (after re-check: " + "; ".join(ready["notes"]) + ")" if res2[0] else "")) if res2[0] else (False, f"{res[1]} | retry: {res2[1]}")
        self._repark()
        return res

    def _act(self, action: Dict[str, Any], som: Dict[str, Any]) -> Tuple[bool, str]:
        kind = action["action"]
        if kind == "click":
            el = element_by_id(som, action.get("target_id"))
            from core_organs import chrome_filter as _CF
            if _CF.is_window_chrome(str(el.get("label", "")), "", el["box"], self.size):
                return False, f"refused: {el.get('label')!r} is window chrome"
            (x, y, w, h), moved = self.fresh_box(el)
            cx, cy = x + w / 2, y + h / 2
            if self.uia_first:
                # MEASURED on an owned Notepad: a UIA pattern call on the control under the point worked 3 of 3; the posted mouse click worked 2 of 3 (and 0 of 4 in the multi-step run). So the control the
                # point falls in is operated through its own pattern, and the posted click is the fallback for what UIA does not expose.
                try:
                    under = [c for c in self.app.controls(self.origin, self.size) if c["box"][0] <= cx <= c["box"][0] + c["box"][2] and c["box"][1] <= cy <= c["box"][1] + c["box"][3]]
                    if under:
                        best = min(under, key=lambda c: c["box"][2] * c["box"][3])
                        if _CF.is_window_chrome(best["name"], best.get("type", ""), best["box"], self.size):
                            return False, f"refused: {best['name']!r} is window chrome"
                        how = self.app.act(best["ctl"])
                        if how:
                            return True, f"uia {how} on {best['name']!r}"
                except Exception:
                    pass
            ok, msg = self.eff.click_xy(int(self.origin[0] + cx), int(self.origin[1] + cy))
            return ok, (msg + " " + moved).strip() if moved else msg
        if kind == "hotkey":
            return self.eff.key(str(action["hotkey"]))
        return self.eff.insert_text(str(action.get("text") or ""))
