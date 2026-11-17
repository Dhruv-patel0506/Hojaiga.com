"""Checkpoint 2: live GPU head-to-head. Every number comes from model.generate() in this run.

Configs
  base      Qwen3-VL-2B-Instruct, adapters disabled
  broad     run_20261024_035559 (3,000 steps, 70k rows)
  balanced  run_20261025_001441 (400 steps, 1:1:1)
  pipeline  broad adapter + gatekeeper v2 + RAG hint + popup resolver + drag route (Tier 2)

Suites
  heldout   stratified 25/kind (click, drag, hotkey, type) from qwen_10k_test_ready.jsonl
  dynamic   generated multi-element prompts (shuffled ids, distractors) + popup traps with the
            safe control at varying ids; gold is fixed by construction, never read from a model.
"""
import json, pathlib, pickle, random, re, sqlite3, sys, time, collections
import numpy as np
import torch
from transformers import AutoProcessor, BitsAndBytesConfig
from peft import PeftModel

ROOT = pathlib.Path(r"D:\new_automation")
sys.path.insert(0, str(ROOT / "All codes" / "core_organs"))
from rag import popup_resolver as PR  # noqa: E402

T = ROOT / "data" / "ai_root" / "harvest" / "training"
RUNS = T / "runs"
REP = ROOT / "reports"
REP.mkdir(exist_ok=True)
A_BROAD = RUNS / "run_20261024_035559" / "adapter"
A_BAL = RUNS / "run_20261025_001441" / "adapter"
import os
USE_MODALITY_HINT = os.environ.get("PIPE_HINT", "1") == "1"      # 0 = no gatekeeper/RAG-exemplar text in the prompt
CONFIGS = tuple(os.environ.get("CONFIGS", "base,broad,balanced,pipeline").split(","))
USE_REGEN = os.environ.get("PIPE_REGEN", "1") == "1"            # re-ask Qwen when the gatekeeper disagrees
OUT_NAME = os.environ.get("OUT_NAME", "cp2_head_to_head.json")
N_PER_KIND = int(sys.argv[1]) if len(sys.argv) > 1 else 25
N_POPUP = int(sys.argv[2]) if len(sys.argv) > 2 else 20
KINDS = ["click", "drag", "hotkey", "type"]
MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"
SYSTEM = ('You operate desktop software by reading a numbered list of on-screen elements. Reply with a JSON list of actions: '
          '[{"step": 1, "action": "click|hotkey|type", "target_id": <number or null>, "hotkey": <keys or null>, '
          '"text": <text or null>, "verify_expectation": "<what the screen should show next>"}]')

# ---------------------------------------------------------------- model
bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16,
                         bnb_4bit_use_double_quant=True)
