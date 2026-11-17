# Branch engine on a batch of 20 real tasks (2026-11-15 17:03)

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
| betaq_v1 | 1.00 ok (c96) | 1.00 ok (c92) | 1.00 ok | 0.00 | recommend | opencode_glm |
| dag_v1 | 1.00 ok (c96) | 1.00 ok (c90) | 1.00 ok (c92) | 1.00 ok (c90) | recommend | opencode_glm |
| glob_v1 | 1.00 ok (c92) | 1.00 ok | 0.00 | 0.00 | recommend | opencode_glm |
| semver_v1 | 1.00 ok (c96) | 1.00 ok (c92) | 1.00 ok (c92) | 0.91 (c90) | recommend | opencode_mimo |
| ttlcache_v1 | 1.00 ok (c97) | 1.00 ok (c90) | 1.00 ok | 1.00 ok (c90) | recommend | opencode_glm |
| intervals_v1 | 0.00 | 0.00 | 0.00 | 1.00 ok (c95) | recommend | opencode_nemotron |
| cmdsplit_v1 | 0.00 | 0.00 | 0.00 | 0.00 | no_feasible_branch | - |
| rank_v1 | 0.00 | 0.00 | 0.00 | 1.00 ok (c95) | recommend | opencode_nemotron |
| cron_v1 | 0.00 | 0.00 | 0.00 | 1.00 ok | recommend | opencode_nemotron |
| diff_v1 | 0.00 | 0.00 | 0.00 | 1.00 ok (c95) | recommend | opencode_nemotron |
| redact_v1 | 0.00 | 0.00 | 0.00 | 0.96 (c90) | no_feasible_branch | - |
| jpath_v1 | 0.00 | 0.00 | 0.00 | 0.97 (c90) | no_feasible_branch | - |
| wilson_v1 | 0.00 | 0.00 | 0.00 | 1.00 ok (c95) | recommend | opencode_nemotron |

Cell = hidden-check quality (passed/total); `ok` = passed every check; (cN) = the agent's stated confidence.

## Policies (same branches, scored by the hidden checks)

| policy | tasks shipped fully correct | tasks shipped with a failing check | mean quality |
|---|---|---|---|
| NI branch engine | 17.00 / 20 | 0.00 / 20 | 0.850 |
| most confident agent | 14.00 / 20 | 4.00 / 20 | 0.834 |
| random single agent (mean over agents) | 11.00 / 20 | 9.00 / 20 | 0.626 |
| single agent: opencode_deepseek | 11.00 / 20 | 9.00 / 20 | 0.588 |
| single agent: opencode_glm | 11.00 / 20 | 9.00 / 20 | 0.588 |
| single agent: opencode_mimo | 11.00 / 20 | 9.00 / 20 | 0.550 |
| single agent: opencode_nemotron | 11.00 / 20 | 9.00 / 20 | 0.778 |
| oracle (best in hindsight) | 17.00 / 20 | 3.00 / 20 | 0.946 |

NI asked the human on 0 of 20 tasks (cross_question).

## NI minus baseline, paired bootstrap over tasks (10 000 resamples, 95% interval)

| baseline | metric | mean difference | 95% interval | reading |
|---|---|---|---|---|
| most confident agent | passed | +0.150 | [+0.000, +0.300] | interval spans 0: not shown |
| most confident agent | broken | -0.200 | [-0.400, -0.050] | NI better |
| most confident agent | quality | +0.016 | [-0.181, +0.212] | interval spans 0: not shown |
| random single agent (mean over agents) | passed | +0.300 | [+0.163, +0.438] | NI better |
| random single agent (mean over agents) | broken | -0.450 | [-0.613, -0.287] | NI better |
| random single agent (mean over agents) | quality | +0.224 | [+0.084, +0.376] | NI better |

Exact sign test (tasks where NI's pick scored higher vs lower than the baseline's; ties dropped). With few tasks the percentile bootstrap is optimistic, so this is the stricter reading:

