$ErrorActionPreference = 'SilentlyContinue'
'--- python / llama procs ---'
Get-Process python,pythonw,llama-server -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,StartTime,@{n='CPU_s';e={[math]::Round($_.CPU,0)}},@{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB,0)}} | Format-Table -AutoSize
'--- suite log write time & size ---'
$f = 'D:\new_automation\scratch\suite_console.log'
$fi = Get-Item $f
'LastWrite: ' + $fi.LastWriteTime + '   Now: ' + (Get-Date) + '   SizeKB: ' + [math]::Round($fi.Length/1KB,0)
'--- how many TEST blocks started vs decided ---'
$t = Get-Content $f
'started: ' + (($t | Select-String -Pattern '^\s*$' -AllMatches).Count)
'TEST headers: ' + (($t | Where-Object { $_ -match 'TEST [A-Z]' }).Count)
'PASS lines: ' + (($t | Where-Object { $_ -match '\[PASS\]' }).Count)
'FAIL lines: ' + (($t | Where-Object { $_ -match '\[FAIL\]' }).Count)
'BLOCKED lines: ' + (($t | Where-Object { $_ -match 'BLOCKED' }).Count)
'--- any TEST headers with no PASS/FAIL after (still open) ---'
$t | Where-Object { $_ -match 'TEST [A-Z]' } | Select-Object -Last 6
