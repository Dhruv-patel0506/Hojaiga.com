# Branch engine on a batch of 16 real tasks (2026-11-15 17:56)

Each task: SPEC.md + empty stub given to every agent on its own copy; scored by a hidden check the agents never saw (each check proven first: reference passes fully, stub fails).

## Branches (hidden-check result per agent)

| task | opencode_deepseek | opencode_glm | opencode_mimo | opencode_nemotron | opencode_longcat | opencode_flint | opencode_iceman | opencode_beam | NI verdict | NI pick |
|---|---|---|---|---|---|---|---|---|---|---|
| coverage_v1 | 1.00 ok (c93) | 1.00 ok (c90) | 1.00 ok (c90) | 0.00 (c95) | - | - | - | - | recommend | opencode_glm |
| cusum_v1 | 1.00 ok (c96) | 1.00 ok (c92) | 1.00 ok (c90) | 0.96 (c95) | - | - | - | - | recommend | opencode_glm |
| chain_v1 | 1.00 ok (c97) | 1.00 ok (c92) | 1.00 ok (c90) | 1.00 ok (c95) | - | - | - | - | recommend | opencode_glm |
| pareto_v1 | 1.00 ok (c92) | 1.00 ok (c90) | 1.00 ok (c90) | 1.00 ok (c95) | - | - | - | - | recommend_equivalent | opencode_glm |
| shapley_v1 | 1.00 ok (c95) | 1.00 ok (c95) | 1.00 ok (c92) | 1.00 ok (c95) | - | - | - | - | recommend | opencode_glm |
| budget_v1 | 1.00 ok (c93) | 1.00 ok (c88) | 1.00 ok (c88) | 1.00 ok (c85) | - | - | - | - | recommend | opencode_nemotron |
| isotonic_v1 | 0.76 (c96) | 0.76 (c92) | 1.00 ok | 0.76 (c90) | - | - | - | - | recommend | opencode_mimo |
| betaq_v1 | 1.00 ok (c96) | 1.00 ok (c92) | 1.00 ok | 0.00 | - | - | - | - | recommend | opencode_glm |
| dag_v1 | 1.00 ok (c96) | 1.00 ok (c90) | 1.00 ok (c92) | 1.00 ok (c90) | - | - | - | - | recommend | opencode_glm |
| glob_v1 | 1.00 ok (c92) | 1.00 ok | 0.00 | 0.00 | - | - | - | - | recommend | opencode_glm |
| semver_v1 | 1.00 ok (c96) | 1.00 ok (c92) | 1.00 ok (c92) | 0.91 (c90) | - | - | - | - | recommend | opencode_mimo |
| ttlcache_v1 | 1.00 ok (c97) | 1.00 ok (c90) | 1.00 ok | 1.00 ok (c90) | - | - | - | - | recommend | opencode_glm |
| intervals_v1 | - | - | - | 1.00 ok (c95) | 1.00 ok (c97) | 1.00 ok (c85) | 1.00 ok (c97) | 1.00 ok (c95) | recommend | opencode_longcat |
| cmdsplit_v1 | - | - | - | 0.00 | 1.00 ok (c92) | 1.00 ok (c85) | 0.92 (c93) | 1.00 ok (c92) | recommend_equivalent | opencode_longcat |
| rank_v1 | - | - | - | 1.00 ok (c95) | 1.00 ok (c95) | 1.00 ok (c85) | 1.00 ok (c94) | 1.00 ok (c95) | recommend | opencode_longcat |
| cron_v1 | - | - | - | 1.00 ok | 1.00 ok (c90) | 1.00 ok (c85) | 1.00 ok (c92) | - | recommend | opencode_longcat |

Cell = hidden-check quality (passed/total); `ok` = passed every check; (cN) = the agent's stated confidence.

## Policies (same branches, scored by the hidden checks)

| policy | tasks shipped fully correct | tasks shipped with a failing check | mean quality |
|---|---|---|---|
| NI branch engine | 16.00 / 16 | 0.00 / 16 | 1.000 |
| most confident agent | 13.00 / 16 | 3.00 / 16 | 0.918 |
| random single agent (mean over agents) | 13.35 / 16 | 2.65 / 16 | 0.911 |
| single agent: opencode_nemotron | 9.00 / 16 | 7.00 / 16 | 0.727 |
| oracle (best in hindsight) | 16.00 / 16 | 0.00 / 16 | 1.000 |

NI asked the human on 0 of 16 tasks (cross_question).

## NI minus baseline, paired bootstrap over tasks (10 000 resamples, 95% interval)