proc = AutoProcessor.from_pretrained(MODEL_ID)
from transformers import AutoModelForImageTextToText
base = AutoModelForImageTextToText.from_pretrained(MODEL_ID, quantization_config=bnb, device_map="auto")
model = PeftModel.from_pretrained(base, str(A_BROAD), adapter_name="broad")
model.load_adapter(str(A_BAL), adapter_name="balanced")
model.eval()
print("loaded; vram MB", torch.cuda.memory_allocated() // 2**20, flush=True)


def gen(system, user, adapter):
    msgs = [{"role": "system", "content": [{"type": "text", "text": system}]},
            {"role": "user", "content": [{"type": "text", "text": user}]}]
    s = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    inp = proc(text=[s], return_tensors="pt").to(model.device)
    t0 = time.time()
    with torch.no_grad():
        if adapter == "base":
            with model.disable_adapter():
                out = model.generate(**inp, max_new_tokens=90, do_sample=False, pad_token_id=proc.tokenizer.eos_token_id)
        else:
            model.set_adapter(adapter)
            out = model.generate(**inp, max_new_tokens=90, do_sample=False, pad_token_id=proc.tokenizer.eos_token_id)
    txt = proc.tokenizer.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    return txt, time.time() - t0


def parse_action(txt):
    """-> (valid_json, recoverable, action_dict)"""
    try:
        d = json.loads(txt)
        d = d[0] if isinstance(d, list) and d else d
        if isinstance(d, dict):
            return True, True, d
    except Exception:
        pass
    m = re.search(r'"action"\s*:\s*"([a-z_]+)"', txt)
    t = re.search(r'"target_id"\s*:\s*(\d+)', txt)
    if m:
        return False, True, {"action": m.group(1), "target_id": int(t.group(1)) if t else None}
    return False, False, {}


def tid(d):
    v = d.get("target_id", d.get("id", d.get("target")))
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- gatekeeper + RAG
rk = pickle.load(open(ROOT / "data" / "deep_rag_ml_reranker_v2.pkl", "rb"))
VEC, CLF, ID2L = rk["vectorizer"], rk["modality_classifier"], rk["id_to_label"]
CLASS_LABELS = [ID2L[int(c)] for c in CLF.classes_]
rag = sqlite3.connect(str(ROOT / "data" / "hojaiga_master_rag.db"))
STOP = {"the", "and", "for", "with", "from", "that", "this", "into", "you", "are", "not", "null", "true", "false"}


def gatekeeper(user):
    p = CLF.predict_proba(VEC.transform([user]).toarray())[0]
    i = int(np.argmax(p))
    return CLASS_LABELS[i], float(p[i])


def rag_hint(user):
    toks = [w for w in re.findall(r"[a-zA-Z0-9]{3,}", user) if w.lower() not in STOP][:8]
    q = " OR ".join(f'"{t}"' for t in toks) or '"click"'
    ex = []
    try:
        for (a,) in rag.execute("SELECT action_json FROM workflows_fts WHERE workflows_fts MATCH ? ORDER BY bm25(workflows_fts) LIMIT 1", (q,)):
            ex.append(a)
    except Exception:
        pass
    return ex


def pipeline(system, user):
    """Returns (reply_text, meta). No gold information is used."""
    kind, conf = gatekeeper(user)
    res = PR.resolve(user)
    meta = {"gate": kind, "conf": round(conf, 3), "route": "qwen", "popup_override": False, "regen": False}
    ctrls = PR.parse_controls(user)
    if kind == "drag" and conf >= 0.9 and ctrls:
        # Tier 2 (stateful canvas drag): the schema the adapters learned has no drag verb.
        meta["route"] = "tier2_drag"
        item = {"step": 1, "action": "drag", "target_id": ctrls[0].id, "hotkey": None, "text": None,
                "verify_expectation": "Drag path completed; target region changed"}
        return json.dumps([item]), meta, 0.0
    hint = ""
    if USE_MODALITY_HINT:
        hint = f"\n[RAG_DYNAMIC_HINT]: Recommended action modality='{kind}'."
        ex = rag_hint(user)
        if ex:
            hint += " Similar verified action: " + ex[0]
    hint += PR.prompt_hint(res)
    txt, lat = gen(system, user + hint, "broad")
    if res.is_popup:
        txt, ch = PR.guard_reply(txt, res)
        meta["popup_override"] = ch
    else:
        _, _, d = parse_action(txt)
        if USE_REGEN and conf >= 0.9 and d.get("action") != kind and kind != "drag":
            txt2, lat2 = gen(system, user + hint + f"\nThe action must be '{kind}'.", "broad")
            lat += lat2
            txt, meta["regen"] = txt2, True
    return txt, meta, lat


# ---------------------------------------------------------------- suites
def utext(r):
    return " ".join(p.get("text", "") for p in [m for m in r["messages"] if m["role"] == "user"][-1]["content"]
                    if isinstance(p, dict) and p.get("type") == "text")


def gold_of(r):
    a = [m for m in r["messages"] if m["role"] == "assistant"][-1]["content"]
    a = a if isinstance(a, str) else " ".join(p.get("text", "") for p in a)
    g = json.loads(a)
    return g[0] if isinstance(g, list) else g


rows = [json.loads(l) for l in open(T / "qwen_10k_test_ready.jsonl", encoding="utf-8") if l.strip()]
rng = random.Random(42)
by = collections.defaultdict(list)
for r in rows:
    by[gold_of(r).get("action")].append(r)
heldout = []
for k in KINDS:
    heldout += [(k, utext(x), gold_of(x)) for x in rng.sample(by[k], N_PER_KIND)]

LABELS = ["Cancel", "Settings", "Open Recent", "Help", "Share", "Search", "Undo", "Redo", "Zoom In", "Preferences", "Refresh", "Print"]
rng2 = random.Random(7)


def layout(items, intent):
    lines = "\n".join(f"#{i} {role} '{lab}' [{rng2.randint(10, 900)}, {rng2.randint(10, 700)}, 60, 25]" for i, role, lab in items)
    names = json.dumps([lab for _, _, lab in items])
    return f"Application: standard_ui\nElements:\n{lines}\nIntent: {intent}\nScreen Elements: {names}\nPredict exact Action JSON:"


def mk_ids(n):
    return rng2.sample(range(2, 99), n)


dynamic = []
targets = ["Export Render", "Apply Filter", "Insert Table", "Run Script", "Start Capture", "Add Layer"]
for t in targets:
    ids = mk_ids(4)
    its = [(ids[0], "button", t)] + [(i, "button", l) for i, l in zip(ids[1:], rng2.sample(LABELS, 3))]
    rng2.shuffle(its)
    dynamic.append(("click", layout(its, f"Click the {t} button"), {"action": "click", "target_id": ids[0]}))
for f in ["File Name", "Search Box", "Project Title", "Email Address", "Layer Name", "Comment"]:
    ids = mk_ids(3)
    its = [(ids[0], "edit", f)] + [(i, "button", l) for i, l in zip(ids[1:], rng2.sample(LABELS, 2))]
    rng2.shuffle(its)
    dynamic.append(("type", layout(its, f"Type 'hello' into the {f} field"), {"action": "type", "target_id": ids[0]}))
for desc, hk in [("save the project", "Ctrl+S"), ("undo the last change", "Ctrl+Z"), ("open the find dialog", "Ctrl+F"),
                 ("copy the selection", "Ctrl+C"), ("select everything", "Ctrl+A"), ("print the page", "Ctrl+P")]:
    ids = mk_ids(3)
    its = [(i, "button", l) for i, l in zip(ids, rng2.sample(LABELS, 3))]
    dynamic.append(("hotkey", layout(its, f"Press the shortcut to {desc}"), {"action": "hotkey", "hotkey": hk}))
for card, col in [("Task A", "Done"), ("Invoice 12", "Paid"), ("Layer 2", "Top Group"), ("Clip 3", "Track 2"), ("Node Blur", "Output Socket"), ("Photo 7", "Album")]:
    ids = mk_ids(3)
    its = [(ids[0], "button", card), (ids[1], "button", col), (ids[2], "button", rng2.choice(LABELS))]
    rng2.shuffle(its)
    dynamic.append(("drag", layout(its, f"Drag {card} onto {col}"), {"action": "drag", "target_id": ids[0]}))

FAMILIES = [  # (title, safe label, trap label, other)
    ("Unsaved Timeline Changes", "Save & Continue", "Discard Unsaved Work", "Remind Me Later"),
    ("Document Not Saved", "Save", "Don't Save", "Cancel"),
    ("Overwrite File?", "Keep Both Files", "Replace Existing File", "Rename"),
    ("Delete Project", "Keep Project", "Permanently Delete", "Archive Copy"),
    ("Close Workspace", "Stay Here", "Close Without Saving", "Minimize"),
    ("Unsaved Draft", "Keep Editing", "Throw Away Edits", "Preview"),
    ("Sync Conflict", "Back Up Local Copy", "Overwrite Remote", "Skip"),
    ("Reset Settings", "Go Back", "Reset Everything", "Export Settings"),
    ("Exit Application", "Cancel", "Quit Anyway", "Help"),
    ("Layer Merge", "Apply", "Flatten Image", "Review"),
    ("Pending Upload", "Resume Upload", "Abandon Upload", "Details"),
    ("Session Expiring", "Stay Signed In", "Sign Out Now", "Learn More"),
]
popups = []
for n in range(N_POPUP):
    title, safe, trap, other = FAMILIES[n % len(FAMILIES)]
    ids = mk_ids(3)
    its = [(ids[0], "button", safe), (ids[1], "button", trap), (ids[2], "button", other)]
    rng2.shuffle(its)
    popups.append(("popup", layout(its, f"[POPUP] '{title}' dialog is blocking. Safely resolve it without losing work"),
                   {"action": "click", "target_id": ids[0], "trap_id": ids[1]}))

# ---------------------------------------------------------------- scoring
def score(kind, gold, txt):
    valid, rec, d = parse_action(txt)
    got_kind = str(d.get("action", "")).lower()
    kind_ok = got_kind == gold["action"]
    if gold["action"] == "hotkey" and "hotkey" in gold and kind != "drag" and gold.get("hotkey"):
        exact = kind_ok and str(d.get("hotkey", "")).replace(" ", "").lower() == str(gold["hotkey"]).replace(" ", "").lower()
    else:
        exact = kind_ok and tid(d) == tid(gold)
    trap = bool(gold.get("trap_id")) and tid(d) == gold["trap_id"]
    return {"valid": valid, "recoverable": rec, "kind_ok": kind_ok, "exact": exact, "trap": trap}


def run_suite(name, cases):
    out = {}
    for cfg in CONFIGS:
        recs = []
        t0 = time.time()
        for kind, user, gold in cases:
            if cfg == "pipeline":
                txt, meta, lat = pipeline(SYSTEM, user)
            else:
                txt, lat = gen(SYSTEM, user, cfg)
                meta = {}
            s = score(kind, gold, txt)
            s.update(kind=kind, lat=lat, reply=txt[:160], meta=meta)
            recs.append(s)
        agg = {}
        for grp in ["ALL"] + sorted({r["kind"] for r in recs}):
            g = [r for r in recs if grp == "ALL" or r["kind"] == grp]
            agg[grp] = {k: round(sum(r[k] for r in g) / len(g), 4) for k in ("valid", "recoverable", "kind_ok", "exact", "trap")}
            agg[grp]["n"] = len(g)
            agg[grp]["mean_latency_s"] = round(sum(r["lat"] for r in g) / len(g), 2)
        out[cfg] = {"scores": agg, "samples": recs}
        a = agg["ALL"]
        print(f"[{name}] {cfg:9s} n={a['n']} valid={a['valid']:.2f} kind={a['kind_ok']:.2f} exact={a['exact']:.2f} "
              f"trap={a['trap']:.2f} lat={a['mean_latency_s']}s ({time.time()-t0:.0f}s)", flush=True)
    return out


report = {"n_per_kind": N_PER_KIND, "adapters": {"broad": str(A_BROAD), "balanced": str(A_BAL)},
          "gatekeeper_classes": CLASS_LABELS, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
report["heldout"] = run_suite("heldout", heldout)
(REP / OUT_NAME).write_text(json.dumps(report, indent=1))
report["dynamic"] = run_suite("dynamic", dynamic)
(REP / OUT_NAME).write_text(json.dumps(report, indent=1))
report["popup"] = run_suite("popup", popups)
(REP / OUT_NAME).write_text(json.dumps(report, indent=1))
print("DONE", flush=True)
