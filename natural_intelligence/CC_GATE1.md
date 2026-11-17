# Gate 1 - can NI tell, before an agent acts, that the action will fail or be refused?

Generated 2026-11-14 16:56 by `cc_gate.py` in 567 s. Data: every Claude Code tool call on this machine (17881 actions with a known outcome, harvested from local transcripts by `cc_harvest.py`).

| | Actions | Failed or refused | Dates |
|---|---|---|---|
| Train (oldest 75%) | 13410 | 368 (2.7%) | 2026-10-03 to 2026-10-30 |
| Test (newest 25%, never seen) | 4471 | 138 (3.1%) | 2026-10-30 to 2026-11-14 |

Models are fitted on the train window and frozen. History features (how often this tool, this kind of action, this exact action, this session have failed) are computed online from earlier actions only, as a live gate would see them.

## Results on the test window

AUROC: 0.5 = chance, 1.0 = perfect ranking of risky actions above safe ones. AUPRC: area under precision-recall; chance = the failure rate (0.031). P@5% = share of the 5% riskiest-rated actions that really failed. R@5% = share of all failures caught in that 5%.

| Method | AUROC | AUPRC | P@2% | P@5% | R@5% | R@10% | Fail rate in safest half |
|---|---|---|---|---|---|---|---|
| B0 everything passes (chance) | 0.523 | 0.035 | 0.02 | 0.02 | 0.03 | 0.12 | 2.773% |
| B1 failure rate of this tool so far | 0.685 | 0.158 | 0.20 | 0.11 | 0.18 | 0.25 | 1.565% |
| B2 failure rate of this kind of action so far | 0.749 | 0.261 | 0.36 | 0.17 | 0.28 | 0.38 | 1.163% |
| B3 failure rate of this exact action so far | 0.526 | 0.035 | 0.01 | 0.06 | 0.10 | 0.14 | 3.131% |
| B4 logistic regression, history features | 0.695 | 0.163 | 0.30 | 0.15 | 0.25 | 0.33 | 1.386% |
| B5 gradient-boosted trees, history features | 0.795 | 0.246 | 0.35 | 0.17 | 0.28 | 0.41 | 0.716% |
| NI history features only | 0.779 | 0.260 | 0.35 | 0.19 | 0.31 | 0.38 | 0.850% |
| NI + action text | 0.780 | 0.277 | 0.37 | 0.19 | 0.31 | 0.41 | 0.894% |
| NI + action text + recent errors | 0.787 | 0.283 | 0.38 | 0.19 | 0.31 | 0.41 | 0.894% |

## Verdict

- Best baseline: **B5 gradient-boosted trees, history features**, AUROC 0.795.
- Best NI variant: **NI + action text + recent errors**, AUROC 0.787.
- Gate 1 criterion (NI beats every baseline on the held-out window): **NOT MET** (margin -0.008).
- Claude Code exposes no per-action confidence, so 'beats the agent's own confidence' cannot be measured here; the baselines above stand in for it.

## Is the difference real? Paired bootstrap, NI + action text + recent errors minus each baseline (1000 resamples of the test window)

| Baseline | AUROC difference [95% interval] | P(NI better) | AUPRC difference [95% interval] | P(NI better) |
|---|---|---|---|---|
| B1 failure rate of this tool so far | +0.103 [+0.060, +0.146] | 100% | +0.125 [+0.069, +0.182] | 100% |
| B2 failure rate of this kind of action so far | +0.038 [+0.000, +0.079] | 98% | +0.021 [-0.016, +0.062] | 84% |
| B3 failure rate of this exact action so far | +0.260 [+0.202, +0.319] | 100% | +0.245 [+0.172, +0.315] | 100% |
| B4 logistic regression, history features | +0.092 [+0.041, +0.144] | 100% | +0.116 [+0.059, +0.180] | 100% |
| B5 gradient-boosted trees, history features | -0.008 [-0.041, +0.025] | 30% | +0.040 [-0.000, +0.082] | 97% |

An interval that contains 0 means the test window cannot tell the two methods apart.

## What NI + action text + recent errors catches in its riskiest 5%, by outcome class (test window)

| Outcome | Failures in test | Caught in riskiest 5% |
|---|---|---|
| exit_nonzero | 77 | 15 (19%) |
| error | 37 | 15 (41%) |
| blocked | 14 | 13 (93%) |
| tool_error | 9 | 0 (0%) |
| rejected | 1 | 0 (0%) |

## Per tool (NI + action text + recent errors, tools with at least 5 test failures)

| Tool | Test actions | Failures | AUROC |
|---|---|---|---|
| Bash | 2181 | 83 | 0.745 |
| PowerShell | 156 | 11 | 0.813 |

## Fit diagnostics

```
{
 "NI history features only": {
  "n_fit": 11801,
  "n_cal": 1609,
  "D": 80,
  "imbalance": 35.99,
  "stack": [
   0.946,
   0.815,
   1.226,
   1.013
  ],
  "T": [
   1.4,
   0.5,
   1.4,
   0.7
  ],
  "tree_mix": 1.0,
  "prior_shift": 0.5
 },
 "NI + action text": {
  "n_fit": 11801,
  "n_cal": 1609,
  "D": 464,
  "imbalance": 35.99,
  "stack": [
   0.901,
   0.962,
   1.07,
   1.067
  ],
  "T": [
   1.0,
   0.5,
   1.4,
   0.7
  ],
  "tree_mix": 1.0,
  "prior_shift": 0.5
 },
 "NI + action text + recent errors": {
  "n_fit": 11801,
  "n_cal": 1609,
  "D": 466,
  "imbalance": 35.99,
  "stack": [
   0.918,
   0.943,
   1.065,
   1.075
  ],
  "T": [
   1.0,
   0.5,
   1.4,
   0.7
  ],
  "tree_mix": 1.0,
  "prior_shift": 0.5
 }
}
```

## Honest limits

- The outcome is the immediate tool result, not whether the whole task was right. Task-level outcomes (did the user keep the work, did tests pass at the end) are the next labels to add.
- One user, one machine, mostly one agent family (Claude models in Claude Code). It says nothing yet about other people or other vendors.
- Some failures are harness rules (for example blocked `sleep`), which are easy to learn; the outcome-class table shows how much of the score comes from them.
