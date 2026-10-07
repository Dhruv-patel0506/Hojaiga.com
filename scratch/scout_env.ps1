$ErrorActionPreference = 'SilentlyContinue'
'--- LISTEN PORTS ---'
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 8081,11434,9229 } | Select-Object LocalPort,OwningProcess | Sort-Object LocalPort -Unique | Format-Table -AutoSize
'--- WINDOWS PACKAGED APPS ---'
Get-ChildItem 'C:\Program Files\WindowsApps' -Directory | Where-Object { $_.Name -match 'VisualStudioCode|Teams|WhatsApp|LinkedIn|Communications' } | ForEach-Object { $_.Name }
'--- APP PATHS ---'
Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths' | Select-Object -Expand PSChildName
'--- EXE COMMANDS ---'
foreach ($a in @('code','whatsapp','msedge')) { $c = Get-Command $a; if ($c) { "{0} -> {1}" -f $a, $c.Source } }
'--- START MENU LINKS ---'
Get-ChildItem 'C:\ProgramData\Microsoft\Windows\Start Menu\Programs' -Recurse -Filter *.lnk | Where-Object { $_.Name -match 'Code|Teams|WhatsApp|LinkedIn' } | ForEach-Object { $_.FullName }
'--- CHROME ---'
Test-Path 'C:\Program Files\Google\Chrome\Application\chrome.exe'
Test-Path 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
