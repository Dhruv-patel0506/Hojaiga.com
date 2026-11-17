# Does the pool help? 20 tasks, done cold and with the pool

- cold (live page only): {'success': '0/20', 'success_rate': 0.0, 'mean_clicks_when_ok': 0.0, 'mean_seconds_all': 0.0}
- pool (RAG procedure replayed): {'success': '0/20', 'success_rate': 0.0, 'mean_clicks_when_ok': 0.0, 'mean_seconds_all': 0.0}
- the right procedure was retrieved first: 0/20; among the top 3: 0/20; retrieval 0 ms on average

| # | site | task | cold | pool | what the pool retrieved | pictures |
|---|---|---|---|---|---|---|
| 1 | Openstreetmap | How do I get to User Diaries on Openstreetmap? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_01_cold_fail.png, task_01_pool_fail.png |
| 2 | Npr | How do I get to Television on Npr? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_02_cold_fail.png, task_02_pool_fail.png |
| 3 | Reddit | How do I get to Explore on Reddit? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_03_cold_fail.png, task_03_pool_fail.png |
| 4 | Python | How do I get to Auto Light Dark on Python? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_04_cold_fail.png, task_04_pool_fail.png |
| 5 | Bbc | How do I get to American Football on Bbc? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_05_cold_fail.png, task_05_pool_fail.png |
| 6 | Openstreetmap | How do I get to Rastia__25_16.28.00.gpx on Openstreetmap? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_06_cold_fail.png, task_06_pool_fail.png |
| 7 | Calculator | How do I get to OTHER on Calculator? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_07_cold_fail.png, task_07_pool_fail.png |
| 8 | Coursera | How do I get to Business Intelligence Analyst on Coursera? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_08_cold_fail.png, task_08_pool_fail.png |
| 9 | Proton | How do I get to Pembuat kata sandi on Proton? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_09_cold_fail.png, task_09_pool_fail.png |
| 10 | Npr | How do I get to Gaming on Npr? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_10_cold_fail.png, task_10_pool_fail.png |
| 11 | Ycombinator | How do I get to Hacker News on Ycombinator? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_11_cold_fail.png, task_11_pool_fail.png |
| 12 | Tinypng | How do I get to Get your API key on Tinypng? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_12_cold_fail.png, task_12_pool_fail.png |
| 13 | Pypi | How do I get to Forgot password? on Pypi? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_13_cold_fail.png, task_13_pool_fail.png |
| 14 | Todoist | How do I get to Now SOC2 Type II compliant on Todoist? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_14_cold_fail.png, task_14_pool_fail.png |
| 15 | Ted | I want to see the Entertainment menu on Ted. What do I click? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_15_cold_fail.png, task_15_pool_fail.png |
| 16 | Github | I want to see the Open Source menu on Github. What do I click? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_16_cold_fail.png, task_16_pool_fail.png |
| 17 | Github | I want to see the Community support menu on Github. What do I click? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_17_cold_fail.png, task_17_pool_fail.png |
| 18 | Jwt | I want to see the "sub" menu on Jwt. What do I click? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_18_cold_fail.png, task_18_pool_fail.png |
| 19 | Ebay | I want to see the Expand: Sporting goods menu on Ebay. What do I click? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_19_cold_fail.png, task_19_pool_fail.png |
| 20 | Mozilla | I want to see the 150 footnote disabled menu on Mozilla. What do I click? | no (0 clicks) | no: Error: Page.goto: Protocol error (Page.n (0 clicks) | - | task_20_cold_fail.png, task_20_pool_fail.png |