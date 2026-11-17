import os, zipfile, tarfile, time
from huggingface_hub import snapshot_download
DU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_user", "video")
def log(m): print(time.strftime("%H:%M:%S"), m, flush=True)
for rid, name in [("nateraw/kinetics-mini", "kinetics_mini"), ("sayakpaul/ucf101-subset", "ucf101_subset"), ("quchenyuan/UCF101-ZIP", "ucf101")]:
    dst = os.path.join(DU, name)
    try:
        log(f"download {rid}"); snapshot_download(rid, repo_type="dataset", local_dir=dst, max_workers=8); log(f"done {rid}")
        for r, _, fs in os.walk(dst):
            if ".cache" in r: continue
            for f in fs:
                p = os.path.join(r, f)
                if f.endswith(".zip") and "Splits" not in f and not os.path.exists(p + ".extracted"):
                    log(f"extract {p}"); zipfile.ZipFile(p).extractall(os.path.join(dst, "x")); open(p + ".extracted", "w").close()
                elif f.endswith(".tar.gz") and not os.path.exists(p + ".extracted"):
                    log(f"extract {p}"); tarfile.open(p).extractall(os.path.join(dst, "x")); open(p + ".extracted", "w").close()
                elif f.endswith(".zip") and "Splits" in f and not os.path.exists(p + ".extracted"):
                    zipfile.ZipFile(p).extractall(os.path.join(dst, "splits")); open(p + ".extracted", "w").close()
    except Exception as e:
        log(f"FAILED {rid}: {repr(e)[:200]}")
log("VIDEO_FETCH_DONE")
