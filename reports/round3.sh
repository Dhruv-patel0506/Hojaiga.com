#!/bin/bash
# round 3: pick + confirm (consequence) + resume + replan rows from the real crawl, whole sites held out; train from the base model, then evaluate base vs adapter on a balanced held-out slice
cd "/d/new_automation/All codes"
export PYTHONPATH="D:/new_automation;D:/new_automation/All codes"
RUN="D:/new_automation/data/ai_root/harvest/training/runs/run_20261027_mind"
LOGS=/d/new_automation/reports
/d/new_automation/hojaiga_env/Scripts/python.exe -X utf8 -m core_organs.mind.train_rows build --out "$RUN" > $LOGS/round3_prep.log 2>&1
PY=/c/Users/dhruv/AppData/Local/Programs/Python/Python313/python.exe
$PY -X utf8 -u -m core_organs.train_qlora train --model Qwen/Qwen3-VL-2B-Instruct --presplit "$RUN" --steps 700 --min-examples 100 > $LOGS/train_mind.log 2>&1
$PY -X utf8 -u -m core_organs.train_qlora evaluate --model Qwen/Qwen3-VL-2B-Instruct --run "$RUN" --max-examples 300 > $LOGS/eval_mind.log 2>&1
echo ROUND3_DONE >> $LOGS/eval_mind.log
