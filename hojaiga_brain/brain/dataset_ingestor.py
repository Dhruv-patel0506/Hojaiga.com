# brain/dataset_ingestor.py
import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from brain.layers_l1_to_l8 import (
    Layer1ThalamusFilter,
    Layer3WernickeUnderstand,
    Layer5DefaultModeThink,
    Layer6BrocaAnswer,
)
from brain.rag_hippocampus import HippocampusRAGEngine
from brain.tokenizer_and_llm import HojaigaTokenizer
from brain.vlm_encoder import HojaigaVLMEncoder


class UniversalDatasetIngestor:
    """
    Zero-Hardcoding Universal Dataset Ingestor:
    Drop ANY file, folder, or memory buffer (plain text, Markdown, code, JSON/CSV workflows,
    edited writing pairs, images/photos, UI screenshots, diagrams, or video tensors) and the brain:
    1. Automatically detects modality & structural topology
    2. Extracts emergent domain clusters, concept/workflow graphs, visual interface prototypes,
       and writing style statistics
    3. Populates L2 Hippocampus RAG, L5/L6 Style Memory, VLM Interface Memory, and L8 Replay Buffer
    """

    IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
    VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".gif"}
    STRUCTURED_EXTS = {".json", ".jsonl", ".csv", ".tsv"}

    def __init__(
        self,
        tokenizer: HojaigaTokenizer,
        vlm: HojaigaVLMEncoder,
        l1: Layer1ThalamusFilter,
        l2: HippocampusRAGEngine,
        l3: Layer3WernickeUnderstand,
        l5: Layer5DefaultModeThink,
        l6: Layer6BrocaAnswer,
        replay_buffer: List[Dict[str, Any]],
    ):
        self.tokenizer = tokenizer
        self.vlm = vlm
        self.l1 = l1
        self.l2 = l2
        self.l3 = l3
        self.l5 = l5
        self.l6 = l6
        self.replay_buffer = replay_buffer

    def ingest_any(self, target: Union[str, Path, np.ndarray, Dict[str, Any]], hint: str = "") -> Dict[str, Any]:
        if isinstance(target, np.ndarray):
            if target.ndim == 3:
                return self._ingest_image_array(target, source_uri=hint or "memory_image")
            if target.ndim == 4:
                return self._ingest_video_array(target, source_uri=hint or "memory_video")
        if isinstance(target, dict):
            return self._ingest_structured_record(target, source_uri=hint or "memory_dict")

        path = Path(str(target))
        try:                                   # long raw text is not a path (ENAMETOOLONG)
            is_dir, is_file = path.is_dir(), path.is_file()
        except (OSError, ValueError):
            is_dir = is_file = False
        if is_dir:
            summary: Dict[str, int] = {"files_processed": 0, "episodes_added": 0, "interfaces_learned": 0}
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    res = self.ingest_file(child)
                    summary["files_processed"] += 1
                    summary["episodes_added"] += res.get("episodes_added", 0)
                    summary["interfaces_learned"] += res.get("interfaces_learned", 0)
            self.l2.save()
            return summary
        if is_file:
            res = self.ingest_file(path)
            self.l2.save()
            return res

        return self._ingest_text_stream(str(target), source_uri=hint or "inline_stream")

    def ingest_file(self, file_path: Path) -> Dict[str, Any]:
        ext = file_path.suffix.lower()
        if ext in self.IMAGE_EXTS:
            from PIL import Image

            img = np.array(Image.open(file_path).convert("RGB"))
            return self._ingest_image_array(img, source_uri=str(file_path))
        if ext in self.VIDEO_EXTS:
            return self._ingest_video_file(file_path)
        if ext in self.STRUCTURED_EXTS:
            raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
            return self._ingest_structured_text(raw_text, ext=ext, source_uri=str(file_path))

        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
        return self._ingest_text_stream(raw_text, source_uri=str(file_path))

    def _ingest_text_stream(self, text: str, source_uri: str,
                            metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) > 15] or [text.strip()]
        self.tokenizer.train_incremental(chunks, max_new_merges=250)
        added = 0
        last_cluster = ""
        for chunk in chunks:
            l1_out = self.l1.process(chunk)
            if l1_out["is_duplicate"] or not l1_out["passes_quality_gate"]:
                continue
            self.l3.predict_and_adapt_intent(chunk)
            triples = self.l3.extract_distributional_relations(chunk, l1_out["salience_map"])
            self.l5.observe_reference_writing(chunk)
            wq = self.l5.compute_distributional_writing_score(chunk)
            _, last_cluster, surprise = self.l2.ingest_episode(
                content=chunk,
                modality="text",
                source_uri=source_uri,
                continuous_value=max(wq, 0.65),
                triples=triples,
                metadata=metadata,
            )
            self.replay_buffer.append(
                {"prompt": " ".join(l1_out["salient_terms"][:4]), "response": chunk, "value": wq, "surprise": surprise}
            )
            added += 1
        return {"modality": "text", "episodes_added": added, "emergent_domain": last_cluster, "interfaces_learned": 0}

    def _ingest_structured_text(self, raw_text: str, ext: str, source_uri: str) -> Dict[str, Any]:
        records: List[Dict[str, Any]] = []
        if ext == ".jsonl":
            for line in raw_text.splitlines():
                if line.strip():
                    records.append(json.loads(line))
        elif ext == ".json":
            parsed = json.loads(raw_text)
            records = parsed if isinstance(parsed, list) else [parsed]
        elif ext in (".csv", ".tsv"):
            delim = "\t" if ext == ".tsv" else ","
            reader = csv.DictReader(io.StringIO(raw_text), delimiter=delim)
            records = [dict(row) for row in reader]

        total_added = 0
        last_domain = ""
        for rec in records:
            r_out = self._ingest_structured_record(rec, source_uri=source_uri)
            total_added += r_out.get("episodes_added", 0)
            last_domain = r_out.get("emergent_domain", last_domain)
        return {"modality": "structured_workflow", "episodes_added": total_added, "emergent_domain": last_domain, "interfaces_learned": 0}

    def _ingest_structured_record(self, rec: Dict[str, Any], source_uri: str) -> Dict[str, Any]:
        str_fields = [(k, v) for k, v in rec.items() if isinstance(v, str) and len(v.strip()) > 10]
        if len(str_fields) >= 2:
            _, s1 = str_fields[0]
            _, s2 = str_fields[1]
            t1, t2 = set(s1.lower().split()), set(s2.lower().split())
            jaccard = len(t1 & t2) / max(len(t1 | t2), 1)
            if 0.15 <= jaccard <= 0.92:
                self.l6.learn_from_edit_pair(s1, s2)
                self.l5.observe_reference_writing(s2)

        triples: List[Tuple[str, str, str]] = []
        for k, v in rec.items():
            if isinstance(v, list) and len(v) >= 2 and all(isinstance(x, str) for x in v):
                for i in range(len(v) - 1):
                    triples.append((v[i].lower(), f"seq_{k}", v[i + 1].lower()))

        serialized = json.dumps(rec, ensure_ascii=False, default=str)
        l1_out = self.l1.process(serialized)
        triples.extend(self.l3.extract_distributional_relations(serialized, l1_out["salience_map"]))
        _, cluster_sig, surprise = self.l2.ingest_episode(
            content=serialized,
            modality="workflow",
            source_uri=source_uri,
            continuous_value=0.75,
            triples=triples,
        )
        self.replay_buffer.append(
            {"prompt": " ".join(l1_out["salient_terms"][:4]), "response": serialized, "value": 0.75, "surprise": surprise}
        )
        return {"modality": "workflow", "episodes_added": 1, "emergent_domain": cluster_sig, "interfaces_learned": 0}

    def _ingest_image_array(self, rgb_array: np.ndarray, source_uri: str) -> Dict[str, Any]:
        scan = self.vlm.perceive_and_remember_interface(rgb_array, context_hint=Path(source_uri).stem)
        regions_desc = ", ".join(
            f"{r.region_id}@({r.rel_geometry[0]:.2f},{r.rel_geometry[1]:.2f})" for r in scan["regions"][:12]
        )
        visual_summary = (
            f"Visual interface/diagram '{scan['interface_id']}' ({scan['label_hint']}) with "
            f"{scan['discovered_regions_count']} dynamic components: {regions_desc}"
        )
        regs = scan["regions"][:12]
        spatial_triples: List[Tuple[str, str, str]] = []
        for i in range(len(regs) - 1):
            spatial_triples.append((regs[i].region_id, "adjacent_to", regs[i + 1].region_id))

        _, cluster_sig, _ = self.l2.ingest_episode(
            content=visual_summary,
            modality="image_or_ui",
            source_uri=source_uri,
            continuous_value=0.80,
            triples=spatial_triples,
            metadata={"interface_id": scan["interface_id"], "surprise": scan["epistemic_surprise"]},
        )
        return {
            "modality": "image_or_ui",
            "episodes_added": 1,
            "emergent_domain": cluster_sig,
            "interface_id": scan["interface_id"],
            "recognized_from_memory": scan["recognized_from_memory"],
            "epistemic_surprise": scan["epistemic_surprise"],
            "interfaces_learned": 0 if scan["recognized_from_memory"] else 1,
        }

    def _ingest_video_array(self, frames_rgb: np.ndarray, source_uri: str) -> Dict[str, Any]:
        t_len = frames_rgb.shape[0]
        diffs = [
            float(np.mean(np.abs(frames_rgb[i + 1].astype(np.float32) - frames_rgb[i].astype(np.float32))) / 255.0)
            for i in range(t_len - 1)
        ] or [0.0]
        mean_motion = float(np.mean(diffs))
        first_scan = self.vlm.perceive_and_remember_interface(frames_rgb[0], context_hint=f"{source_uri}_start")
        last_scan = self.vlm.perceive_and_remember_interface(frames_rgb[-1], context_hint=f"{source_uri}_end")

        triples = [(first_scan["interface_id"], f"temporal_motion_{mean_motion:.3f}", last_scan["interface_id"])]
        summary = (
            f"Temporal video sequence ({t_len} frames, motion={mean_motion:.4f}) transitioning from "
            f"{first_scan['interface_id']} ({first_scan['discovered_regions_count']} regions) to "
            f"{last_scan['interface_id']} ({last_scan['discovered_regions_count']} regions)."
        )
        _, cluster_sig, _ = self.l2.ingest_episode(
            content=summary,
            modality="video",
            source_uri=source_uri,
            continuous_value=0.82,
            triples=triples,
        )
        return {
            "modality": "video",
            "episodes_added": 1,
            "emergent_domain": cluster_sig,
            "mean_motion": round(mean_motion, 4),
            "interfaces_learned": 1,
        }

    def _ingest_video_file(self, file_path: Path) -> Dict[str, Any]:
        frames = []
        if file_path.suffix.lower() == ".gif":
            from PIL import Image, ImageSequence

            frames = [np.array(f.convert("RGB")) for f in ImageSequence.Iterator(Image.open(file_path))][:16]
        else:
            try:
                import cv2
            except ImportError:
                return {"modality": "video", "episodes_added": 0, "interfaces_learned": 0,
                        "skipped": "install opencv-python to read video files"}
            cap = cv2.VideoCapture(str(file_path))
            while len(frames) < 16:
                ret, frame = cap.read()
                if not ret:
                    break
                frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            cap.release()
        if not frames:
            return {"modality": "video", "episodes_added": 0, "interfaces_learned": 0}
        return self._ingest_video_array(np.stack(frames, axis=0), source_uri=str(file_path))
