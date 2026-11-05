# brain_cli.py
import argparse
import json
from pathlib import Path
from typing import Dict

import numpy as np

from brain.config import BrainSystemConfig, LLMConfig
from brain.curiosity_and_langchain import HojaigaExecutiveBrain
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
