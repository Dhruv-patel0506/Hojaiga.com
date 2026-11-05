# brain/layers_l1_to_l8.py
import ast
import difflib
import hashlib
import math
import operator
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from brain.rag_hippocampus import HippocampusRAGEngine, MemoryEpisode


# ============================================================================
# L1: FILTER (Thalamus) — 100% Statistical & Information-Theoretic (Zero Hardcoded Lists)
# ============================================================================
class Layer1ThalamusFilter:
    """
    - Normalises Unicode streams
    - Redacts high-entropy credential/PII tokens via character-transition entropy & digit-density analysis
    - Deduplicates via 64-bit SimHash
    - Computes emergent token salience via corpus Inverse Document Frequency (IDF) + local burstiness
      (High-frequency background words automatically converge to salience -> 0 without a hardcoded stopword list)
    """

    def __init__(self, hamming_threshold: int = 3, min_entropy: float = 1.0):
        self.seen_simhashes: List[int] = []
        self.hamming_threshold = hamming_threshold
        self.min_entropy = min_entropy
        self.doc_freq: Counter = Counter()
        self.total_docs: int = 0

    def simhash64(self, text: str) -> int:
        tokens = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
        v = [0] * 64
        for tok in tokens:
            h = int(hashlib.blake2b(tok.encode("utf-8"), digest_size=8).hexdigest(), 16)
            for i in range(64):
                v[i] += 1 if (h & (1 << i)) else -1
        ans = 0
        for i in range(64):
            if v[i] > 0:
                ans |= 1 << i
        return ans

    def shannon_entropy(self, text: str) -> float:
        if not text:
            return 0.0
        counts = Counter(text)
        n = len(text)
        return -sum((c / n) * math.log2(c / n) for c in counts.values())

    def _redact_statistical_secrets(self, text: str) -> str:
        def _inspect_token(match: re.Match) -> str:
            tok = match.group(0)
            if len(tok) < 14:
                return tok
            classes = [
                1 if c.islower() else (2 if c.isupper() else (3 if c.isdigit() else 4))
                for c in tok
            ]
            transitions = sum(1 for i in range(len(classes) - 1) if classes[i] != classes[i + 1])
            ent = self.shannon_entropy(tok)
            if ent > 3.85 and (transitions / len(tok)) > 0.42:
                return "[REDACTED_HIGH_ENTROPY_TOKEN]"
            return tok

        return re.sub(r"\S+", _inspect_token, text)

    def get_emergent_salience(self, tokens: List[str]) -> Dict[str, float]:
        if not tokens:
            return {}
        tf = Counter(tokens)
        n = len(tokens)
        scores: Dict[str, float] = {}
        for tok, freq in tf.items():
            df = self.doc_freq.get(tok, 1)
            idf = math.log(1.0 + (self.total_docs + 1.0) / (df + 0.5))
            char_complexity = math.log2(len(tok) + 1.0)
            scores[tok] = round((freq / n) * idf * char_complexity, 5)
        return scores

    def process(self, raw_text: str) -> Dict[str, Any]:
        norm = unicodedata.normalize("NFKC", raw_text).strip()
        redacted = self._redact_statistical_secrets(norm)
        sh = self.simhash64(redacted)
        is_dup = any(bin(sh ^ old).count("1") <= self.hamming_threshold for old in self.seen_simhashes)
        if not is_dup:
            self.seen_simhashes.append(sh)

        ent = self.shannon_entropy(redacted)
        tokens = re.findall(r"\w+", redacted.lower(), flags=re.UNICODE)
        self.total_docs += 1
        for t in set(tokens):
            self.doc_freq[t] += 1

        salience_map = self.get_emergent_salience(tokens)
        top_salient = sorted(salience_map.keys(), key=lambda k: salience_map[k], reverse=True)[:8]
        return {
            "clean_text": redacted,
            "simhash": sh,
            "is_duplicate": is_dup,
            "entropy": round(ent, 3),
            "passes_quality_gate": ent >= self.min_entropy,
            "salience_map": salience_map,
            "salient_terms": top_salient,
        }


