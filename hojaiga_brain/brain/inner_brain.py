# brain/inner_brain.py
"""
The brain inside the brain.

InnerBrain is a fast student that grows from the main brain's verified work:
  * inner RAG     — question → answer memory with embeddings, confirmations and failures
  * inner LLM     — a small HojaigaLLM distilled on that memory (trained by `distill`)
  * inner policy  — answer only when the nearest remembered question is near-identical AND the
                    memory has been confirmed more than refuted; otherwise defer to the main brain

DualBrain wires them: inner first → main brain when unsure → verified main answers are distilled
into the inner brain, corrections overwrite it. `self_reliance` = share of questions the inner
brain answered on its own; it rises as the brain learns.
"""
import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

try:
    from langgraph.graph import END, StateGraph
    HAS_LANGGRAPH = True
except Exception:
    HAS_LANGGRAPH = False


class InnerBrain:
    def __init__(self, store_dir: Path, embed: Callable[[str], np.ndarray],
                 match_threshold: float = 0.9, trust_threshold: float = 0.6):
        self.dir = Path(store_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.embed = embed
        self.match_threshold = match_threshold
        self.trust_threshold = trust_threshold
        self.memory: List[Dict[str, Any]] = []
        self.stats = {"inner_answers": 0, "main_answers": 0, "distilled": 0, "corrections": 0}
        self.llm = None
        self._load()

    # ------------------------------------------------------------------ persistence
    def _load(self) -> None:
        p = self.dir / "inner_memory.json"
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            self.memory, self.stats = st.get("memory", []), {**self.stats, **st.get("stats", {})}

    def save(self) -> None:
        tmp = self.dir / "inner_memory.tmp"
        tmp.write_text(json.dumps({"memory": self.memory, "stats": self.stats}), encoding="utf-8")
        tmp.replace(self.dir / "inner_memory.json")

    # ------------------------------------------------------------------ memory
    def _nearest(self, question: str):
        if not self.memory:
            return None, 0.0
        q = self.embed(question)
        sims = [float(np.dot(q, np.asarray(m["vec"], dtype=np.float32))) for m in self.memory]
        i = int(np.argmax(sims))
        return self.memory[i], sims[i]

    @staticmethod
    def trust(m: Dict[str, Any]) -> float:
        return (m["confirmations"] + 1) / (m["confirmations"] + m["failures"] + 2)

    def recall(self, question: str) -> Optional[Dict[str, Any]]:
        m, sim = self._nearest(question)
        if m is None or sim < self.match_threshold or self.trust(m) < self.trust_threshold or m["failures"] > m["confirmations"]:
            return None
        return {"answer": m["answer"], "similarity": round(sim, 4), "trust": round(self.trust(m), 3),
                "source": m["source"]}

    def learn(self, question: str, answer: str, source: str = "main_brain") -> str:
        """Same question again with a consistent answer → confirmation; a different answer replaces
        the old one only if the old one is not better established."""
        m, sim = self._nearest(question)
        if m is not None and sim >= 0.97:
            same_text = float(np.dot(self.embed(answer), np.asarray(m["avec"], dtype=np.float32))) >= 0.9
            same_numbers = self._numbers(answer) == self._numbers(m["answer"])
            if source != "human" and same_text and same_numbers:
                m["confirmations"] += 1
                state = "confirmed"
            elif source == "human" or m["confirmations"] <= 1:
                m.update(answer=answer, avec=self.embed(answer).tolist(), source=source,
                         confirmations=1, failures=0)
                state = "replaced"
            else:
                m["failures"] += 1
                state = "disputed"
            m["ts"] = time.time()
        else:
            self.memory.append({"question": question, "answer": answer, "source": source,
                                "vec": self.embed(question).tolist(), "avec": self.embed(answer).tolist(),
                                "confirmations": 1, "failures": 0, "ts": time.time()})
            state = "new"
        self.stats["distilled"] += 1
        self.save()
        return state

    @staticmethod
    def _numbers(text: str) -> List[str]:
        """'three to five days' vs 'two to four days' look alike as text; their facts do not."""
        import re
        return sorted(re.findall(r"\d+(?:\.\d+)?|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
                                 r"eleven|twelve|hundred|thousand|million|billion)\b", text.lower()))

    def correct(self, question: str, answer: str) -> None:
        self.learn(question, answer, source="human")
        m, _ = self._nearest(question)
        m["confirmations"] = max(m["confirmations"], 3)          # a human correction is strong evidence
        self.stats["corrections"] += 1
        self.save()

    def penalize(self, question: str) -> None:
        m, sim = self._nearest(question)
        if m is not None and sim >= self.match_threshold:
            m["failures"] += 1
            self.save()

    # ------------------------------------------------------------------ inner LLM distillation
    def distill_llm(self, tokenizer, variant: str = "tiny_5m", epochs: int = 2) -> Dict[str, Any]:
        """Train the inner brain's own small language model on its confirmed Q→A memory."""
        from brain.config import LLMConfig
        from brain.tokenizer_and_llm import HAS_TORCH, HojaigaLLM
        pairs = [m for m in self.memory if m["confirmations"] > m["failures"]]
        if not pairs:
            return {"trained_pairs": 0}
        cfg = LLMConfig.from_variant(variant)
        self.llm = self.llm or HojaigaLLM(cfg)
        loss = 0.0
        if HAS_TORCH:
            import torch
            ck = self.dir / f"inner_llm_{variant}.pt"
            if ck.exists() and not getattr(self, "_llm_loaded", False):
                self.llm.load_state_dict(torch.load(ck, map_location="cpu", weights_only=True))
            self._llm_loaded = True
            opt = torch.optim.AdamW(self.llm.parameters(), lr=3e-4, weight_decay=0.01)
            self.llm.train()
            for _ in range(epochs):
                for m in pairs:
                    ids = tokenizer.encode(f"{m['question']}\n{m['answer']}", add_bos=True, add_eos=True)
                    ids = [i % cfg.vocab_size for i in ids][: cfg.max_seq_len + 1]
                    if len(ids) < 2:
                        continue
                    x, y = torch.tensor([ids[:-1]]), torch.tensor([ids[1:]])
                    opt.zero_grad()
                    out = self.llm(x, targets=y, target_value=torch.tensor([self.trust(m)]))
                    out["loss"].backward()
                    torch.nn.utils.clip_grad_norm_(self.llm.parameters(), 1.0)
                    opt.step()
                    loss = float(out["loss"].item())
            torch.save(self.llm.state_dict(), ck)
        else:
            for _ in range(epochs):
                for m in pairs:
                    ids = tokenizer.encode(f"{m['question']}\n{m['answer']}", add_bos=True, add_eos=True)
                    loss = self.llm.fit_sequence([i % cfg.vocab_size for i in ids], reward_value=self.trust(m))
        return {"trained_pairs": len(pairs), "final_loss": round(loss, 4)}


class DualBrain:
    """Ask flow: inner → (confident? done : main) → distill. A LangGraph graph when available."""

    def __init__(self, main_brain, inner: Optional[InnerBrain] = None):
        self.main = main_brain
        self.inner = inner or InnerBrain(main_brain.cfg.workspace_dir / "inner_brain", main_brain.l2.compute_embedding)
        self.graph = self._build_graph() if HAS_LANGGRAPH else None

    # nodes ---------------------------------------------------------------------------------
    def _n_inner(self, s: Dict[str, Any]) -> Dict[str, Any]:
        hit = self.inner.recall(s["question"])
        return {"inner_hit": hit}

    def _n_main(self, s: Dict[str, Any]) -> Dict[str, Any]:
        return {"main_result": self.main.run_cognitive_cycle(s["question"], media_payload=s.get("media"))}

    def _n_distill(self, s: Dict[str, Any]) -> Dict[str, Any]:
        r = s["main_result"]
        ok = r["verification"].get("passes_verification") and r["value_tier"] in ("GOOD", "BETTER", "BEST")
        body = r["answer"].split(" [Sources:")[0]
        return {"distilled": self.inner.learn(s["question"], body) if ok else "not_verified"}

    def _build_graph(self):
        from typing import TypedDict

        class AskState(TypedDict, total=False):
            question: str
            media: Any
            inner_hit: Any
            main_result: Any
            distilled: str

        g = StateGraph(AskState)
        g.add_node("inner_brain", self._n_inner)
        g.add_node("main_brain", self._n_main)
        g.add_node("distill", self._n_distill)
        g.set_entry_point("inner_brain")
        g.add_conditional_edges("inner_brain", lambda s: END if s.get("inner_hit") else "main_brain",
                                {END: END, "main_brain": "main_brain"})
        g.add_edge("main_brain", "distill")
        g.add_edge("distill", END)
        return g.compile()

    # public --------------------------------------------------------------------------------
    def ask(self, question: str, media=None) -> Dict[str, Any]:
        t0 = time.time()
        state: Dict[str, Any] = {"question": question, "media": media}
        if self.graph is not None:
            state = self.graph.invoke(state)
        else:
            state.update(self._n_inner(state))
            if not state.get("inner_hit"):
                state.update(self._n_main(state))
                state.update(self._n_distill(state))
        if state.get("inner_hit"):
            self.inner.stats["inner_answers"] += 1
            out = {"answer": state["inner_hit"]["answer"], "answered_by": "inner_brain",
                   "inner": state["inner_hit"]}
        else:
            self.inner.stats["main_answers"] += 1
            r = state["main_result"]
            out = {"answer": r["answer"], "answered_by": "main_brain", "value_tier": r["value_tier"],
                   "verification": r["verification"], "distilled_into_inner": state.get("distilled")}
        self.inner.save()
        out["self_reliance"] = self.self_reliance()
        out["ms"] = round((time.time() - t0) * 1000, 1)
        return out

    def feedback(self, question: str, good: bool, correction: Optional[str] = None) -> Dict[str, Any]:
        if correction:
            self.main.run_cognitive_cycle(question, user_correction=correction)
            self.inner.correct(question, correction)
        elif not good:
            self.inner.penalize(question)
        else:
            m, sim = self.inner._nearest(question)
            if m is not None and sim >= self.inner.match_threshold:
                m["confirmations"] += 1
                self.inner.save()
        return {"recorded": True, "self_reliance": self.self_reliance()}

    def self_reliance(self) -> float:
        n = self.inner.stats["inner_answers"] + self.inner.stats["main_answers"]
        return round(self.inner.stats["inner_answers"] / n, 4) if n else 0.0
