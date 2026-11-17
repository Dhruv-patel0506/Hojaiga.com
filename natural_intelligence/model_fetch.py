import os, time
from huggingface_hub import snapshot_download
MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models_hf")
for rid, nm in [("openai/whisper-base", "whisper-base"), ("laion/clap-htsat-unfused", "clap-htsat-unfused")]:
    try:
        print(time.strftime("%H:%M:%S"), "get", rid, flush=True)
        snapshot_download(rid, local_dir=os.path.join(MD, nm), allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"] , max_workers=4)
        print("done", rid, flush=True)
    except Exception as e: print("FAILED", rid, repr(e)[:200], flush=True)
print("MODEL_FETCH_DONE", flush=True)
