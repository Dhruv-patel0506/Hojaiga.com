# brain/tokenizer_and_llm.py
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from brain.config import LLMConfig

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


class HojaigaTokenizer:
    """
    100% Data-Driven Byte-Level BPE Tokenizer.
    Learns its vocabulary and subword merges purely from whatever dataset or stream you feed it.
    """

    CONTROL_TOKENS = ["<pad>", "<bos>", "<eos>", "<unk>", "<vis>", "</vis>", "<node>", "</node>"]

    def __init__(self, vocab_size: int = 16384):
        self.vocab_size = vocab_size
        self.token_to_id: Dict[str, int] = {}
        self.id_to_token: Dict[int, str] = {}
        self.merges: List[Tuple[str, str]] = []
        self._init_byte_alphabet()

    def _init_byte_alphabet(self) -> None:
        idx = 0
        for ct in self.CONTROL_TOKENS:
            self.token_to_id[ct] = idx
            self.id_to_token[idx] = ct
            idx += 1
        for b in range(256):
            ch = chr(b)
            if ch not in self.token_to_id:
                self.token_to_id[ch] = idx
                self.id_to_token[idx] = ch
                idx += 1

    @staticmethod
    def _to_bytes(text: str) -> str:
        """Byte-level view: every UTF-8 byte becomes one of the 256 base symbols, so any
        language, emoji or math symbol is representable (no <unk> for non-Latin text)."""
        return text.encode("utf-8").decode("latin-1")

    @staticmethod
    def _from_bytes(text: str) -> str:
        return text.encode("latin-1", errors="ignore").decode("utf-8", errors="replace")

    def train_incremental(self, texts: List[str], max_new_merges: int = 2000) -> int:
        """Dynamically expands BPE merges as new datasets or domains are fed."""
        word_freqs: Counter = Counter()
        texts = [self._to_bytes(t) for t in texts]
        for text in texts:
            for chunk in re.findall(r"\S+|\s+", text):
                word_freqs[tuple(chunk)] += 1

        available_slots = max(self.vocab_size - len(self.token_to_id), 0)
        target_merges = min(max_new_merges, available_slots)
        added = 0

        for _ in range(target_merges):
            pair_counts: Counter = Counter()
            for word_tuple, freq in word_freqs.items():
                for i in range(len(word_tuple) - 1):
                    pair_counts[(word_tuple[i], word_tuple[i + 1])] += freq
            if not pair_counts:
                break
            best_pair, best_freq = pair_counts.most_common(1)[0]
            if best_freq < 2:
                break
            merged_tok = best_pair[0] + best_pair[1]
            if merged_tok not in self.token_to_id:
                new_id = len(self.token_to_id)
                self.token_to_id[merged_tok] = new_id
                self.id_to_token[new_id] = merged_tok
                self.merges.append(best_pair)
                added += 1

            updated_freqs: Counter = Counter()
            for word_tuple, freq in word_freqs.items():
                new_w: List[str] = []
                i = 0
                while i < len(word_tuple):
                    if i < len(word_tuple) - 1 and (word_tuple[i], word_tuple[i + 1]) == best_pair:
                        new_w.append(merged_tok)
                        i += 2
                    else:
                        new_w.append(word_tuple[i])
                        i += 1
                updated_freqs[tuple(new_w)] += freq
            word_freqs = updated_freqs
        return added

    def encode(self, text: str, add_bos: bool = True, add_eos: bool = False) -> List[int]:
        tokens = list(self._to_bytes(text))
        for p0, p1 in self.merges:
            i = 0
            merged: List[str] = []
            while i < len(tokens):
                if i < len(tokens) - 1 and tokens[i] == p0 and tokens[i + 1] == p1:
                    merged.append(p0 + p1)
                    i += 2
                else:
                    merged.append(tokens[i])
                    i += 1
            tokens = merged
        unk_id = self.token_to_id["<unk>"]
        ids = [self.token_to_id.get(t, unk_id) for t in tokens]
        if add_bos:
            ids = [self.token_to_id["<bos>"]] + ids
        if add_eos:
            ids = ids + [self.token_to_id["<eos>"]]
        return ids

    def decode(self, ids: List[int]) -> str:
        return self._from_bytes("".join(
            self.id_to_token.get(i, "") for i in ids if self.id_to_token.get(i, "") not in self.CONTROL_TOKENS
        ))

    def save(self, path: Path) -> None:
        payload = {"vocab_size": self.vocab_size, "token_to_id": self.token_to_id, "merges": self.merges}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "HojaigaTokenizer":
        payload = json.loads(path.read_text(encoding="utf-8"))
        tok = cls(vocab_size=payload["vocab_size"])
        tok.token_to_id = payload["token_to_id"]
        tok.id_to_token = {int(v): k for k, v in tok.token_to_id.items()}
        tok.merges = [tuple(p) for p in payload["merges"]]
        return tok


