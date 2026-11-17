## probe 2026-11-07 19:23  algos=v2,v3 rounds=3 cap=12000 device=cpu

| task | algo | n_tr | vote acc | balanced acc | AUROC | NLL | Logic | Pattern | Verifier | Explor. | sec/round |
|---|---|---|---|---|---|---|---|---|---|---|---|
| enc/text/rotten_tomatoes | v2 | 7496 | 0.7742 | 0.7741 | 0.8527 | 0.4794 | 0.765 | 0.751 | 0.698 | 0.725 | 17.6 |
| enc/text/rotten_tomatoes | v3 | 7496 | 0.7743 | 0.7743 | 0.8560 | 0.4824 | 0.765 | 0.754 | 0.739 | 0.759 | 38.0 |
|  | v3 diag | | {"refit_on_all": true, "n_fit": 6606, "n_cal": 900, "D": 384, "imbalance": 1.0, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [1.4, 2.8, 1.0, 0.7], "stack": [1.141, 0.931, 0.856, 1.072], "prior_shift": 0.0} |
| enc2/text/rotten_tomatoes | v2 | 7387 | 0.8611 | 0.8611 | 0.9359 | 0.3250 | 0.858 | 0.855 | 0.848 | 0.837 | 19.0 |
| enc2/text/rotten_tomatoes | v3 | 7387 | 0.8600 | 0.8599 | 0.9370 | 0.3244 | 0.858 | 0.851 | 0.857 | 0.849 | 41.8 |
|  | v3 diag | | {"refit_on_all": true, "n_fit": 6604, "n_cal": 900, "D": 768, "imbalance": 1.01, "pattern_seeds": 2, "verifier_k": 40, "verifier_tau": 0.1, "T": [1.0, 1.4, 1.0, 1.0], "stack": [1.034, 0.92, 1.102, 0.944], "prior_shift": 0.0} |

