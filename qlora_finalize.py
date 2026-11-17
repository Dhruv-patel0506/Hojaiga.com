"""
qlora_finalize -- run ONCE after qlora_train.py finishes (does NOT touch the training PID).
Reads the real loss history from the checkpoint's trainer_state.json, verifies the saved LoRA
adapter files are non-empty, records brain/qlora_status.json, and regenerates fig9/metrics so
QLoRA (b) shows COMPLETE with the true final loss. Safe to run early: if the adapter isn't
written yet it reports status=RUNNING and does nothing harmful.
"""
import json
import glob
import os
import subprocess
from pathlib import Path

OUT = Path("brain/qlora_adapter")


def _latest_state():
    cands = sorted(glob.glob(str(OUT / "checkpoint-*" / "trainer_state.json")),
                   key=lambda p: int(p.split("checkpoint-")[1].split(os.sep)[0]))
    return cands[-1] if cands else None


def main():
    status = {"status": "PENDING", "steps": None, "final_loss": None,
              "first_loss": None, "adapter_bytes": 0}
    st = _latest_state()
    losses = []
    if st:
        try:
            hist = json.loads(Path(st).read_text(encoding="utf-8")).get("log_history", [])
            losses = [h["loss"] for h in hist if "loss" in h]
        except Exception:
            losses = []
    if losses:
        status["first_loss"] = round(float(losses[0]), 4)
        status["final_loss"] = round(float(losses[-1]), 4)
        status["steps"] = len(losses)
    am = OUT / "adapter_model.safetensors"
    ac = OUT / "adapter_config.json"
    if am.exists() and ac.exists() and am.stat().st_size > 0:
        status["adapter_bytes"] = am.stat().st_size
        status["status"] = "COMPLETE" if losses else "COMPLETE (loss log unavailable)"
    else:
        status["status"] = "RUNNING" if not losses else "SAVING"

    Path("brain/qlora_status.json").write_text(json.dumps(status, indent=3), encoding="utf-8")
    print("[finalize]", json.dumps(status))
    if status["status"].startswith("COMPLETE"):
        subprocess.run(["C:\\Users\\dhruv\\AppData\\Local\\Programs\\Python\\Python313\\python.exe", "dashboard.py"])
        print("[finalize] fig9/metrics regenerated with QLoRA (b) COMPLETE")
    else:
        print("[finalize] adapter not ready yet -- re-run this once training finishes.")


if __name__ == "__main__":
    main()
