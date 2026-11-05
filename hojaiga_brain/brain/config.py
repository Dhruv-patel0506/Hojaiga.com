# brain/config.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


@dataclass
class LLMConfig:
    """Dynamic configuration for Hojaiga's custom Transformer LLM (Tiny 5.3M, Small 17M, Base 37M)."""
    variant: str = "small_17m"
    vocab_size: int = 16384
    max_seq_len: int = 1024
    dim: int = 384
    n_layers: int = 8
    n_heads: int = 6
    n_kv_heads: int = 2
    multiple_of: int = 64
    dropout: float = 0.05
    lora_rank: int = 8
    lora_alpha: float = 16.0

    @classmethod
    def from_variant(cls, variant: str) -> "LLMConfig":
        presets: Dict[str, Dict[str, int]] = {
            "tiny_5m": {"vocab_size": 8192, "dim": 256, "n_layers": 6, "n_heads": 4, "n_kv_heads": 2},
            "small_17m": {"vocab_size": 16384, "dim": 384, "n_layers": 8, "n_heads": 6, "n_kv_heads": 2},
            "base_37m": {"vocab_size": 24576, "dim": 512, "n_layers": 12, "n_heads": 8, "n_kv_heads": 4},
        }
        cfg = presets.get(variant, presets["small_17m"])
        return cls(variant=variant, **cfg)


@dataclass
class VLMConfig:
    """Dynamic configuration for Hojaiga's Unified Vision-Language & UI Topology Encoder."""
    image_size: int = 224
    patch_size: int = 16
    temporal_frames: int = 8
    temporal_tubelet: int = 2
    vision_dim: int = 256
    vision_layers: int = 4
    vision_heads: int = 4
    proj_dim: int = 384
    vigilance_threshold: float = 0.72  # Adaptive Resonance threshold for recognizing known vs novel UI layouts


@dataclass
class BrainSystemConfig:
    """Master configuration for the 8-Layer Cortical Brain, Universal Ingestor, and Autonomous Graduation."""
    workspace_dir: Path = field(default_factory=lambda: Path("./hojaiga_storage"))
    llm: LLMConfig = field(default_factory=lambda: LLMConfig.from_variant("small_17m"))
    vlm: VLMConfig = field(default_factory=VLMConfig)
    verify_confidence_threshold: float = 0.72
    curiosity_surprise_threshold: float = 0.55
    graduation_competence_threshold: float = 0.85
    min_runs_before_graduation: int = 25
    teacher_provider: str = "auto"     # "auto" | "anthropic" | "ollama" | "none"
    teacher_model: str = ""            # Resolved dynamically from environment or local Ollama list

    def ensure_dirs(self) -> None:
        for sub in ["checkpoints", "rag_store", "episodic_db", "ui_topologies", "style_memory", "renders"]:
            (self.workspace_dir / sub).mkdir(parents=True, exist_ok=True)
