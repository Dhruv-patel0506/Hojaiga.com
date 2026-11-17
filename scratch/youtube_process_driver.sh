#!/bin/bash
# Captions-only processing, slow pace. Waits for the ledger's cool-down (set by a YouTube refusal) to pass, then runs; stops at the next refusal.
cd /d/new_automation || exit 1
export PYTHONPATH="D:/new_automation;D:/new_automation/All codes"
PY="hojaiga_env/Scripts/python.exe -u -X utf8"
H=youtube_video_rag_harvester.py
until_ts=$($PY -c "import sqlite3;print(int(float(sqlite3.connect('data/ai_root/harvest/youtube_rag/ledger.db').execute(\"select v from meta where k='blocked_until'\").fetchone()[0])))")
echo "=== $(date +%H:%M:%S) cool-down ends at epoch $until_ts"
while [ "$(date +%s)" -le "$((until_ts + 120))" ]; do sleep 30; done
echo "=== $(date +%H:%M:%S) process --pace 25,45"
$PY $H process --no-frames --no-ingest --pace 25,45 --max-videos 100000 --budget-minutes 240
rc=$?
echo "rc=$rc"
if [ $rc -eq 2 ]; then echo "STOPPED: refused by YouTube (cool-down is in the ledger)"; fi
echo "=== DONE $(date +%H:%M:%S)"
