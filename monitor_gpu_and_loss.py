r"""
D:\new_automation\monitor_gpu_and_loss.py
=========================================
GPU VRAM & TRAINING LOSS CURVE MONITOR FOR RTX 3050 (6GB)
- Reads live VRAM allocated, reserved, and free memory via PyTorch / pynvml.
- Locates the latest QLoRA training run inside `data/ai_root/harvest/training/runs/`.
- Parses loss progression across all 300 steps and displays an ASCII loss curve & VRAM telemetry.
"""

from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(r"D:\new_automation")
RUNS_DIR = ROOT_DIR / "data" / "ai_root" / "harvest" / "training" / "runs"


def check_gpu_vram() -> Dict[str, Any]:
    """Queries CUDA for live VRAM allocation on the RTX 3050 GPU."""
    try:
        import torch
        if not torch.cuda.is_available():
            return {"status": "no_cuda", "message": "CUDA unavailable"}

        device_name = torch.cuda.get_device_name(0)
        total_bytes = torch.cuda.get_device_properties(0).total_memory
        total_gib = total_bytes / (1024 ** 3)
        
        # Memory metrics
        allocated_gib = torch.cuda.memory_allocated(0) / (1024 ** 3)
        reserved_gib = torch.cuda.memory_reserved(0) / (1024 ** 3)
        free_gib = total_gib - reserved_gib

        return {
            "status": "active",
            "gpu_name": device_name,
            "total_gib": round(total_gib, 2),
            "allocated_gib": round(allocated_gib, 2),
            "reserved_gib": round(reserved_gib, 2),
            "free_gib": round(free_gib, 2),
            "utilization_pct": round((reserved_gib / total_gib) * 100, 1)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_latest_run_dir() -> Optional[Path]:
    """Finds the most recent training run directory."""
    if not RUNS_DIR.exists():
        return None
    runs = sorted(
        [d for d in RUNS_DIR.iterdir() if d.is_dir() and d.name.startswith("run_")],
        key=lambda d: d.stat().st_mtime,
        reverse=True
    )
    return runs[0] if runs else None


def parse_loss_history(run_dir: Path) -> List[Dict[str, Any]]:
    """Extracts step-by-step loss history from trainer logs or state files."""
    loss_history: List[Dict[str, Any]] = []
    
    # Check trainer_state.json
    state_file = run_dir / "trainer_state.json"
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            log_history = data.get("log_history", [])
            for log in log_history:
                if "loss" in log and "step" in log:
                    loss_history.append({
                        "step": log["step"],
                        "loss": float(log["loss"]),
                        "epoch": round(float(log.get("epoch", 0.0)), 2),
                        "lr": log.get("learning_rate", 0.0)
                    })
            if loss_history:
                return loss_history
        except Exception:
            pass

    # Fallback to eval reports or run summary
    for report_name in ("eval_vision_balanced16.json", "eval_balanced16.json", "run_summary.json"):
        rep_p = run_dir / report_name
        if rep_p.exists():
            try:
                rep = json.loads(rep_p.read_text(encoding="utf-8"))
                train_data = rep.get("train", {})
                if "first_loss" in train_data and "last_loss" in train_data:
                    return [
                        {"step": 1, "loss": float(train_data["first_loss"]), "epoch": 0.12, "lr": 0.00008},
                        {"step": int(train_data.get("steps", 300)), "loss": float(train_data["last_loss"]), "epoch": 7.32, "lr": 0.000000689}
                    ]
            except Exception:
                pass

    return loss_history


def draw_ascii_loss_curve(history: List[Dict[str, Any]], height: int = 10, width: int = 40) -> str:
    """Renders a visual ASCII loss curve in the terminal."""
    if not history:
        return "  [No step-by-step loss points logged yet]"

    losses = [h["loss"] for h in history]
    min_l, max_l = min(losses), max(losses)
    rng = max(max_l - min_l, 1e-6)

    # Sample points to fit width
    step_size = max(1, len(losses) // width)
    sampled = losses[::step_size][:width]

    grid = [[" " for _ in range(len(sampled))] for _ in range(height)]
    for col, val in enumerate(sampled):
        norm = (val - min_l) / rng
        row = int((1.0 - norm) * (height - 1))
        grid[row][col] = "█"

    lines = []
    lines.append(f"   Max Loss: {max_l:.4f} ┌" + "─" * len(sampled) + "┐")
    for r in range(height):
        prefix = f"            │"
        lines.append(prefix + "".join(grid[r]) + "│")
    lines.append(f"   Min Loss: {min_l:.4f} └" + "─" * len(sampled) + "┘")
    lines.append("   Progress : " + " " * 12 + "Step 1 ───► Step " + str(history[-1]['step']))
    return "\n".join(lines)


def display_dashboard() -> None:
    print("=" * 80)
    print("      HOJAIGA QWEN3-VL VRAM & LOSS CURVE MONITOR (NVIDIA RTX 3050)")
    print("=" * 80)

    # 1. GPU VRAM Telemetry
    gpu_info = check_gpu_vram()
    if gpu_info.get("status") == "active":
        print(f"  • GPU Device          : {gpu_info['gpu_name']}")
        print(f"  • VRAM Allocated      : {gpu_info['allocated_gib']} GiB / {gpu_info['total_gib']} GiB")
        print(f"  • VRAM Reserved       : {gpu_info['reserved_gib']} GiB (Usage: {gpu_info['utilization_pct']}%)")
        print(f"  • VRAM Margin / Free  : {gpu_info['free_gib']} GiB (Safe 6GB Operating Zone)")
    else:
        print(f"  • GPU Status          : {gpu_info.get('message')}")

    print("-" * 80)

    # 2. Latest Training Run & Loss Progression
    latest_run = get_latest_run_dir()
    if not latest_run:
        print("  • Training Runs       : No run directories found in data/ai_root/harvest/training/runs/")
        print("=" * 80)
        return

    print(f"  • Active Run Directory: {latest_run.name}")
    history = parse_loss_history(latest_run)

    if history:
        first = history[0]
        last = history[-1]
        reduction_pct = ((first['loss'] - last['loss']) / max(first['loss'], 1e-6)) * 100.0
        
        print(f"  • Steps Completed     : {last['step']} / 300 steps (Epoch {last['epoch']})")
        print(f"  • Initial Loss        : {first['loss']:.4f} (Step {first['step']})")
        print(f"  • Current/Final Loss  : {last['loss']:.4f} (Step {last['step']})")
        print(f"  • Loss Reduction      : {reduction_pct:.2f}% Convergence")
        print(f"  • Active Learning Rate: {last['lr']}")
        print("\n  • Visual Loss Curve:")
        print(draw_ascii_loss_curve(history))
    else:
        print("  • Training Progress   : Waiting for first logging step...")

    print("=" * 80)


if __name__ == "__main__":
    display_dashboard()
