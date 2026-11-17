# Branch run on a real task: coverage_v1 (2026-11-14 19:09)

Task: `D:\new_automation\natural_intelligence\data_user\gov\tasks\coverage_v1` (SPEC.md + empty stub). Hidden check: test_coverage.py (the agents never saw it). Every branch ran on its own copy; original unchanged: **True**. Branch record: `data_user/gov/branches/1114_190900_7c2f90.json`.

| branch (agent) | vendor / model | stated confidence | hidden check passed | quality | lines changed | NI's reason |
|---|---|---|---|---|---|---|
| claude_code_sonnet | Anthropic Claude Code (claude -p, sonnet) | - | no | 0.00 | 0 | failed: transform error RuntimeError('agent produced no code: headless run could not authenticate (401 via the session gateway; ECONNREFUSED direct)') |
| copilot_claude_sonnet | OpenCode + GitHub Copilot claude-sonnet-5.5 | - | no | 0.00 | 0 | failed: transform error RuntimeError('agent produced no code: Copilot rejected the configured personal access token') |
| opencode_deepseek | OpenCode + deepseek-v4.1-flash (free) | 88 | yes | 1.00 | 62 | recommended |
| opencode_glm | OpenCode + glm-5.3-flash (free) | 92 | yes | 1.00 | 71 | dominated by opencode_deepseek (no better beyond noise anywhere, worse beyond noise somewhere) |
| opencode_mimo | OpenCode + mimo-v2.6-flash (free) | 90 | yes | 1.00 | 59 | on the Pareto front; P_best 0.50 |
| opencode_nemotron | OpenCode + nemotron-3.5-lightning (free) | - | no | 0.78 | 63 | failed: check failed (exit 1): 
FAILED: considered: binding without colon
FAILED: covered count (case-insensitive, colon prefix)
FAILED: coverage value
FAILED: missed lower-cased and counted
 |

| policy | picks | hidden-check quality of the pick |
|---|---|---|
| first branch (incumbent agent) | claude_code_sonnet | 0.00 |
| most confident agent | opencode_glm | 1.00 |
| NI branch engine | opencode_deepseek | 1.00 |

Best achievable quality among the branches: 1.00. NI verdict: **recommend_equivalent**; P_best {'claude_code_sonnet': 0.0, 'copilot_claude_sonnet': 0.0, 'opencode_deepseek': 0.5, 'opencode_glm': 0.0, 'opencode_mimo': 0.5, 'opencode_nemotron': 0.0}.

NI's message:

```
Pick 'opencode_deepseek'. The leading branches are equivalent within measurement noise (expected loss from picking now 0.000 < 0.05), so asking you would not be worth your time.
- claude_code_sonnet (Anthropic Claude Code (claude -p, sonnet)): check FAILED (quality 0.00), 0.45s, 0 lines changed -> failed: transform error RuntimeError('agent produced no code: headless run could not authenticate (401 via the session gateway; ECONNREFUSED direct)')
- copilot_claude_sonnet (OpenCode + GitHub Copilot claude-sonnet-5.5): check FAILED (quality 0.00), 0.44s, 0 lines changed -> failed: transform error RuntimeError('agent produced no code: Copilot rejected the configured personal access token')
- opencode_deepseek (OpenCode + deepseek-v4.1-flash (free)): check passed (quality 1.00), 0.27s, 62 lines changed -> recommended
- opencode_glm (OpenCode + glm-5.3-flash (free)): check passed (quality 1.00), 0.24s, 71 lines changed -> dominated by opencode_deepseek (no better beyond noise anywhere, worse beyond noise somewhere)
- opencode_mimo (OpenCode + mimo-v2.6-flash (free)): check passed (quality 1.00), 0.27s, 59 lines changed -> on the Pareto front; P_best 0.50
- opencode_nemotron (OpenCode + nemotron-3.5-lightning (free)): check FAILED (quality 0.78), 0.27s, 63 lines changed -> failed: check failed (exit 1): 
FAILED: considered: binding without colon
FAILED: covered count (case-insensitive, colon prefix)
FAILED: coverage value
FAILED: missed lower-cased and counted

Original unchanged: True.
```

Honest reading: NI's advantage here comes from RUNNING the check on every branch instead of trusting one agent or a stated confidence. One task is a demonstration, not evidence; the claim needs many tasks (section 5.1 test).