# ============================================================================
# L3: UNDERSTAND (Wernicke · Temporal Cortex) — Zero Seed Dicts, Zero Hardcoded Verbs
# ============================================================================
class Layer3WernickeUnderstand:
    """
    - Discovers intents dynamically via Online Multinomial & Structural Signature Clustering
      (Zero `_seed_intents` and zero hardcoded `STOPWORDS`)
    - Extracts key-phrases by partitioning around low-IDF background tokens learned by L1
    - Extracts relational triples `(Node_A, Relational_Bridge, Node_B)` via distributional
      salience valleys between high-salience anchor phrases
    """

    def __init__(self):
        self.cluster_word_counts: Dict[str, Counter] = defaultdict(Counter)
        self.cluster_totals: Counter = Counter()
        self.vocab: Set[str] = set()

    def _structural_signature(self, text: str, tokens: List[str]) -> str:
        if not tokens:
            return "mode_empty"
        digit_op_ratio = len(re.findall(r"[\d\+\-\*\/\%\^\=]", text)) / max(len(text), 1)
        arrow_ratio = len(re.findall(r"->|→|=>", text)) / max(len(tokens), 1)
        brace_ratio = len(re.findall(r"[\{\}\[\]]", text)) / max(len(text), 1)
        if digit_op_ratio > 0.18:
            return "emergent_symbolic_quantitative"
        if brace_ratio > 0.04 or arrow_ratio > 0.05:
            return "emergent_structural_workflow"
        if len(tokens) > 45:
            return "emergent_narrative_discourse"
        return "emergent_conceptual_inquiry"

    def predict_and_adapt_intent(self, text: str) -> Tuple[str, float]:
        tokens = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
        struct_mode = self._structural_signature(text, tokens)

        if not self.cluster_totals:
            self.update_intent(tokens, struct_mode)
            return struct_mode, 1.0

        v_size = max(len(self.vocab), 1)
        total_all = max(sum(self.cluster_totals.values()), 1)
        scores: Dict[str, float] = {}
        for cid, total in self.cluster_totals.items():
            lp = math.log(total / total_all)
            for tok in tokens:
                c = self.cluster_word_counts[cid][tok]
                lp += math.log((c + 1.0) / (total + v_size))
            scores[cid] = lp

        best_cid = max(scores, key=scores.get)
        max_lp = scores[best_cid]
        prob = 1.0 / max(sum(math.exp(lp - max_lp) for lp in scores.values()), 1.0)

        target_cid = best_cid if prob >= 0.55 else struct_mode
        self.update_intent(tokens, target_cid)
        return target_cid, round(prob, 4)

    def update_intent(self, tokens: List[str], cluster_id: str) -> None:
        for tok in tokens:
            self.cluster_word_counts[cluster_id][tok] += 1
            self.cluster_totals[cluster_id] += 1
            self.vocab.add(tok)

    def extract_dynamic_keyphrases(self, text: str, salience_map: Dict[str, float]) -> List[str]:
        words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
        if not words:
            return []
        vals = list(salience_map.values()) or [0.1]
        median_sal = float(np.percentile(vals, 35))

        phrases: List[List[str]] = []
        curr: List[str] = []
        for w in words:
            if salience_map.get(w, 0.0) <= median_sal and len(words) > 4:
                if curr:
                    phrases.append(curr)
                    curr = []
            else:
                curr.append(w)
        if curr:
            phrases.append(curr)

        freq: Counter = Counter()
        deg: Counter = Counter()
        for p in phrases:
            for w in p:
                freq[w] += 1
                deg[w] += len(p)
        scored = {" ".join(p): sum(deg[w] / max(freq[w], 1) for w in p) for p in phrases}
        return sorted(scored.keys(), key=lambda k: scored[k], reverse=True)[:6]

    def extract_distributional_relations(
        self, text: str, salience_map: Dict[str, float]
    ) -> List[Tuple[str, str, str]]:
        triples: List[Tuple[str, str, str]] = []
        for arrow_match in re.finditer(r"([^,\.;\n\->→=]{2,40})\s*(?:->|→|=>)\s*([^,\.;\n\->→=]{2,40})", text):
            u, v = arrow_match.group(1).strip().lower(), arrow_match.group(2).strip().lower()
            triples.append((u, "transitions_to", v))

        clauses = [c.strip() for c in re.split(r"[.!?;:\n]+", text) if c.strip()]
        if not salience_map:
            return triples
        threshold = float(np.percentile(list(salience_map.values()), 55))

        for clause in clauses:
            tokens = re.findall(r"\w+", clause.lower(), flags=re.UNICODE)
            if len(tokens) < 3:
                continue
            high_mask = [salience_map.get(t, 0.0) >= threshold for t in tokens]
            spans: List[Tuple[str, str]] = []
            i = 0
            while i < len(tokens):
                mode = "anchor" if high_mask[i] else "bridge"
                j = i
                while j < len(tokens) and (("anchor" if high_mask[j] else "bridge") == mode):
                    j += 1
                spans.append((mode, " ".join(tokens[i:j])))
                i = j
            for k in range(len(spans) - 2):
                if spans[k][0] == "anchor" and spans[k + 1][0] == "bridge" and spans[k + 2][0] == "anchor":
                    triples.append((spans[k][1][:35], spans[k + 1][1][:25], spans[k + 2][1][:35]))
        return triples


