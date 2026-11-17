# Does the pool help? 20 tasks, done cold and with the pool

- cold (live page only): {'success': '10/20', 'success_rate': 0.5, 'mean_clicks_when_ok': 1.1, 'mean_seconds_all': 8.0}
- pool (RAG procedure replayed): {'success': '13/20', 'success_rate': 0.65, 'mean_clicks_when_ok': 1.2, 'mean_seconds_all': 8.4}
- the right procedure was retrieved first: 18/20; among the top 3: 20/20; retrieval 270 ms on average

| # | site | task | cold | pool | what the pool retrieved | pictures |
|---|---|---|---|---|---|---|
| 1 | Youtube | How do I get to YouTube Home on Youtube? | no (0 clicks) | ok (1 clicks) | Go to the YouTube Home page on Youtube | task_01_cold_fail.png, task_01_pool_ok.png |
| 2 | Openstreetmap | How do I get to Find directions between two points on Openstreetmap? | ok (1 clicks) | ok (1 clicks) | Go to the Find directions between two points page on Openstr | task_02_cold_ok.png, task_02_pool_ok.png |
| 3 | Tinypng | How do I get to More about conversion on Tinypng? | ok (1 clicks) | ok (2 clicks) | Go to the More about conversion page on Tinypng via Tools | task_03_cold_ok.png, task_03_pool_ok.png |
| 4 | Time | How do I get to Make UTC time default on Time? | no (0 clicks) | no: the stored path failed (skipped ['Make U (0 clicks) | Go to the Make UTC time default page on Time | task_04_cold_fail.png, task_04_pool_fail.png |
| 5 | W3schools | How do I get to What is an Exercise? on W3schools? | no (1 clicks) | ok (2 clicks) | Go to the Exercises Practice with interactive exercises Brow | task_05_cold_fail.png, task_05_pool_ok.png |
| 6 | Lobste | How do I get to chat room on Lobste? | no (0 clicks) | no: the stored path failed (skipped ['chat r (0 clicks) | Go to the chat room page on Lobste | task_06_cold_fail.png, task_06_pool_fail.png |
| 7 | Calculator | How do I get to sitemap on Calculator? | ok (1 clicks) | ok (1 clicks) | Go to the sitemap page on Calculator | task_07_cold_ok.png, task_07_pool_ok.png |
| 8 | Ted | How do I get to Oldest on Ted? | no (5 clicks) | no: the stored path failed (skipped ['Sort b (5 clicks) | Go to the Oldest page on Ted via Sort by | task_08_cold_fail.png, task_08_pool_fail.png |
| 9 | Openstreetmap | How do I get to Copyright on Openstreetmap? | ok (1 clicks) | ok (1 clicks) | Go to the Copyright page on Openstreetmap | task_09_cold_ok.png, task_09_pool_ok.png |
| 10 | Tinypng | How do I get to Pricing on Tinypng? | ok (1 clicks) | ok (1 clicks) | Go to the Pricing page on Tinypng | task_10_cold_ok.png, task_10_pool_ok.png |
| 11 | Proton | How do I get to Bisnis on Proton? | ok (2 clicks) | ok (2 clicks) | Go to the Bisnis page on Proton | task_11_cold_ok.png, task_11_pool_ok.png |
| 12 | Bbc | How do I get to Culture on Bbc? | ok (1 clicks) | ok (2 clicks) | Go to the Culture page on Bbc via Open menu | task_12_cold_ok.png, task_12_pool_ok.png |
| 13 | Duckduckgo | How do I get to Learn about DuckDuckGo on Duckduckgo? | ok (1 clicks) | ok (1 clicks) | Go to the Learn about DuckDuckGo page on Duckduckgo | task_13_cold_ok.png, task_13_pool_ok.png |
| 14 | Speedtest | How do I get to Apps on Speedtest? | ok (1 clicks) | ok (1 clicks) | Go to the Apps page on Speedtest | task_14_cold_ok.png, task_14_pool_ok.png |
| 15 | Ted | I want to see the Type to search menu on Ted. What do I click? | no (6 clicks) | no: the stored path failed (skipped []) and  (6 clicks) | Open the Type to search menu on Ted | task_15_cold_fail.png, task_15_pool_fail.png |
| 16 | Desmos | I want to see the Add folder menu on Desmos. What do I click? | no (7 clicks) | no: the stored path failed (skipped ['Add It (5 clicks) | Open the Add folder menu on Desmos via Add Item | task_16_cold_fail.png, task_16_pool_fail.png |
| 17 | Wikipedia | I want to see the Requesting protection menu on Wikipedia. What do I click? | no (0 clicks) | ok (0 clicks) | Open the Requesting protection menu on Wikipedia via Toggle  | task_17_cold_fail.png, task_17_pool_ok.png |
| 18 | Speedtest | I want to see the Email menu on Speedtest. What do I click? | no (2 clicks) | no: the stored path failed (skipped []) and  (6 clicks) | Open the Sign In with Email menu on Speedtest | task_18_cold_fail.png, task_18_pool_fail.png |
| 19 | Khanacademy | I want to see the All boards menu on Khanacademy. What do I click? | ok (1 clicks) | ok (1 clicks) | Open the All boards menu on Khanacademy via Explore | task_19_cold_ok.png, task_19_pool_ok.png |
| 20 | Github | I want to see the Milestones menu on Github. What do I click? | no (8 clicks) | no: the stored path failed (skipped ['Milest (5 clicks) | Open the Milestones menu on Github | task_20_cold_fail.png, task_20_pool_fail.png |