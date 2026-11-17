# Does the pool help? 20 tasks, done cold and with the pool

- cold (live page only): {'success': '10/20', 'success_rate': 0.5, 'mean_clicks_when_ok': 1.3, 'mean_seconds_all': 10.5}
- pool (RAG procedure replayed): {'success': '7/20', 'success_rate': 0.35, 'mean_clicks_when_ok': 1.3, 'mean_seconds_all': 8.2}
- the right procedure was retrieved first: 18/20; among the top 3: 19/20; retrieval 233 ms on average

| # | site | task | cold | pool | what the pool retrieved | pictures |
|---|---|---|---|---|---|---|
| 1 | Npr | How do I get to Books on Npr? | ok (2 clicks) | no: step 'Resume Listening NPR 24 Ho' not on (0 clicks) | Go to the Books page on Npr via Resume Listening NPR 24 Ho | task_01_cold_ok.png, task_01_pool_fail.png |
| 2 | Python | How do I get to structures on Python? | no (0 clicks) | no: step 'structures' not on the page (0 clicks) | Go to the structures page on Python | task_02_cold_fail.png, task_02_pool_fail.png |
| 3 | Pypi | How do I get to Forgot password? on Pypi? | no (1 clicks) | no: step 'Forgot password?' not on the page (0 clicks) | Go to the Forgot password? page on Pypi | task_03_cold_fail.png, task_03_pool_fail.png |
| 4 | Time | How do I get to Time here&there on Time? | no (0 clicks) | no: step 'menu' not on the page (0 clicks) | Go to the Time here&there page on Time via menu | task_04_cold_fail.png, task_04_pool_fail.png |
| 5 | Npr | How do I get to Art & Design on Npr? | no (1 clicks) | no: step 'Resume Listening NPR 24 Ho' not on (0 clicks) | Go to the Art & Design page on Npr via Resume Listening NPR  | task_05_cold_fail.png, task_05_pool_fail.png |
| 6 | Coursera | How do I get to For Governments on Coursera? | ok (1 clicks) | ok (1 clicks) | Go to the For Governments page on Coursera | task_06_cold_ok.png, task_06_pool_ok.png |
| 7 | Lobste | How do I get to Comments on Lobste? | ok (1 clicks) | ok (1 clicks) | Go to the Comments page on Lobste | task_07_cold_ok.png, task_07_pool_ok.png |
| 8 | Coursera | How do I get to Software Engineering & IT on Coursera? | ok (3 clicks) | no: the page did not show what the task name (1 clicks) | Open the Software Engineering menu on Coursera | task_08_cold_ok.png, task_08_pool_fail.png |
| 9 | Bbc | How do I get to Search BBC on Bbc? | ok (1 clicks) | no: step 'Search BBC' not on the page (0 clicks) | Go to the Search BBC page on Bbc | task_09_cold_ok.png, task_09_pool_fail.png |
| 10 | Tinypng | How do I get to Get API key on Tinypng? | ok (1 clicks) | ok (2 clicks) | Go to the Get your API key page on Tinypng via Solutions | task_10_cold_ok.png, task_10_pool_ok.png |
| 11 | Openstreetmap | How do I get to About on Openstreetmap? | ok (1 clicks) | ok (1 clicks) | Go to the About page on Openstreetmap | task_11_cold_ok.png, task_11_pool_ok.png |
| 12 | Wikipedia | How do I get to high-risk templates on Wikipedia? | no (5 clicks) | no: step 'high-risk templates' not on the pa (0 clicks) | Go to the high-risk templates page on Wikipedia | task_12_cold_fail.png, task_12_pool_fail.png |
| 13 | Proton | How do I get to Harga on Proton? | no (5 clicks) | no: step 'Harga' not on the page (0 clicks) | Go to the Harga page on Proton | task_13_cold_fail.png, task_13_pool_fail.png |
| 14 | Calculator | How do I get to MATH on Calculator? | ok (1 clicks) | ok (1 clicks) | Go to the MATH page on Calculator | task_14_cold_ok.png, task_14_pool_ok.png |
| 15 | Proton | I want to see the Bagaimana cara membuat kat menu on Proton. What do I click? | no (5 clicks) | no: step 'Bagaimana cara membuat kat' not on (0 clicks) | Open the Bagaimana cara membuat kat menu on Proton | task_15_cold_fail.png, task_15_pool_fail.png |
| 16 | Speedtest | I want to see the Key Terms menu on Speedtest. What do I click? | ok (1 clicks) | ok (2 clicks) | Open the Key Terms menu on Speedtest via Menu menu | task_16_cold_ok.png, task_16_pool_ok.png |
| 17 | Youtube | How do I open Search with your voice on Youtube? | ok (1 clicks) | ok (1 clicks) | Open Search with your voice on Youtube | task_17_cold_ok.png, task_17_pool_ok.png |
| 18 | Duckduckgo | I want to see the We Hatched menu on Duckduckgo. What do I click? | no (5 clicks) | no: step 'Our Story of Protection' not on th (0 clicks) | Open the We Hatched menu on Duckduckgo via Our Story of Prot | task_18_cold_fail.png, task_18_pool_fail.png |
| 19 | Naukri | I want to see the Project Mgmt menu on Naukri. What do I click? | no (0 clicks) | no: step 'Jobs' not on the page (0 clicks) | Open the Project Mgmt menu on Naukri via Jobs | task_19_cold_fail.png, task_19_pool_fail.png |
| 20 | Speedtest | I want to see the Palej - Charotar Broadband menu on Speedtest. What do I click? | no (0 clicks) | no: TimeoutError: Page.goto: Timeout 30000ms (0 clicks) | - | task_20_cold_fail.png, task_20_pool_fail.png |