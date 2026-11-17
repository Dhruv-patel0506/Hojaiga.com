## probe 2026-11-07 18:56  algos=v2,v3 rounds=2 cap=8000 device=cpu

| task | algo | n_tr | vote acc | balanced acc | AUROC | NLL | Logic | Pattern | Verifier | Explor. | sec/round |
|---|---|---|---|---|---|---|---|---|---|---|---|
| enc/graph/imdb_binary | v2 | 680 | 0.6854 | 0.6853 | 0.7597 | 0.5867 | 0.675 | 0.680 | 0.653 | 0.643 | 16.1 |
| enc/graph/imdb_binary | v3 | 680 | 0.6718 | 0.6711 | 0.7561 | 0.5864 | 0.661 | 0.649 | 0.661 | 0.676 | 25.7 |
|  | v3 diag | | {"n_fit": 615, "n_cal": 83, "D": 534, "imbalance": 1.02, "pattern_seeds": 3, "verifier_k": 40, "verifier_tau": 0.1, "T": [0.7, 2.0, 2.8, 1.0], "stack": [1.208, 0.845, 1.062, 0.884], "prior_shift": 0.0} |
| enc/text/rotten_tomatoes | v2 | 5635 | 0.7742 | 0.7742 | 0.8516 | 0.4840 | 0.761 | 0.742 | 0.707 | 0.719 | 26.3 |
| enc/text/rotten_tomatoes | v3 | 5635 | 0.7767 | 0.7770 | 0.8553 | 0.4805 | 0.763 | 0.751 | 0.753 | 0.755 | 32.4 |
|  | v3 diag | | {"n_fit": 4910, "n_cal": 669, "D": 384, "imbalance": 1.04, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [1.4, 2.0, 0.7, 0.7], "stack": [1.0, 1.041, 0.969, 0.99], "prior_shift": 0.0} |

