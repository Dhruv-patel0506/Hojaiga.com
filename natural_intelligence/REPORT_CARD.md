# Agents' report card (2026-11-17, last 7 days vs before)

Source: 18236 real Claude Code actions on this machine. Autonomy = earned level from the lower 95% bound of success (unit: agent x action class). Policy approved by a human: **yes**.

| agent | action class | actions (week) | failure rate week | failure rate before | lower bound of success | level | drift | top failure reasons |
|---|---|---|---|---|---|---|---|---|
| claude-sonnet-5-5 | shell | 5 | 0.0% | 3.7% | 0.914 | 2 worker | - | task_failed 207, unsafe_blocked 54, malformed_action 34 |
| claude-sonnet-5-5 | reversible_write | 0 | - | 0.9% | 0.976 | 3 senior | - | wrong_fact 13, wrong_scope 8, task_failed 5 |
| claude-sonnet-5-5 | read | 0 | - | 1.2% | 0.960 | 3 senior | - | task_failed 13, wrong_fact 6, malformed_action 3 |
| claude-opus-5-5 | shell | 173 | 7.5% | 2.4% | 0.889 | 1 junior | - | task_failed 46, malformed_action 4, wrong_fact 3 |
| claude-opus-5-5 | reversible_write | 156 | 0.0% | 1.6% | 0.986 | 4 lead | - | wrong_fact 6, wrong_scope 2, task_failed 1 |
| claude-sonnet-5-5 | other | 0 | - | 4.4% | 0.896 | 1 junior | - | task_failed 12, too_slow 8, unsafe_blocked 1 |
| claude-sonnet-5-5 | plan_ui | 1 | 0.0% | 0.2% | 0.973 | 3 senior | - | malformed_action 1 |
| claude-sonnet-5-5 | ui_action | 0 | - | 1.1% | 0.965 | 3 senior | - | too_slow 2, malformed_action 1 |
| claude-sonnet-5-5 | process_control | 1 | 0.0% | 9.5% | 0.883 | 1 junior | - | task_failed 18 |
| claude-opus-5-5 | read | 37 | 0.0% | 6.3% | 0.925 | 2 worker | - | task_failed 7, too_slow 1, wrong_fact 1 |
| claude-opus-5-5 | plan_ui | 69 | 0.0% | 0.9% | 0.982 | 3 senior | - | task_failed 1 |
| claude-sonnet-5-5 | destructive_local | 0 | - | 7.2% | 0.900 | 2 worker | - | task_failed 8, unsafe_blocked 2, malformed_action 1 |
| claude-sonnet-5-5 | external_publish | 0 | - | 1.8% | 0.950 | 2 worker | - | task_failed 1 |
| claude-opus-5-5 | process_control | 8 | 0.0% | 22.2% | 0.778 | 0 intern | - | task_failed 6 |
| claude-opus-5-5 | destructive_local | 5 | 20.0% | 0.0% | 0.901 | 2 worker | - | task_failed 1 |
| claude-opus-5-5 | other | 12 | 8.3% | 0.0% | 0.883 | 1 junior | - | wrong_fact 1 |
| claude-sonnet-5-5 | secret_exposure | 0 | - | 0.0% | 0.969 | 2 worker | - |  |
| claude-haiku-4-5-20251001 | reversible_write | 0 | - | 0.0% | 0.980 | 1 junior | - |  |
| claude-fable-5-1 | other | 15 | 20.0% | - | 0.777 | 0 intern | - | task_failed 3 |
| claude-fable-5-1 | shell | 11 | 9.1% | - | 0.843 | 1 junior | - | task_failed 1 |

Irreversible classes (publish, delete, money, secrets) need a human at every level, whatever the record.

## Live shadow verdicts (logged before each action, never enforced)

265 actions scored, 265 with a known outcome, 11 failed. Verdicts (as if approved): {'proceed': 146, 'verify': 114, 'ask_human': 5}.
Escalated and failed: 10 of 119 escalations; failures escalated: 10 of 11.

## NI's own record (L18)

Gate calibration on held-out actions: ECE 0.13131 raw -> 0.00691 after the adopted map; autonomy budget 0.7995. Ledger: {'ok': False, 'n': 89, 'broken_at': 89, 'decisions': 53, 'outcomes': 36, 'resolved_fraction': None}.

