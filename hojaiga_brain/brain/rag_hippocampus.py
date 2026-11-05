# brain/rag_hippocampus.py
import hashlib
import json
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class MemoryEpisode:
    doc_id: str
    content: str
    modality: str
    domain_cluster: str
    source_uri: str
    timestamp: float = field(default_factory=time.time)
    surprise_score: float = 0.5
    continuous_value: float = 0.6
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class StreamingDomainClusterer:
    """
    Unsupervised online clustering (Adaptive Resonance / Dirichlet Process style) that automatically
    discovers what any fed dataset or stream is about without predefined category lists.
    """

    def __init__(self, vigilance: float = 0.55):
        self.vigilance = vigilance
        self.centroids: Dict[str, np.ndarray] = {}
        self.counts: Counter = Counter()
        self.cluster_term_freqs: Dict[str, Counter] = defaultdict(Counter)

    def assign_and_update(self, vec: np.ndarray, tokens: List[str]) -> Tuple[str, float]:
        best_cid = None
        best_sim = -1.0
        for cid, c_vec in self.centroids.items():
            sim = float(np.dot(vec, c_vec))
            if sim > best_sim:
                best_sim = sim
                best_cid = cid

        surprise = float(np.clip(1.0 - max(best_sim, 0.0), 0.0, 1.0))
        if best_cid is not None and best_sim >= self.vigilance:
            n = self.counts[best_cid]
            new_c = (self.centroids[best_cid] * n + vec) / (n + 1)
            norm = np.linalg.norm(new_c)
            self.centroids[best_cid] = new_c / norm if norm > 1e-8 else new_c
            self.counts[best_cid] += 1
            assigned_id = best_cid
        else:
            assigned_id = f"domain_{len(self.centroids) + 1}"
            self.centroids[assigned_id] = vec.copy()
            self.counts[assigned_id] = 1

        for t in tokens:
            if len(t) >= 3:
                self.cluster_term_freqs[assigned_id][t] += 1
        return assigned_id, round(surprise, 4)

    def get_emergent_cluster_signature(self, cluster_id: str, top_n: int = 4) -> str:
        tf = self.cluster_term_freqs.get(cluster_id, Counter())
        if not tf:
            return cluster_id
        top_terms = [w for w, _ in tf.most_common(top_n)]
        return f"{cluster_id}:{'_'.join(top_terms)}"


