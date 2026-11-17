#!/bin/bash
# wait until the web action rows have grown to 2200, then retrain on all of them (sites held out) and evaluate
cd "/d/new_automation/All codes"
export PYTHONPATH="D:/new_automation;D:/new_automation/All codes"
until [ "$(wc -l < /d/new_automation/data/ai_root/harvest/training/web_action_rows.jsonl)" -ge 2200 ]; do sleep 120; done
RUN="D:/new_automation/data/ai_root/harvest/training/runs/run_20261027_web2"
/d/new_automation/hojaiga_env/Scripts/python.exe -X utf8 -m core_organs.harvest.web_train_prep --out "$RUN" > /d/new_automation/reports/round2_prep.log 2>&1
PY=/c/Users/dhruv/AppData/Local/Programs/Python/Python313/python.exe
$PY -X utf8 -u -m core_organs.train_qlora train --model Qwen/Qwen3-VL-2B-Instruct --presplit "$RUN" --steps 240 --min-examples 100 > /d/new_automation/reports/train_web2.log 2>&1
$PY -X utf8 -u -m core_organs.train_qlora evaluate --model Qwen/Qwen3-VL-2B-Instruct --run "$RUN" > /d/new_automation/reports/eval_web2.log 2>&1
