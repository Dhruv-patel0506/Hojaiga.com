# Does the pool help? 20 tasks, done cold and with the pool

- cold (live page only): {'success': '4/8', 'success_rate': 0.5, 'mean_clicks_when_ok': 1.5, 'mean_seconds_all': 6.9}
- pool (RAG procedure replayed): {'success': '6/8', 'success_rate': 0.75, 'mean_clicks_when_ok': 1.7, 'mean_seconds_all': 7.5}
- the right procedure was retrieved first: 7/8; among the top 3: 7/8; retrieval 224 ms on average

| # | site | task | cold | pool | what the pool retrieved | pictures |
|---|---|---|---|---|---|---|
| 1 | Microsoft | How do I get to Earn credentials on Microsoft? | ok (1 clicks) | ok (2 clicks) | Go to the Earn credentials page on Microsoft via Learn Azure | task_01_cold_ok.png, task_01_pool_ok.png |
| 2 | Vimeo | How do I get to Live Streaming on Vimeo? | ok (1 clicks) | ok (1 clicks) | Go to the Live Streaming page on Vimeo | task_02_cold_ok.png, task_02_pool_ok.png |
| 3 | Substack | How do I get to Business on Substack? | no (0 clicks) | ok (1 clicks) | Go to the Business page on Substack via Explore | task_03_cold_fail.png, task_03_pool_ok.png |
| 4 | Ebay | How do I get to Motorcycle and scooter parts on Ebay? | no (0 clicks) | no: the stored path failed (skipped ['Expand (0 clicks) | Go to the Motorcycle and scooter parts page on Ebay via Expa | task_04_cold_fail.png, task_04_pool_fail.png |
| 5 | W3schools | How do I get to C Powerful low-level programming on W3schools? | no (1 clicks) | ok (2 clicks) | Go to the C Powerful low-level programming page on W3schools | task_05_cold_fail.png, task_05_pool_ok.png |
| 6 | Tradingview | I want to see the Open user menu menu on Tradingview. What do I click? | ok (1 clicks) | ok (1 clicks) | Open the Open user menu menu on Tradingview | task_06_cold_ok.png, task_06_pool_ok.png |
| 7 | Github | I want to see the Projects menu on Github. What do I click? | no (8 clicks) | no: the stored path failed (skipped ['Projec (5 clicks) | Open the Projects menu on Github | task_07_cold_fail.png, task_07_pool_fail.png |
| 8 | Github | I want to see the GitHub Connect menu on Github. What do I click? | ok (3 clicks) | ok (3 clicks) | Open the GitHub Connect menu on Github | task_08_cold_ok.png, task_08_pool_ok.png |