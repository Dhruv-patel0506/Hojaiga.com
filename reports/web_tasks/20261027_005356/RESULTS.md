# Does the pool help? 20 tasks, done cold and with the pool

- cold (live page only): {'success': '5/8', 'success_rate': 0.62, 'mean_clicks_when_ok': 1.6, 'mean_seconds_all': 6.4}
- pool (RAG procedure replayed): {'success': '5/8', 'success_rate': 0.62, 'mean_clicks_when_ok': 1.2, 'mean_seconds_all': 5.5}
- the right procedure was retrieved first: 8/8; among the top 3: 8/8; retrieval 147 ms on average

| # | site | task | cold | pool | what the pool retrieved | pictures |
|---|---|---|---|---|---|---|
| 1 | Postgresql | How do I get to Support on Postgresql? | ok (1 clicks) | ok (1 clicks) | Go to the Support page on Postgresql | task_01_cold_ok.png, task_01_pool_ok.png |
| 2 | Gitlab | How do I get to Learn more on Gitlab? | no (6 clicks) | no: the stored path failed (skipped ['Learn  (5 clicks) | Go to the Learn more page on Gitlab | task_02_cold_fail.png, task_02_pool_fail.png |
| 3 | Pypi | How do I get to Forgot password? on Pypi? | no (1 clicks) | no: the stored path failed (skipped ['Forgot (1 clicks) | Go to the Forgot password? page on Pypi | task_03_cold_fail.png, task_03_pool_fail.png |
| 4 | Mastodon | How do I get to About on Mastodon? | ok (1 clicks) | ok (1 clicks) | Go to the About page on Mastodon | task_04_cold_ok.png, task_04_pool_ok.png |
| 5 | Bbc | How do I get to Disability Sport on Bbc? | ok (4 clicks) | ok (2 clicks) | Go to the Disability Sport page on Bbc via More | task_05_cold_ok.png, task_05_pool_ok.png |
| 6 | Diagrams | I want to see the Options menu on Diagrams. What do I click? | no (3 clicks) | no: the stored path failed (skipped []) and  (4 clicks) | Open the Options menu on Diagrams | task_06_cold_fail.png, task_06_pool_fail.png |
| 7 | Tinypng | I want to see the Solutions menu on Tinypng. What do I click? | ok (1 clicks) | ok (1 clicks) | Open the Solutions menu on Tinypng | task_07_cold_ok.png, task_07_pool_ok.png |
| 8 | Mit | How do I open Open feedback survey on Mit? | ok (1 clicks) | ok (1 clicks) | Open Open feedback survey on Mit | task_08_cold_ok.png, task_08_pool_ok.png |