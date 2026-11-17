# Batch: deep scan + reverse engineering

| site | status | controls | deep exploration | stack | traffic | shortcuts read | recognised as | in the way |
|---|---|---|---|---|---|---|---|---|
| github.com | ok / 238 s | 2113 | 80 clicks, 3 deep, 6 pages | React | 5641 req / 7 api | 0 | file_manager (ambiguous) | - |
| youtube.com | exit 1 | - | - | - | - | - | - | Error: Page.evaluate: TypeError: Failed to set the 'innerHTM |
| twitch.tv | ok / 310 s | 579 | 20 clicks, 3 deep, 6 pages | React, webpack | 10214 req / 13 api | 0 | media_player (ambiguous) | - |
| linkedin.com | ok / 13 s | 0 | 0 clicks, 0 deep, 0 pages | - | 1 req / 0 api | 0 | - | - |
| mail.google.com | ok / 178 s | 379 | 44 clicks, 3 deep, 2 pages | - | 2593 req / 2 api | 0 | settings_panel (candidate) | login wall (only the logged-out page is visible) |
| joinhandshake.com | ok / 280 s | 1152 | 33 clicks, 3 deep, 6 pages | React, Next.js, webpack | 11383 req / 25 api | 0 | media_player (ambiguous) | - |
| naukri.com | ok / 272 s | 588 | 33 clicks, 3 deep, 4 pages | React, webpack, Google Tag Manager dataLayer | 5883 req / 15 api | 0 | media_player (ambiguous) | - |
| reddit.com | ok / 281 s | 763 | 19 clicks, 3 deep, 6 pages | Google Tag Manager dataLayer, Google Analytics | 2876 req / 25 api | 0 | chat_messenger (ambiguous) | - |
| stackoverflow.com | ok / 22 s | 2 | 0 clicks, 0 deep, 0 pages | - | 18 req / 1 api | 0 | browser (candidate) | the site refused this automated browser: HTTP 403 (reported, not worke |
| notion.so | ok / 276 s | 681 | 45 clicks, 3 deep, 2 pages | React, Next.js, Google Tag Manager dataLayer | 12030 req / 15 api | 0 | note_taking (ambiguous) | cookie banner on the page (not clicked) |

Per site: `UNDERSTANDING.md`, `report.json` and pictures in each site's proof folder (path is the last line of its .log).