| baseline | NI higher | NI lower | two-sided p |
|---|---|---|---|
| most confident agent | 3 | 2 | 1.000 |
| random single agent (mean over agents) | 11 | 2 | 0.022 |

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
- intervals_v1 / opencode_deepseek (stated confidence -): merge sorts and merges (raised NotImplementedError); merge touching (raised NotImplementedError); merge contained (raised NotImplementedError); merge accepts lists, returns tuples (raised NotImplementedError); merge empty (raised NotImplementedError); empty interval (raised NotImplementedError, wanted ValueError)
- intervals_v1 / opencode_glm (stated confidence -): merge sorts and merges (raised NotImplementedError); merge touching (raised NotImplementedError); merge contained (raised NotImplementedError); merge accepts lists, returns tuples (raised NotImplementedError); merge empty (raised NotImplementedError); empty interval (raised NotImplementedError, wanted ValueError)
- intervals_v1 / opencode_mimo (stated confidence -): merge sorts and merges (raised NotImplementedError); merge touching (raised NotImplementedError); merge contained (raised NotImplementedError); merge accepts lists, returns tuples (raised NotImplementedError); merge empty (raised NotImplementedError); empty interval (raised NotImplementedError, wanted ValueError)
- cmdsplit_v1 / opencode_deepseek (stated confidence -): simple (raised NotImplementedError); all separators (raised NotImplementedError); operators in order (raised NotImplementedError); no spaces needed (raised NotImplementedError); quotes protect separators (raised NotImplementedError); escaped separator (raised NotImplementedError)
- cmdsplit_v1 / opencode_glm (stated confidence -): simple (raised NotImplementedError); all separators (raised NotImplementedError); operators in order (raised NotImplementedError); no spaces needed (raised NotImplementedError); quotes protect separators (raised NotImplementedError); escaped separator (raised NotImplementedError)
- cmdsplit_v1 / opencode_mimo (stated confidence -): simple (raised NotImplementedError); all separators (raised NotImplementedError); operators in order (raised NotImplementedError); no spaces needed (raised NotImplementedError); quotes protect separators (raised NotImplementedError); escaped separator (raised NotImplementedError)
- cmdsplit_v1 / opencode_nemotron (stated confidence -): simple (raised NotImplementedError); all separators (raised NotImplementedError); operators in order (raised NotImplementedError); no spaces needed (raised NotImplementedError); quotes protect separators (raised NotImplementedError); escaped separator (raised NotImplementedError)
- rank_v1 / opencode_deepseek (stated confidence -): rankdata ties (raised NotImplementedError); rankdata three-way tie (raised NotImplementedError); rankdata empty (raised NotImplementedError); tau perfect (raised NotImplementedError); tau reversed (raised NotImplementedError); tau with ties in y (raised NotImplementedError)
- rank_v1 / opencode_glm (stated confidence -): rankdata ties (raised NotImplementedError); rankdata three-way tie (raised NotImplementedError); rankdata empty (raised NotImplementedError); tau perfect (raised NotImplementedError); tau reversed (raised NotImplementedError); tau with ties in y (raised NotImplementedError)
- rank_v1 / opencode_mimo (stated confidence -): rankdata ties (raised NotImplementedError); rankdata three-way tie (raised NotImplementedError); rankdata empty (raised NotImplementedError); tau perfect (raised NotImplementedError); tau reversed (raised NotImplementedError); tau with ties in y (raised NotImplementedError)
- cron_v1 / opencode_deepseek (stated confidence -): every 15 minutes (raised NotImplementedError); strictly after an exact match (raised NotImplementedError); seconds ignored, still strictly after (raised NotImplementedError); weekdays 9am from Friday evening (raised NotImplementedError); month rollover (raised NotImplementedError); year rollover (raised NotImplementedError)
- cron_v1 / opencode_glm (stated confidence -): every 15 minutes (raised NotImplementedError); strictly after an exact match (raised NotImplementedError); seconds ignored, still strictly after (raised NotImplementedError); weekdays 9am from Friday evening (raised NotImplementedError); month rollover (raised NotImplementedError); year rollover (raised NotImplementedError)
- cron_v1 / opencode_mimo (stated confidence -): every 15 minutes (raised NotImplementedError); strictly after an exact match (raised NotImplementedError); seconds ignored, still strictly after (raised NotImplementedError); weekdays 9am from Friday evening (raised NotImplementedError); month rollover (raised NotImplementedError); year rollover (raised NotImplementedError)
- diff_v1 / opencode_deepseek (stated confidence -): lcs classic (raised NotImplementedError); lcs empty (raised NotImplementedError); ops substitute: delete before insert (raised NotImplementedError); ops swap (raised NotImplementedError); ops exact rule on a longer case (raised NotImplementedError); ops tail (raised NotImplementedError)
- diff_v1 / opencode_glm (stated confidence -): lcs classic (raised NotImplementedError); lcs empty (raised NotImplementedError); ops substitute: delete before insert (raised NotImplementedError); ops swap (raised NotImplementedError); ops exact rule on a longer case (raised NotImplementedError); ops tail (raised NotImplementedError)
- diff_v1 / opencode_mimo (stated confidence -): lcs classic (raised NotImplementedError); lcs empty (raised NotImplementedError); ops substitute: delete before insert (raised NotImplementedError); ops swap (raised NotImplementedError); ops exact rule on a longer case (raised NotImplementedError); ops tail (raised NotImplementedError)
- redact_v1 / opencode_deepseek (stated confidence -): openai key (raised NotImplementedError); openai key with dashes (raised NotImplementedError); sk- inside a word is not a key (raised NotImplementedError); openai too short (raised NotImplementedError); github token (raised NotImplementedError); github wrong letter (raised NotImplementedError)
- redact_v1 / opencode_glm (stated confidence -): openai key (raised NotImplementedError); openai key with dashes (raised NotImplementedError); sk- inside a word is not a key (raised NotImplementedError); openai too short (raised NotImplementedError); github token (raised NotImplementedError); github wrong letter (raised NotImplementedError)
- redact_v1 / opencode_mimo (stated confidence -): openai key (raised NotImplementedError); openai key with dashes (raised NotImplementedError); sk- inside a word is not a key (raised NotImplementedError); openai too short (raised NotImplementedError); github token (raised NotImplementedError); github wrong letter (raised NotImplementedError)
- redact_v1 / opencode_nemotron (stated confidence 90): rule order: openai inside an assignment
- jpath_v1 / opencode_deepseek (stated confidence -): parse dots and index (raised NotImplementedError); parse root forms (raised NotImplementedError); parse quoted keys (raised NotImplementedError); parse escaped quote (raised NotImplementedError); parse leading index (raised NotImplementedError); quoted digits are a string key (raised NotImplementedError)
- jpath_v1 / opencode_glm (stated confidence -): parse dots and index (raised NotImplementedError); parse root forms (raised NotImplementedError); parse quoted keys (raised NotImplementedError); parse escaped quote (raised NotImplementedError); parse leading index (raised NotImplementedError); quoted digits are a string key (raised NotImplementedError)
- jpath_v1 / opencode_mimo (stated confidence -): parse dots and index (raised NotImplementedError); parse root forms (raised NotImplementedError); parse quoted keys (raised NotImplementedError); parse escaped quote (raised NotImplementedError); parse leading index (raised NotImplementedError); quoted digits are a string key (raised NotImplementedError)
- jpath_v1 / opencode_nemotron (stated confidence 90): parse rejects '$a' (did not raise)
- wilson_v1 / opencode_deepseek (stated confidence -): wilson 5/10 matches scipy (raised NotImplementedError); wilson 0/10 matches scipy (raised NotImplementedError); wilson 10/10 matches scipy (raised NotImplementedError); wilson 37/400 matches scipy (raised NotImplementedError); wilson 1/3 matches scipy (raised NotImplementedError); wilson n = 0 (raised NotImplementedError)
- wilson_v1 / opencode_glm (stated confidence -): wilson 5/10 matches scipy (raised NotImplementedError); wilson 0/10 matches scipy (raised NotImplementedError); wilson 10/10 matches scipy (raised NotImplementedError); wilson 37/400 matches scipy (raised NotImplementedError); wilson 1/3 matches scipy (raised NotImplementedError); wilson n = 0 (raised NotImplementedError)
- wilson_v1 / opencode_mimo (stated confidence -): wilson 5/10 matches scipy (raised NotImplementedError); wilson 0/10 matches scipy (raised NotImplementedError); wilson 10/10 matches scipy (raised NotImplementedError); wilson 37/400 matches scipy (raised NotImplementedError); wilson 1/3 matches scipy (raised NotImplementedError); wilson n = 0 (raised NotImplementedError)

## Integrity

- Original task folders unchanged by every branch: True.
- Agents whose output mentions the hidden folder (possible peeking): none.
- Extra files agents created against the spec (ignored by the branch copy): [('pareto_v1', 'opencode_mimo', ['__pycache__']), ('shapley_v1', 'opencode_nemotron', ['test_shapley.py', 'test_shapley2.py', 'test_shapley3.py']), ('glob_v1', 'opencode_deepseek', ['__pycache__']), ('semver_v1', 'opencode_nemotron', ['test.py', 'test_edge.py', 'test_final.py', 'test_full.py', 'test_tilde_caret.py']), ('intervals_v1', 'opencode_nemotron', ['test_impl.py']), ('cron_v1', 'opencode_nemotron', ['test_gov_cron.py']), ('redact_v1', 'opencode_nemotron', ['fix.py', 'test_count.py', 'test_edge.py', 'test_redact.py'])].
- Mean agent wall time: 458 s.

Honest reading: with this many tasks, a difference whose interval spans 0 is not evidence. The tasks were written by the same author as the checks (me), from NI's own needs; they are small single-file functions, not real repository work.
