# brain/dataset_hub_loader.py
"""
Zero-hardcoding dataset importer for the Hugging Face Hub (`datasets.load_dataset`) and any
iterable of dict rows. Every row is routed by the runtime type of its values, never by column name:

* PIL images / image arrays / lists of images / undecoded {"bytes": ...} images → VLM + L2
* numpy arrays with 4 dims → video
* lists of dicts that each carry a string (chat turns, document pools) → readable text
* one dominant long string (web/edu text) → chunked text stream (L1→L2/L3/L5, tokenizer, replay)
* everything else (short fields, <draft, polished> pairs, lists of steps) → structured record
  (L6 learns span edits from pairs, list fields become workflow transitions)

Blueprint fixes: rows are fed in one batch and state is saved once (not after every row), values
are made JSON-safe (numpy scalars, dates, bytes), and long text is no longer stored as one escaped
JSON blob.
"""
import io
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
from brain.curiosity_and_langchain import HojaigaExecutiveBrain


class DynamicHubDatasetStreamer:
    def __init__(self, brain: HojaigaExecutiveBrain, long_text_chars: int = 300):
        self.brain = brain
        self.long_text_chars = long_text_chars

    # ------------------------------------------------------------------ type-driven routing
    @staticmethod
    def _as_image(v: Any) -> Optional[np.ndarray]:
        if hasattr(v, "convert"):                                    # PIL.Image.Image
            return np.array(v.convert("RGB"))
        if isinstance(v, np.ndarray) and v.ndim == 3 and v.shape[-1] in (1, 3, 4):
            return v[..., :3] if v.shape[-1] != 1 else np.repeat(v, 3, axis=-1)
        if isinstance(v, dict) and isinstance(v.get("bytes"), (bytes, bytearray)):   # undecoded HF image
            try:
                from PIL import Image
                return np.array(Image.open(io.BytesIO(v["bytes"])).convert("RGB"))
            except Exception:
                return None
        return None

    @staticmethod
    def _json_safe(v: Any) -> Any:
        if isinstance(v, (str, int, float, bool)) or v is None:
            return v
        if isinstance(v, np.generic):
            return v.item()
        if isinstance(v, (bytes, bytearray)):
            return f"<{len(v)} bytes>"
        if isinstance(v, dict):
            return {str(k): DynamicHubDatasetStreamer._json_safe(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [DynamicHubDatasetStreamer._json_safe(x) for x in v]
        if isinstance(v, np.ndarray) and v.size <= 64:
            return v.tolist()
        return str(v)

    @staticmethod
    def _turns_to_text(v: Any) -> Optional[str]:
        """A list of dicts that each hold text (chat turns, retrieved passages) → readable lines."""
        if not (isinstance(v, list) and v and all(isinstance(x, dict) for x in v)):
            return None
        lines = []
        for x in v:
            strs = [s for s in x.values() if isinstance(s, str) and s.strip()]
            if strs:
                lines.append(": ".join(strs) if len(strs) <= 2 else " | ".join(strs))
        return "\n".join(lines) if lines else None

    def _extract_images_and_payload(self, row: Dict[str, Any]) -> Tuple[List[np.ndarray], List[np.ndarray],
                                                                       Dict[str, Any], List[str]]:
        images: List[np.ndarray] = []
        videos: List[np.ndarray] = []
        texts: List[str] = []
        clean: Dict[str, Any] = {}
        for k, v in row.items():
            img = self._as_image(v)
            if img is not None:
                images.append(img)
            elif isinstance(v, np.ndarray) and v.ndim == 4:
                videos.append(v)
            elif isinstance(v, list) and v and self._as_image(v[0]) is not None:
                images.extend(x for x in (self._as_image(i) for i in v[:4]) if x is not None)
            elif self._turns_to_text(v):
                texts.append(self._turns_to_text(v))
            else:
                clean[k] = self._json_safe(v)
        return images, videos, clean, texts

    # ------------------------------------------------------------------ ingestion
    def ingest_iterable_stream(self, stream: Iterable[Dict[str, Any]], source_tag: str = "hub_stream",
                               max_samples: int = 500) -> Dict[str, Any]:
        ing = self.brain.ingestor
        stats: Dict[str, Any] = {"source": source_tag, "rows_streamed": 0, "text_or_workflow_episodes": 0,
                                 "visual_episodes": 0, "video_episodes": 0, "interfaces_learned": 0,
                                 "emergent_domains_discovered": set()}

        def note(res: Dict[str, Any], key: str) -> None:
            stats[key] += res.get("episodes_added", 0)
            stats["interfaces_learned"] += res.get("interfaces_learned", 0)
            if res.get("emergent_domain"):
                stats["emergent_domains_discovered"].add(res["emergent_domain"].split(":")[0])

        for idx, row in enumerate(stream):
            if idx >= max_samples:
                break
            if not isinstance(row, dict):
                continue
            images, videos, payload, texts = self._extract_images_and_payload(row)
            for i, img in enumerate(images):
                note(ing.ingest_any(img, hint=f"{source_tag}_r{idx}_img{i}"), "visual_episodes")
            for i, vid in enumerate(videos):
                note(ing.ingest_any(vid, hint=f"{source_tag}_r{idx}_vid{i}"), "video_episodes")

            strings = {k: v for k, v in payload.items() if isinstance(v, str)}
            longest = max(strings, key=lambda k: len(strings[k]), default=None)
            if longest and len(strings[longest]) >= self.long_text_chars and \
                    sum(len(v) for k, v in strings.items() if k != longest) < len(strings[longest]) / 3:
                texts.insert(0, strings[longest])              # dominant passage: treat as prose
                payload.pop(longest)
            if texts:
                # the row's passage is the knowledge; its short fields (question, title, label, ids)
                # travel with it as metadata instead of becoming separate memories that a later
                # question would retrieve in place of the answer
                for t in texts:
                    note(ing._ingest_text_stream(t, source_uri=f"{source_tag}_r{idx}", metadata=payload),
                         "text_or_workflow_episodes")
            elif payload and any(isinstance(v, (str, list)) and v for v in payload.values()):
                note(ing.ingest_any(payload, hint=f"{source_tag}_r{idx}"), "text_or_workflow_episodes")
            stats["rows_streamed"] += 1

        self.brain.l2.save()
        self.brain.save_learned_state()                         # once per batch, not per row
        stats["emergent_domains_discovered"] = sorted(stats["emergent_domains_discovered"])
        return stats

    def import_from_huggingface(self, repo_id: str, config_name: Optional[str] = None, split: str = "train",
                                max_samples: int = 500, streaming: bool = True) -> Dict[str, Any]:
        """Streams any Hugging Face dataset into the brain without downloading it to disk."""
        from datasets import load_dataset

        ds = load_dataset(repo_id, name=config_name, split=split, streaming=streaming)
        tag = f"hf://{repo_id}" + (f"/{config_name}" if config_name else "")
        return self.ingest_iterable_stream(ds, source_tag=tag, max_samples=max_samples)