class HippocampusRAGEngine:
    """
    L2 (Know — Hippocampus):
    - Lexical BM25 + Local Character/Token N-Gram Distributional Embeddings
    - Unsupervised Streaming Domain Discovery (`StreamingDomainClusterer`)
    - Continuous Ebbinghaus / Surprise-Driven Retention (`FOREVER` / `SuRe` dynamics)
    - Emergent Concept & Workflow Transition Graph (`concept_triples`)
    - Reciprocal Rank Fusion (RRF)
    """

    def __init__(self, storage_dir: Path, embedding_dim: int = 256):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_dim = embedding_dim
        self.episodes: Dict[str, MemoryEpisode] = {}
        self.inverted_index: Dict[str, Dict[str, int]] = defaultdict(dict)
        self.doc_lengths: Dict[str, int] = {}
        self.avg_doc_len: float = 1.0
        self.dense_vectors: Dict[str, np.ndarray] = {}
        self.concept_triples: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
        self.domain_clusterer = StreamingDomainClusterer(vigilance=0.45)
        self._load_if_exists()

    def tokenize(self, text: str) -> List[str]:
        return re.findall(r"\w+", text.lower(), flags=re.UNICODE)

    def compute_embedding(self, text: str) -> np.ndarray:
        vec = np.zeros(self.embedding_dim, dtype=np.float32)
        tokens = self.tokenize(text)
        if not tokens:
            return vec
        for pos, tok in enumerate(tokens):
            for n in (2, 3, 4):
                padded = f"<{tok}>"
                for i in range(max(len(padded) - n + 1, 1)):
                    gram = padded[i : i + n]
                    h = int(hashlib.blake2b(gram.encode("utf-8"), digest_size=8).hexdigest(), 16)
                    idx = h % self.embedding_dim
                    sign = 1.0 if (h & 1) == 0 else -1.0
                    vec[idx] += sign / math.log2(pos + 2.0)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-8 else vec

    def ingest_episode(
        self,
        content: str,
        modality: str = "text",
        source_uri: str = "stream",
        continuous_value: float = 0.6,
        triples: Optional[List[Tuple[str, str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, float]:
        vec = self.compute_embedding(content)
        tokens = self.tokenize(content)
        cluster_id, surprise = self.domain_clusterer.assign_and_update(vec, tokens)

        doc_id = hashlib.sha1(f"{source_uri}:{modality}:{content}".encode("utf-8")).hexdigest()[:12]
        ep = MemoryEpisode(
            doc_id=doc_id,
            content=content,
            modality=modality,
            domain_cluster=cluster_id,
            source_uri=source_uri,
            surprise_score=surprise,
            continuous_value=float(np.clip(continuous_value, 0.0, 1.0)),
            metadata=metadata or {},
        )
        self.episodes[doc_id] = ep
        self.dense_vectors[doc_id] = vec

        self.doc_lengths[doc_id] = len(tokens)
        self.avg_doc_len = sum(self.doc_lengths.values()) / max(len(self.doc_lengths), 1)
        for term, freq in Counter(tokens).items():
            self.inverted_index[term][doc_id] = freq

        if triples:
            for s, p, o in triples:
                self.concept_triples[s.lower()].append((p.lower(), o.lower(), doc_id))

        return doc_id, self.domain_clusterer.get_emergent_cluster_signature(cluster_id), surprise

    def _bm25_scores(self, query_tokens: List[str], k1: float = 1.5, b: float = 0.75) -> Dict[str, float]:
        scores: Dict[str, float] = defaultdict(float)
        n_docs = len(self.episodes)
        if n_docs == 0:
            return scores
        for term in query_tokens:
            postings = self.inverted_index.get(term, {})
            df = len(postings)
            if df == 0:
                continue
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for doc_id, tf in postings.items():
                dl = self.doc_lengths.get(doc_id, 1)
                denom = tf + k1 * (1.0 - b + b * (dl / max(self.avg_doc_len, 1.0)))
                scores[doc_id] += idf * ((tf * (k1 + 1.0)) / denom)
        return scores

    def _retention_strength(self, ep: MemoryEpisode) -> float:
        age_hours = max((time.time() - ep.timestamp) / 3600.0, 0.0)
        multiplier = 0.2 + 1.8 * ep.continuous_value
        half_life = 24.0 * multiplier * (1.0 + ep.surprise_score + 0.25 * ep.access_count)
        return math.exp(-age_hours / max(half_life, 1.0)) * multiplier

    def retrieve_rrf(self, query: str, top_k: int = 5, rrf_k: int = 60) -> List[Tuple[MemoryEpisode, float]]:
        if not self.episodes:
            return []
        q_tokens = self.tokenize(query)
        q_vec = self.compute_embedding(query)

        bm25 = self._bm25_scores(q_tokens)
        dense = {doc_id: float(np.dot(q_vec, d_vec)) for doc_id, d_vec in self.dense_vectors.items()}

        bm25_ranked = sorted(bm25.keys(), key=lambda d: bm25[d], reverse=True)
        dense_ranked = sorted(dense.keys(), key=lambda d: dense[d], reverse=True)
        mem_ranked = sorted(self.episodes.keys(), key=lambda d: self._retention_strength(self.episodes[d]), reverse=True)

        rrf: Dict[str, float] = defaultdict(float)
        for rank, d_id in enumerate(bm25_ranked):
            rrf[d_id] += 1.0 / (rrf_k + rank + 1)
        for rank, d_id in enumerate(dense_ranked):
            rrf[d_id] += 1.0 / (rrf_k + rank + 1)
        for rank, d_id in enumerate(mem_ranked):
            rrf[d_id] += 0.5 / (rrf_k + rank + 1)

        best_ids = sorted(rrf.keys(), key=lambda d: rrf[d], reverse=True)[:top_k]
        out: List[Tuple[MemoryEpisode, float]] = []
        for d_id in best_ids:
            ep = self.episodes[d_id]
            ep.access_count += 1
            out.append((ep, round(rrf[d_id], 4)))
        return out

    def save(self) -> None:
        payload = {
            "episodes": {k: asdict(v) for k, v in self.episodes.items()},
            "triples": {k: v for k, v in self.concept_triples.items()},
        }
        (self.storage_dir / "hippocampus_rag.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_if_exists(self) -> None:
        p = self.storage_dir / "hippocampus_rag.json"
        if not p.exists():
            return
        payload = json.loads(p.read_text(encoding="utf-8"))
        for _, d in payload.get("episodes", {}).items():
            self.ingest_episode(
                content=d["content"],
                modality=d.get("modality", "text"),
                source_uri=d.get("source_uri", "disk"),
                continuous_value=d.get("continuous_value", 0.6),
                metadata=d.get("metadata", {}),
            )
        for subj, t_list in payload.get("triples", {}).items():
            self.concept_triples[subj] = [tuple(x) for x in t_list]
