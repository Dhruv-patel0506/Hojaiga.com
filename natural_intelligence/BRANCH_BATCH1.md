# Branch engine on a batch of 7 real tasks (2026-11-14 21:46)

Each task: SPEC.md + empty stub given to every agent on its own copy; scored by a hidden check the agents never saw (each check proven first: reference passes fully, stub fails).

## Branches (hidden-check result per agent)

| task | opencode_deepseek | opencode_glm | opencode_mimo | opencode_nemotron | NI verdict | NI pick |
|---|---|---|---|---|---|---|
| coverage_v1 | 1.00 ok (c93) | 1.00 ok (c90) | 1.00 ok (c90) | 0.00 (c95) | recommend | opencode_glm |
| cusum_v1 | 1.00 ok (c96) | 1.00 ok (c92) | 1.00 ok (c90) | 0.96 (c95) | recommend | opencode_glm |
| chain_v1 | 1.00 ok (c97) | 1.00 ok (c92) | 1.00 ok (c90) | 1.00 ok (c95) | recommend | opencode_glm |
| pareto_v1 | 1.00 ok (c92) | 1.00 ok (c90) | 1.00 ok (c90) | 1.00 ok (c95) | recommend_equivalent | opencode_glm |
| shapley_v1 | 1.00 ok (c95) | 1.00 ok (c95) | 1.00 ok (c92) | 1.00 ok (c95) | recommend | opencode_glm |
| budget_v1 | 1.00 ok (c93) | 1.00 ok (c88) | 1.00 ok (c88) | 1.00 ok (c85) | recommend | opencode_nemotron |
| isotonic_v1 | 0.76 (c96) | 0.76 (c92) | 1.00 ok | 0.76 (c90) | recommend | opencode_mimo |

Cell = hidden-check quality (passed/total); `ok` = passed every check; (cN) = the agent's stated confidence.

## Policies (same branches, scored by the hidden checks)

| policy | tasks shipped fully correct | tasks shipped with a failing check | mean quality |
|---|---|---|---|
| NI branch engine | 7.00 / 7 | 0.00 / 7 | 1.000 |
| most confident agent | 5.00 / 7 | 2.00 / 7 | 0.823 |
| random single agent (mean over agents) | 5.75 / 7 | 1.25 / 7 | 0.937 |
| single agent: opencode_deepseek | 6.00 / 7 | 1.00 / 7 | 0.966 |
| single agent: opencode_glm | 6.00 / 7 | 1.00 / 7 | 0.966 |
| single agent: opencode_mimo | 7.00 / 7 | 0.00 / 7 | 1.000 |
| single agent: opencode_nemotron | 4.00 / 7 | 3.00 / 7 | 0.817 |
| oracle (best in hindsight) | 7.00 / 7 | 0.00 / 7 | 1.000 |

NI asked the human on 0 of 7 tasks (cross_question).

## NI minus baseline, paired bootstrap over tasks (10 000 resamples, 95% interval)

| baseline | metric | mean difference | 95% interval | reading |
|---|---|---|---|---|
| most confident agent | passed | +0.286 | [+0.000, +0.714] | interval spans 0: not shown |
| most confident agent | broken | -0.286 | [-0.714, +0.000] | interval spans 0: not shown |
| most confident agent | quality | +0.177 | [+0.000, +0.463] | interval spans 0: not shown |
| random single agent (mean over agents) | passed | +0.179 | [+0.036, +0.393] | NI better |
| random single agent (mean over agents) | broken | -0.179 | [-0.393, -0.036] | NI better |
| random single agent (mean over agents) | quality | +0.063 | [+0.001, +0.143] | NI better |

Exact sign test (tasks where NI's pick scored higher vs lower than the baseline's; ties dropped). With few tasks the percentile bootstrap is optimistic, so this is the stricter reading:

| baseline | NI higher | NI lower | two-sided p |
|---|---|---|---|
| most confident agent | 2 | 0 | 0.500 |
| random single agent (mean over agents) | 3 | 0 | 0.250 |

## What the failing branches got wrong (hidden-check lines)

- coverage_v1 / opencode_nemotron (stated confidence 95): TypeError: 'NoneType' object is not iterable
- cusum_v1 / opencode_nemotron (stated confidence 95): final: zero after alarm reset
- isotonic_v1 / opencode_deepseek (stated confidence 96): simple violation pooled; unsorted input; equal x merged first; weights respected; pooling must back-track; longer case
- isotonic_v1 / opencode_glm (stated confidence 92): simple violation pooled; unsorted input; equal x merged first; weights respected; pooling must back-track; longer case
- isotonic_v1 / opencode_nemotron (stated confidence 90): simple violation pooled; unsorted input; equal x merged first; weights respected; pooling must back-track; longer case

## Integrity

- Original task folders unchanged by every branch: True.
- Agents whose output mentions the hidden folder (possible peeking): none.
- Extra files agents created against the spec (ignored by the branch copy): [('pareto_v1', 'opencode_mimo', ['__pycache__']), ('shapley_v1', 'opencode_nemotron', ['test_shapley.py', 'test_shapley2.py', 'test_shapley3.py'])].
- Mean agent wall time: 156 s.

Honest reading: with this many tasks, a difference whose interval spans 0 is not evidence. The tasks were written by the same author as the checks (me), from NI's own needs; they are small single-file functions, not real repository work.
