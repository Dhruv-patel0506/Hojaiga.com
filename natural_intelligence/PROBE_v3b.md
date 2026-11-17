## probe 2026-11-07 19:14  algos=v2,v3 rounds=3 cap=8000 device=cpu

| task | algo | n_tr | vote acc | balanced acc | AUROC | NLL | Logic | Pattern | Verifier | Explor. | sec/round |
|---|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/imdb | v2 | 5537 | 0.7839 | 0.7838 | 0.8644 | 0.4706 | 0.771 | 0.755 | 0.716 | 0.728 | 15.4 |
| enc/text/imdb | v3 | 5537 | 0.7787 | 0.7784 | 0.8640 | 0.4758 | 0.771 | 0.756 | 0.746 | 0.753 | 32.2 |
|  | v3 diag | | {"refit_on_all": true, "n_fit": 4919, "n_cal": 670, "D": 384, "imbalance": 1.04, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [1.4, 2.0, 0.7, 0.7], "stack": [1.084, 1.145, 0.906, 0.865], "prior_shift": 0.0} |
| enc/text/emotion | v2 | 5663 | 0.7190 | 0.6103 | nan | 0.8469 | 0.678 | 0.704 | 0.645 | 0.594 | 14.3 |
| enc/text/emotion | v3 | 5663 | 0.7053 | 0.6756 | nan | 0.7901 | 0.678 | 0.708 | 0.668 | 0.645 | 33.9 |
|  | v3 diag | | {"refit_on_all": true, "n_fit": 4901, "n_cal": 668, "D": 384, "imbalance": 10.01, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.05, "T": [1.0, 1.0, 1.0, 0.7], "stack": [0.586, 1.924, 0.947, 0.544], "prior_shift": 0.75} |
| enc/text/sst2 | v2 | 5642 | 0.8111 | 0.8108 | 0.8943 | 0.4188 | 0.810 | 0.796 | 0.732 | 0.769 | 14.1 |
| enc/text/sst2 | v3 | 5642 | 0.8138 | 0.8134 | 0.8968 | 0.4132 | 0.810 | 0.795 | 0.763 | 0.796 | 32.9 |
|  | v3 diag | | {"refit_on_all": true, "n_fit": 4896, "n_cal": 667, "D": 384, "imbalance": 1.06, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [1.4, 1.4, 0.5, 0.7], "stack": [1.001, 1.223, 0.899, 0.878], "prior_shift": 0.0} |
| enc/graph/imdb_binary | v2 | 680 | 0.6857 | 0.6857 | 0.7594 | 0.5903 | 0.677 | 0.677 | 0.645 | 0.644 | 8.7 |
| enc/graph/imdb_binary | v3 | 680 | 0.6738 | 0.6738 | 0.7616 | 0.5821 | 0.677 | 0.663 | 0.651 | 0.670 | 28.7 |
|  | v3 diag | | {"refit_on_all": true, "n_fit": 614, "n_cal": 83, "D": 534, "imbalance": 1.05, "pattern_seeds": 3, "verifier_k": 40, "verifier_tau": 0.1, "T": [2.0, 2.8, 4.0, 1.0], "stack": [0.951, 0.84, 1.136, 1.072], "prior_shift": 0.0} |

