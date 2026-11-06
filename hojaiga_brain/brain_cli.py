# brain_cli.py
import argparse
import json
from pathlib import Path
from typing import Dict

import numpy as np

from brain.config import BrainSystemConfig, LLMConfig
from brain.curiosity_and_langchain import HojaigaExecutiveBrain
from brain.dataset_hub_loader import DynamicHubDatasetStreamer
from brain.tokenizer_and_llm import HAS_TORCH
from brain.universal_renderer import HojaigaUniversalRenderer

if HAS_TORCH:
    import torch


def run_overnight_consolidation(brain: HojaigaExecutiveBrain, epochs: int = 3, lr: float = 3e-4) -> Dict[str, float]:
    """
    Trains Hojaiga's local LLM on the Surprise-Prioritized Replay Buffer (`SuRe`)
    and consolidates Orthogonal-LoRA adapters into the base model weights.
    Supports both PyTorch CUDA/CPU and the zero-dependency NumPy neural engine.
    """
    samples = sorted(brain.l8.golden_replay_buffer, key=lambda s: s.get("surprise", 0.5), reverse=True)
    if not samples:
        return {"trained_samples": 0, "final_loss": 0.0}

    texts = [f"{s['prompt']}\n{s['response']}" for s in samples]
    brain.tokenizer.train_incremental(texts, max_new_merges=1000)

    last_loss = 0.0
    if HAS_TORCH:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        brain.llm.to(device)
        brain.llm.train()
        optimizer = torch.optim.AdamW(brain.llm.parameters(), lr=lr, weight_decay=0.01)

        for _ in range(epochs):
            for s in samples:
                ids = brain.tokenizer.encode(f"{s['prompt']}\n{s['response']}", add_bos=True, add_eos=True)
                ids = ids[: brain.cfg.llm.max_seq_len + 1]
                if len(ids) < 2:
                    continue
                x = torch.tensor([ids[:-1]], dtype=torch.long, device=device)
                y = torch.tensor([ids[1:]], dtype=torch.long, device=device)
                v_target = torch.tensor([float(s.get("value", 0.8))], dtype=torch.float32, device=device)
                optimizer.zero_grad()
                out = brain.llm(x, targets=y, target_value=v_target)
                loss = out["loss"]
                loss.backward()
                torch.nn.utils.clip_grad_norm_(brain.llm.parameters(), 1.0)
                optimizer.step()
                last_loss = float(loss.item())

        for module in brain.llm.modules():
            if hasattr(module, "consolidate_into_base"):
                module.consolidate_into_base()

        ckpt = brain.cfg.workspace_dir / "checkpoints" / f"hojaiga_{brain.cfg.llm.variant}.pt"
        torch.save(brain.llm.state_dict(), ckpt)
    else:
        for _ in range(epochs):
            for s in samples:
                ids = brain.tokenizer.encode(f"{s['prompt']}\n{s['response']}", add_bos=True, add_eos=True)
                last_loss = brain.llm.fit_sequence(ids, reward_value=float(s.get("value", 0.8)))
        ck = brain.cfg.workspace_dir / "checkpoints"
        np.savez(ck / f"hojaiga_{brain.cfg.llm.variant}_numpy.npz", embed_matrix=brain.llm.embed_matrix,
                 lora_A=brain.llm.lora_A, lora_B=brain.llm.lora_B, value_w=brain.llm.value_w,
                 verify_w=brain.llm.verify_w)
        (ck / "numpy_continuations.json").write_text(json.dumps(
            {str(k): {str(a): b for a, b in v.items()} for k, v in brain.llm.learned_continuations.items()}),
            encoding="utf-8")

    brain.llm_trained = True
    brain.save_learned_state()
    return {"trained_samples": len(samples), "final_loss": round(last_loss, 4)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Hojaiga Brain — Zero-Hardcoding Dynamic CLI")
    parser.add_argument("--workspace", default="hojaiga_storage", help="where the brain keeps everything it learns")
    parser.add_argument("--variant", default="small_17m", choices=["tiny_5m", "small_17m", "base_37m"])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Feed ANY dataset file or directory (text, JSON, CSV, images, UI, video)")
    p_ingest.add_argument("path", type=str)

    p_hf = sub.add_parser("import-hf", help="Stream ANY Hugging Face dataset directly into LLM, VLM & Hippocampus RAG")
    p_hf.add_argument("repo_id", type=str, help="Hugging Face dataset repo ID (e.g. Voxel51/WaveUI-25k)")
    p_hf.add_argument("--config", type=str, default=None, help="Optional dataset subset/config name")
    p_hf.add_argument("--split", type=str, default="train", help="Dataset split")
    p_hf.add_argument("--max-samples", type=int, default=500, help="Number of samples to stream in this batch")

    p_belt = sub.add_parser("belt", help="Conveyor belt: ingest → clean → ML → DL → algorithms → LLM/VLM → RAG → report")
    p_belt.add_argument("paths", nargs="+")
    p_belt.add_argument("--train-llm", action="store_true", help="also train the neural LLM at the end")

    p_cls = sub.add_parser("classify", help="Classify text with the classifier the belt trained")
    p_cls.add_argument("text", type=str)

    p_task = sub.add_parser("task", help="Give the controller any request; it routes it to a skill")
    p_task.add_argument("text", type=str)
    p_task.add_argument("--path", default=None)
    p_task.add_argument("--image", default=None)

    p_serve = sub.add_parser("serve", help="Always-on controller: HTTP API + inbox learning + consolidation")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--inbox", default=None, help="folder to drop new datasets into (default workspace/inbox)")
    p_serve.add_argument("--consolidate-minutes", type=float, default=60.0)

    sub.add_parser("init", help="Create an empty brain workspace and show what will live where")

    p_tr = sub.add_parser("train", help="Train the multimodal network (text+image+video+audio) from zero / resume")
    p_tr.add_argument("paths", nargs="+")
    p_tr.add_argument("--size", default="small", choices=["tiny", "small", "base"])
    p_tr.add_argument("--epochs", type=int, default=3)
    p_tr.add_argument("--batch", type=int, default=8)
    p_tr.add_argument("--lr", type=float, default=3e-4)
    p_tr.add_argument("--minutes", type=float, default=0.0, help="stop after this many minutes (0 = no limit)")

    p_desc = sub.add_parser("describe", help="Describe an image, video or audio file with the trained network")
    p_desc.add_argument("media")
    p_gen = sub.add_parser("generate", help="Continue text with the trained network")
    p_gen.add_argument("prompt")
    p_srch = sub.add_parser("search", help="Rank media files by similarity to a text query (cross-modal)")
    p_srch.add_argument("query")
    p_srch.add_argument("media", nargs="+")
    sub.add_parser("models", help="AI models the brain governs and their switchboard beliefs")

    p_ask = sub.add_parser("ask", help="Run any query, workflow, or screen path through the 8 cortical layers")
    p_ask.add_argument("input", type=str)
    p_ask.add_argument("--image", type=str, default="", help="Optional path to UI screenshot, diagram, or photo")

    p_render = sub.add_parser("render", help="Render any input or file into 2D/3D/Hologram HTML")
    p_render.add_argument("target", type=str)
    p_render.add_argument("--out", type=str, default="hojaiga_storage/renders/projection.html")

    p_overnight = sub.add_parser("overnight", help="Run overnight Orthogonal-LoRA consolidation on accumulated memory")
    p_overnight.add_argument("--epochs", type=int, default=3)

    args = parser.parse_args()
    brain = HojaigaExecutiveBrain(BrainSystemConfig(workspace_dir=Path(args.workspace),
                                                    llm=LLMConfig.from_variant(args.variant)))

    if args.cmd == "ingest":
        res = brain.feed_dataset(args.path)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.cmd == "import-hf":
        streamer = DynamicHubDatasetStreamer(brain)
        res = streamer.import_from_huggingface(
            repo_id=args.repo_id, config_name=args.config, split=args.split, max_samples=args.max_samples
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.cmd == "init":
        ws = brain.cfg.workspace_dir
        layout = {
            "checkpoints/": "tokenizer + main LLM weights (after overnight)",
            "omni/": "multimodal network trained from zero (after train)",
            "rag_store/": "hippocampus: every remembered episode",
            "episodic_db/": "learned layer state: failures, graduation, writing edits, replay",
            "ui_topologies/": "vision weights + interfaces the brain recognises",
            "inner_brain/": "the brain inside the brain: its memory and distilled LLM",
            "controller/": "switchboard (model governance), router, audit log",
            "conveyor_reports/": "one report + charts per dataset run",
            "models/": "classifiers the conveyor trained",
            "inbox/": "drop datasets here while `serve` is running",
        }
        for d in layout:
            (ws / d).mkdir(parents=True, exist_ok=True)
        print(json.dumps({"workspace": str(ws.resolve()), "episodes": len(brain.l2.episodes),
                          "vocab": len(brain.tokenizer.token_to_id), "layout": layout,
                          "next": ["brain_cli.py belt <data>", "brain_cli.py train <data>", "brain_cli.py serve"]},
                         indent=2))
    elif args.cmd in ("train", "describe", "generate", "search"):
        from brain.omni.trainer import OmniTrainer
        tr = OmniTrainer(brain, size=getattr(args, "size", "small"))
        if args.cmd == "train":
            print(json.dumps(tr.train(args.paths, epochs=args.epochs, batch=args.batch, lr=args.lr,
                                      max_minutes=args.minutes), indent=2, default=str))
        elif not (brain.cfg.workspace_dir / "omni" / "omni.pt").exists():
            print(json.dumps({"error": "the multimodal network is not trained yet: run `train <data>` first"}))
        elif args.cmd == "describe":
            print(json.dumps({"media": args.media, "description": tr.describe(args.media)}, indent=2))
        elif args.cmd == "generate":
            print(json.dumps({"prompt": args.prompt, "continuation": tr.generate(args.prompt)}, indent=2))
        else:
            print(json.dumps({"query": args.query, "ranked": tr.search(args.query, args.media, top_k=len(args.media))},
                             indent=2))
    elif args.cmd == "models":
        from brain.controller import NaturalIntelligenceController
        ctrl = NaturalIntelligenceController(brain)
        print(json.dumps(ctrl.handle({"skill": "models", "text": "report"})["result"], indent=2, default=str))
    elif args.cmd == "belt":
        from brain.conveyor.belt import ConveyorBelt
        print(json.dumps(ConveyorBelt(brain, train_llm=args.train_llm).run(args.paths), indent=2, default=str))
    elif args.cmd == "classify":
        from brain.conveyor.belt import classify_text
        print(json.dumps(classify_text(brain.cfg.workspace_dir, args.text) or
                         {"error": "no classifier yet: run `belt` on labeled data first"}, indent=2))
    elif args.cmd == "task":
        from brain.controller import NaturalIntelligenceController
        req = {"text": args.text, **({"path": args.path} if args.path else {}), **({"image": args.image} if args.image else {})}
        print(json.dumps(NaturalIntelligenceController(brain).handle(req), indent=2, default=str))
    elif args.cmd == "serve":
        from brain.controller import NaturalIntelligenceController
        ctrl = NaturalIntelligenceController(brain, inbox=Path(args.inbox) if args.inbox else None)
        print(f"Hojaiga controller on http://127.0.0.1:{args.port}  (inbox: {ctrl.inbox})", flush=True)
        ctrl.serve(port=args.port, consolidate_every_s=args.consolidate_minutes * 60)
    elif args.cmd == "ask":
        media = None
        if args.image and Path(args.image).exists():
            from PIL import Image
            import numpy as np

            media = np.array(Image.open(args.image).convert("RGB"))
        res = brain.run_cognitive_cycle(args.input, media_payload=media)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif args.cmd == "render":
        renderer = HojaigaUniversalRenderer()
        p = Path(args.target)
        raw = p.read_text(encoding="utf-8", errors="ignore") if p.is_file() else args.target
        l1_out = brain.l1.process(raw)
        triples = brain.l3.extract_distributional_relations(raw, l1_out["salience_map"])
        out_path = renderer.render_to_html(raw, Path(args.out), triples=triples)
        print(json.dumps({"rendered_html": str(out_path.resolve()), "extracted_edges": len(triples)}, indent=2))
    elif args.cmd == "overnight":
        stats = run_overnight_consolidation(brain, epochs=args.epochs)
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
