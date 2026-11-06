# brain/omni/model.py
"""
HojaigaOmni — one network, trained from zero, for text, images, video and audio.

  image  [B,3,H,W]      ─ Conv2d patches ───┐
  video  [B,3,T,H,W]    ─ Conv3d tubelets ──┼─▶ modality encoder (Transformer) ─▶ projector ─┐
  audio  [B,1,mels,T]   ─ Conv2d patches ───┘                                                │
  text   token ids ────────────────────────────────────────────▶ embeddings ─────────────────┤
                                                                                              ▼
                       causal decoder (RoPE · grouped-query attention · SwiGLU · RMSNorm)  ─▶ LM head

Objectives (all optimised together):
  lm           next-token prediction on text
  caption      next-token prediction on text that follows a media prefix (describe what is seen/heard)
  contrastive  InfoNCE between pooled media and pooled text embeddings (cross-modal search)
  jepa         world-model objective: from the visible patches, predict the EMA target encoder's
               representation of the hidden patches (no pixels/samples reconstructed)
"""
import copy
import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from brain.config import LLMConfig
from brain.tokenizer_and_llm import RMSNorm, TransformerBlock, precompute_rope_freqs


@dataclass
class OmniConfig:
    vocab_size: int = 16384
    dim: int = 384
    n_layers: int = 6
    n_heads: int = 6
    n_kv_heads: int = 2
    enc_dim: int = 256
    enc_layers: int = 3
    enc_heads: int = 4
    image_size: int = 128
    patch: int = 16
    video_frames: int = 8
    tubelet: int = 2
    n_mels: int = 64
    audio_frames: int = 512           # ~5 s at a 10 ms hop
    max_text: int = 256
    embed_dim: int = 256
    jepa_mask_ratio: float = 0.5
    ema_decay: float = 0.996

    @classmethod
    def preset(cls, size: str, vocab_size: int = 16384) -> "OmniConfig":
        p = {"tiny": dict(dim=192, n_layers=4, n_heads=4, n_kv_heads=2, enc_dim=128, enc_layers=2, enc_heads=4,
                          image_size=64, audio_frames=256, max_text=128, embed_dim=128),
             "small": dict(),
             "base": dict(dim=512, n_layers=10, n_heads=8, n_kv_heads=4, enc_dim=384, enc_layers=6, enc_heads=6,
                          image_size=192, max_text=512, embed_dim=384)}[size]
        return cls(vocab_size=vocab_size, **p)


class PatchEncoder(nn.Module):
    """Patch/tubelet embedding + Transformer encoder, with a mask token for JEPA context views."""

    def __init__(self, embed: nn.Module, n_tokens: int, dim: int, layers: int, heads: int):
        super().__init__()
        self.embed = embed
        self.pos = nn.Parameter(torch.randn(1, n_tokens, dim) * 0.02)
        self.mask_token = nn.Parameter(torch.zeros(1, 1, dim))
        layer = nn.TransformerEncoderLayer(dim, heads, dim * 4, dropout=0.0, activation="gelu",
                                           batch_first=True, norm_first=True)
        self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(dim)

    def tokens(self, x: torch.Tensor) -> torch.Tensor:
        t = self.embed(x).flatten(2).transpose(1, 2)            # [B, N, dim]
        return t + self.pos[:, : t.shape[1]]

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        t = self.tokens(x)
        if mask is not None:                                    # mask: [B, N] True = hidden from context
            t = torch.where(mask.unsqueeze(-1), self.mask_token.expand_as(t) + self.pos[:, : t.shape[1]], t)
        return self.norm(self.enc(t))


