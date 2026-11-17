"""Dataset hub: add a Hugging Face dataset to NI with one line.

    python ni_hub.py fetch --wave 1            # download + auto-detect columns + register (resumable)
    python ni_hub.py add <hf_id> <modality> [--label-col L] [--text-cols a,b] [--include 'split/*'] [--limit N]
    python ni_hub.py list

A registered dataset becomes the encode task "<modality>/<name>" (see ni_encode.py, which reads hub_registry.json);
from there the scheduler (ni_sched.py) trains it automatically. Nothing is hard-coded per dataset: columns are
detected from the parquet/jsonl schema and recorded in the registry, so a wrong guess is visible and editable.
"""
import os, sys, json, glob, time, argparse
from ni_common import ROOT, log, set_logfile

DU = os.path.join(ROOT, "data_user")
REG = os.path.join(DU, "hub_registry.json")
LABELS = ["label", "labels", "target", "category", "class", "intent", "topic", "fine_label", "genre", "emotion", "y", "label_text"]
TEXTS = ["text", "sentence", "content", "document", "utterance", "question_title", "question_content", "review", "article", "title", "sms", "message", "description"]
SKIP_WORDS = ("unsplit", "unsupervised", ".cache")

# verified to exist, ungated, with a viewer (Hugging Face API check, Nov 2026). wave 1 = small/medium, wave 2 = large.
CATALOG = [
    # text
    dict(id="SetFit/enron_spam", modality="text", wave=1), dict(id="stanfordnlp/imdb", modality="text", wave=1),
    dict(id="cornell-movie-review-data/rotten_tomatoes", modality="text", wave=1), dict(id="SetFit/sst2", modality="text", wave=1),
    dict(id="SetFit/bbc-news", modality="text", wave=1), dict(id="ucirvine/sms_spam", modality="text", wave=1),
    dict(id="community-datasets/yahoo_answers_topics", modality="text", wave=1, limit=120000),
    dict(id="fancyzhx/yelp_polarity", modality="text", wave=1, limit=100000),
    dict(id="fancyzhx/amazon_polarity", modality="text", wave=2, limit=120000),
    dict(id="dair-ai/emotion", modality="text", wave=1, include=["split/*"]),
    # image (incl. UI-like / road-sign / satellite)
    dict(id="tanganke/gtsrb", modality="image", wave=1), dict(id="tanganke/resisc45", modality="image", wave=1),
    dict(id="tanganke/kmnist", modality="image", wave=1), dict(id="tanganke/emnist_letters", modality="image", wave=1),
    dict(id="jxie/dtd", modality="image", wave=1), dict(id="AI-Lab-Makerere/beans", modality="image", wave=1),
    dict(id="microsoft/cats_vs_dogs", modality="image", wave=1), dict(id="timm/oxford-iiit-pet", modality="image", wave=1),
    dict(id="ethz/food101", modality="image", wave=2, limit=60000), dict(id="clane9/imagenet-100", modality="image", wave=2, limit=60000),
    # audio
    dict(id="confit/cremad-parquet", modality="audio", wave=1), dict(id="xbgoose/ravdess", modality="audio", wave=1),
    dict(id="lewtun/music_genres_small", modality="audio", wave=1),
    dict(id="ccmusic-database/music_genre", modality="audio", wave=2, limit=8000),
    dict(id="renumics/speech_commands_enriched", modality="audio", wave=2, limit=8000),
    # graph
    dict(id="graphs-datasets/reddit_threads", modality="graph", wave=1), dict(id="graphs-datasets/twitch_egos", modality="graph", wave=1),
    dict(id="graphs-datasets/deezer_ego_nets", modality="graph", wave=1), dict(id="graphs-datasets/CSL", modality="graph", wave=1),
    dict(id="OGB/ogbg-ppa", modality="graph", wave=2),
]


def load_registry():
    try:
        with open(REG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_registry(r):
    os.makedirs(DU, exist_ok=True)
    tmp = REG + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=1)
    os.replace(tmp, REG)


def _files(root):
    out = []
    for ext in ("parquet", "jsonl", "json", "csv"):
        out += glob.glob(os.path.join(root, "**", f"*.{ext}"), recursive=True)
    out = [p for p in out if not any(w in p for w in SKIP_WORDS) and not p.endswith(("dataset_infos.json", "state.json", "dataset_dict.json"))]
    pq = [p for p in out if p.endswith(".parquet")]
    return sorted(pq or out)


