| tier | target | cold s | warm s | controls | sections | commands | deepen | focus ms | expose ms | criteria failed |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|
| T1 easy | Notepad | 48.08 | 20.73 | 94 | 15 | 36 | dropdowns=4,dropdowns=4 | 41 | 62 | restored |
| T1 easy | Calculator | 9.6 | 8.39 | 3 | 1 | 5 |  | 0 | 22 | layout>=20, sections>=3 |
| T2 moderate | Paint | 50.99 | 8.96 | 401 | 18 | 34 | dropdowns=4,dropdowns=4,scrollables=2 | 40 | 48 | none |
| T2 moderate | Sticky Notes | 9.42 | 8.42 | 6 | 2 | 5 |  | 26 | 23 | layout>=20, sections>=3 |
| T3 medium | File Explorer | 55.7 | 31.12 | 418 | 32 | 0 | dropdowns=2,dropdowns=2,tree=11,scrollab | 41 | 48819 | menus/cmds, expose<=80ms |
| T3 medium | Settings | 46.86 |  | None | None | None |  | - | - | scanned, layout>=20, sections>=3, menus/cmds, hidden ERR: no window (not running and could not be launched) |
| T4 hard | Visual Studio Code | 39.13 | 13.71 | 184 | 17 | 11 | dropdowns=4,dropdowns=4,scrollables=1 | 28 | 0 | none |
| T4 hard | OBS Studio | 186.24 | 12.49 | 113 | 40 | 65 | dropdowns=2,dropdowns=2 | 17262 | 42 | focus<=80ms |
| T5 complex | Word | 26.35 | 24.6 | 55 | 12 | 0 |  | 0 | 25 | menus/cmds |
| T5 complex | Excel | 46.58 |  | None | None | 0 |  | 0 | 0 | scanned, layout>=20, sections>=3, menus/cmds, hidden ERR: COMError: (-2147220991, 'An event was unable to invoke any o |
| T5 complex | PowerPoint | 46.2 |  | None | None | 0 |  | 0 | 0 | scanned, layout>=20, sections>=3, menus/cmds, hidden ERR: COMError: (-2147220991, 'An event was unable to invoke any o |
| T6 deep | Visual Studio 2022 | 45.96 |  | None | None | 0 |  | 0 | 0 | scanned, layout>=20, sections>=3, menus/cmds, hidden ERR: COMError: (-2147220991, 'An event was unable to invoke any o |
| W1 easy | https://example.org | 2.65 | 2.71 | 1 | 2 | 1 |  | - | - | controls>=20, sections>=3 |
| W2 moderate | https://news.ycombinator.com | 5.29 | 5.14 | 233 | 6 | 197 | scroll=1 | - | - | none |
| W3 medium | https://en.wikipedia.org/wiki/Notepad | 9.13 | 8.41 | 539 | 50 | 427 | disclosures=4,disclosures=4,scroll=6 | - | - | none |
| W4 hard | https://github.com/microsoft/vscode | 12.07 | 11.31 | 569 | 36 | 347 | disclosures=10,disclosures=10,scroll=6 | - | - | none |
| W4 hard | https://www.youtube.com | 6.66 | 6.68 | 60 | 10 | 51 | disclosures=2,disclosures=2 | - | - | none |
| W5 complex | https://excalidraw.com | 4.62 | 4.03 | 53 | 9 | 37 | disclosures=2,disclosures=1 | - | - | none |
| W6 deep | https://app.diagrams.net | 4.89 | 5.23 | 22 | 5 | 14 |  | - | - | none |
| W7 logged-in | https://mail.google.com/mail/u/0/ | 3.47 | 8.53 | 17 | 5 | 9 |  | - | - | controls>=20 |
| W7 logged-in | https://www.youtube.com | 6.91 | 6.76 | 60 | 10 | 51 | disclosures=2,disclosures=2 | - | - | none |