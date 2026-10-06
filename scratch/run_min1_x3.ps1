# MIN1 three times in a row, sequentially, so a timing race is measured rather than asserted.
# Separate processes: a shared process would carry UIA/COM state from run to run and flatter the result.
$env:PYTHONPATH = 'D:\new_automation;D:\new_automation\All codes'
$env:HOJAIGA_TEST_TIMEOUT_S = '300'
Set-Location 'D:\new_automation\All codes\core_organs'
for ($i = 3; $i -le 5; $i++) {
    "=== pass $i starting $(Get-Date -Format HH:mm:ss) ==="
    & 'D:\new_automation\hojaiga_env\Scripts\python.exe' -X utf8 -u `
        'D:\new_automation\All codes\core_organs\run_system_intelligence_tests.py' `
        --e2e --only MIN1 1> "D:\new_automation\_m$i.out" 2> "D:\new_automation\_m$i.err"
    "=== pass $i exit $LASTEXITCODE done $(Get-Date -Format HH:mm:ss) ==="
}
