# Branch engine on a batch of 13 real tasks (2026-11-15 17:02)

Each task: SPEC.md + empty stub given to every agent on its own copy; scored by a hidden check the agents never saw (each check proven first: reference passes fully, stub fails).

## Branches (hidden-check result per agent)

| task | opencode_deepseek | opencode_glm | opencode_mimo | opencode_nemotron | NI verdict | NI pick |
|---|---|---|---|---|---|---|
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
| NI branch engine | 10.00 / 13 | 0.00 / 13 | 0.769 |
| most confident agent | 9.00 / 13 | 2.00 / 13 | 0.840 |
| random single agent (mean over agents) | 5.25 / 13 | 7.75 / 13 | 0.458 |
| single agent: opencode_deepseek | 5.00 / 13 | 8.00 / 13 | 0.385 |
| single agent: opencode_glm | 5.00 / 13 | 8.00 / 13 | 0.385 |
| single agent: opencode_mimo | 4.00 / 13 | 9.00 / 13 | 0.308 |
| single agent: opencode_nemotron | 7.00 / 13 | 6.00 / 13 | 0.756 |
| oracle (best in hindsight) | 10.00 / 13 | 3.00 / 13 | 0.917 |

NI asked the human on 0 of 13 tasks (cross_question).

## NI minus baseline, paired bootstrap over tasks (10 000 resamples, 95% interval)

| baseline | metric | mean difference | 95% interval | reading |
|---|---|---|---|---|
| most confident agent | passed | +0.077 | [+0.000, +0.231] | interval spans 0: not shown |
| most confident agent | broken | -0.154 | [-0.385, +0.000] | interval spans 0: not shown |
| most confident agent | quality | -0.071 | [-0.297, +0.157] | interval spans 0: not shown |
| random single agent (mean over agents) | passed | +0.365 | [+0.192, +0.538] | NI better |
| random single agent (mean over agents) | broken | -0.596 | [-0.769, -0.404] | NI better |
| random single agent (mean over agents) | quality | +0.311 | [+0.102, +0.520] | NI better |

Exact sign test (tasks where NI's pick scored higher vs lower than the baseline's; ties dropped). With few tasks the percentile bootstrap is optimistic, so this is the stricter reading:

| baseline | NI higher | NI lower | two-sided p |
|---|---|---|---|
| most confident agent | 1 | 2 | 1.000 |
| random single agent (mean over agents) | 8 | 2 | 0.109 |

## What the failing branches got wrong (hidden-check lines)

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
- Extra files agents created against the spec (ignored by the branch copy): [('glob_v1', 'opencode_deepseek', ['__pycache__']), ('semver_v1', 'opencode_nemotron', ['test.py', 'test_edge.py', 'test_final.py', 'test_full.py', 'test_tilde_caret.py']), ('intervals_v1', 'opencode_nemotron', ['test_impl.py']), ('cron_v1', 'opencode_nemotron', ['test_gov_cron.py']), ('redact_v1', 'opencode_nemotron', ['fix.py', 'test_count.py', 'test_edge.py', 'test_redact.py'])].
- Mean agent wall time: 621 s.

Honest reading: with this many tasks, a difference whose interval spans 0 is not evidence. The tasks were written by the same author as the checks (me), from NI's own needs; they are small single-file functions, not real repository work.
