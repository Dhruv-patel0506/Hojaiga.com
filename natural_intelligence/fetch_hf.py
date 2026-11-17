"""Download the NI starter set from Hugging Face into data_user/ and models_hf/ (resumable, logged)."""
import os, sys, time
from huggingface_hub import snapshot_download, HfApi

ROOT = os.path.dirname(os.path.abspath(__file__))
DU = os.path.join(ROOT, "data_user"); MD = os.path.join(ROOT, "models_hf")
LOG = os.path.join(DU, "download_log.txt")
os.makedirs(DU, exist_ok=True); os.makedirs(MD, exist_ok=True)

DATASETS = {
    "text": ["fancyzhx/dbpedia_14", "SetFit/20_newsgroups", "PolyAI/banking77"],
    "image": ["uoft-cs/cifar100", "zh-plus/tiny-imagenet"],
    "audio": ["ashraq/esc50", "marsyas/gtzan"],
    "graph": ["OGB/ogbg-molhiv", "graphs-datasets/IMDB-BINARY", "graphs-datasets/AIDS"],
    "video": ["divm/hmdb51"],            # flwrlabs/ucf101 is 54.5 GB: only on explicit request (--ucf101)
}
MODELS = ["sentence-transformers/all-MiniLM-L6-v2", "facebook/dinov2-small",
          "MIT/ast-finetuned-audioset-10-10-0.4593", "MCG-NJU/videomae-base"]
if "--ucf101" in sys.argv:
    DATASETS["video"].append("flwrlabs/ucf101")
if "--extra-models" in sys.argv:       # stronger encoders for the A/B against the first set (frozen, no fine-tuning)
    DATASETS = {}
    MODELS = ["BAAI/bge-base-en-v1.5", "facebook/dinov2-base", "microsoft/xclip-base-patch32", "facebook/vjepa2-vitl-fpc64-256"]


def log(*a):
    s = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def model_patterns(repo):
    files = [s.rfilename for s in HfApi().model_info(repo).siblings]
    root = [f for f in files if "/" not in f]
    pat = [f for f in root if f.endswith((".json", ".txt", ".model"))]
    weights = [f for f in root if f.endswith(".safetensors")] or [f for f in root if f.endswith(".bin")]
    # sentence-transformers keep their module folders (1_Pooling etc.) as small json
    pat += [f for f in files if "/" in f and f.endswith(".json") and not f.startswith(("onnx", "openvino"))]
    return pat + weights


for cat, L in DATASETS.items():
    for rid in L:
        dst = os.path.join(DU, cat, rid.split("/")[-1])
        t0 = time.time()
        try:
            snapshot_download(rid, repo_type="dataset", local_dir=dst, max_workers=8)
            sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(dst) for f in fs)
            log(f"[ok] dataset {cat}/{rid} -> {dst} {sz / 1e6:.1f} MB {time.time() - t0:.0f}s")
        except Exception as e:
            log(f"[FAIL] dataset {rid}: {repr(e)[:200]}")

for rid in MODELS:
    dst = os.path.join(MD, rid.split("/")[-1])
    t0 = time.time()
    try:
        snapshot_download(rid, repo_type="model", local_dir=dst, allow_patterns=model_patterns(rid), max_workers=8)
        sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(dst) for f in fs)
        log(f"[ok] model {rid} -> {dst} {sz / 1e6:.1f} MB {time.time() - t0:.0f}s")
    except Exception as e:
        log(f"[FAIL] model {rid}: {repr(e)[:200]}")
log("DONE")
