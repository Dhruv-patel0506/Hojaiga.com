# Resumes the NI overnight run after a reboot. Starts only what is not already running; everything hidden.
# Remove autostart: delete  %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\NI_resume.vbs
Set-Location D:\new_automation\natural_intelligence
Start-Sleep -Seconds 90      # let login, drivers and the GPU settle first
$py = "D:\new_automation\venv\Scripts\python.exe"
function Running($pat) { [bool](Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $pat }) }
if (Test-Path SCHED_STOP) { Remove-Item SCHED_STOP }
if (-not (Running 'ni_sched\.py'))   { Start-Process $py -ArgumentList "-u","ni_sched.py" -WindowStyle Hidden -RedirectStandardOutput sched.out.txt -RedirectStandardError sched.err.txt }
if (-not (Running 'ni_serve\.py'))   { Start-Process $py -ArgumentList "-u","ni_serve.py","--serve","--port","8765","--retrain-every","20" -WindowStyle Hidden -RedirectStandardOutput gate.out.txt -RedirectStandardError gate.err.txt }
if (-not (Running 'report_loop\.py')) { Start-Process $py -ArgumentList "-u","report_loop.py" -WindowStyle Hidden }
# Gate 1: keep a copy of every Claude Code tool call outcome (transcripts are cleaned up after 30 days), then start the
# shadow-mode scorer that the PreToolUse hook calls (port 8766, never blocks).
Start-Process $py -ArgumentList "-X","utf8","cc_harvest.py" -WindowStyle Hidden -Wait -RedirectStandardOutput cc_harvest.out.txt -RedirectStandardError cc_harvest.err.txt
if ((Test-Path data_user\cc\cc_model.pt) -and -not (Running 'cc_serve\.py')) { Start-Process $py -ArgumentList "-X","utf8","-u","cc_serve.py" -WindowStyle Hidden -RedirectStandardOutput cc_serve.out.txt -RedirectStandardError cc_serve.err.txt }
Start-Process $py -ArgumentList "-X","utf8","gov_card.py" -WindowStyle Hidden -RedirectStandardOutput gov_card.out.txt -RedirectStandardError gov_card.err.txt
"resumed $(Get-Date -Format s)" | Add-Content resume_log.txt
