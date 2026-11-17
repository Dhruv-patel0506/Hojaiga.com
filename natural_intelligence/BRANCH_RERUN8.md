# Branch engine on a batch of 8 real tasks (2026-11-15 17:56)

Each task: SPEC.md + empty stub given to every agent on its own copy; scored by a hidden check the agents never saw (each check proven first: reference passes fully, stub fails).

## Branches (hidden-check result per agent)

| task | opencode_longcat | opencode_flint | opencode_iceman | opencode_beam | opencode_nemotron | NI verdict | NI pick |
|---|---|---|---|---|---|---|---|
| intervals_v1 | 1.00 ok (c97) | 1.00 ok (c85) | 1.00 ok (c97) | 1.00 ok (c95) | 1.00 ok (c95) | recommend | opencode_longcat |
| cmdsplit_v1 | 1.00 ok (c92) | 1.00 ok (c85) | 0.92 (c93) | 1.00 ok (c92) | 0.00 | recommend_equivalent | opencode_longcat |
| rank_v1 | 1.00 ok (c95) | 1.00 ok (c85) | 1.00 ok (c94) | 1.00 ok (c95) | 1.00 ok (c95) | recommend | opencode_longcat |
| cron_v1 | 1.00 ok (c90) | 1.00 ok (c85) | 1.00 ok (c92) | - | 1.00 ok | recommend | opencode_longcat |
| diff_v1 | - | - | - | - | 1.00 ok (c95) | recommend | opencode_nemotron |
| redact_v1 | - | - | - | - | 0.96 (c90) | no_feasible_branch | - |
| jpath_v1 | - | - | - | - | 0.97 (c90) | no_feasible_branch | - |
| wilson_v1 | - | - | - | - | 1.00 ok (c95) | recommend | opencode_nemotron |

Cell = hidden-check quality (passed/total); `ok` = passed every check; (cN) = the agent's stated confidence.

## Policies (same branches, scored by the hidden checks)

| policy | tasks shipped fully correct | tasks shipped with a failing check | mean quality |
|---|---|---|---|
| NI branch engine | 6.00 / 8 | 0.00 / 8 | 0.750 |
| most confident agent | 5.00 / 8 | 3.00 / 8 | 0.981 |
| random single agent (mean over agents) | 5.60 / 8 | 2.40 / 8 | 0.964 |
| single agent: opencode_nemotron | 5.00 / 8 | 3.00 / 8 | 0.866 |
| oracle (best in hindsight) | 6.00 / 8 | 2.00 / 8 | 0.991 |

NI asked the human on 0 of 8 tasks (cross_question).

## NI minus baseline, paired bootstrap over tasks (10 000 resamples, 95% interval)

| baseline | metric | mean difference | 95% interval | reading |
|---|---|---|---|---|
| most confident agent | passed | +0.125 | [+0.000, +0.375] | interval spans 0: not shown |
| most confident agent | broken | -0.375 | [-0.750, -0.125] | NI better |
| most confident agent | quality | -0.231 | [-0.590, +0.019] | interval spans 0: not shown |
| random single agent (mean over agents) | passed | +0.050 | [+0.000, +0.150] | interval spans 0: not shown |
| random single agent (mean over agents) | broken | -0.300 | [-0.625, -0.050] | NI better |
| random single agent (mean over agents) | quality | -0.214 | [-0.572, +0.054] | interval spans 0: not shown |

Exact sign test (tasks where NI's pick scored higher vs lower than the baseline's; ties dropped). With few tasks the percentile bootstrap is optimistic, so this is the stricter reading:

| baseline | NI higher | NI lower | two-sided p |
|---|---|---|---|
| most confident agent | 1 | 2 | 1.000 |
| random single agent (mean over agents) | 1 | 2 | 1.000 |

## What the failing branches got wrong (hidden-check lines)

- cmdsplit_v1 / opencode_iceman (stated confidence 93): escaped quote in double quotes; other backslash kept in double quotes
- cmdsplit_v1 / opencode_nemotron (stated confidence -): simple (raised NotImplementedError); all separators (raised NotImplementedError); operators in order (raised NotImplementedError); no spaces needed (raised NotImplementedError); quotes protect separators (raised NotImplementedError); escaped separator (raised NotImplementedError)
- redact_v1 / opencode_nemotron (stated confidence 90): rule order: openai inside an assignment
- jpath_v1 / opencode_nemotron (stated confidence 90): parse rejects '$a' (did not raise)

## Integrity

- Original task folders unchanged by every branch: True.
- Agents whose output mentions the hidden folder (possible peeking): none.
- Extra files agents created against the spec (ignored by the branch copy): [('intervals_v1', 'opencode_iceman', ['__pycache__']), ('intervals_v1', 'opencode_nemotron', ['test_impl.py']), ('rank_v1', 'opencode_iceman', ['__pycache__']), ('cron_v1', 'opencode_longcat', ['__pycache__']), ('cron_v1', 'opencode_flint', ['__pycache__']), ('cron_v1', 'opencode_nemotron', ['test_gov_cron.py']), ('redact_v1', 'opencode_nemotron', ['fix.py', 'test_count.py', 'test_edge.py', 'test_redact.py'])].
- Mean agent wall time: 253 s.

Honest reading: with this many tasks, a difference whose interval spans 0 is not evidence. The tasks were written by the same author as the checks (me), from NI's own needs; they are small single-file functions, not real repository work.
