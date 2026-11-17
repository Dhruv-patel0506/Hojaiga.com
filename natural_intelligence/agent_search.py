from huggingface_hub import HfApi
api=HfApi(); seen=set()
for q in ["SWE-agent-trajectories","nebius swe","agent trajectories","openhands","webarena","osworld","tau-bench","toolbench"]:
    try:
        for d in api.list_datasets(search=q, sort="downloads", limit=6):
            if d.id in seen: continue
            seen.add(d.id)
            try:
                info=api.dataset_info(d.id, files_metadata=True); sz=sum((s.size or 0) for s in info.siblings)/1e9
                print(f"[{q}] {d.id:58} {sz:7.2f} GB gated={info.gated} dl={d.downloads}", flush=True)
            except Exception: pass
    except Exception as e: print("ERR", q, repr(e)[:80], flush=True)
