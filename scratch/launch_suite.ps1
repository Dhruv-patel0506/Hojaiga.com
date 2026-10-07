# Launch a suite run detached, with its own stdout/stderr files, and print the child pid.
# A file, not an inline -Command: the outer shell strips `$var` from inline PowerShell, which
# cost several turns in this session.
param(
    [Parameter(Mandatory = $true)][string]$TestIds,
    [Parameter(Mandatory = $true)][string]$Tag,
    [string]$TimeoutS = '600'
)

$env:PYTHONPATH = 'D:\new_automation;D:\new_automation\All codes'
$env:HOJAIGA_TEST_TIMEOUT_S = $TimeoutS

# 'ALL' runs every registered test: --only writes a _partial results file, and the owed proof is a
# complete run of the whole suite appended to the normal log.
$argList = @('-X', 'utf8', '-u', 'run_system_intelligence_tests.py', '--e2e')
if ($TestIds -ne 'ALL') { $argList += @('--only', $TestIds) }

$proc = Start-Process -FilePath 'D:\new_automation\hojaiga_env\Scripts\python.exe' `
    -ArgumentList $argList `
    -WorkingDirectory 'D:\new_automation\All codes\core_organs' `
    -NoNewWindow `
    -RedirectStandardOutput "D:\new_automation\_$Tag.out" `
    -RedirectStandardError "D:\new_automation\_$Tag.err" `
    -PassThru

"launched pid=$($proc.Id) tag=$Tag ids=$TestIds timeout=$TimeoutS"
