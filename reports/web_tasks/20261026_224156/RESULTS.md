# Does the pool help? 20 tasks, done cold and with the pool

- cold (live page only): {'success': '9/20', 'success_rate': 0.45, 'mean_clicks_when_ok': 1.0, 'mean_seconds_all': 7.7}
- pool (RAG procedure replayed): {'success': '11/20', 'success_rate': 0.55, 'mean_clicks_when_ok': 1.2, 'mean_seconds_all': 7.2}
- the right procedure was retrieved first: 16/20; among the top 3: 18/20; retrieval 516 ms on average

| # | site | task | cold | pool | what the pool retrieved | pictures |
|---|---|---|---|---|---|---|
| 1 | Todoist | How do I get to See full pricing details on Todoist? | ok (1 clicks) | ok (1 clicks) | Go to the See full pricing details page on Todoist via What’ | task_01_cold_ok.png, task_01_pool_ok.png |
| 2 | Github | How do I get to Pricing on Github? | ok (1 clicks) | ok (1 clicks) | Go to the Pricing page on Github | task_02_cold_ok.png, task_02_pool_ok.png |
| 3 | Duckduckgo | How do I get to Learn about DuckDuckGo on Duckduckgo? | ok (1 clicks) | ok (1 clicks) | Go to the Learn about DuckDuckGo page on Duckduckgo | task_03_cold_ok.png, task_03_pool_ok.png |
| 4 | Lobste | How do I get to chat room on Lobste? | no (0 clicks) | no: the stored path failed (skipped ['chat r (0 clicks) | Go to the chat room page on Lobste | task_04_cold_fail.png, task_04_pool_fail.png |
| 5 | Pypi | How do I get to trademarks on Pypi? | ok (1 clicks) | ok (2 clicks) | Go to the PyPI Trademarks page on Pypi | task_05_cold_ok.png, task_05_pool_ok.png |
| 6 | Time | How do I get to Unix clock on Time? | no (0 clicks) | no: the stored path failed (skipped ['menu', (0 clicks) | Go to the Unix clock page on Time via menu | task_06_cold_fail.png, task_06_pool_fail.png |
| 7 | Todoist | How do I get to Calendar Layout on Todoist? | ok (1 clicks) | ok (1 clicks) | Go to the Calendar Layout page on Todoist | task_07_cold_ok.png, task_07_pool_ok.png |
| 8 | Openstreetmap | How do I get to Copyright and License page on Openstreetmap? | ok (1 clicks) | ok (1 clicks) | Go to the Copyright and License page page on Openstreetmap | task_08_cold_ok.png, task_08_pool_ok.png |
| 9 | Python | How do I get to Auto Light Dark on Python? | no (0 clicks) | no: the stored path failed (skipped []) and  (1 clicks) | Go to the Auto Light Dark page on Python | task_09_cold_fail.png, task_09_pool_fail.png |
| 10 | Tinypng | How do I get to Compress on Tinypng? | ok (1 clicks) | ok (1 clicks) | Open the 05. How do I compress my e menu on Tinypng | task_10_cold_ok.png, task_10_pool_ok.png |
| 11 | Youtube | How do I get to YouTube Home on Youtube? | no (0 clicks) | ok (1 clicks) | Go to the YouTube Home page on Youtube | task_11_cold_fail.png, task_11_pool_ok.png |
| 12 | Time | How do I get to Vadodara, Gujarat, India on Time? | no (0 clicks) | no: the stored path failed (skipped ['Vadoda (0 clicks) | Go to the Vadodara, Gujarat, India page on Time | task_12_cold_fail.png, task_12_pool_fail.png |
| 13 | Algolia | How do I get to Search Hacker News on Algolia? | no (4 clicks) | no: the pool had no procedure for the questi (0 clicks) | - | task_13_cold_fail.png, task_13_pool_fail.png |
| 14 | Ebay | How do I get to Motorcycle and scooter parts on Ebay? | no (0 clicks) | no: the stored path failed (skipped ['Expand (0 clicks) | Go to the Motorcycle and scooter parts page on Ebay via Expa | task_14_cold_fail.png, task_14_pool_fail.png |
| 15 | Speedtest | I want to see the Vadodara - NexTech Broadband menu on Speedtest. What do I click? | no (3 clicks) | ok (2 clicks) | Open the Vadodara - NexTech Broadband menu on Speedtest via  | task_15_cold_fail.png, task_15_pool_ok.png |
| 16 | Ebay | I want to see the Expand Watch List menu on Ebay. What do I click? | no (0 clicks) | no: the stored path failed (skipped ['Expand (0 clicks) | Open the Collapse Watch List menu on Ebay via Expand Watch L | task_16_cold_fail.png, task_16_pool_fail.png |
| 17 | Github | I want to see the Push protection bypass con menu on Github. What do I click? | no (6 clicks) | no: the stored path failed (skipped ['Push p (5 clicks) | Open the Push protection bypass con menu on Github | task_17_cold_fail.png, task_17_pool_fail.png |
| 18 | Khanacademy | I want to see the Show password menu on Khanacademy. What do I click? | no (8 clicks) | no: the stored path failed (skipped ['Show p (5 clicks) | Open the Show password menu on Khanacademy | task_18_cold_fail.png, task_18_pool_fail.png |
| 19 | W3schools | I want to see the References menu on W3schools. What do I click? | ok (1 clicks) | ok (1 clicks) | Open the References menu on W3schools | task_19_cold_ok.png, task_19_pool_ok.png |
| 20 | W3schools | I want to see the Tutorials menu on W3schools. What do I click? | ok (1 clicks) | ok (1 clicks) | Open the Tutorials menu on W3schools | task_20_cold_ok.png, task_20_pool_ok.png |