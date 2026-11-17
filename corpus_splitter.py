"""
corpus_splitter -- deterministic, stratified 70/30 TRAIN/TEST split over a tiered web-app
corpus so every complexity tier is represented in BOTH splits (a random split can drop a whole
tier from TEST). Emits brain/web_corpus_split.json (train/test id lists + per-tier counts) that
Stage-1 scan + Stage-3 execution consume to generate clean episodic trajectories for TRAIN,
while TEST stays held out for honest generalization scoring.
"""
import json
import hashlib
from pathlib import Path

OUT = Path("brain/web_corpus_split.json")

# tiered corpus: (id, tier, kind) -- mix of reachable public pages + local deterministic apps
CORPUS = [
    # Tier 1: atomic controls
    ("t1_checkboxes", 1, "the-internet/checkboxes"), ("t1_dropdown", 1, "the-internet/dropdown"),
    ("t1_inputs", 1, "the-internet/inputs"), ("t1_addrm", 1, "the-internet/add_remove_elements"),
    ("t1_login", 1, "the-internet/login"), ("t1_register", 1, "local:register_form"),
    ("t1_radio", 1, "local:radio_group"),
    # Tier 2: dynamic state
    ("t2_tabs", 2, "w3c/aria-tabs"), ("t2_accordion", 2, "w3c/aria-accordion"),
    ("t2_todo", 2, "todomvc/react"), ("t2_searchfilter", 2, "local:search_filter"),
    ("t2_keypress", 2, "the-internet/key_presses"), ("t2_dynamiccontrols", 2, "the-internet/dynamic_controls"),
    ("t2_combobox", 2, "w3c/aria-combobox"),
    # Tier 3: complicated
    ("t3_tables", 3, "the-internet/tables"), ("t3_entryad", 3, "the-internet/entry_ad"),
    ("t3_modal", 3, "w3c/aria-modal-dialog"), ("t3_calc", 3, "local:web_calculator"),
    ("t3_kanban", 3, "local:kanban_board"), ("t3_crm", 3, "local:crm_dashboard"),
    ("t3_chain_notepad", 3, "local:web_to_desktop_chain"),
]


def _h(s):
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def stratified_split(corp, train_frac=0.7):
    """Deterministic per-tier split: sort each tier by a stable hash, take ceil(frac*n) to TRAIN,
    guaranteeing >=1 item per tier in TEST (so no tier is unseen)."""
    train, test = [], []
    for tier in sorted({c[1] for c in corp}):
        items = sorted([c for c in corp if c[1] == tier], key=lambda c: _h(c[0]))
        n = len(items)
        n_train = max(1, round(n * train_frac))
        n_train = min(n_train, n - 1) if n >= 2 else n_train   # keep >=1 in TEST per tier
        train += items[:n_train]
        test += items[n_train:]
    return train, test


def main():
    train, test = stratified_split(CORPUS)
    def by_tier(rows):
        d = {}
        for r in rows:
            d[r[1]] = d.get(r[1], 0) + 1
        return {str(k): v for k, v in sorted(d.items())}
    out = {"n_total": len(CORPUS), "train_frac": 0.7,
           "train": [r[0] for r in train], "test": [r[0] for r in test],
           "train_tier_counts": by_tier(train), "test_tier_counts": by_tier(test),
           "test_kinds": {r[0]: r[2] for r in test}}
    OUT.write_text(json.dumps(out, indent=3), encoding="utf-8")
    print(f"[split] {len(CORPUS)} webapps -> TRAIN {len(train)} / TEST {len(test)} (deterministic 70/30, stratified)")
    print(f"[split] TRAIN tiers {out['train_tier_counts']} | TEST tiers {out['test_tier_counts']}")
    print(f"[split] held-out TEST: {out['test']}")
    return out


if __name__ == "__main__":
    main()
