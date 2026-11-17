#!/bin/bash
cd /d/new_automation/natural_intelligence
PY=D:/new_automation/venv/Scripts/python.exe
$PY ni_hub.py fetch --wave 2
$PY ni_hub.py add pollen-robotics/speech-commands-v0.02 audio
$PY ni_hub.py add RapidOrc121/audio-emotion-detection-dataset audio
$PY ni_hub.py add laura63/BirdClefTop20 audio
$PY ni_hub.py add mteb/birdclef25-mini audio
$PY ni_hub.py add mchl914/fma_xsmall audio
echo OVERNIGHT_HUB_DONE
