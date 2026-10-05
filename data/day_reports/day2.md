# Day report day2

**3 done / 3 failed / 2 waiting for you**  (8 ticket(s); complete=True)

## Done (independently verified)

- #0 `a` write the weekly report - DONE: verified
  - evidence: scripted DONE for a (execution #1) | independent check passed
- #1 `b` open the spreadsheet and add a column - DONE: verified
  - evidence: scripted DONE for b (execution #2) | independent check passed
- #7 `h` rename the heading - DONE: verified
  - evidence: scripted DONE for h (execution #1) | independent check passed

## Failed

- #2 `c` press the totals button - FAILED: executor raised RuntimeError: scripted failure
- #4 `e` summarize the notes - TIMEOUT: watchdog: no result within 3s; the queue moved on
- #6 `g` export the chart - FAILED: executor claimed DONE but the independent check failed: the output file is not on disk
  - evidence: scripted DONE for g (execution #1) | the output file is not on disk

## Waiting for you

- #3 `d` delete all files in the downloads folder - ESCALATED: destructive/irreversible class (E2): queued for a human, not executed
- #5 `f` send the invoice to the customer - ESCALATED: destructive/irreversible class (E2): queued for a human, not executed
