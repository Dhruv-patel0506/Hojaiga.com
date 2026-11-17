# Does the pool help? 20 tasks, done cold and with the pool

- cold (live page only): {'success': '6/8', 'success_rate': 0.75, 'mean_clicks_when_ok': 1.7, 'mean_seconds_all': 8.2}
- pool (RAG procedure replayed): {'success': '6/8', 'success_rate': 0.75, 'mean_clicks_when_ok': 1.7, 'mean_seconds_all': 7.2}
- the right procedure was retrieved first: 7/8; among the top 3: 8/8; retrieval 398 ms on average

| # | site | task | cold | pool | what the pool retrieved | pictures |
|---|---|---|---|---|---|---|
| 1 | Coursera | How do I get to Business Intelligence Analyst on Coursera? | ok (1 clicks) | ok (2 clicks) | Go to the Business Intelligence Analyst page on Coursera via | task_01_cold_ok.png, task_01_pool_ok.png |
| 2 | Weather | How do I get to Weather Safety on Weather? | ok (2 clicks) | ok (2 clicks) | Go to the Weather Safety page on Weather | task_02_cold_ok.png, task_02_pool_ok.png |
| 3 | Lobste | How do I get to Recent on Lobste? | ok (1 clicks) | ok (1 clicks) | Go to the Recent page on Lobste | task_03_cold_ok.png, task_03_pool_ok.png |
| 4 | Loc | How do I get to About on Loc? | ok (1 clicks) | ok (2 clicks) | Go to the About page on Loc via Global Menu | task_04_cold_ok.png, task_04_pool_ok.png |
| 5 | Wikipedia | How do I get to View source on Wikipedia? | ok (1 clicks) | ok (1 clicks) | Go to the View source page on Wikipedia | task_05_cold_ok.png, task_05_pool_ok.png |
| 6 | Substack | How do I open Subscriptions on Substack? | no (0 clicks) | no: the stored path failed (skipped ['Subscr (0 clicks) | Open Subscriptions on Substack | task_06_cold_fail.png, task_06_pool_fail.png |
| 7 | Notion | I want to see the Pricing menu on Notion. What do I click? | ok (4 clicks) | ok (2 clicks) | Open the Click to show simpler choices menu on Notion via Pr | task_07_cold_ok.png, task_07_pool_ok.png |
| 8 | Github | I want to see the Issues Plan and track work menu on Github. What do I click? | no (7 clicks) | no: the stored path failed (skipped ['Issues (5 clicks) | Open the Issues Plan and track work menu on Github | task_08_cold_fail.png, task_08_pool_fail.png |