# ============================================================================
# L4: REASON (Prefrontal Cortex) — PageRank, Workflow Chaining & Exact Symbolic AST
# ============================================================================
class Layer4PrefrontalReason:
    SAFE_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.Mod: operator.mod,
    }

    last_expression: str = ""

    def evaluate_symbolic_math(self, text: str) -> Optional[float]:
        """Exact evaluation of the longest arithmetic expression in the text (parentheses allowed)."""
        self.last_expression = ""
        spans = sorted(re.findall(r"[\d\.\s\+\-\*\/\%\^\(\)]{3,}", text), key=len, reverse=True)
        for span in spans:
            expr = span.strip()
            while expr.count("(") > expr.count(")") and expr.startswith("("):
                expr = expr[1:].strip()
            while expr.count(")") > expr.count("(") and expr.endswith(")"):
                expr = expr[:-1].strip()
            if not re.search(r"\d", expr) or not re.search(r"\d\s*[\+\-\*\/\%\^]\s*[\d(]", expr):
                continue
            try:
                tree = ast.parse(expr.replace("^", "**"), mode="eval")
                value = round(float(self._eval_ast(tree.body)), 6)
            except Exception:
                continue
            self.last_expression = expr
            return value
        return None

    def _eval_ast(self, node: Any) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in self.SAFE_OPS:
            return self.SAFE_OPS[type(node.op)](self._eval_ast(node.left), self._eval_ast(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in self.SAFE_OPS:
            return self.SAFE_OPS[type(node.op)](self._eval_ast(node.operand))
        raise ValueError("Unsupported symbolic AST node")

    def personalized_pagerank(
        self, triples: Dict[str, List[Tuple[str, str, str]]], seeds: List[str], alpha: float = 0.85, iters: int = 20
    ) -> Dict[str, float]:
        nodes: Set[str] = set()
        adj: Dict[str, List[str]] = defaultdict(list)
        for s, rels in triples.items():
            nodes.add(s)
            for _, o, _ in rels:
                nodes.add(o)
                adj[s].append(o)
        if not nodes:
            return {}
        n = len(nodes)
        p_vec = {node: (1.0 if any(sd in node for sd in seeds) else 0.0) for node in nodes}
        s_sum = sum(p_vec.values())
        p_vec = {k: (v / s_sum if s_sum > 0 else 1.0 / n) for k, v in p_vec.items()}
        ranks = dict(p_vec)

        for _ in range(iters):
            nxt = {node: (1.0 - alpha) * p_vec[node] for node in nodes}
            for u in nodes:
                nbrs = adj.get(u, [])
                if nbrs:
                    share = alpha * ranks[u] / len(nbrs)
                    for v in nbrs:
                        nxt[v] += share
                else:
                    for v in nodes:
                        nxt[v] += alpha * ranks[u] / n
            ranks = nxt
        return dict(sorted(ranks.items(), key=lambda item: item[1], reverse=True)[:8])

    def forward_chain(
        self, triples: Dict[str, List[Tuple[str, str, str]]], start_terms: List[str], max_hops: int = 4
    ) -> List[str]:
        chains: List[str] = []
        frontier = [s for s in triples.keys() if any(t in s for t in start_terms)] or list(start_terms)
        visited: Set[str] = set()
        for _ in range(max_hops):
            nxt_frontier: List[str] = []
            for u in frontier:
                if u in visited:
                    continue
                visited.add(u)
                for pred, obj, _ in triples.get(u, []):
                    chains.append(f"{u} -> [{pred}] -> {obj}")
                    nxt_frontier.append(obj)
            frontier = nxt_frontier
        return chains


# ============================================================================
# L5: THINK (Default-Mode Network + Dynamic Distributional 5-Tier Critic)
# Zero Hardcoded Cliché Lists — Uses Corpus Burstiness, Entropy & Quantile Tiers
# ============================================================================
@dataclass
class ThoughtCandidate:
    strategy: str
    text: str
    features: np.ndarray
    value_score: float = 0.5
    value_tier: str = "GOOD"
    pain_cost: float = 0.0


class Layer5DefaultModeThink:
    """
    Evaluates candidates and differentiates between WORST, BAD, GOOD, BETTER, and BEST
    dynamically using:
    - Distributional Style Alignment (Burstiness + N-gram Surprisal Variance vs. learned corpus statistics)
    - Online Welford Quantile Calibration (adapts tier thresholds to the evolving distribution)
    - Homeostatic Pain/Suffering Penalty from L8 FailureMemory
    """

    def __init__(self, feature_dim: int = 5):
        self.weights = np.array([1.25, 1.10, 0.95, 0.80, -1.75], dtype=np.float64)
        self.bias = 0.0
        self.target_burstiness: float = 0.45
        self.target_ttr: float = 0.62
        self.ngram_counts: Counter = Counter()
        self.total_ngrams: int = 0
        self.score_count: int = 0
        self.score_mean: float = 0.55
        self.score_m2: float = 0.05

    def observe_reference_writing(self, text: str) -> None:
        words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
        if len(words) < 5:
            return
        ttr = len(set(words)) / len(words)
        sents = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        lens = [len(s.split()) for s in sents] if len(sents) > 1 else [len(words)]
        burst = float(np.std(lens) / max(np.mean(lens), 1.0))

        self.target_ttr = 0.9 * self.target_ttr + 0.1 * ttr
        self.target_burstiness = 0.9 * self.target_burstiness + 0.1 * burst
        for i in range(len(words) - 2):
            gram = (words[i], words[i + 1], words[i + 2])
            self.ngram_counts[gram] += 1
            self.total_ngrams += 1

    def compute_distributional_writing_score(self, text: str) -> float:
        words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
        if not words:
            return 0.1
        ttr = len(set(words)) / len(words)
        sents = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        lens = [len(s.split()) for s in sents] if len(sents) > 1 else [len(words)]
        burst = float(np.std(lens) / max(np.mean(lens), 1.0))

        ttr_fit = max(0.0, 1.0 - abs(ttr - self.target_ttr))
        burst_fit = max(0.0, 1.0 - abs(burst - self.target_burstiness) * 0.7)

        if len(words) >= 6:
            grams = [(words[i], words[i + 1], words[i + 2]) for i in range(len(words) - 2)]
            unique_gram_ratio = len(set(grams)) / len(grams)
        else:
            unique_gram_ratio = 1.0

        return float(np.clip(0.40 * ttr_fit + 0.30 * burst_fit + 0.30 * unique_gram_ratio, 0.0, 1.0))

    def _assign_dynamic_quantile_tier(self, score: float, pain_overlap: float) -> str:
        if pain_overlap > 0.72:
            return "WORST"
        self.score_count += 1
        delta = score - self.score_mean
        self.score_mean += delta / self.score_count
        delta2 = score - self.score_mean
        self.score_m2 += delta * delta2
        std = math.sqrt(self.score_m2 / max(self.score_count, 1)) if self.score_count > 3 else 0.18
        std = max(std, 0.08)

        z = (score - self.score_mean) / std
        if z < -1.0 or score < 0.22:
            return "WORST"
        if z < -0.35 or score < 0.42:
            return "BAD"
        if z < 0.35 or score < 0.65:
            return "GOOD"
        if z < 0.95 or score < 0.82:
            return "BETTER"
        return "BEST"

    def score_and_classify_tier(
        self, text: str, grounding: float, symbolic_consistency: float, pain_overlap: float
    ) -> Tuple[float, str, np.ndarray]:
        wq = self.compute_distributional_writing_score(text)
        info_density = min(len(set(re.findall(r"\w+", text.lower()))) / 25.0, 1.0)
        feats = np.array([grounding, symbolic_consistency, wq, info_density, pain_overlap], dtype=np.float64)
        logit = float(np.dot(self.weights, feats) + self.bias)
        score = 1.0 / (1.0 + math.exp(-logit))
        tier = self._assign_dynamic_quantile_tier(score, pain_overlap)
        return round(score, 4), tier, feats

    def select_mmr(self, candidates: List[ThoughtCandidate], lambda_param: float = 0.75,
                   pain_block: float = 0.72) -> Optional[ThoughtCandidate]:
        """Best candidate by value minus pain. Candidates that resemble a remembered failure
        (pain ≥ pain_block) are never selected; returns None when every candidate is blocked."""
        unblocked = [c for c in candidates if c.pain_cost < pain_block]
        if not unblocked:
            return None
        viable = [c for c in unblocked if c.value_tier not in ("WORST", "BAD")] or unblocked
        return max(viable, key=lambda c: lambda_param * c.value_score - (1.0 - lambda_param) * c.pain_cost)

    def update_online_logistic(self, features: np.ndarray, target_reward: float, lr: float = 0.05) -> None:
        pred = 1.0 / (1.0 + math.exp(-float(np.dot(self.weights, features) + self.bias)))
        err = target_reward - pred
        self.weights += lr * err * features
        self.bias += lr * err


# ============================================================================
# L6: ANSWER (Broca's Area + Learned Contrastive Span Style Transfer)
# Zero Hardcoded Replacement Dicts — Learns Edits Directly From Fed Writing Pairs
# ============================================================================
class Layer6BrocaAnswer:
    """
    Learns `<suboptimal_span -> preferred_span>` transformations dynamically via sequence-alignment
    diffing whenever fed `<raw_draft, polished_text>` pairs or user corrections.
    """

    def __init__(self):
        self.learned_span_edits: Dict[str, str] = {}

    def learn_from_edit_pair(self, raw_draft: str, polished_text: str) -> List[Tuple[str, str]]:
        w_raw = raw_draft.split()
        w_pol = polished_text.split()
        matcher = difflib.SequenceMatcher(None, w_raw, w_pol)
        discovered: List[Tuple[str, str]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ("replace", "delete") and 1 <= (i2 - i1) <= 6 and (j2 - j1) <= 6:
                src_span = " ".join(w_raw[i1:i2]).strip()
                dst_span = " ".join(w_pol[j1:j2]).strip()
                if len(src_span) >= 4 and src_span.lower() != dst_span.lower():
                    self.learned_span_edits[src_span.lower()] = dst_span
                    discovered.append((src_span, dst_span))
        return discovered

    def polish_writing_dynamically(self, draft: str) -> Tuple[str, List[str]]:
        """3-step span editor:
        1. apply every learned <bad span → preferred span> edit (learned from draft/polished pairs)
        2. collapse statistically duplicated adjacent n-grams ("the the", "very good very good")
        3. normalise whitespace left behind by deletions
        """
        edits_applied: List[str] = []
        polished = draft
        for bad_span, preferred_span in self.learned_span_edits.items():
            pat = re.compile(r"\b" + re.escape(bad_span) + r"\b", re.IGNORECASE)
            if pat.search(polished):
                edits_applied.append(f"'{bad_span}' -> '{preferred_span or '[condensed]'}'")
                polished = pat.sub(preferred_span, polished)

        polished = re.sub(r"\b(\w+(?:\s+\w+){1,3})\s+\1\b", r"\1", polished, flags=re.IGNORECASE)
        polished = re.sub(r"\s{2,}", " ", polished).strip()
        return polished, edits_applied

    def compose(
        self, best_candidate: ThoughtCandidate, citations: List[str], active_layers: List[str]
    ) -> Dict[str, Any]:
        polished_text, edit_trace = self.polish_writing_dynamically(best_candidate.text)
        cite_str = f" [Sources: {', '.join(citations)}]" if citations else ""
        provenance = f" [Layers: {' -> '.join(active_layers)} | Tier: {best_candidate.value_tier}]"
        return {
            "final_text": f"{polished_text}{cite_str}",
            "provenance_badge": provenance,
            "writing_edit_trace": edit_trace,
            "value_tier": best_candidate.value_tier,
            "value_score": best_candidate.value_score,
        }


# ============================================================================
# L7: VERIFY (Anterior Cingulate Cortex) — Vector Cosine Entailment & Platt Calibration
# Zero Hardcoded Negation Word Lists
# ============================================================================
class Layer7ACCVerify:
    def __init__(self, rag_engine: HippocampusRAGEngine, platt_a: float = -2.4, platt_b: float = 0.75):
        self.rag = rag_engine
        self.platt_a = platt_a
        self.platt_b = platt_b

    def check_grounding(self, answer: str, episodes: List[MemoryEpisode]) -> float:
        if not episodes:
            return 0.55
        ans_vec = self.rag.compute_embedding(answer)
        ans_tokens = set(self.rag.tokenize(answer))
        if not ans_tokens:
            return 0.0

        sims: List[float] = []
        for ep in episodes:
            ep_vec = self.rag.compute_embedding(ep.content)
            cos_sim = float(np.dot(ans_vec, ep_vec))
            ep_tokens = set(self.rag.tokenize(ep.content))
            lex_overlap = len(ans_tokens & ep_tokens) / max(len(ans_tokens), 1)
            sims.append(0.5 * max(cos_sim, 0.0) + 0.5 * min(lex_overlap * 1.4, 1.0))
        return round(float(max(sims)), 4)

    def detect_structural_contradiction(self, answer: str, episodes: List[MemoryEpisode]) -> bool:
        ans_nums = re.findall(r"\b\d+(?:\.\d+)?\b", answer)
        ans_tokens = set(self.rag.tokenize(answer))
        for ep in episodes:
            ep_tokens = set(self.rag.tokenize(ep.content))
            shared_ratio = len(ans_tokens & ep_tokens) / max(len(ans_tokens | ep_tokens), 1)
            if shared_ratio > 0.35:
                ep_nums = re.findall(r"\b\d+(?:\.\d+)?\b", ep.content)
                if ans_nums and ep_nums and set(ans_nums).isdisjoint(set(ep_nums)):
                    return True
        return False

    def verify(
        self,
        answer: str,
        candidates: List[ThoughtCandidate],
        episodes: List[MemoryEpisode],
        neural_conf: float = 0.7,
    ) -> Dict[str, Any]:
        grounding = self.check_grounding(answer, episodes)
        contradiction = self.detect_structural_contradiction(answer, episodes)

        if len(candidates) > 1:
            v0 = self.rag.compute_embedding(answer)
            consistency = float(
                np.mean([max(float(np.dot(v0, self.rag.compute_embedding(c.text))), 0.0) for c in candidates[1:]])
            )
        else:
            consistency = 0.85

        raw_score = 0.45 * grounding + 0.30 * consistency + 0.25 * neural_conf - (0.55 if contradiction else 0.0)
        calibrated = 1.0 / (1.0 + math.exp(self.platt_a * raw_score + self.platt_b))
        return {
            "grounding": grounding,
            "self_consistency": round(consistency, 4),
            "has_contradiction": contradiction,
            "calibrated_confidence": round(calibrated, 4),
            "passes_verification": (calibrated >= 0.64 and not contradiction),
        }


# ============================================================================
# L8: LEARN (Basal Ganglia · Per-Domain/Per-Interface Autonomy & Pain Consolidation)
# ============================================================================
class FailureMemory(list):
    """
    Homeostatic pain registry: every refuted / unverified / WORST-BAD output is stored as an
    embedding. A new candidate's pain = its highest cosine similarity to any remembered failure.
    At or above `block_threshold` the trajectory is blocked — the brain will not say it again.
    (A list subclass so existing code that iterates/appends keeps working.)
    """

    def __init__(self, rag_engine: HippocampusRAGEngine, block_threshold: float = 0.72,
                 items: Optional[List[Dict[str, Any]]] = None):
        super().__init__(items or [])
        self.rag = rag_engine
        self.block_threshold = block_threshold
        self.endorsed: List[List[float]] = []      # vectors of human-approved corrections

    def register(self, domain_id: str, query: str, bad_output: str, value_score: float) -> Dict[str, Any]:
        item = {"domain_id": domain_id, "query": query, "bad_output": bad_output,
                "vector": self.rag.compute_embedding(bad_output).tolist(),
                "pain_severity": round(1.0 - value_score, 4)}
        self.append(item)
        return item

    def endorse(self, approved_text: str) -> None:
        """A correction given by a human is the opposite of pain: wording close to it must not be
        blocked just because it also resembles the refuted answer."""
        self.endorsed.append(self.rag.compute_embedding(approved_text).tolist())

    def pain_overlap(self, candidate_text: str) -> float:
        if not self:
            return 0.0
        c_vec = self.rag.compute_embedding(candidate_text)
        best = max(float(np.dot(c_vec, np.asarray(it["vector"], dtype=np.float32))) for it in self)
        if self.endorsed:
            relief = max(float(np.dot(c_vec, np.asarray(v, dtype=np.float32))) for v in self.endorsed)
            if relief >= best:
                return 0.0
        return round(float(np.clip(best, 0.0, 1.0)), 4)

    def blocks(self, candidate_text: str) -> bool:
        return self.pain_overlap(candidate_text) >= self.block_threshold


class Layer8BasalGangliaLearn:
    def __init__(self, storage_dir: Path, rag_engine: HippocampusRAGEngine):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.rag = rag_engine
        self.failure_memory = FailureMemory(rag_engine)
        self.min_runs = 25            # overwritten from BrainSystemConfig by the executive
        self.threshold = 0.85
        self.golden_replay_buffer: List[Dict[str, Any]] = []
        self.domain_outcomes: Dict[str, List[int]] = defaultdict(list)

    def compute_pain_overlap(self, candidate_text: str) -> float:
        return self.failure_memory.pain_overlap(candidate_text)

    def is_domain_graduated(self, domain_or_interface_id: str, min_runs: Optional[int] = None,
                            threshold: Optional[float] = None) -> bool:
        min_runs = self.min_runs if min_runs is None else min_runs
        threshold = self.threshold if threshold is None else threshold
        history = self.domain_outcomes.get(domain_or_interface_id, [])
        if len(history) < min_runs:
            return False
        return (sum(history[-min_runs:]) / len(history[-min_runs:])) >= threshold

    def record_outcome(
        self,
        domain_id: str,
        query: str,
        output: str,
        value_score: float,
        value_tier: str,
        verified: bool,
        surprise: float,
        used_teacher: bool,
        correction: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not verified or value_tier in ("WORST", "BAD") or correction:
            self.failure_memory.register(domain_id, query, output, value_score)
            if correction:
                self.failure_memory.endorse(correction)
            if correction:
                self.golden_replay_buffer.append(
                    {"prompt": query, "response": correction, "value": 0.95, "surprise": max(surprise, 0.9)}
                )
        elif value_tier in ("BETTER", "BEST"):
            self.golden_replay_buffer.append(
                {"prompt": query, "response": output, "value": value_score, "surprise": surprise}
            )

        if not used_teacher:
            self.domain_outcomes[domain_id].append(1 if verified else 0)
            self.domain_outcomes[domain_id] = self.domain_outcomes[domain_id][-200:]

        hist = self.domain_outcomes[domain_id]
        comp = sum(hist) / len(hist) if hist else 0.0
        return {
            "domain_id": domain_id,
            "domain_competence": round(comp, 4),
            "domain_runs": len(hist),
            "domain_graduated_off_api": self.is_domain_graduated(domain_id),
            "total_failures_remembered": len(self.failure_memory),
            "replay_buffer_size": len(self.golden_replay_buffer),
        }
