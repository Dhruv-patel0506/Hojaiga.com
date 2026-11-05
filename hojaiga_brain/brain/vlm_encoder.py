# brain/vlm_encoder.py
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from brain.config import VLMConfig

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass
class DiscoveredVisualRegion:
    """Dynamically discovered visual contour/component on ANY screen, diagram, or photo (zero fixed grid)."""
    region_id: str
    bbox: Tuple[int, int, int, int]
    rel_geometry: Tuple[float, float, float, float]  # (cx, cy, w_ratio, h_ratio) in [0, 1]
    edge_density: float
    color_entropy: float
    aspect_ratio: float


@dataclass
class LearnedInterfacePrototype:
    """Persistent memory of an application interface, diagram schema, or visual environment."""
    prototype_id: str
    label_hint: str
    observation_count: int
    centroid_vector: List[float]
    region_layout_graph: List[Tuple[float, float, float, float]]
    action_transitions: List[Dict[str, Any]] = field(default_factory=list)


class HojaigaVLMEncoder:
    """
    Zero-Hardcoding Vision-Language & Dynamic UI/Diagram Topology Engine:
    - Encodes 2D images, diagrams, and UI screenshots (`encode_image`)
    - Encodes 3D video clips and screen recordings (`encode_video`)
    - Discovers visual components via adaptive gradient connected-components (no fixed grid, no hardcoded widget names)
    - Remembers and recognizes ANY application interface or diagram pattern via Adaptive Resonance (`known_interfaces`)
    """

    def __init__(self, cfg: VLMConfig, memory_dir: Optional[Path] = None):
        self.cfg = cfg
        self.memory_dir = memory_dir
        self.known_interfaces: Dict[str, LearnedInterfacePrototype] = {}
        self._load_interface_memory()

        if HAS_TORCH:
            num_patches_2d = (cfg.image_size // cfg.patch_size) ** 2
            self.patch_embed_2d = nn.Conv2d(3, cfg.vision_dim, kernel_size=cfg.patch_size, stride=cfg.patch_size)
            self.tubelet_embed_3d = nn.Conv3d(
                3,
                cfg.vision_dim,
                kernel_size=(cfg.temporal_tubelet, cfg.patch_size, cfg.patch_size),
                stride=(cfg.temporal_tubelet, cfg.patch_size, cfg.patch_size),
            )
            self.cls_token = nn.Parameter(torch.randn(1, 1, cfg.vision_dim) * 0.02)
            self.pos_embed_2d = nn.Parameter(torch.randn(1, num_patches_2d + 1, cfg.vision_dim) * 0.02)
            enc_layer = nn.TransformerEncoderLayer(
                d_model=cfg.vision_dim,
                nhead=cfg.vision_heads,
                dim_feedforward=cfg.vision_dim * 4,
                dropout=0.05,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.transformer = nn.TransformerEncoder(enc_layer, num_layers=cfg.vision_layers)
            self.norm = nn.LayerNorm(cfg.vision_dim)
            self.llm_projector = nn.Sequential(
                nn.Linear(cfg.vision_dim, cfg.proj_dim),
                nn.GELU(),
                nn.Linear(cfg.proj_dim, cfg.proj_dim),
            )
            self._load_or_save_vision_weights()

    # -- persistence of the vision network (stable embeddings across runs) -----
    def _vision_modules(self) -> Dict[str, Any]:
        return {"patch_embed_2d": self.patch_embed_2d, "tubelet_embed_3d": self.tubelet_embed_3d,
                "transformer": self.transformer, "norm": self.norm, "llm_projector": self.llm_projector}

    def vision_state_dict(self) -> Dict[str, Any]:
        state = {f"{n}.{k}": v for n, m in self._vision_modules().items() for k, v in m.state_dict().items()}
        state["cls_token"] = self.cls_token.data
        state["pos_embed_2d"] = self.pos_embed_2d.data
        return state

    def load_vision_state_dict(self, state: Dict[str, Any]) -> None:
        for n, m in self._vision_modules().items():
            m.load_state_dict({k[len(n) + 1:]: v for k, v in state.items() if k.startswith(n + ".")})
        self.cls_token.data.copy_(state["cls_token"])
        self.pos_embed_2d.data.copy_(state["pos_embed_2d"])

    def _load_or_save_vision_weights(self) -> None:
        """Without this the network is re-initialised randomly in every process and an app seen
        yesterday would look brand new today. Weights live next to learned_interfaces.json."""
        if not self.memory_dir:
            return
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        wpath = self.memory_dir / "vlm_weights.pt"
        if wpath.exists():
            self.load_vision_state_dict(torch.load(wpath, map_location="cpu", weights_only=True))
        else:
            torch.save(self.vision_state_dict(), wpath)
            if self.known_interfaces:      # embeddings from a previous random network no longer match
                self.known_interfaces.clear()
                self._save_interface_memory()

    # -- public perception API -------------------------------------------------
    def encode_image(self, rgb_array: np.ndarray) -> Any:
        """2D image / diagram / UI screenshot [H,W,3] uint8 → multimodal tokens ([1, 1+P, proj_dim]
        tensor with PyTorch, or a proj_dim NumPy vector in the zero-dependency engine)."""
        return self.encode_image_array(rgb_array)

    def encode_video(self, frames_rgb: np.ndarray) -> Any:
        """3D clip / screen recording [T,H,W,3] uint8 → tokens from the SAME network as images:
        tubelet (time×patch) embedding → shared transformer → shared LLM projector."""
        frames = np.asarray(frames_rgb)
        if frames.ndim != 4:
            raise ValueError("encode_video expects [T,H,W,3] frames")
        t_target = self.cfg.temporal_frames
        idx = np.linspace(0, frames.shape[0] - 1, num=t_target).round().astype(int)
        frames = frames[idx]
        if HAS_TORCH:
            with torch.no_grad():
                vid = torch.from_numpy(frames.astype(np.float32) / 255.0).permute(0, 3, 1, 2)   # T,3,H,W
                if vid.shape[-2:] != (self.cfg.image_size, self.cfg.image_size):
                    vid = F.interpolate(vid, size=(self.cfg.image_size, self.cfg.image_size),
                                        mode="bilinear", align_corners=False)
                vid = vid.permute(1, 0, 2, 3).unsqueeze(0)                                      # 1,3,T,H,W
                tubes = self.tubelet_embed_3d(vid)                                              # 1,D,T',h,w
                t_slices = tubes.shape[2]
                tubes = tubes.flatten(3).permute(0, 2, 3, 1)                                    # 1,T',hw,D
                tubes = tubes + self.pos_embed_2d[:, 1:].unsqueeze(1)
                tubes = tubes.reshape(1, t_slices * tubes.shape[2], -1)
                cls_tok = self.cls_token.expand(1, -1, -1) + self.pos_embed_2d[:, :1]
                x = self.norm(self.transformer(torch.cat([cls_tok, tubes], dim=1)))
                return self.llm_projector(x)
        per_frame = np.stack([np.asarray(self.encode_image_array(f), dtype=np.float32) for f in frames])
        motion = np.abs(np.diff(per_frame, axis=0)).mean(axis=0) if len(per_frame) > 1 else np.zeros_like(per_frame[0])
        vec = 0.8 * per_frame.mean(axis=0) + 0.2 * motion
        n = np.linalg.norm(vec)
        return vec / n if n > 1e-8 else vec

    def deep_scan_ui_screen(self, rgb_array: np.ndarray, context_hint: str = "") -> Dict[str, Any]:
        """Full scan of any app screen / diagram: discovered regions with pixel boxes, interface
        recognition against memory (Adaptive Resonance) and epistemic surprise."""
        scan = self.perceive_and_remember_interface(rgb_array, context_hint=context_hint)
        scan["layout"] = [{"region_id": r.region_id, "bbox": r.bbox, "rel_geometry": r.rel_geometry,
                           "edge_density": r.edge_density, "color_entropy": r.color_entropy}
                          for r in scan["regions"]]
        return scan

    def encode_image_array(self, rgb_array: np.ndarray) -> Any:
        """Encodes an RGB image array into multimodal token embeddings (PyTorch Tensor or NumPy vector)."""
        if HAS_TORCH:
            with torch.no_grad():
                img_t = torch.from_numpy(rgb_array).permute(2, 0, 1).float().unsqueeze(0) / 255.0
                if img_t.shape[-2:] != (self.cfg.image_size, self.cfg.image_size):
                    img_t = F.interpolate(
                        img_t, size=(self.cfg.image_size, self.cfg.image_size), mode="bilinear", align_corners=False
                    )
                patches = self.patch_embed_2d(img_t).flatten(2).transpose(1, 2)
                cls_tok = self.cls_token.expand(1, -1, -1)
                x = torch.cat([cls_tok, patches], dim=1) + self.pos_embed_2d
                x = self.norm(self.transformer(x))
                return self.llm_projector(x)

        # Pure NumPy multi-scale spatial-spectral descriptor when PyTorch is absent
        arr = rgb_array.astype(np.float32) / 255.0
        h, w, _ = arr.shape
        gh, gw = min(h, 8), min(w, 8)
        th, tw = (h // gh) * gh, (w // gw) * gw
        pooled = arr[:th, :tw].reshape(gh, th // gh, gw, tw // gw, 3).mean(axis=(1, 3)).ravel()
        vec = np.zeros(self.cfg.proj_dim, dtype=np.float32)
        vec[: min(len(pooled), self.cfg.proj_dim)] = pooled[: self.cfg.proj_dim]
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-8 else vec

    def _extract_dynamic_connected_regions(self, rgb_array: np.ndarray) -> List[DiscoveredVisualRegion]:
        """
        Finds arbitrary interactive controls, diagram nodes, or visual objects dynamically using
        spatial gradient energy + connected-component flood-fill on adaptive salience maps.
        Zero fixed grids and zero hardcoded widget categories.
        """
        h, w, _ = rgb_array.shape
        gray = np.mean(rgb_array.astype(np.float32), axis=2)
        gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
        gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
        grad = (gx + gy) / 255.0

        scale_y, scale_x = max(h // 32, 1), max(w // 32, 1)
        gh, gw = max(h // scale_y, 1), max(w // scale_x, 1)
        trimmed = grad[: gh * scale_y, : gw * scale_x]
        pooled = trimmed.reshape(gh, scale_y, gw, scale_x).mean(axis=(1, 3))

        thresh = float(np.mean(pooled) + 0.65 * np.std(pooled))
        active_mask = pooled > max(thresh, 0.02)

        visited = np.zeros_like(active_mask, dtype=bool)
        regions: List[DiscoveredVisualRegion] = []

        for r in range(gh):
            for c in range(gw):
                if active_mask[r, c] and not visited[r, c]:
                    stack = [(r, c)]
                    visited[r, c] = True
                    cells = []
                    while stack:
                        cr, cc = stack.pop()
                        cells.append((cr, cc))
                        for dr in (-1, 0, 1):
                            for dc in (-1, 0, 1):
                                nr, nc = cr + dr, cc + dc
                                if 0 <= nr < gh and 0 <= nc < gw and active_mask[nr, nc] and not visited[nr, nc]:
                                    visited[nr, nc] = True
                                    stack.append((nr, nc))

                    rs = [pt[0] for pt in cells]
                    cs = [pt[1] for pt in cells]
                    y1, y2 = min(rs) * scale_y, min((max(rs) + 1) * scale_y, h)
                    x1, x2 = min(cs) * scale_x, min((max(cs) + 1) * scale_x, w)
                    if (y2 - y1) < 4 or (x2 - x1) < 4:
                        continue

                    crop = rgb_array[y1:y2, x1:x2]
                    edge_d = float(np.mean(grad[y1:y2, x1:x2]))
                    hist, _ = np.histogram(crop, bins=16, range=(0, 256), density=True)
                    hist = hist[hist > 0]
                    col_ent = float(-np.sum(hist * np.log2(hist + 1e-9)))
                    cx_rel = ((x1 + x2) / 2.0) / max(w, 1)
                    cy_rel = ((y1 + y2) / 2.0) / max(h, 1)
                    w_rel = (x2 - x1) / max(w, 1)
                    h_rel = (y2 - y1) / max(h, 1)

                    reg_id = f"reg_{len(regions)}_{int(cx_rel*100)}_{int(cy_rel*100)}"
                    regions.append(
                        DiscoveredVisualRegion(
                            region_id=reg_id,
                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                            rel_geometry=(round(cx_rel, 4), round(cy_rel, 4), round(w_rel, 4), round(h_rel, 4)),
                            edge_density=round(edge_d, 4),
                            color_entropy=round(col_ent, 4),
                            aspect_ratio=round((x2 - x1) / max(y2 - y1, 1), 3),
                        )
                    )
        return regions

    def perceive_and_remember_interface(
        self, rgb_array: np.ndarray, context_hint: str = ""
    ) -> Dict[str, Any]:
        """
        1. Dynamically extracts connected visual regions (UI widgets, diagram nodes, or visual objects)
        2. Computes holistic VLM embedding + topological layout descriptor
        3. Matches against learned interface prototypes using Adaptive Resonance Theory (ART):
           - If similarity >= vigilance_threshold: recognizes the interface/app pattern from memory!
           - If similarity < vigilance_threshold: high Epistemic Surprise! Registers a new prototype and
             remembers this interface for future runs.
        """
        regions = self._extract_dynamic_connected_regions(rgb_array)
        vis_tokens = self.encode_image_array(rgb_array)
        if HAS_TORCH and hasattr(vis_tokens, "mean"):
            global_vec = F.normalize(vis_tokens.mean(dim=1)[0], dim=-1).cpu().numpy()
        else:
            global_vec = np.asarray(vis_tokens, dtype=np.float32).ravel()

        topo_stats = np.zeros(16, dtype=np.float32)
        if regions:
            geoms = np.array([r.rel_geometry for r in regions], dtype=np.float32)
            topo_stats[:4] = np.mean(geoms, axis=0)
            topo_stats[4:8] = np.std(geoms, axis=0)
            topo_stats[8] = min(len(regions) / 50.0, 1.0)
            topo_stats[9] = float(np.mean([r.edge_density for r in regions]))
            topo_stats[10] = float(np.mean([r.color_entropy for r in regions])) / 4.0

        combined_sig = np.concatenate([global_vec[:48], topo_stats])
        norm = np.linalg.norm(combined_sig)
        if norm > 1e-8:
            combined_sig = combined_sig / norm

        best_proto_id: Optional[str] = None
        best_sim: float = -1.0
        for pid, proto in self.known_interfaces.items():
            c_vec = np.array(proto.centroid_vector, dtype=np.float32)
            sim = float(np.dot(combined_sig, c_vec))
            if sim > best_sim:
                best_sim = sim
                best_proto_id = pid

        is_recognized = best_sim >= self.cfg.vigilance_threshold and best_proto_id is not None
        epistemic_surprise = float(np.clip(1.0 - max(best_sim, 0.0), 0.0, 1.0))

        if is_recognized and best_proto_id is not None:
            proto = self.known_interfaces[best_proto_id]
            n = proto.observation_count
            updated = (np.array(proto.centroid_vector) * n + combined_sig) / (n + 1)
            updated = updated / max(np.linalg.norm(updated), 1e-8)
            proto.centroid_vector = [round(float(x), 5) for x in updated]
            proto.observation_count += 1
            if context_hint and not proto.label_hint:
                proto.label_hint = context_hint
            matched_id = best_proto_id
        else:
            sig_hash = hashlib.sha1(combined_sig.tobytes()).hexdigest()[:10]
            matched_id = f"interface_{sig_hash}"
            self.known_interfaces[matched_id] = LearnedInterfacePrototype(
                prototype_id=matched_id,
                label_hint=context_hint or f"discovered_layout_{len(self.known_interfaces) + 1}",
                observation_count=1,
                centroid_vector=[round(float(x), 5) for x in combined_sig],
                region_layout_graph=[r.rel_geometry for r in regions[:32]],
            )

        self._save_interface_memory()
        proto_obj = self.known_interfaces[matched_id]
        return {
            "interface_id": matched_id,
            "recognized_from_memory": is_recognized,
            "label_hint": proto_obj.label_hint,
            "observation_count": proto_obj.observation_count,
            "epistemic_surprise": round(epistemic_surprise, 4),
            "discovered_regions_count": len(regions),
            "regions": regions,
            "vision_tokens": vis_tokens,
        }

    def _save_interface_memory(self) -> None:
        if not self.memory_dir:
            return
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        data = {k: asdict(v) for k, v in self.known_interfaces.items()}
        (self.memory_dir / "learned_interfaces.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load_interface_memory(self) -> None:
        if not self.memory_dir:
            return
        p = self.memory_dir / "learned_interfaces.json"
        if not p.exists():
            return
        raw = json.loads(p.read_text(encoding="utf-8"))
        for k, v in raw.items():
            self.known_interfaces[k] = LearnedInterfacePrototype(
                prototype_id=v["prototype_id"],
                label_hint=v.get("label_hint", ""),
                observation_count=v.get("observation_count", 1),
                centroid_vector=v["centroid_vector"],
                region_layout_graph=[tuple(x) for x in v.get("region_layout_graph", [])],
                action_transitions=v.get("action_transitions", []),
            )