| baseline | metric | mean difference | 95% interval | reading |
|---|---|---|---|---|
| most confident agent | passed | +0.188 | [+0.000, +0.375] | interval spans 0: not shown |
| most confident agent | broken | -0.188 | [-0.375, +0.000] | interval spans 0: not shown |
| most confident agent | quality | +0.082 | [+0.000, +0.217] | interval spans 0: not shown |
| random single agent (mean over agents) | passed | +0.166 | [+0.062, +0.284] | NI better |
| random single agent (mean over agents) | broken | -0.166 | [-0.284, -0.062] | NI better |
| random single agent (mean over agents) | quality | +0.089 | [+0.028, +0.165] | NI better |

Exact sign test (tasks where NI's pick scored higher vs lower than the baseline's; ties dropped). With few tasks the percentile bootstrap is optimistic, so this is the stricter reading:

| baseline | NI higher | NI lower | two-sided p |
|---|---|---|---|
| most confident agent | 3 | 0 | 0.250 |
| random single agent (mean over agents) | 7 | 0 | 0.016 |

## What the failing branches got wrong (hidden-check lines)

- coverage_v1 / opencode_nemotron (stated confidence 95): TypeError: 'NoneType' object is not iterable
- cusum_v1 / opencode_nemotron (stated confidence 95): final: zero after alarm reset
- isotonic_v1 / opencode_deepseek (stated confidence 96): simple violation pooled; unsorted input; equal x merged first; weights respected; pooling must back-track; longer case
- isotonic_v1 / opencode_glm (stated confidence 92): simple violation pooled; unsorted input; equal x merged first; weights respected; pooling must back-track; longer case
- isotonic_v1 / opencode_nemotron (stated confidence 90): simple violation pooled; unsorted input; equal x merged first; weights respected; pooling must back-track; longer case
- betaq_v1 / opencode_nemotron (stated confidence -): uniform CDF (raised NotImplementedError); I_x(a,1) = x^a (raised NotImplementedError); I_x(1,b) = 1-(1-x)^b (raised NotImplementedError); symmetric at one half (raised NotImplementedError); Beta(2,3) closed form (raised NotImplementedError); large parameters (raised NotImplementedError)
- glob_v1 / opencode_mimo (stated confidence -): star in a name (raised NotImplementedError); star does not cross / (raised NotImplementedError); question mark (raised NotImplementedError); double star any depth (raised NotImplementedError); double star zero segments (raised NotImplementedError); middle double star zero (raised NotImplementedError)
- glob_v1 / opencode_nemotron (stated confidence -): star in a name (raised NotImplementedError); star does not cross / (raised NotImplementedError); question mark (raised NotImplementedError); double star any depth (raised NotImplementedError); double star zero segments (raised NotImplementedError); middle double star zero (raised NotImplementedError)
- semver_v1 / opencode_nemotron (stated confidence 90): invalid comparator even when already decided (did not raise); invalid alternative after a true one (did not raise); empty alternative (did not raise)
- cmdsplit_v1 / opencode_iceman (stated confidence 93): escaped quote in double quotes; other backslash kept in double quotes
- cmdsplit_v1 / opencode_nemotron (stated confidence -): simple (raised NotImplementedError); all separators (raised NotImplementedError); operators in order (raised NotImplementedError); no spaces needed (raised NotImplementedError); quotes protect separators (raised NotImplementedError); escaped separator (raised NotImplementedError)

## Integrity

- Original task folders unchanged by every branch: True.
- Agents whose output mentions the hidden folder (possible peeking): none.
- Extra files agents created against the spec (ignored by the branch copy): [('pareto_v1', 'opencode_mimo', ['__pycache__']), ('shapley_v1', 'opencode_nemotron', ['test_shapley.py', 'test_shapley2.py', 'test_shapley3.py']), ('glob_v1', 'opencode_deepseek', ['__pycache__']), ('semver_v1', 'opencode_nemotron', ['test.py', 'test_edge.py', 'test_final.py', 'test_full.py', 'test_tilde_caret.py']), ('intervals_v1', 'opencode_iceman', ['__pycache__']), ('intervals_v1', 'opencode_nemotron', ['test_impl.py']), ('rank_v1', 'opencode_iceman', ['__pycache__']), ('cron_v1', 'opencode_longcat', ['__pycache__']), ('cron_v1', 'opencode_flint', ['__pycache__']), ('cron_v1', 'opencode_nemotron', ['test_gov_cron.py'])].
- Mean agent wall time: 267 s.

Honest reading: with this many tasks, a difference whose interval spans 0 is not evidence. The tasks were written by the same author as the checks (me), from NI's own needs; they are small single-file functions, not real repository work.