if HAS_TORCH:
    class RMSNorm(nn.Module):
        def __init__(self, dim: int, eps: float = 1e-6):
            super().__init__()
            self.eps = eps
            self.weight = nn.Parameter(torch.ones(dim))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return (x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)) * self.weight

    def precompute_rope_freqs(dim: int, max_seq_len: int, theta: float = 10000.0) -> torch.Tensor:
        freqs = 1.0 / (theta ** (torch.arange(0, dim, 2)[: (dim // 2)].float() / dim))
        t = torch.arange(max_seq_len, dtype=torch.float32)
        freqs = torch.outer(t, freqs)
        return torch.polar(torch.ones_like(freqs), freqs)

    def apply_rope(xq: torch.Tensor, xk: torch.Tensor, freqs_cis: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        xq_ = torch.view_as_complex(xq.float().reshape(*xq.shape[:-1], -1, 2))
        xk_ = torch.view_as_complex(xk.float().reshape(*xk.shape[:-1], -1, 2))
        freqs = freqs_cis[: xq.shape[1]].unsqueeze(0).unsqueeze(2)
        xq_out = torch.view_as_real(xq_ * freqs).flatten(3)
        xk_out = torch.view_as_real(xk_ * freqs).flatten(3)
        return xq_out.type_as(xq), xk_out.type_as(xk)

    class OrthogonalLoRALinear(nn.Module):
        """Orthogonal Subspace LoRA (O-LoRA) layer preventing catastrophic forgetting across continual runs."""

        def __init__(self, in_features: int, out_features: int, rank: int = 8, alpha: float = 16.0):
            super().__init__()
            self.base = nn.Linear(in_features, out_features, bias=False)
            self.lora_A = nn.Parameter(torch.randn(rank, in_features) * 0.01)
            self.lora_B = nn.Parameter(torch.zeros(out_features, rank))
            self.scaling = alpha / max(rank, 1)
            self.register_buffer("consolidated_subspace", torch.zeros(rank, in_features))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.base(x) + (x @ self.lora_A.T @ self.lora_B.T) * self.scaling

        def orthogonal_loss(self) -> torch.Tensor:
            if self.consolidated_subspace.abs().sum() == 0:
                return torch.tensor(0.0, device=self.lora_A.device)
            return torch.norm(self.lora_A @ self.consolidated_subspace.T, p="fro") ** 2

        @torch.no_grad()
        def consolidate_into_base(self) -> None:
            self.base.weight.data += (self.lora_B @ self.lora_A) * self.scaling
            self.consolidated_subspace.copy_(F.normalize(self.lora_A.data, dim=-1))
            self.lora_B.zero_()

    class GroupedQueryAttention(nn.Module):
        def __init__(self, cfg: LLMConfig):
            super().__init__()
            self.n_heads = cfg.n_heads
            self.n_kv_heads = cfg.n_kv_heads
            self.repeats = self.n_heads // self.n_kv_heads
            self.head_dim = cfg.dim // cfg.n_heads

            self.wq = OrthogonalLoRALinear(cfg.dim, cfg.n_heads * self.head_dim, cfg.lora_rank, cfg.lora_alpha)
            self.wk = nn.Linear(cfg.dim, cfg.n_kv_heads * self.head_dim, bias=False)
            self.wv = OrthogonalLoRALinear(cfg.dim, cfg.n_kv_heads * self.head_dim, cfg.lora_rank, cfg.lora_alpha)
            self.wo = OrthogonalLoRALinear(cfg.n_heads * self.head_dim, cfg.dim, cfg.lora_rank, cfg.lora_alpha)

        def forward(self, x: torch.Tensor, freqs_cis: torch.Tensor) -> torch.Tensor:
            bsz, seqlen, _ = x.shape
            xq = self.wq(x).view(bsz, seqlen, self.n_heads, self.head_dim)
            xk = self.wk(x).view(bsz, seqlen, self.n_kv_heads, self.head_dim)
            xv = self.wv(x).view(bsz, seqlen, self.n_kv_heads, self.head_dim)

            xq, xk = apply_rope(xq, xk, freqs_cis)
            if self.repeats > 1:
                xk = torch.repeat_interleave(xk, repeats=self.repeats, dim=2)
                xv = torch.repeat_interleave(xv, repeats=self.repeats, dim=2)

            xq, xk, xv = xq.transpose(1, 2), xk.transpose(1, 2), xv.transpose(1, 2)
            out = F.scaled_dot_product_attention(xq, xk, xv, is_causal=True)
            return self.wo(out.transpose(1, 2).contiguous().view(bsz, seqlen, -1))

    class SwiGLUFFN(nn.Module):
        def __init__(self, cfg: LLMConfig):
            super().__init__()
            hidden = int(2 * (4 * cfg.dim) / 3)
            hidden = cfg.multiple_of * ((hidden + cfg.multiple_of - 1) // cfg.multiple_of)
            self.w1 = nn.Linear(cfg.dim, hidden, bias=False)
            self.w2 = nn.Linear(hidden, cfg.dim, bias=False)
            self.w3 = nn.Linear(cfg.dim, hidden, bias=False)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.w2(F.silu(self.w1(x)) * self.w3(x))

    class TransformerBlock(nn.Module):
        def __init__(self, cfg: LLMConfig):
            super().__init__()
            self.attn_norm = RMSNorm(cfg.dim)
            self.attn = GroupedQueryAttention(cfg)
            self.ffn_norm = RMSNorm(cfg.dim)
            self.ffn = SwiGLUFFN(cfg)

        def forward(self, x: torch.Tensor, freqs_cis: torch.Tensor) -> torch.Tensor:
            x = x + self.attn(self.attn_norm(x), freqs_cis)
            x = x + self.ffn(self.ffn_norm(x))
            return x

    class HojaigaLLM(nn.Module):
        """PyTorch GPU/CPU Transformer Backbone with Orthogonal-LoRA, Value Head, and Verifier Head."""

        def __init__(self, cfg: LLMConfig):
            super().__init__()
            self.cfg = cfg
            self.tok_embeddings = nn.Embedding(cfg.vocab_size, cfg.dim)
            self.layers = nn.ModuleList([TransformerBlock(cfg) for _ in range(cfg.n_layers)])
            self.norm = RMSNorm(cfg.dim)
            self.lm_head = nn.Linear(cfg.dim, cfg.vocab_size, bias=False)
            self.tok_embeddings.weight = self.lm_head.weight

            self.value_head = nn.Linear(cfg.dim, 1)
            self.verifier_head = nn.Linear(cfg.dim, 1)

            freqs = precompute_rope_freqs(cfg.dim // cfg.n_heads, cfg.max_seq_len * 2)
            self.register_buffer("freqs_cis", freqs, persistent=False)

        def forward_features(
            self, input_ids: torch.Tensor, multimodal_embeds: Optional[torch.Tensor] = None
        ) -> torch.Tensor:
            h = self.tok_embeddings(input_ids)
            if multimodal_embeds is not None:
                h = torch.cat([multimodal_embeds.to(h.dtype), h], dim=1)
            freqs_cis = self.freqs_cis[: h.shape[1]].to(h.device)
            for layer in self.layers:
                h = layer(h, freqs_cis)
            return self.norm(h)

        def forward(
            self,
            input_ids: torch.Tensor,
            multimodal_embeds: Optional[torch.Tensor] = None,
            targets: Optional[torch.Tensor] = None,
            target_value: Optional[torch.Tensor] = None,
        ) -> Dict[str, torch.Tensor]:
            h = self.forward_features(input_ids, multimodal_embeds)
            logits = self.lm_head(h)
            pooled = h[:, -1, :]
            pred_value = torch.sigmoid(self.value_head(pooled))
            verify_conf = torch.sigmoid(self.verifier_head(pooled))

            out = {"logits": logits, "pred_value": pred_value, "verify_conf": verify_conf, "pooled_state": pooled}
            if targets is not None:
                text_logits = logits[:, -targets.shape[1] :, :]
                ce_loss = F.cross_entropy(text_logits.reshape(-1, self.cfg.vocab_size), targets.reshape(-1))
                ortho_loss = sum(
                    m.orthogonal_loss() for m in self.modules() if isinstance(m, OrthogonalLoRALinear)
                )
                val_loss = (
                    F.mse_loss(pred_value.squeeze(-1), target_value)
                    if target_value is not None
                    else torch.tensor(0.0, device=logits.device)
                )
                out["loss"] = ce_loss + 0.05 * ortho_loss + 0.2 * val_loss
            return out

        @torch.no_grad()
        def generate(
            self,
            tokenizer: HojaigaTokenizer,
            prompt: str,
            multimodal_embeds: Optional[Any] = None,
            max_new_tokens: int = 96,
            temperature: float = 0.65,
        ) -> Tuple[str, Dict[str, float]]:
            self.eval()
            device = next(self.parameters()).device
            ids = torch.tensor([tokenizer.encode(prompt, add_bos=True)[-self.cfg.max_seq_len:]],
                               dtype=torch.long, device=device)
            eos_id = tokenizer.token_to_id["<eos>"]

            for _ in range(max_new_tokens):
                out = self.forward(ids[:, -self.cfg.max_seq_len :], multimodal_embeds=multimodal_embeds)
                next_logits = out["logits"][:, -1, :] / max(temperature, 1e-4)
                next_logits[:, len(tokenizer.token_to_id):] = -float("inf")   # only ids the tokenizer knows
                probs = F.softmax(next_logits, dim=-1)
                next_id = torch.multinomial(probs, num_samples=1)
                ids = torch.cat([ids, next_id], dim=1)
                if next_id.item() == eos_id:
                    break

            final_out = self.forward(ids[:, -self.cfg.max_seq_len :], multimodal_embeds=multimodal_embeds)
            n_prompt = len(tokenizer.encode(prompt, add_bos=True)[-self.cfg.max_seq_len:])
            gen_only = tokenizer.decode(ids[0, n_prompt:].cpu().tolist()).strip()
            return gen_only, {
                "neural_value": round(float(final_out["pred_value"][0].item()), 4),
                "verifier_confidence": round(float(final_out["verify_conf"][0].item()), 4),
            }

else:
    class HojaigaLLM:
        """
        Zero-Dependency NumPy Neural & Transition Backbone (active automatically when PyTorch is not installed).
        Maintains low-rank Orthogonal-LoRA projection matrices and n-gram transition weights in pure NumPy.
        """

        def __init__(self, cfg: LLMConfig):
            self.cfg = cfg
            rng = np.random.default_rng(42)
            self.embed_matrix = rng.normal(0.0, 0.02, size=(cfg.vocab_size, cfg.dim)).astype(np.float32)
            self.lora_A = rng.normal(0.0, 0.02, size=(cfg.lora_rank, cfg.dim)).astype(np.float32)
            self.lora_B = np.zeros((cfg.dim, cfg.lora_rank), dtype=np.float32)
            self.value_w = rng.normal(0.0, 0.05, size=(cfg.dim,)).astype(np.float32)
            self.verify_w = rng.normal(0.0, 0.05, size=(cfg.dim,)).astype(np.float32)
            self.learned_continuations: Dict[int, Counter] = {}

        def fit_sequence(self, ids: List[int], reward_value: float = 0.8, lr: float = 0.02) -> float:
            if len(ids) < 2:
                return 0.0
            for i in range(len(ids) - 1):
                prev_id, nxt_id = ids[i], ids[i + 1]
                if prev_id not in self.learned_continuations:
                    self.learned_continuations[prev_id] = Counter()
                self.learned_continuations[prev_id][nxt_id] += 1

            valid_ids = [idx % self.cfg.vocab_size for idx in ids]
            h = np.mean(self.embed_matrix[valid_ids], axis=0)
            lora_delta = self.lora_B @ (self.lora_A @ h)
            state = h + lora_delta
            pred_v = 1.0 / (1.0 + math.exp(-float(np.dot(self.value_w, state))))
            err = reward_value - pred_v
            self.value_w += lr * err * state
            self.verify_w += lr * err * state
            self.lora_B += lr * err * np.outer(state, self.lora_A @ h)
            return float(err ** 2)

        def generate(
            self,
            tokenizer: HojaigaTokenizer,
            prompt: str,
            multimodal_embeds: Optional[Any] = None,
            max_new_tokens: int = 48,
            temperature: float = 0.65,
        ) -> Tuple[str, Dict[str, float]]:
            ids = tokenizer.encode(prompt, add_bos=True)
            eos_id = tokenizer.token_to_id["<eos>"]
            for _ in range(max_new_tokens):
                last_id = ids[-1]
                cont = self.learned_continuations.get(last_id)
                if not cont:
                    break
                next_id = cont.most_common(1)[0][0]
                if next_id == eos_id:
                    break
                ids.append(next_id)

            valid_ids = [idx % self.cfg.vocab_size for idx in ids]
            h = np.mean(self.embed_matrix[valid_ids], axis=0)
            if isinstance(multimodal_embeds, np.ndarray) and multimodal_embeds.size >= self.cfg.dim:
                h = 0.7 * h + 0.3 * multimodal_embeds.ravel()[: self.cfg.dim]
            state = h + self.lora_B @ (self.lora_A @ h)
            val_score = 1.0 / (1.0 + math.exp(-float(np.dot(self.value_w, state))))
            ver_score = 1.0 / (1.0 + math.exp(-float(np.dot(self.verify_w, state))))
            decoded = tokenizer.decode(ids)
            gen_only = decoded[len(prompt) :].strip() if decoded.startswith(prompt) else decoded
            return gen_only, {
                "neural_value": round(val_score, 4),
                "verifier_confidence": round(ver_score, 4),
            }
