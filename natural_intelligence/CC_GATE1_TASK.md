# Gate 1, task level

Generated 2026-11-14 17:00 by `cc_gate_task.py`. Train window = actions before 2026-10-30; test window = after. NI = outer brain on history features + action text + recent-error features.

## T2 - after an edit, will the next run in the same turn fail?

Edits followed by a shell command in the same turn: 3364 (train 2615, test 749); next run failed: 114 (3.4%), test failures 24.

| Method | AUROC | AUPRC | R@10% |
|---|---|---|---|
| B1 failure rate of the next run after edits to this file type, so far | 0.425 | 0.029 | 0.04 |
| B2 gradient-boosted trees, history features | 0.412 | 0.041 | 0.12 |
| NI | 0.549 | 0.035 | 0.00 |

NI minus best baseline (B1 failure rate of the next run after edits to this file type, so far) AUROC: +0.121 [95% -0.052, +0.297], P(NI better) 91%.

## T3 - will the human correct or interrupt this turn?

Correction classifier (fallback for unlabelled messages only; 5-fold grouped CV on 348 teacher labels): AUROC 0.784, accuracy 0.767 vs 0.822 for always-'no', precision 0.39, recall 0.53. It is weak, so every turn evaluated here uses a teacher label, an interrupt or a rejection.

Turns with a known outcome: 299 (train 194 with 50 bad, test 105 with 15 bad).

| Method | AUROC | AUPRC | Bad turns in riskiest 20% |
|---|---|---|---|
| B1 number of actions in the turn | 0.484 | 0.158 | 3 of 15 |
| B2 number of failed actions in the turn | 0.507 | 0.184 | 3 of 15 |
| B3 share of failed actions in the turn | 0.502 | 0.284 | 4 of 15 |
| B4 gradient-boosted trees on turn summaries | 0.418 | 0.125 | 1 of 15 |
| NI, riskiest action in the turn | 0.527 | 0.178 | 4 of 15 |
| NI, mean over the turn's actions | 0.586 | 0.251 | 7 of 15 |

NI, mean over the turn's actions minus best baseline (B2 number of failed actions in the turn) AUROC: +0.076 [95% -0.212, +0.344], P(NI better) 72%.

## Honest limits

- Turn labels come from one teacher (Claude) reading the first ~170 characters of each follow-up message, on one person's sessions. They have not been checked by the person.
- The test windows are small, so the bootstrap intervals are wide; treat these as direction, not proof.
- Runtime 437 s.
