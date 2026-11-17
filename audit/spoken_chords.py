import json, glob, collections, os, sys
sys.path.insert(0, r"D:\new_automation\All codes")
from core_organs.rag.procedures import extract_steps
from core_organs.harvest import video_explain as VE

votes = collections.defaultdict(set)
ex = {}
n = 0
for p in glob.glob(r"D:\new_automation\data\video_graph\_downloads\*\*.transcript.json"):
    vid = os.path.basename(p).split(".")[0]
    segs = json.load(open(p, encoding="utf-8"))["segments"]
    for u in VE.utterances(segs):
        for st in extract_steps(u["text"]):
            if st.get("chord"):
                n += 1
                votes[st["chord"]].add(vid)
                ex.setdefault(st["chord"], u["text"][:120])
print("spoken chord mentions:", n, "| distinct chords:", len(votes))
for ch, v in sorted(votes.items(), key=lambda kv: -len(kv[1]))[:16]:
    print(len(v), ch, "|", ex[ch])
