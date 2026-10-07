$ErrorActionPreference = 'SilentlyContinue'
'--- START APPS (targets) ---'
Get-StartApps | Where-Object { $_.Name -match 'Code|Teams|WhatsApp|Settings|Linked|YouTube|Chrome' } | ForEach-Object { "{0}  ||  {1}" -f $_.Name, $_.AppID }
'--- CDP PORTS ---'
$ports = Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 9222,9229,8081,11434,11435 }
foreach ($p in ($ports | Sort-Object LocalPort -Unique)) { "{0} <- pid {1}" -f $p.LocalPort, $p.OwningProcess }
'--- CHROME EXE ---'
if (Test-Path 'C:\Program Files\Google\Chrome\Application\chrome.exe') { 'chrome: C:\Program Files\Google\Chrome\Application\chrome.exe' }