class HojaigaOmni(nn.Module):
    MODALITIES = ("image", "video", "audio")

    def __init__(self, cfg: OmniConfig):
        super().__init__()
        self.cfg = cfg
        g = cfg.image_size // cfg.patch
        a_tokens = (cfg.n_mels // cfg.patch) * (cfg.audio_frames // cfg.patch)
        self.encoders = nn.ModuleDict({
            "image": PatchEncoder(nn.Conv2d(3, cfg.enc_dim, cfg.patch, cfg.patch), g * g,
                                  cfg.enc_dim, cfg.enc_layers, cfg.enc_heads),
            "video": PatchEncoder(nn.Conv3d(3, cfg.enc_dim, (cfg.tubelet, cfg.patch, cfg.patch),
                                            (cfg.tubelet, cfg.patch, cfg.patch)),
                                  (cfg.video_frames // cfg.tubelet) * g * g, cfg.enc_dim, cfg.enc_layers, cfg.enc_heads),
            "audio": PatchEncoder(nn.Conv2d(1, cfg.enc_dim, cfg.patch, cfg.patch), a_tokens,
                                  cfg.enc_dim, cfg.enc_layers, cfg.enc_heads),
        })
        # EMA target encoders for JEPA (never receive gradients)
        self.targets = copy.deepcopy(self.encoders)
        for p in self.targets.parameters():
            p.requires_grad_(False)
        pred_layer = nn.TransformerEncoderLayer(cfg.enc_dim, cfg.enc_heads, cfg.enc_dim * 2, dropout=0.0,
                                                batch_first=True, norm_first=True)
        self.jepa_predictor = nn.TransformerEncoder(pred_layer, 2, enable_nested_tensor=False)
        self.projectors = nn.ModuleDict({m: nn.Sequential(nn.Linear(cfg.enc_dim, cfg.dim), nn.GELU(),
                                                          nn.Linear(cfg.dim, cfg.dim)) for m in self.MODALITIES})
        self.modality_embed = nn.ParameterDict({m: nn.Parameter(torch.zeros(1, 1, cfg.dim)) for m in self.MODALITIES})

        lcfg = LLMConfig(vocab_size=cfg.vocab_size, max_seq_len=cfg.max_text + 1024, dim=cfg.dim,
                         n_layers=cfg.n_layers, n_heads=cfg.n_heads, n_kv_heads=cfg.n_kv_heads)
        self.tok = nn.Embedding(cfg.vocab_size, cfg.dim)
        self.blocks = nn.ModuleList(TransformerBlock(lcfg) for _ in range(cfg.n_layers))
        self.norm = RMSNorm(cfg.dim)
        self.lm_head = nn.Linear(cfg.dim, cfg.vocab_size, bias=False)
        self.lm_head.weight = self.tok.weight
        self.register_buffer("freqs", precompute_rope_freqs(cfg.dim // cfg.n_heads, lcfg.max_seq_len), persistent=False)
        self.text_proj = nn.Linear(cfg.dim, cfg.embed_dim)
        self.media_proj = nn.Linear(cfg.enc_dim, cfg.embed_dim)
        self.logit_scale = nn.Parameter(torch.tensor(math.log(1 / 0.07)))

    def num_params(self, trainable_only: bool = True) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad or not trainable_only)

    # ------------------------------------------------------------------ pieces
    def encode_media(self, modality: str, x: torch.Tensor) -> torch.Tensor:
        return self.encoders[modality](x)

    def decode(self, ids: Optional[torch.Tensor], prefix: Optional[torch.Tensor] = None) -> torch.Tensor:
        parts = [prefix] if prefix is not None else []
        if ids is not None:
            parts.append(self.tok(ids))
        h = torch.cat(parts, dim=1)
        f = self.freqs[: h.shape[1]].to(h.device)
        for b in self.blocks:
            h = b(h, f)
        return self.norm(h)

    def media_prefix(self, modality: str, enc: torch.Tensor) -> torch.Tensor:
        return self.projectors[modality](enc) + self.modality_embed[modality]

    @staticmethod
    def _pool(h: torch.Tensor, ids: torch.Tensor) -> torch.Tensor:
        keep = (ids != 0).unsqueeze(-1).float()
        return (h * keep).sum(1) / keep.sum(1).clamp(min=1)

    def text_embedding(self, ids: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.text_proj(self._pool(self.decode(ids), ids)), dim=-1)

    def media_embedding(self, modality: str, x: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.media_proj(self.encode_media(modality, x).mean(1)), dim=-1)

    # ------------------------------------------------------------------ training step
    def jepa_loss(self, modality: str, x: torch.Tensor) -> torch.Tensor:
        enc = self.encoders[modality]
        B = x.shape[0]
        N = enc.tokens(x).shape[1]
        n_mask = max(1, int(N * self.cfg.jepa_mask_ratio))
        mask = torch.zeros(B, N, dtype=torch.bool, device=x.device)
        mask.scatter_(1, torch.rand(B, N, device=x.device).argsort(1)[:, :n_mask], True)
        ctx = enc(x, mask=mask)
        pred = self.jepa_predictor(ctx)
        with torch.no_grad():
            tgt = F.layer_norm(self.targets[modality](x), (self.cfg.enc_dim,))
        return F.smooth_l1_loss(pred[mask], tgt[mask])

    def forward(self, batch: Dict[str, Any]) -> Dict[str, torch.Tensor]:
        losses: Dict[str, torch.Tensor] = {}
        ids = batch.get("ids")
        modality = next((m for m in self.MODALITIES if batch.get(m) is not None), None)
        if modality is None:
            h = self.decode(ids)
            logits = self.lm_head(h[:, :-1])
            losses["lm"] = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), ids[:, 1:].reshape(-1), ignore_index=0)
        else:
            x = batch[modality]
            enc = self.encode_media(modality, x)
            losses["jepa"] = self.jepa_loss(modality, x)
            if ids is not None:
                prefix = self.media_prefix(modality, enc)
                h = self.decode(ids, prefix)
                P = prefix.shape[1]
                logits = self.lm_head(h[:, P:-1])
                losses["caption"] = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), ids[:, 1:].reshape(-1),
                                                    ignore_index=0)
                if x.shape[0] > 1:
                    m = F.normalize(self.media_proj(enc.mean(1)), dim=-1)
                    t = self.text_embedding(ids)
                    sim = self.logit_scale.exp().clamp(max=100) * m @ t.T
                    lbl = torch.arange(sim.shape[0], device=sim.device)
                    losses["contrastive"] = (F.cross_entropy(sim, lbl) + F.cross_entropy(sim.T, lbl)) / 2
        losses["total"] = sum(v for k, v in losses.items())
        return losses

    @torch.no_grad()
    def update_targets(self) -> None:
        d = self.cfg.ema_decay
        for (_, p_t), (_, p_o) in zip(self.targets.named_parameters(), self.encoders.named_parameters()):
            p_t.mul_(d).add_(p_o.detach(), alpha=1 - d)

    # ------------------------------------------------------------------ inference
    @torch.no_grad()
    def generate(self, ids: torch.Tensor, modality: Optional[str] = None, media: Optional[torch.Tensor] = None,
                 max_new: int = 64, vocab_limit: Optional[int] = None, eos_id: int = 2,
                 temperature: float = 0.0) -> torch.Tensor:
        self.eval()
        prefix = self.media_prefix(modality, self.encode_media(modality, media)) if modality else None
        for _ in range(max_new):
            h = self.decode(ids[:, -self.cfg.max_text:], prefix)
            logits = self.lm_head(h[:, -1])
            if vocab_limit:
                logits[:, vocab_limit:] = -float("inf")
            logits[:, 0] = -float("inf")
            nxt = (torch.multinomial(F.softmax(logits / temperature, -1), 1) if temperature > 0
                   else logits.argmax(-1, keepdim=True))
            ids = torch.cat([ids, nxt], 1)
            if int(nxt[0, 0]) == eos_id:
                break
        return ids

    def config_dict(self) -> Dict[str, Any]:
        return asdict(self.cfg)
