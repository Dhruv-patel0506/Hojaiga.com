# Does the pool help? 20 tasks, done cold and with the pool

- cold (live page only): {'success': '6/8', 'success_rate': 0.75, 'mean_clicks_when_ok': 1.5, 'mean_seconds_all': 5.1}
- pool (RAG procedure replayed): {'success': '6/8', 'success_rate': 0.75, 'mean_clicks_when_ok': 1.7, 'mean_seconds_all': 5.2}
- the right procedure was retrieved first: 8/8; among the top 3: 8/8; retrieval 147 ms on average

| # | site | task | cold | pool | what the pool retrieved | pictures |
|---|---|---|---|---|---|---|
| 1 | Coursera | How do I get to Software Engineering & IT on Coursera? | ok (3 clicks) | ok (3 clicks) | Open the Software Engineering menu on Coursera | task_01_cold_ok.png, task_01_pool_ok.png |
| 2 | Python | How do I get to bytes literal on Python? | no (0 clicks) | no: the stored path failed (skipped ['bytes  (0 clicks) | Go to the bytes literal page on Python | task_02_cold_fail.png, task_02_pool_fail.png |
| 3 | Github | How do I get to Pricing on Github? | ok (1 clicks) | ok (1 clicks) | Go to the Pricing page on Github | task_03_cold_ok.png, task_03_pool_ok.png |
| 4 | Archive | How do I get to Government Documents on Archive? | ok (1 clicks) | ok (2 clicks) | Go to the Government Documents page on Archive via TEXTS | task_04_cold_ok.png, task_04_pool_ok.png |
| 5 | Gov | How do I get to Benefits on Gov? | ok (1 clicks) | ok (1 clicks) | Go to the Benefits page on Gov via Contents | task_05_cold_ok.png, task_05_pool_ok.png |
| 6 | Lichess | I want to see the Quick pairing menu on Lichess. What do I click? | no (3 clicks) | no: the stored path failed (skipped []) and  (4 clicks) | Open the Quick pairing menu on Lichess | task_06_cold_fail.png, task_06_pool_fail.png |
| 7 | Gitlab | How do I open the Resources menu on Gitlab? | ok (1 clicks) | ok (1 clicks) | Hover over Resources on Gitlab to open its menu | task_07_cold_ok.png, task_07_pool_ok.png |
| 8 | Cloudconvert | I want to see the File Conversion API menu on Cloudconvert. What do I click? | ok (2 clicks) | ok (2 clicks) | Open the File Conversion API menu on Cloudconvert via API | task_08_cold_ok.png, task_08_pool_ok.png |