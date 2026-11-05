# brain/curiosity_and_langchain.py
import base64
import io
import json
import math
import os
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, TypedDict, Union

import numpy as np
from brain.config import BrainSystemConfig
from brain.dataset_ingestor import UniversalDatasetIngestor
from brain.layers_l1_to_l8 import (
    Layer1ThalamusFilter,
    Layer3WernickeUnderstand,
    Layer4PrefrontalReason,
    Layer5DefaultModeThink,
    Layer6BrocaAnswer,
    Layer7ACCVerify,
    Layer8BasalGangliaLearn,
    ThoughtCandidate,
)
from brain.rag_hippocampus import HippocampusRAGEngine
from brain.tokenizer_and_llm import HAS_TORCH, HojaigaLLM, HojaigaTokenizer
from brain.vlm_encoder import HojaigaVLMEncoder


class BrainExecutionState(TypedDict):
    raw_input: str
    media_payload: Optional[Any]
    segregated_steps: List[str]
    emergent_domain: str
    interface_scan: Dict[str, Any]
    answer: str
    provenance: str
    value_tier: str
    value_score: float
    verification: Dict[str, Any]
    autonomy_status: Dict[str, Any]


class HojaigaExecutiveBrain:
    """
    Zero-Hardcoding Natural Intelligence Controller:
    - Accepts ANY dataset or live task (`feed_dataset` / `run_cognitive_cycle`)
    - Recognizes ANY app UI or diagram dynamically via Adaptive Resonance (`HojaigaVLMEncoder`)
    - Segregates multi-part inputs into ordered execution steps dynamically based on discovered clause/graph structure
    - Escalates to an external Teacher ONLY when the specific emergent domain/interface has not yet graduated
      and local verification or visual epistemic surprise requires guidance.
    """

    def __init__(self, cfg: Optional[BrainSystemConfig] = None):
        self.cfg = cfg or BrainSystemConfig()
        self.cfg.ensure_dirs()

        self.tokenizer = HojaigaTokenizer(vocab_size=self.cfg.llm.vocab_size)
        self.llm = HojaigaLLM(self.cfg.llm)
        self.vlm = HojaigaVLMEncoder(self.cfg.vlm, memory_dir=self.cfg.workspace_dir / "ui_topologies")

        self.l1 = Layer1ThalamusFilter()
        self.l2 = HippocampusRAGEngine(self.cfg.workspace_dir / "rag_store")
        self.l3 = Layer3WernickeUnderstand()
        self.l4 = Layer4PrefrontalReason()
        self.l5 = Layer5DefaultModeThink()
        self.l6 = Layer6BrocaAnswer()
        self.l7 = Layer7ACCVerify(self.l2)
        self.l8 = Layer8BasalGangliaLearn(self.cfg.workspace_dir / "episodic_db", self.l2)
        self.l8.min_runs = self.cfg.min_runs_before_graduation
        self.l8.threshold = self.cfg.graduation_competence_threshold

        self.ingestor = UniversalDatasetIngestor(
            tokenizer=self.tokenizer,
            vlm=self.vlm,
            l1=self.l1,
            l2=self.l2,
            l3=self.l3,
            l5=self.l5,
            l6=self.l6,
            replay_buffer=self.l8.golden_replay_buffer,
        )
        self.teacher_calls = 0
        self.llm_trained = False
        self._load_learned_state()

    # ------------------------------------------------------------------ persistence
    @property
    def _ckpt_dir(self):
        return self.cfg.workspace_dir / "checkpoints"

    @property
    def _state_path(self):
        return self.cfg.workspace_dir / "episodic_db" / "brain_state.json"

    def _load_learned_state(self) -> None:
        """Everything the brain learned in earlier runs: tokenizer merges, trained network,
        L1 document statistics, L3 intent model, L5 value/style statistics, L6 span edits,
        L8 failure memory, graduation history and replay buffer."""
        tok_path = self._ckpt_dir / "tokenizer.json"
        if tok_path.exists():
            self.tokenizer = HojaigaTokenizer.load(tok_path)
            self.ingestor.tokenizer = self.tokenizer
        if HAS_TORCH:
            import torch
            ck = self._ckpt_dir / f"hojaiga_{self.cfg.llm.variant}.pt"
            if ck.exists():
                self.llm.load_state_dict(torch.load(ck, map_location="cpu", weights_only=True))
                self.llm_trained = True
        else:
            ck = self._ckpt_dir / f"hojaiga_{self.cfg.llm.variant}_numpy.npz"
            if ck.exists():
                z = np.load(ck, allow_pickle=False)
                for k in ("embed_matrix", "lora_A", "lora_B", "value_w", "verify_w"):
                    setattr(self.llm, k, z[k])
                cont = json.loads((self._ckpt_dir / "numpy_continuations.json").read_text(encoding="utf-8"))
                self.llm.learned_continuations = {int(k): Counter({int(a): b for a, b in v.items()})
                                                  for k, v in cont.items()}
                self.llm_trained = True
        if not self._state_path.exists():
            return
        st = json.loads(self._state_path.read_text(encoding="utf-8"))
        self.l1.doc_freq = Counter(st.get("l1_doc_freq", {}))
        self.l1.total_docs = st.get("l1_total_docs", 0)
        self.l1.seen_simhashes = st.get("l1_simhashes", [])
        self.l3.cluster_word_counts = defaultdict(Counter, {k: Counter(v) for k, v in st.get("l3_counts", {}).items()})
        self.l3.cluster_totals = Counter(st.get("l3_totals", {}))
        self.l3.vocab = set(st.get("l3_vocab", []))
        l5 = st.get("l5", {})
        if l5:
            self.l5.weights = np.asarray(l5["weights"], dtype=np.float64)
            self.l5.bias = l5["bias"]
            self.l5.target_burstiness, self.l5.target_ttr = l5["target_burstiness"], l5["target_ttr"]
            self.l5.score_count, self.l5.score_mean, self.l5.score_m2 = l5["count"], l5["mean"], l5["m2"]
        self.l6.learned_span_edits = st.get("l6_edits", {})
        self.l8.failure_memory.clear()
        self.l8.failure_memory.extend(st.get("l8_failures", []))
        self.l8.failure_memory.endorsed = st.get("l8_endorsed", [])
        self.l8.domain_outcomes = defaultdict(list, st.get("l8_outcomes", {}))
        self.l8.golden_replay_buffer[:] = st.get("l8_replay", [])
        self.teacher_calls = st.get("teacher_calls", 0)

    def save_learned_state(self) -> None:
        self._ckpt_dir.mkdir(parents=True, exist_ok=True)
        self.tokenizer.save(self._ckpt_dir / "tokenizer.json")
        st = {
            "l1_doc_freq": dict(self.l1.doc_freq), "l1_total_docs": self.l1.total_docs,
            "l1_simhashes": self.l1.seen_simhashes[-20000:],
            "l3_counts": {k: dict(v) for k, v in self.l3.cluster_word_counts.items()},
            "l3_totals": dict(self.l3.cluster_totals), "l3_vocab": sorted(self.l3.vocab),
            "l5": {"weights": self.l5.weights.tolist(), "bias": self.l5.bias,
                   "target_burstiness": self.l5.target_burstiness, "target_ttr": self.l5.target_ttr,
                   "count": self.l5.score_count, "mean": self.l5.score_mean, "m2": self.l5.score_m2},
            "l6_edits": self.l6.learned_span_edits,
            "l8_failures": list(self.l8.failure_memory)[-5000:],
            "l8_endorsed": self.l8.failure_memory.endorsed[-5000:],
            "l8_outcomes": dict(self.l8.domain_outcomes),
            "l8_replay": self.l8.golden_replay_buffer[-20000:],
            "teacher_calls": self.teacher_calls,
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._state_path)

    def feed_dataset(self, source: Union[str, os.PathLike, np.ndarray, Dict[str, Any]], hint: str = "") -> Dict[str, Any]:
        res = self.ingestor.ingest_any(source, hint=hint)
        self.l2.save()
        self.save_learned_state()
        return res

    # ------------------------------------------------------------------ answer synthesis
    def _token_weights(self, tokens: List[str]) -> Dict[str, float]:
        """Corpus IDF from L1's document statistics: rare, specific words carry the question."""
        n = max(self.l1.total_docs, 1)
        return {t: math.log(1.0 + (n + 1.0) / (self.l1.doc_freq.get(t, 0) + 0.5)) for t in set(tokens)}

    @staticmethod
    def _match(q_tok: str, s_toks: set) -> bool:
        if q_tok in s_toks:
            return True
        if len(q_tok) < 5:
            return False
        stem = q_tok[: max(5, len(q_tok) - 2)]
        return any(len(t) >= 5 and (t.startswith(stem) or q_tok.startswith(t[: max(5, len(t) - 2)])) for t in s_toks)

    def _synthesize_from_memory(self, query: str, episodes: List[Any], max_sentences: int = 3) -> tuple:
        """Pick the sentences that answer the question instead of pasting whole memories:
        each sentence is scored by the IDF weight of the question words it contains."""
        q_toks = self.l2.tokenize(query)
        weights = self._token_weights(q_toks)
        total = sum(weights.values()) or 1.0
        scored = []
        for e_rank, ep in enumerate(episodes):
            for s_idx, sent in enumerate(re.split(r"(?<=[.!?])\s+|\n+", ep.content)):
                sent = sent.strip()
                if len(sent.split()) < 3:
                    continue
                s_toks = set(self.l2.tokenize(sent))
                cov = sum(w for t, w in weights.items() if self._match(t, s_toks)) / total
                scored.append((cov - 0.01 * e_rank, e_rank, s_idx, sent))
        if not scored:
            return "", []
        best = max(sc[0] for sc in scored)
        keep = sorted([sc for sc in scored if sc[0] >= 0.75 * best], key=lambda x: -x[0])[:max_sentences]
        keep.sort(key=lambda x: (x[1], x[2]))
        used = list(dict.fromkeys(episodes[k[1]].source_uri for k in keep))
        return " ".join(dict.fromkeys(k[3] for k in keep)), used

    def segregate_task_dynamically(self, clean_text: str, salient_terms: List[str], has_visual: bool) -> List[str]:
        sub_clauses = [c.strip() for c in clean_text.replace(";", ".").split(".") if c.strip()]
        steps = [
            f"1. [L1 Filter]: Gate entropy & extract top salient anchors ({', '.join(salient_terms[:5]) or 'stream'})."
        ]
        if has_visual:
            steps.append(
                "2. [VLM Curiosity Topology]: Extract connected visual contours, match against learned interface prototypes, and measure epistemic surprise."
            )
        for idx, clause in enumerate(sub_clauses[:4], start=len(steps) + 1):
            steps.append(f"{idx}. [Sub-Task Execution]: Resolve '{clause[:80]}' via L2 Hippocampus RRF & L4 PageRank/AST.")
        steps.append(
            f"{len(steps) + 1}. [L5-L8 Homeostasis]: Score 5-tier value quantile, apply learned L6 span edits, verify grounding in L7, and update L8 autonomy."
        )
        return steps

    def _consult_teacher_if_needed(
        self, domain_id: str, prompt: str, visual_rgb: Optional[np.ndarray] = None
    ) -> Optional[str]:
        if self.l8.is_domain_graduated(
            domain_id,
            min_runs=self.cfg.min_runs_before_graduation,
            threshold=self.cfg.graduation_competence_threshold,
        ):
            return None

        provider = self.cfg.teacher_provider
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key and provider in ("auto", "anthropic"):
            try:
                import anthropic
                from PIL import Image

                client = anthropic.Anthropic(api_key=api_key)
                blocks: List[Dict[str, Any]] = []
                if visual_rgb is not None:
                    buf = io.BytesIO()
                    Image.fromarray(visual_rgb.astype(np.uint8)).save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    blocks.append(
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}
                    )
                blocks.append({"type": "text", "text": prompt})
                model_name = self.cfg.teacher_model or os.environ.get("HOJAIGA_TEACHER_MODEL", "claude-opus-5-5")
                self.teacher_calls += 1
                resp = client.messages.create(
                    model=model_name, max_tokens=2000, messages=[{"role": "user", "content": blocks}]
                )
                if getattr(resp, "stop_reason", None) == "refusal":
                    return None
                text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
                return text.strip() or None
            except Exception:
                return None
        if provider in ("auto", "ollama"):
            try:
                import requests

                model_name = self.cfg.teacher_model or os.environ.get("HOJAIGA_TEACHER_MODEL", "qwen2.5:7b")
                url = os.environ.get("HOJAIGA_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
                msg: Dict[str, Any] = {"role": "user", "content": prompt}
                if visual_rgb is not None:
                    from PIL import Image
                    buf = io.BytesIO()
                    Image.fromarray(visual_rgb.astype(np.uint8)).save(buf, format="PNG")
                    msg["images"] = [base64.b64encode(buf.getvalue()).decode("utf-8")]
                self.teacher_calls += 1
                r = requests.post(url, json={"model": model_name, "messages": [msg], "stream": False}, timeout=120)
                r.raise_for_status()
                return (r.json().get("message", {}).get("content") or "").strip() or None
            except Exception:
                return None
        return None

    def run_cognitive_cycle(
        self,
        raw_input: str,
        media_payload: Optional[np.ndarray] = None,
        user_correction: Optional[str] = None,
    ) -> Dict[str, Any]:
        active_layers = ["L1:Filter"]
        l1_res = self.l1.process(raw_input)
        clean_q = l1_res["clean_text"]
        salient = l1_res["salient_terms"]

        vis_embeds = None
        ui_scan: Dict[str, Any] = {"recognized_from_memory": False, "epistemic_surprise": 0.0, "discovered_regions_count": 0}
        if isinstance(media_payload, np.ndarray) and media_payload.ndim == 3:
            active_layers.append("VLM:DynamicTopology")
            ui_scan = self.vlm.perceive_and_remember_interface(media_payload, context_hint=salient[0] if salient else "")
            vis_embeds = ui_scan.pop("vision_tokens", None)

        steps = self.segregate_task_dynamically(clean_q, salient, has_visual=(vis_embeds is not None))

        active_layers.append("L2:Know")
        retrieved = self.l2.retrieve_rrf(clean_q, top_k=4)
        episodes = [ep for ep, _ in retrieved]

        q_vec = self.l2.compute_embedding(clean_q)
        domain_id, text_surprise = self.l2.domain_clusterer.assign_and_update(q_vec, salient)
        if ui_scan.get("interface_id"):
            domain_id = f"{domain_id}::{ui_scan['interface_id']}"
        combined_surprise = max(text_surprise, float(ui_scan.get("epistemic_surprise", 0.0)))

        active_layers.append("L3:Understand")
        intent_mode, _ = self.l3.predict_and_adapt_intent(clean_q)
        keyphrases = self.l3.extract_dynamic_keyphrases(clean_q, l1_res["salience_map"])
        # (the blueprint stored every question as knowledge, so later answers echoed questions back;
        #  questions are kept in L8's outcome history instead)

        active_layers.append("L4:Reason")
        math_val = self.l4.evaluate_symbolic_math(clean_q)
        ppr = self.l4.personalized_pagerank(self.l2.concept_triples, salient)
        chains = self.l4.forward_chain(self.l2.concept_triples, salient)

        active_layers.append("L5:Think")
        candidates: List[ThoughtCandidate] = []

        if math_val is not None:
            ans_str = f"{self.l4.last_expression} = {math_val:g}"
            pain = self.l8.compute_pain_overlap(ans_str)
            sc, tier, feats = self.l5.score_and_classify_tier(ans_str, 1.0, 1.0, pain)
            # an exact AST evaluation of the question's own expression is self-verifying:
            # writing-style statistics must not out-vote it
            if pain < 0.72:
                sc, tier = max(sc, 0.99), "BEST"
            candidates.append(ThoughtCandidate("L4_Exact_Symbolic", ans_str, feats, sc, tier, pain))

        memory_sources: List[str] = []
        if episodes:
            synthesized, memory_sources = self._synthesize_from_memory(clean_q, episodes)
            if not synthesized:
                synthesized, memory_sources = episodes[0].content, [episodes[0].source_uri]
            if chains and intent_mode == "emergent_structural_workflow":
                synthesized += f" ({'; '.join(chains[:3])})"
            pain = self.l8.compute_pain_overlap(synthesized)
            grounding = self.l7.check_grounding(synthesized, episodes)
            sc, tier, feats = self.l5.score_and_classify_tier(synthesized, grounding, 0.92, pain)
            candidates.append(ThoughtCandidate("L2_L4_Memory_Graph", synthesized, feats, sc, tier, pain))

        llm_gen, llm_diag = "", {}
        if self.llm_trained:      # an untrained network only produces noise
            mm = vis_embeds if (vis_embeds is not None and getattr(vis_embeds, "shape", [0])[-1] == self.cfg.llm.dim) else None
            llm_gen, llm_diag = self.llm.generate(self.tokenizer, clean_q, multimodal_embeds=mm, max_new_tokens=80)
        if llm_gen:
            pain = self.l8.compute_pain_overlap(llm_gen)
            grounding = self.l7.check_grounding(llm_gen, episodes)
            sc, tier, feats = self.l5.score_and_classify_tier(llm_gen, grounding, llm_diag["verifier_confidence"], pain)
            candidates.append(ThoughtCandidate("Local_Neural_Backbone", llm_gen, feats, sc, tier, pain))

        if not candidates:
            synth = f"[{intent_mode}] Key concepts: {', '.join(keyphrases or salient)}."
            sc, tier, feats = self.l5.score_and_classify_tier(synth, 0.55, 0.75, 0.0)
            candidates.append(ThoughtCandidate("Emergent_Synthesis", synth, feats, sc, tier, 0.0))

        best_cand = self.l5.select_mmr(candidates)
        if best_cand is None:     # every candidate resembles a remembered failure → abstain, don't repeat it
            synth = "No verified answer yet: every candidate matches a previously refuted answer."
            sc, tier, feats = self.l5.score_and_classify_tier(synth, 0.0, 0.5, 0.0)
            best_cand = ThoughtCandidate("Pain_Blocked_Abstain", synth, feats, sc, "BAD", 0.0)
            candidates.append(best_cand)

        active_layers.append("L7:Verify")
        v_report = self.l7.verify(best_cand.text, candidates, episodes)
        if best_cand.strategy == "L4_Exact_Symbolic":
            # exact AST evaluation of the question's own expression is its own proof; checking it
            # against textbook memory would mark every calculation as ungrounded and poison pain memory
            v_report.update({"grounding": 1.0, "has_contradiction": False, "verified_by": "exact_symbolic_ast",
                             "calibrated_confidence": max(v_report["calibrated_confidence"], 0.99),
                             "passes_verification": True})
        used_teacher = False

        if not v_report["passes_verification"] or combined_surprise > self.cfg.curiosity_surprise_threshold:
            t_ans = self._consult_teacher_if_needed(domain_id, clean_q, visual_rgb=media_payload)
            if t_ans:
                used_teacher = True
                active_layers.append("Teacher:Distillation")
                self.l6.learn_from_edit_pair(best_cand.text, t_ans)
                self.l5.observe_reference_writing(t_ans)
                pain = self.l8.compute_pain_overlap(t_ans)
                sc, tier, feats = self.l5.score_and_classify_tier(t_ans, 0.95, 0.95, pain)
                best_cand = ThoughtCandidate("Teacher_Distilled", t_ans, feats, sc, "BEST", pain)
                t_triples = self.l3.extract_distributional_relations(t_ans, self.l1.process(t_ans)["salience_map"])
                self.l2.ingest_episode(t_ans, modality="teacher_distilled", source_uri="teacher", continuous_value=0.95, triples=t_triples)
                v_report = self.l7.verify(best_cand.text, [best_cand], episodes)

        if user_correction:
            self.l6.learn_from_edit_pair(best_cand.text, user_correction)
            self.l5.observe_reference_writing(user_correction)
            # the corrected answer becomes high-value knowledge so the next answer can come from it
            c_l1 = self.l1.process(user_correction)
            self.l2.ingest_episode(user_correction, modality="correction", source_uri="user_correction",
                                   continuous_value=0.95,
                                   triples=self.l3.extract_distributional_relations(user_correction, c_l1["salience_map"]))

        active_layers.append("L6:Answer")
        sources = memory_sources if best_cand.strategy == "L2_L4_Memory_Graph" else []
        composed = self.l6.compose(best_cand, citations=sources, active_layers=active_layers)

        active_layers.append("L8:Learn")
        autonomy = self.l8.record_outcome(
            domain_id=domain_id,
            query=clean_q,
            output=composed["final_text"],
            value_score=composed["value_score"],
            value_tier=composed["value_tier"],
            verified=v_report["passes_verification"],
            surprise=combined_surprise,
            used_teacher=used_teacher,
            correction=user_correction,
        )
        self.l2.save()
        self.save_learned_state()

        return {
            "segregated_steps": steps,
            "emergent_domain": self.l2.domain_clusterer.get_emergent_cluster_signature(domain_id.split("::")[0]),
            "intent_mode": intent_mode,
            "interface_perception": {k: v for k, v in ui_scan.items() if k != "regions"},
            "top_pagerank_concepts": ppr,
            "answer": composed["final_text"],
            "provenance": composed["provenance_badge"],
            "value_tier": composed["value_tier"],
            "value_score": composed["value_score"],
            "learned_writing_edits_applied": composed["writing_edit_trace"],
            "verification": v_report,
            "autonomy_status": autonomy,
        }
