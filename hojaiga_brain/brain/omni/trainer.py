# brain/omni/trainer.py
"""
Train HojaigaOmni from zero on any folder (text, records, images, video, audio), resume later,
and use it: describe media, generate text, cross-modal search.

Pairing (no hard-coded schema): a media file pairs with a same-name text sidecar
(photo.jpg + photo.txt, clip.mp4 + clip.srt, talk.wav + talk.txt); media in class folders pair
with the folder name; records with media paths pair with their text. Unpaired media still trains
the JEPA world model; all text trains the language model.
"""
import json
import math
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from brain.conveyor.ingest_clean import IMAGE_EXTS, VIDEO_EXTS, clean_items, ingest_folder, load_image, load_video
from brain.omni.audio import AUDIO_EXTS, load_audio, log_mel

try:
    import torch
    import torch.nn.functional as F
    from brain.omni.model import HojaigaOmni, OmniConfig
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


def _sidecar_text(path: Path) -> Optional[str]:
    for ext in (".txt", ".md", ".caption", ".srt", ".vtt"):
        p = path.with_suffix(ext)
        if p.exists() and p != path:
            t = p.read_text(encoding="utf-8", errors="ignore")
            t = re.sub(r"(?m)^\d+\s*$|^\d\d:\d\d.*-->.*$|^WEBVTT.*$", "", t)
            return re.sub(r"\s+", " ", t).strip() or None
    return None


