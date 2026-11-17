import json, pathlib, re

runs_root = pathlib.Path(r"D:\new_automation\data\ai_root\harvest\training\runs")
pipe_root = pathlib.Path(r"D:\new_automation\data\ai_root\harvest\training")

print("=" * 90)
print(" HOJAIGA TRAINING LEDGER: HOW MUCH HAS BEEN TRAINED TILL NOW")
print("=" * 90)

total_steps_all_runs = 0
for run_dir in sorted(runs_root.iterdir(), key=lambda p: p.stat().st_mtime):
    if not run_dir.is_dir():
        continue
    cps = sorted(
        [p for p in run_dir.glob("checkpoint-*") if (p / "trainer_state.json").exists()],
        key=lambda x: int(re.findall(r"\d+", x.name)[0])
    )
    adapter_ok = (run_dir / "adapter" / "adapter_model.safetensors").exists()
    if not cps and not adapter_ok:
        continue

    latest_step = 0
    max_steps = 0
    last_loss = "N/A"
    if cps:
        st = json.loads((cps[-1] / "trainer_state.json").read_text(encoding="utf-8"))
        latest_step = st.get("global_step", 0)
        max_steps = st.get("max_steps", 0)
        for h in reversed(st.get("log_history", [])):
            if "loss" in h:
                last_loss = f"{h['loss']:.6f}"
                break
    total_steps_all_runs += latest_step
    cp_names = ", ".join(p.name for p in cps[-4:]) if cps else "final adapter only"
    print(f" • Run Folder : {run_dir.name:<32} | Step: {latest_step:>4}/{max_steps:<4} | Last Loss: {last_loss:<10} | Checkpoints: {cp_names}")

print("-" * 90)
print(f" [+] Cumulative QLoRA Steps Trained Across Runs : {total_steps_all_runs} steps")
print(f" [+] Proven 1200-Step 4B Adapter Ready on Disk  : {(pipe_root / 'master_4b_seed100_pipeline/adapter/adapter_model.safetensors').exists()}")
print(f" [+] Current Ultron 4B Checkpoint Ready on Disk : {(runs_root / 'hojaiga_4b_ultron_complete/checkpoint-100/trainer_state.json').exists()}")
print("=" * 90)
