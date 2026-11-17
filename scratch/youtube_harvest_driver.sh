#!/bin/bash
# Sequential YouTube harvest driver: waits for any other harvester process to end, then index (3 kinds) and captions-only process.
# Stops at the first refusal from YouTube (exit code 2). No master-RAG writes (--no-ingest): run `ingest-chains` after training.
cd /d/new_automation || exit 1
export PYTHONPATH="D:/new_automation;D:/new_automation/All codes"
PY="hojaiga_env/Scripts/python.exe -u -X utf8"
H=youtube_video_rag_harvester.py
L=data/ai_root/harvest/youtube_rag
echo "=== waiting for other harvester processes $(date +%H:%M:%S)"
while powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'python.exe' -and \$_.CommandLine -like '*youtube_video_rag_harvester*' }) { exit 0 } else { exit 1 }"; do sleep 30; done
for step in "index --apps-file $L/apps_app.txt --kind app --per-query 3 --budget-minutes 45 --no-ingest" \
            "index --apps-file $L/apps_web_app.txt --kind web_app --per-query 3 --budget-minutes 25 --no-ingest" \
            "index --apps-file $L/apps_website.txt --kind website --per-query 3 --budget-minutes 25 --no-ingest" \
            "process --no-frames --no-ingest --max-videos 100000 --budget-minutes 120"; do
  echo "=== $(date +%H:%M:%S) $step"
  $PY $H $step
  rc=$?
  echo "rc=$rc"
  if [ $rc -eq 2 ]; then echo "STOPPED: refused by YouTube (cool-down is in the ledger)"; break; fi
done
echo "=== DONE $(date +%H:%M:%S)"
