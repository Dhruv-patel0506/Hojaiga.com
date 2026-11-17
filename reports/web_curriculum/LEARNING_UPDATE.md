# Web curriculum: learning update (2026-10-26, 17:05)

The run is STOPPED (by PID; it keeps its place). 27 sites were learned in 2.49 hours of scanning (14:09 to 17:00), all on rungs 1 and 2 of 5. 98 sites are still on the ladder.

## What was done
| | |
|---|---|
| sites learned | 27 of 125 (rung 1: 22, rung 2: 5) |
| refused / failed | 0 / 0 in this run (LinkedIn and Stack Overflow, refused earlier, are not on this ladder) |
| controls mapped | 72,561 |
| clicks made | 1,352 |
| time per site | 94 to 554 s, mean 332 s |

## What went into the knowledge pool
| | before the web run | now |
|---|---|---|
| web apps with commands in the lexicon | 9 (earlier work) | 35 |
| web commands (menu / page paths such as "Features > Inbox") | about 0 | 1,314 |
| understanding documents stored as retrievable chunks | 0 | 272 chunks |
| hotkey rows | 284 rows overall | unchanged: 0 added (no logged-out site opened a shortcut sheet in this run) |
| site word profiles for kind recognition | 0 | 34 sites, 14 categories |
| cross-site patterns | none | 29 sites (stacks, sign-in, traffic, shortcut sheets) |

Lookups work: a query "css reference" inside MDN finds the "CSS" command (score 0.74); a question about GitHub search retrieves GitHub's understanding document (it ranked the overview first, not the search section).

## Is it getting smarter?  Honest answer: not yet, and here are the numbers
* **Category recognised BEFORE learning from the site:** 6 of 19 scored (32%); first half 3 of 9, second half 3 of 10. Flat.
* **Held-out accuracy (each site predicted from all the others):** top-1 42%, top-2 65% on 31 sites. 14 categories with only 1 to 6 sites each, so this is data-limited, not method-limited. Tried ignoring words only one site uses: worse (29%); reverted.
* **Sections predicted from sibling sites:** 0 of 3 found, twice. The shared sections were topic words from MDN / W3Schools (javascript, css, html), which do not carry over to Python docs or regex101. This prior is not useful yet.
* What does generalise: 13 of the 14 categories now have a word profile; the words that set categories apart are sensible (jobs: job, employers, career; dev_docs: module, reference, documentation; news: culture, arts, listen).

## What the 29 sites have in common (the patterns it found)
* React is on 14 of 29 sites, Google Tag Manager on 9, Google Analytics 7, webpack 7, Next.js 4, jQuery 5.
* 55% ship a PWA manifest. 7% (2 sites) have a keyboard-shortcut sheet; none of the logged-out public sites in this run opened one.
* On average 27% of a page's requests go to third parties (analytics, ads, CDN-like) and about 12 first-party API endpoints are visible per site.
* No site in this run sat behind a login wall or refused the automated browser.

## Known weaknesses
* Content-heavy sites (docs, news, Khan Academy) have thousands of links; the explorer clicks menus and buttons first, so "clicked %" is low (1 to 10%) but the interface itself was covered.
* Canvas-style editors (Photopea: 32 controls, 1 click) are not reachable by this method.
* Many pages produce menus that cannot be re-opened after a navigation; those clicks are logged as unreachable.
* 0 hotkeys learned: shortcut sheets mostly need a login.

## How to continue
```
D:\new_automation\hojaiga_env\Scripts\python.exe -X utf8 -m core_organs.harvest.web_curriculum run --hours 16 --no-backup      (on screen, resumes where it stopped)
... run --headless ...                                                                                                          (same, silently)
... report                                                                                                                      (this table, live)
... rebuild-kind                                                                                                                (re-derive profiles and print held-out accuracy)
... rollback <run stamp>                                                                                                        (undo what a run wrote)
```
Pool backup taken before the run: data/backups/rag_before_web_curriculum_20261026_140929.