def collect_samples(paths: List[str], l1) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Folder → training samples {modality, path?, text?}; audio files are found here too."""
    items, _ = ingest_folder(paths)
    items, clean_rep = clean_items(items, l1)
    sidecars = set()
    samples: List[Dict[str, Any]] = []
    folder_media: Dict[str, int] = {}
    for root in paths:
        root = Path(root)
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for f in files:
            ext = f.suffix.lower()
            if ext in IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS:
                folder_media[str(f.parent)] = folder_media.get(str(f.parent), 0) + 1
        class_folders = {k for k, v in folder_media.items() if v >= 2}
        multiple_classes = len({Path(k).parent for k in class_folders}) < len(class_folders)
        for f in files:
            ext = f.suffix.lower()
            mod = "image" if ext in IMAGE_EXTS else "video" if ext in VIDEO_EXTS else "audio" if ext in AUDIO_EXTS else None
            if not mod:
                continue
            text = _sidecar_text(f)
            if text:
                sidecars.update(str(f.with_suffix(e)) for e in (".txt", ".md", ".caption", ".srt", ".vtt"))
            elif multiple_classes and str(f.parent) in class_folders:
                text = f.parent.name.replace("_", " ")
            samples.append({"modality": mod, "path": str(f), "text": text})
    for it in items:
        if it.modality in ("text", "record") and it.text and it.source not in sidecars:
            samples.append({"modality": "text", "text": it.text})
    counts: Dict[str, int] = {}
    for s in samples:
        key = s["modality"] + ("+text" if s["modality"] != "text" and s.get("text") else "")
        counts[key] = counts.get(key, 0) + 1
    return samples, {"samples": len(samples), "by_kind": counts, "clean": clean_rep}


class OmniTrainer:
    def __init__(self, brain, size: str = "small", device: str = "auto"):
        if not HAS_TORCH:
            raise RuntimeError("Training the omni network needs PyTorch: pip install torch")
        self.brain = brain
        self.tok = brain.tokenizer
        self.dir = brain.cfg.workspace_dir / "omni"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ckpt = self.dir / "omni.pt"
        self.device = ("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device
        if self.ckpt.exists():
            st = torch.load(self.ckpt, map_location="cpu", weights_only=False)
            self.cfg = OmniConfig(**st["config"])
            self.model = HojaigaOmni(self.cfg)
            self.model.load_state_dict(st["model"])
            self.step = st.get("step", 0)
            self.history = st.get("history", [])
            self._opt_state = st.get("optim")
        else:
            self.cfg = OmniConfig.preset(size, vocab_size=brain.cfg.llm.vocab_size)
            self.model = HojaigaOmni(self.cfg)
            self.step, self.history, self._opt_state = 0, [], None
        self.model.to(self.device)

    # ------------------------------------------------------------------ tensors
    def _ids(self, texts: List[str]) -> "torch.Tensor":
        rows = [[i % self.cfg.vocab_size for i in self.tok.encode(t, add_bos=True, add_eos=True)][: self.cfg.max_text]
                for t in texts]
        w = max(len(r) for r in rows)
        return torch.tensor([r + [0] * (w - len(r)) for r in rows], dtype=torch.long)

    def _media(self, s: Dict[str, Any]) -> Optional["torch.Tensor"]:
        c = self.cfg
        try:
            if s["modality"] == "image":
                a = load_image(s["path"], max_side=1024)
                t = torch.from_numpy(a).permute(2, 0, 1).float().unsqueeze(0) / 255.0
                return F.interpolate(t, size=(c.image_size, c.image_size), mode="bilinear", align_corners=False)[0]
            if s["modality"] == "video":
                fr = load_video(s["path"], frames=64)
                if fr is None or len(fr) < 2:
                    return None
                fr = fr[np.linspace(0, len(fr) - 1, c.video_frames).round().astype(int)]
                t = torch.from_numpy(fr).permute(0, 3, 1, 2).float() / 255.0
                t = F.interpolate(t, size=(c.image_size, c.image_size), mode="bilinear", align_corners=False)
                return t.permute(1, 0, 2, 3)
            if s["modality"] == "audio":
                x = load_audio(s["path"])
                if x is None or len(x) < 400:
                    return None
                m = log_mel(x, n_mels=c.n_mels)
                m = (m - m.mean()) / (m.std() + 1e-5)
                m = m[:, : c.audio_frames]
                if m.shape[1] < c.audio_frames:
                    m = np.pad(m, ((0, 0), (0, c.audio_frames - m.shape[1])), constant_values=m.min())
                return torch.from_numpy(m).unsqueeze(0).float()
        except Exception:
            return None
        return None

    def _batches(self, samples: List[Dict[str, Any]], batch: int, rng: random.Random):
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for s in samples:
            groups.setdefault(s["modality"] + ("+text" if s["modality"] != "text" and s.get("text") else ""), []).append(s)
        out = []
        for key, g in groups.items():
            rng.shuffle(g)
            out += [(key, g[i:i + batch]) for i in range(0, len(g), batch)]
        rng.shuffle(out)
        for key, chunk in out:
            mod = key.split("+")[0]
            b: Dict[str, Any] = {}
            if mod != "text":
                tens = [(s, self._media(s)) for s in chunk]
                tens = [(s, t) for s, t in tens if t is not None]
                if not tens:
                    continue
                chunk = [s for s, _ in tens]
                b[mod] = torch.stack([t for _, t in tens]).to(self.device)
            if key.endswith("+text") or mod == "text":
                b["ids"] = self._ids([s["text"] for s in chunk]).to(self.device)
            yield b

    # ------------------------------------------------------------------ training
    def train(self, paths: List[str], epochs: int = 3, batch: int = 8, lr: float = 3e-4, max_minutes: float = 0.0,
              seed: int = 0) -> Dict[str, Any]:
        rng = random.Random(seed)
        torch.manual_seed(seed)
        samples, data_rep = collect_samples(paths, self.brain.l1)
        if not samples:
            raise RuntimeError(f"no usable samples in {paths}")
        self.tok.train_incremental([s["text"] for s in samples if s.get("text")], max_new_merges=2000)
        rng.shuffle(samples)
        n_val = max(1, len(samples) // 10) if len(samples) >= 10 else 0
        val, train = samples[:n_val], samples[n_val:]
        opt = torch.optim.AdamW([p for p in self.model.parameters() if p.requires_grad], lr=lr,
                                betas=(0.9, 0.95), weight_decay=0.05)
        if self._opt_state:
            try:
                opt.load_state_dict(self._opt_state)
                for g in opt.param_groups:
                    g["lr"] = lr
            except Exception:
                pass
        steps_total = max(1, epochs * math.ceil(len(train) / batch))
        warm = max(1, min(100, steps_total // 10))
        amp = self.device == "cuda"
        dtype = torch.bfloat16 if amp and torch.cuda.is_bf16_supported() else torch.float16
        scaler = torch.amp.GradScaler("cuda", enabled=amp and dtype == torch.float16)
        t0, local = time.time(), 0
        self.model.train()
        stop = False
        for ep in range(epochs):
            for b in self._batches(train, batch, rng):
                for g in opt.param_groups:
                    g["lr"] = lr * min(1.0, (local + 1) / warm) * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * min(1.0, local / steps_total))))
                with torch.autocast("cuda", dtype=dtype, enabled=amp):
                    losses = self.model(b)
                opt.zero_grad(set_to_none=True)
                scaler.scale(losses["total"]).backward()
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                scaler.step(opt)
                scaler.update()
                self.model.update_targets()
                self.step += 1
                local += 1
                self.history.append({"step": self.step, **{k: round(float(v.detach()), 4) for k, v in losses.items()}})
                if max_minutes and (time.time() - t0) / 60 >= max_minutes:
                    stop = True
                    break
            if stop:
                break
        val_loss = self.evaluate(val) if val else None
        self.save(opt)
        self.brain.save_learned_state()                    # tokenizer merges grew
        chart = self.plot_history()
        return {"steps": local, "total_steps": self.step, "epochs_run": ep + 1, "train_samples": len(train),
                "val_loss": val_loss, "params_m": round(self.model.num_params() / 1e6, 2), "device": self.device,
                "minutes": round((time.time() - t0) / 60, 2), "data": data_rep, "chart": chart,
                "last": self.history[-1] if self.history else None}

    @torch.no_grad()
    def evaluate(self, samples: List[Dict[str, Any]]) -> Dict[str, float]:
        self.model.eval()
        sums: Dict[str, List[float]] = {}
        for b in self._batches(samples, 8, random.Random(1)):
            for k, v in self.model(b).items():
                sums.setdefault(k, []).append(float(v))
        self.model.train()
        return {k: round(float(np.mean(v)), 4) for k, v in sums.items()}

    def save(self, opt=None) -> None:
        tmp = self.ckpt.with_suffix(".tmp")
        torch.save({"config": self.model.config_dict(), "model": self.model.state_dict(), "step": self.step,
                    "history": self.history[-20000:], "optim": opt.state_dict() if opt else None}, tmp)
        tmp.replace(self.ckpt)

    def plot_history(self) -> Optional[str]:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return None
        if not self.history:
            return None
        fig, ax = plt.subplots(figsize=(8, 4))
        for key in ("lm", "caption", "contrastive", "jepa"):
            pts = [(h["step"], h[key]) for h in self.history if key in h]
            if pts:
                xs, ys = zip(*pts)
                w = max(1, len(ys) // 50)
                smooth = np.convolve(ys, np.ones(w) / w, mode="valid")
                ax.plot(xs[w - 1:], smooth, label=key)
        ax.set_xlabel("step")
        ax.set_ylabel("loss")
        ax.set_title("HojaigaOmni training")
        ax.legend()
        ax.grid(alpha=0.3)
        out = self.dir / "training_curves.png"
        fig.tight_layout()
        fig.savefig(out, dpi=110)
        plt.close(fig)
        return str(out)

    # ------------------------------------------------------------------ using the trained network
    def _decode_new(self, out: "torch.Tensor", n_prompt: int) -> str:
        return self.tok.decode(out[0, n_prompt:].tolist()).strip()

    @torch.no_grad()
    def describe(self, path: str, max_new: int = 48) -> str:
        ext = Path(path).suffix.lower()
        mod = "image" if ext in IMAGE_EXTS else "video" if ext in VIDEO_EXTS else "audio" if ext in AUDIO_EXTS else None
        if mod is None:
            raise ValueError(f"not a media file: {path}")
        x = self._media({"modality": mod, "path": path})
        if x is None:
            raise ValueError(f"could not read {path}")
        bos = torch.tensor([[self.tok.token_to_id["<bos>"]]], device=self.device)
        out = self.model.generate(bos, mod, x.unsqueeze(0).to(self.device), max_new=max_new,
                                  vocab_limit=len(self.tok.token_to_id), eos_id=self.tok.token_to_id["<eos>"])
        return self._decode_new(out, 1)

    @torch.no_grad()
    def generate(self, prompt: str, max_new: int = 64) -> str:
        ids = self._ids([prompt]).to(self.device)
        ids = ids[:, : int((ids != 0).sum()) - 1]          # drop the EOS so the model continues
        out = self.model.generate(ids, max_new=max_new, vocab_limit=len(self.tok.token_to_id),
                                  eos_id=self.tok.token_to_id["<eos>"])
        return self._decode_new(out, ids.shape[1])

    @torch.no_grad()
    def search(self, query: str, media_paths: List[str], top_k: int = 3) -> List[Tuple[str, float]]:
        """Cross-modal retrieval: rank images/clips/sounds by similarity to a text query."""
        self.model.eval()
        q = self.model.text_embedding(self._ids([query]).to(self.device))
        scored = []
        for p in media_paths:
            ext = Path(p).suffix.lower()
            mod = "image" if ext in IMAGE_EXTS else "video" if ext in VIDEO_EXTS else "audio"
            x = self._media({"modality": mod, "path": p})
            if x is not None:
                m = self.model.media_embedding(mod, x.unsqueeze(0).to(self.device))
                scored.append((p, round(float(q @ m.T), 4)))
        return sorted(scored, key=lambda kv: -kv[1])[:top_k]