def autodetect(modality, root):
    """Inspect the first data file; returns a spec dict (and notes) without assuming any dataset-specific name."""
    files = _files(root)
    if not files:
        return None, ["no data files found"]
    f0 = files[0]; notes = []
    if f0.endswith(".parquet"):
        import pyarrow.parquet as pq
        sch = pq.ParquetFile(f0).schema_arrow
        cols = {n: str(sch.field(n).type) for n in sch.names}
    else:
        first = None
        for f0 in files:                       # first file whose first non-empty line is a JSON object (skips metadata json)
            try:
                with open(f0, encoding="utf-8") as fh:
                    for line in fh:
                        if line.strip():
                            first = json.loads(line); break
                if isinstance(first, dict):
                    break
            except Exception:
                first = None
        if not isinstance(first, dict):
            return None, ["no readable jsonl rows"]
        cols = {k: type(v).__name__ for k, v in first.items()}
    spec = dict(modality=modality, files=[os.path.relpath(p, DU) for p in files])
    lab = next((c for c in LABELS if c in cols and any(t in cols[c] for t in ("int", "str", "bool", "large_string"))), None)
    if modality == "text":
        tc = [c for c in TEXTS if c in cols and "str" in cols[c]]
        # prefer a title+body pair when both exist, otherwise the single best text column
        pairs = [("title", "content"), ("question_title", "question_content")]
        pick = next((list(p) for p in pairs if p[0] in tc and p[1] in tc), tc[:1])
        spec["text_cols"] = pick
        if not pick:
            notes.append("no text column recognised: " + str(cols))
    elif modality in ("image", "audio"):
        cands = ["image", "img", "im", "pixel_values"] if modality == "image" else ["audio", "sound", "wav"]
        col = next((c for c in cands if c in cols and "bytes" in cols[c]), None) or next((c for c, t in cols.items() if "bytes" in t), None)
        spec[modality + "_col"] = col
        if not col:
            notes.append(f"no {modality} bytes column: {cols}")
    elif modality == "graph":
        lab = lab or ("y" if "y" in cols else None)
        if "edge_index" not in cols:
            notes.append("no edge_index column")
    spec["label_col"] = lab
    if not lab:
        notes.append("no label column recognised: " + str(cols))
    spec["columns"] = cols
    spec["ok"] = not notes
    return spec, notes


def fetch(entry):
    from huggingface_hub import snapshot_download
    rid = entry["id"]; name = rid.split("/")[-1].replace("-", "_").lower(); mod = entry["modality"]
    dst = os.path.join(DU, mod, rid.split("/")[-1])
    allow = (entry.get("include") or ["*"])
    allow = [a if "/" in a or a == "*" else a for a in allow]
    allow = [p for a in allow for p in ((a + ".parquet", a + ".jsonl", a + ".json", a + ".csv") if a != "*" else ("*.parquet", "*.jsonl", "*.json", "*.csv", "README.md"))]
    t0 = time.time()
    snapshot_download(rid, repo_type="dataset", local_dir=dst, allow_patterns=allow, max_workers=8)
    mb = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(dst) for f in fs if ".cache" not in r) / 1e6
    spec, notes = autodetect(mod, dst)
    reg = load_registry()
    if spec is None:
        log(f"[hub] {rid}: downloaded {mb:.0f} MB but nothing usable: {notes}"); return
    spec.update(id=rid, limit=entry.get("limit"), size_mb=round(mb), notes=notes)
    reg[f"{mod}/{name}"] = spec; save_registry(reg)
    log(f"[hub] {rid} -> {mod}/{name}: {mb:.0f} MB in {time.time() - t0:.0f}s, label={spec['label_col']}, "
        f"{'text=' + str(spec.get('text_cols')) if mod == 'text' else ''} ok={spec['ok']} {'NOTES: ' + str(notes) if notes else ''}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "add", "list"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--wave", type=int, default=1)
    ap.add_argument("--include", default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    os.makedirs(DU, exist_ok=True); set_logfile(os.path.join(DU, "hub_log.txt"))
    if a.cmd == "list":
        for k, v in load_registry().items():
            print(f"{k:42} {v.get('size_mb', '?'):>6} MB label={v.get('label_col')} ok={v.get('ok')}")
    elif a.cmd == "add":
        fetch(dict(id=a.args[0], modality=a.args[1], include=(a.include.split(",") if a.include else None), limit=a.limit))
    else:
        done = set(load_registry())
        for e in [e for e in CATALOG if e["wave"] <= a.wave]:
            nm = f"{e['modality']}/{e['id'].split('/')[-1].replace('-', '_').lower()}"
            if nm in done:
                continue
            try:
                fetch(e)
            except Exception as ex:
                log(f"[hub] {e['id']} FAILED: {repr(ex)[:200]}")
        log("[hub] wave done")
