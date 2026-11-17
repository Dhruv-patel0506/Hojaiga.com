"""Proof sheets for a shortcut_verify run: per verdict, before | control (no key) | after for the attempt that decided it, plus an evidence table for the effects a picture cannot show."""
import sys, os, json
import numpy as np, cv2

run = sys.argv[1]
r = json.load(open(os.path.join(run, "results.json"), encoding="utf-8"))
TW, TH = 300, 188


def tile(path, label, box=None):
    im = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    im = cv2.resize(im, (TW, TH))
    cv2.rectangle(im, (0, 0), (TW, 14), (0, 0, 0), -1)
    cv2.putText(im, label[:52], (3, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1)
    return im


def deciding(x):
    eff = [a for a in x["attempts"] if a.get("effect")]
    for a in eff:
        if a.get("name_check") is True:
            return a
    return eff[0] if eff else x["attempts"][-1]


rows_v, rows_e, table = [], [], []
for x in r["results"]:
    a = deciding(x)
    f = a["files"]
    row = np.hstack([tile(os.path.join(run, f["before"]), f"{x['action'][:16]} {x['chord']} BEFORE"), tile(os.path.join(run, f["control_after"]), "CONTROL (no key)"),
                     tile(os.path.join(run, f["after"]), f"AFTER {x['verdict']} @{x['rung'][:2] if x['rung'] else ''}")])
    (rows_v if x["verdict"] == "VERIFIED" else rows_e).append((x["action"], row))
    sd = a.get("scene_diff", {})
    ev = []
    if a["pixel"]["frac"] >= 0.0015:
        ev.append(f"pixels {a['pixel']['frac'] * 100:.2f}%")
    if a["dom"]["removed"] + a["dom"]["added"]:
        ev.append(f"aria -{a['dom']['removed']}/+{a['dom']['added']}")
    for k, v in sd.items():
        ev.append(f"scene.{k}" + (f"={v}" if k in ("count", "deleted", "locked", "state") else ""))
    c = a.get("clipboard_after", {})
    if c.get("any"):
        ev.append(f"clipboard {c.get('types')} text_len={c.get('text_len')}")
    table.append((x["action"], x["chord"], x.get("variant_of") and f"(video said {x['variant_of']})" or "", x["verdict"], x["rung"] or "", a.get("name_check"), "; ".join(ev)[:230]))


def save(rows, name):
    for i in range(0, len(rows), 4):
        chunk = rows[i:i + 4]
        img = np.vstack([c[1] for c in chunk])
        out = os.path.join(run, f"{name}_{i // 4 + 1}.png")
        cv2.imencode(".png", img)[1].tofile(out)
        print("wrote", out, [c[0] for c in chunk])


save(rows_v, "proof_verified")
save(rows_e, "proof_effect_only")
print()
for t in table:
    print(" | ".join(str(x) for x in t))
