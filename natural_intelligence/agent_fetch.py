import os, time
from huggingface_hub import snapshot_download
DU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_user", "agent")
for rid in ["nebius/SWE-agent-trajectories", "nebius/SWE-rebench-openhands-trajectories"]:
    try:
        print(time.strftime("%H:%M:%S"), "download", rid, flush=True)
        snapshot_download(rid, repo_type="dataset", local_dir=os.path.join(DU, rid.split("/")[-1]), max_workers=8,
                          allow_patterns=["*.parquet", "*.json", "*.jsonl", "README.md"])
        print(time.strftime("%H:%M:%S"), "done", rid, flush=True)
    except Exception as e: print("FAILED", rid, repr(e)[:200], flush=True)
print("AGENT_FETCH_DONE", flush=True)
