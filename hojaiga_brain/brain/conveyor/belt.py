# brain/conveyor/belt.py
"""
The conveyor belt: one dataset in, a trained and measured brain out.

  1 ingest → 2 clean → 3 vectorize → 4 classical ML → 5 deep learning → 6 algorithms
  → 7 LLM/VLM (tokenizer, interface memory, optional neural training) → 8 RAG (feed the brain,
  measure retrieval) → 9 report

Stations are LangGraph nodes when `langgraph` is installed (a StateGraph with a conditional exit
when cleaning leaves nothing); otherwise a built-in runner executes the same nodes in the same order.
"""
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypedDict

import numpy as np

from brain.conveyor.ingest_clean import Item, clean_items, ingest_folder, load_image, load_video
from brain.conveyor import ml_stations as ml

try:
    from langgraph.graph import END, StateGraph
    HAS_LANGGRAPH = True
except Exception:
    HAS_LANGGRAPH = False


class BeltState(TypedDict):
    ctx: Dict[str, Any]


class ConveyorBelt:
    def __init__(self, brain, train_llm: bool = False, llm_epochs: int = 1, use_langgraph: bool = True):
        self.brain = brain
        self.train_llm = train_llm
        self.llm_epochs = llm_epochs
        self.use_langgraph = use_langgraph and HAS_LANGGRAPH
        self.stations: List[tuple] = [
            ("ingest", self.st_ingest), ("clean", self.st_clean), ("vectorize", self.st_vectorize),
            ("classical_ml", self.st_classical_ml), ("deep_learning", self.st_deep_learning),
            ("algorithms", self.st_algorithms), ("llm_vlm", self.st_llm_vlm), ("rag", self.st_rag),
            ("report", self.st_report),
        ]

    # ------------------------------------------------------------------ orchestration
    def _timed(self, name: str, fn: Callable[[Dict[str, Any]], None]) -> Callable[[BeltState], BeltState]:
        def node(state: BeltState) -> BeltState:
            ctx = state["ctx"]
            t0 = time.time()
            try:
                fn(ctx)
            except Exception as exc:                       # one broken station is reported, not fatal
                ctx["report"].setdefault("errors", {})[name] = f"{type(exc).__name__}: {exc}"
            ctx["report"].setdefault("seconds", {})[name] = round(time.time() - t0, 2)
            return {"ctx": ctx}
        return node

    def run(self, paths: List[str]) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {"paths": [str(p) for p in paths], "report": {"started": time.time()}}
        if self.use_langgraph:
            g = StateGraph(BeltState)
            for name, fn in self.stations:
                g.add_node(name, self._timed(name, fn))
            g.set_entry_point("ingest")
            g.add_edge("ingest", "clean")
            g.add_conditional_edges("clean", lambda s: "vectorize" if s["ctx"]["items"] else "report",
                                    {"vectorize": "vectorize", "report": "report"})
            names = [n for n, _ in self.stations]
            for a, b in zip(names[2:-1], names[3:]):
                g.add_edge(a, b)
            g.add_edge("report", END)
            out = g.compile().invoke({"ctx": ctx})
            ctx = out["ctx"]
            ctx["report"]["orchestrator"] = "langgraph"
        else:
            state: BeltState = {"ctx": ctx}
            for name, fn in self.stations:
                if name == "vectorize" and not state["ctx"]["items"]:
                    state = self._timed("report", self.st_report)(state)
                    break
                state = self._timed(name, fn)(state)
            ctx = state["ctx"]
            ctx["report"]["orchestrator"] = "built-in"
        return ctx["report"]

    # ------------------------------------------------------------------ stations
    def st_ingest(self, ctx: Dict[str, Any]) -> None:
        ctx["items"], ctx["report"]["ingest"] = ingest_folder(ctx["paths"])

    def st_clean(self, ctx: Dict[str, Any]) -> None:
        ctx["items"], ctx["report"]["clean"] = clean_items(ctx["items"], self.brain.l1)

    def st_vectorize(self, ctx: Dict[str, Any]) -> None:
        texts = [it for it in ctx["items"] if it.text]
        ctx["text_items"] = texts
        rep: Dict[str, Any] = {"text_items": len(texts)}
        if texts:
            tf = ml.TfidfVectorizer().fit([it.text for it in texts])
            ctx["tfidf"], ctx["X_tfidf"] = tf, tf.transform([it.text for it in texts])
            ctx["X_emb"] = np.stack([self.brain.l2.compute_embedding(it.text) for it in texts])
            rep.update(tfidf_features=len(tf.vocab), embedding_dim=int(ctx["X_emb"].shape[1]))
        imgs = [it for it in ctx["items"] if it.modality == "image"]
        vecs = []
        for it in imgs:
            arr = load_image(it.media)
            it.meta["array"] = arr
            tok = self.brain.vlm.encode_image(arr)
            v = tok.mean(1)[0].detach().cpu().numpy() if hasattr(tok, "detach") else np.asarray(tok)
            v = v / max(np.linalg.norm(v), 1e-8)
            # VLM embedding (improves as the VLM trains) + classic CV descriptor (works from day one)
            vecs.append(np.concatenate([0.5 * v, ml.image_features(arr)]).astype(np.float32))
        ctx["image_items"], ctx["X_img"] = imgs, (np.stack(vecs) if vecs else None)
        rep["image_vectors"] = len(vecs)
        from brain.omni.audio import load_audio, mfcc_features
        auds, avecs = [], []
        for it in ctx["items"]:
            if it.modality == "audio":
                x = load_audio(it.media)
                if x is not None:
                    auds.append(it)
                    avecs.append(mfcc_features(x))
        if avecs:
            A = np.stack(avecs)
            ctx["audio_stats"] = (A.mean(0), A.std(0) + 1e-6)
            A = (A - ctx["audio_stats"][0]) / ctx["audio_stats"][1]          # standardise MFCC features
        ctx["audio_items"], ctx["X_audio"] = auds, (A if avecs else None)
        rep["audio_vectors"] = len(avecs)
        ctx["report"]["vectorize"] = rep

    def _labels(self, ctx: Dict[str, Any]) -> None:
        """Text labels from a categorical record field; image labels from class folders."""
        texts: List[Item] = ctx.get("text_items", [])
        rec_idx = [i for i, it in enumerate(texts) if it.modality == "record"]
        recs = [texts[i].record for i in rec_idx]
        ranked = ml.rank_label_fields([texts[i].text for i in rec_idx], recs, ctx["X_tfidf"][rec_idx]) \
            if recs and "X_tfidf" in ctx else []
        ctx["label_candidates"] = ranked
        field = ranked[0]["field"] if ranked and ranked[0]["lift"] > 0.05 else None
        if field:
            for it in texts:
                if it.modality == "record" and field in it.record:
                    it.label = str(it.record[field]).strip().lower()
        ctx["label_field"] = field
        for key in ("image_items", "audio_items"):
            media: List[Item] = ctx.get(key, [])
            folders = [it.meta.get("folder") for it in media]
            counts = {f: folders.count(f) for f in set(folders)}
            if len(counts) >= 2 and min(counts.values()) >= 2:
                for it in media:
                    it.label = it.meta["folder"]

    def st_classical_ml(self, ctx: Dict[str, Any]) -> None:
        self._labels(ctx)
        rep: Dict[str, Any] = {}
        if "X_tfidf" in ctx and len(ctx["text_items"]) >= 4:
            topics = ml.discover_topics(ctx["X_tfidf"], ctx["tfidf"])
            ctx["topics"] = topics
            rep["topics"] = {k: v for k, v in topics.items() if k != "labels"}
        labeled = [i for i, it in enumerate(ctx.get("text_items", [])) if it.label]
        if len(labeled) >= 6:
            X, y = ctx["X_tfidf"][labeled], np.array([ctx["text_items"][i].label for i in labeled])
            cmp_ = ml.compare_models(X, y)
            ctx.setdefault("comparisons", {})["text"] = cmp_
            ctx["confusion"] = (f"text: {cmp_['best_model']}", *ml.confusion(y, cmp_["_best_preds"])) \
                if cmp_["_best_preds"] is not None else None
            rep["text_classification"] = {
                "label_field": ctx["label_field"], "label_candidates": ctx["label_candidates"],
                "classes": sorted(set(y.tolist())), "samples": len(y),
                **cmp_["models"], "best_model": cmp_["best_model"],
            }
            model = ml.SoftmaxRegression().fit(X, y)
            ml.save_classifier(self.brain.cfg.workspace_dir / "models" / "text_classifier.json",
                               ctx["tfidf"], model, ctx["label_field"])
            rep["text_classification"]["saved"] = "models/text_classifier.json"
        img_lab = [i for i, it in enumerate(ctx.get("image_items", [])) if it.label]
        if len(img_lab) >= 6:
            X, y = ctx["X_img"][img_lab], np.array([ctx["image_items"][i].label for i in img_lab])
            cmp_ = ml.compare_models(X, y, nonneg=bool((X >= 0).all()))
            ctx.setdefault("comparisons", {})["image"] = cmp_
            rep["image_classification"] = {"classes": sorted(set(y.tolist())), "samples": len(y),
                                           **cmp_["models"], "best_model": cmp_["best_model"]}
        aud_lab = [i for i, it in enumerate(ctx.get("audio_items", [])) if it.label]
        if len(aud_lab) >= 6:
            X, y = ctx["X_audio"][aud_lab], np.array([ctx["audio_items"][i].label for i in aud_lab])
            cmp_ = ml.compare_models(X, y, nonneg=False)
            ctx.setdefault("comparisons", {})["audio"] = cmp_
            rep["audio_classification"] = {"classes": sorted(set(y.tolist())), "samples": len(y),
                                           **cmp_["models"], "best_model": cmp_["best_model"]}
        ctx["report"]["classical_ml"] = rep

    def st_deep_learning(self, ctx: Dict[str, Any]) -> None:
        rep: Dict[str, Any] = {"engine": "pytorch" if ml.HAS_TORCH else "numpy"}
        labeled = [i for i, it in enumerate(ctx.get("text_items", [])) if it.label]
        if len(labeled) >= 10:
            y = np.array([ctx["text_items"][i].label for i in labeled])
            X = np.concatenate([ctx["X_tfidf"][labeled], ctx["X_emb"][labeled]], axis=1)
            rep["mlp_text"] = ml.holdout_accuracy(ml.MLPClassifier, X, y)
            rep["transformer_text"] = ml.transformer_text_classifier(
                [ctx["text_items"][i].text for i in labeled], y, self.brain.tokenizer)
        img_lab = [i for i, it in enumerate(ctx.get("image_items", [])) if it.label]
        if len(img_lab) >= 10:
            y = np.array([ctx["image_items"][i].label for i in img_lab])
            rep["mlp_image"] = ml.holdout_accuracy(ml.MLPClassifier, ctx["X_img"][img_lab], y)
        aud_lab = [i for i, it in enumerate(ctx.get("audio_items", [])) if it.label]
        if len(aud_lab) >= 10:
            y = np.array([ctx["audio_items"][i].label for i in aud_lab])
            rep["mlp_audio"] = ml.holdout_accuracy(ml.MLPClassifier, ctx["X_audio"][aud_lab], y)
        ctx["report"]["deep_learning"] = rep

    def st_algorithms(self, ctx: Dict[str, Any]) -> None:
        texts = [it.text for it in ctx.get("text_items", [])]
        g = ml.concept_graph(texts, self.brain.l1, self.brain.l3) if texts else {"nodes": 0}
        for s, p, o in g.pop("triples", []):
            self.brain.l2.concept_triples[s].append((p, o, "conveyor"))
        anomalies = ctx.get("topics", {}).get("anomalies", [])
        g["anomalous_items"] = [ctx["text_items"][i].item_id for i in anomalies][:20]
        ctx["report"]["algorithms"] = g

    def st_llm_vlm(self, ctx: Dict[str, Any]) -> None:
        texts = [it.text for it in ctx.get("text_items", [])]
        merges = self.brain.tokenizer.train_incremental(texts, max_new_merges=1000) if texts else 0
        rep: Dict[str, Any] = {"tokenizer_new_merges": merges, "vocab": len(self.brain.tokenizer.token_to_id)}
        interfaces = {"new": 0, "recognized": 0}
        for it in ctx.get("image_items", []):
            res = self.brain.ingestor.ingest_any(it.meta.pop("array", None) if "array" in it.meta
                                                 else load_image(it.media), hint=Path(it.media).stem)
            interfaces["recognized" if res.get("recognized_from_memory") else "new"] += 1
        for it in ctx["items"]:
            if it.modality == "video":
                frames = load_video(it.media)
                if frames is not None and len(frames) >= 2:
                    self.brain.ingestor.ingest_any(frames, hint=it.media)
                    interfaces["videos"] = interfaces.get("videos", 0) + 1
        rep["vlm_interfaces"] = interfaces
        ctx["report"]["llm_vlm"] = rep

    def st_rag(self, ctx: Dict[str, Any]) -> None:
        ing = self.brain.ingestor
        added = 0
        for it in ctx.get("text_items", []):
            res = ing._ingest_text_stream(it.text, source_uri=it.source,
                                          metadata={**({"label": it.label} if it.label else {}),
                                                    **(it.meta.get("fields") or {})})
            added += res.get("episodes_added", 0)
        if self.train_llm:
            from brain_cli import run_overnight_consolidation
            ctx["report"]["llm_training"] = run_overnight_consolidation(self.brain, epochs=self.llm_epochs)
        self.brain.l2.save()
        self.brain.save_learned_state()
        # retrieval check: does a sentence's own salient words find the memory it came from?
        probes, hits = 0, 0
        for it in ctx.get("text_items", [])[:60]:
            sents = [s for s in it.text.replace("\n", " ").split(". ") if len(s.split()) >= 6]
            if not sents:
                continue
            s = sents[0]
            q = " ".join(self.brain.l1.process(s)["salient_terms"][:5])
            top = [ep.content for ep, _ in self.brain.l2.retrieve_rrf(q, top_k=3)]
            probes += 1
            hits += any(s[:60] in c for c in top)
        ctx["report"]["rag"] = {"episodes_added": added, "memory_size": len(self.brain.l2.episodes),
                                "retrieval_probes": probes,
                                "recall_at_3": round(hits / probes, 3) if probes else None}

    def st_report(self, ctx: Dict[str, Any]) -> None:
        rep = ctx["report"]
        rep["finished"] = time.time()
        out = self.brain.cfg.workspace_dir / "conveyor_reports"
        out.mkdir(parents=True, exist_ok=True)
        topics = ctx.get("topics") or {}
        rep["charts"] = ml.render_charts(out / f"run_{int(rep['finished'])}", ctx.get("comparisons", {}),
                                         ctx.get("X_tfidf") if "labels" in topics else None,
                                         topics.get("labels"), ctx.get("confusion"))
        path = out / f"run_{int(rep['finished'])}.json"
        path.write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
        rep["report_file"] = str(path)


def classify_text(workspace: Path, text: str) -> Optional[Dict[str, Any]]:
    """Use the text classifier the belt trained (if any) on new text."""
    p = Path(workspace) / "models" / "text_classifier.json"
    if not p.exists():
        return None
    tf, model, field = ml.load_classifier(p)
    proba = model.predict_proba(tf.transform([text]))[0]
    order = np.argsort(-proba)
    return {"field": field, "label": str(model.classes[order[0]]), "confidence": round(float(proba[order[0]]), 3),
            "alternatives": [[str(model.classes[i]), round(float(proba[i]), 3)] for i in order[1:3]]}
