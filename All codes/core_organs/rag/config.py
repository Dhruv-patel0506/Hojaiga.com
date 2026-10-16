"""rag.config -- every tunable of the federated RAG in one place (DESIGN.md sections 5-7, 12). Nothing else in the package holds a magic number."""
from __future__ import annotations

SCHEMA_VERSION = 1
VEC_DIM = 768                      # column width of every vector column; smaller embedders are zero-padded (cosine-neutral), larger ones need a migration
TEXT_EMBEDDER_ID = "nomic-embed-text@ollama-cpu"

# ---- state recognition (graph.localize) -------------------------------------------------------------------------------------------------------------
SAME_STATE = 0.75                  # IDF-weighted Jaccard >= this: the same state
VARIANT_STATE = 0.50               # between VARIANT and SAME: a variant of that state; below: a new node
MERGE_STATE = 0.90                 # two nodes this similar after accumulating landmarks are aliased
BLIND_TREE_MIN_LANDMARKS = 5       # fewer named structural landmarks than this: use OCR / icon / layout-grid landmarks
BLIND_LANDMARK_WEIGHT = 0.5
MAX_LANDMARK_NAME = 40             # longer names are content, not structure
GRAPH_LRU_APPS = 8

# ---- planning ---------------------------------------------------------------------------------------------------------------------------------------
ROUTE_COST_MS = {"script": 50, "wm_command": 20, "hotkey": 15, "uia_invoke": 60, "menu_path": 400, "control_click": 250, "posted_click": 300, "type": 40}
LAMBDA = 2.0                       # weight of -ln(p) in an edge's cost
STALE_DAYS = 90.0                  # edge confidence erodes as p ** (1 + age/STALE_DAYS)
MAX_PATH_DEPTH = 12
K_ALTERNATIVES = 3
MAX_REPLANS = 3
PRIORS = {"verified": (4, 1), "learned": (3, 1), "catalog": (2, 1), "seed": (2, 1), "transcript": (1, 1), "official_doc": (2, 1), "web": (1, 1), "llm": (1, 2),
          "borrowed": (1, 2), "docs": (2, 1)}
TRUST_W = {"verified": 1.0, "learned": 0.9, "catalog": 0.8, "official_doc": 0.85, "seed": 0.7, "transcript": 0.6, "web": 0.5, "llm": 0.35, "borrowed": 0.4}
PROMOTE_AFTER_OK = 2               # a probe that succeeded this many times in different runs becomes verified
DEMOTE_AFTER_FAIL = 3              # consecutive failures that drop one trust level
TRUST_LADDER = ["llm", "web", "transcript", "seed", "catalog", "learned", "verified"]

# ---- utility of a plan --------------------------------------------------------------------------------------------------------------------------------
ALPHA_COST = 0.05                  # per second
BETA_UNGROUNDED = 0.6
GAMMA_HUMAN = 0.1
MIN_P_STOP = 0.7                   # router stops when a plan is fully grounded and at least this likely
RRF_K = 60
VEC_MAX_DISTANCE = 0.65            # cosine distance beyond which a vector hit is noise, not recall (nearest-neighbour search always returns something)
UNIQUE_TOKEN_SCORE = 0.82          # a rare content word that appears in exactly one command's names resolves to that command
UNIQUE_TOKEN_MIN_IDF = 1.6

# ---- router budgets ---------------------------------------------------------------------------------------------------------------------------------
BUDGET_MS = 150
ROUTE_SHARES = {"DO": {"skill": .1, "fast": .2, "proc": .35, "graph": .25, "icon": .1}, "EXPLAIN": {"proc": .6, "fast": .15, "graph": .25},
                "IDENTIFY": {"icon": .3, "graph": .3, "proc": .4}, "LOCATE": {"graph": .6, "icon": .2, "proc": .2}, "RECOVER": {"recovery": .5, "graph": .5},
                "CURRICULUM": {"proc": .7, "graph": .3}}
TIER_ROUTE_MULT = {0: {"menu_path": 1.0, "hotkey": 1.0}, 1: {"posted_click": 0.8, "control_click": 0.9}, 2: {"hotkey": 0.7, "menu_path": 1.1}, 3: {"script": 0.5, "hotkey": 0.6, "menu_path": 1.4}}
BORROW_MIN_COMMANDS = 20           # an app with fewer known commands than this (or < BORROW_MIN_CHUNKS chunks) may borrow from its archetype
BORROW_MIN_CHUNKS = 3
BORROW_CONFIDENCE_MULT = 0.5
VERSION_OTHER_MULT = 0.8
CACHE_TTL_S = 3600
ROUTER_VERSION = 3                # part of every router-cache key: BUMP IT whenever routing/fusion/planning logic changes, so a cached answer from older logic can never be served
EMBED_CACHE_MAX = 50000
LLM_REWRITE_TIMEOUT_S = 4.0        # a WALL-CLOCK cap (the call runs in a worker; the router stops waiting at this point and answers without the rewrite)
QUERY_EMBED_TIMEOUT_S = 2.0        # a cold Ollama reload can take ~1 s; beyond this the vector leg is skipped for that query
# Weak recall = no passage was found by BOTH the lexical and the vector leg. A raw reciprocal-rank score of one leg's best hit is 1/(RRF_K+1) = 0.016; a passage both legs return scores >= ~0.03.
# (The first version thresholded the score AFTER multiplying by quality and trust, which on real auto-captions is always tiny: the model was called on almost every query.)
WEAK_RECALL_SCORE = 0.025
# a question about KEYS ("what is the shortcut for ...") is answered best by the hotkey rows: their evidence is weighted up
SHORTCUT_QUERY_BOOST = 2.5

# ---- retrieval --------------------------------------------------------------------------------------------------------------------------------------
IVF_PQ_MIN_ROWS = 20_000          # a flat vector scan costs ~3 us/row (measured: 160 ms at 50k x 768-d); past this size the ANN index (tools.build_ann) is what keeps a query under budget
CHUNK_QUALITY = {"auto_caption": 0.5, "manual_caption": 0.7, "official_doc": 0.9, "self_doc": 0.8, "manual": 0.9, "guide": 0.8, "web_doc": 0.6}
FUZZY_RESOLVE = 0.88
EXPLORE_TARGET_MIN_SOURCES = 3
ICON_DHASH_MAX_BITS = 12           # a dHash hit is accepted only if the 256-bit distance is this small
ICON_HAMMING_TOL = 30
