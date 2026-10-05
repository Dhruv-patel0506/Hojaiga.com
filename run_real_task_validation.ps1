$env:PYTHONPATH = "d:\new_automation\All codes"

Write-Host "Running Standard OFF"
python d:\new_automation\test_hojaiga_real_task.py --test standard_off | Out-File -FilePath d:\new_automation\real_task_results.txt -Append

Write-Host "Running Standard ON"
python d:\new_automation\test_hojaiga_real_task.py --test standard_on | Out-File -FilePath d:\new_automation\real_task_results.txt -Append

Write-Host "Running Failure Injection"
python d:\new_automation\test_hojaiga_real_task.py --test fail | Out-File -FilePath d:\new_automation\real_task_results.txt -Append

Write-Host "Running Checkpoint Recovery"
python d:\new_automation\test_hojaiga_real_task.py --test checkpoint | Out-File -FilePath d:\new_automation\real_task_results.txt -Append

Write-Host "Done"
