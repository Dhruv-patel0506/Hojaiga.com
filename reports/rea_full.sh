#!/bin/bash
cd "/d/new_automation/All codes"
export PYTHONPATH="/d/new_automation/All codes"
/d/new_automation/hojaiga_env/Scripts/python.exe -X utf8 -u -W ignore -m core_organs.harvest.rea_sweep run --workers 3 --phase fast > /d/new_automation/reports/rea_full2.log 2>&1
echo REA_FULL_DONE >> /d/new_automation/reports/rea_full2.log
