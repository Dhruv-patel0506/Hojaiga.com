$ErrorActionPreference = 'SilentlyContinue'
$f = 'D:\new_automation\scratch\suite_console.log'
$t = Get-Content $f
'================ VERDICT TABLE (TEST -> verdict) ================'
$cur = ''
for ($i=0; $i -lt $t.Count; $i++) {
  $ln = $t[$i]
  if ($ln -match '^(TEST|=====)' -and $ln -match 'TEST ([A-Z0-9]+)') { $cur = $matches[1] }
  if ($ln -match '\[PASS\]' -or $ln -match '\[FAIL\]' -or $ln -match 'BLOCKED') {
    $v = if ($ln -match '\[FAIL\]') { 'FAIL' } elseif ($ln -match '\[PASS\]') { 'PASS' } else { 'BLOCKED' }
    $short = $ln
    if ($short.Length -gt 150) { $short = $short.Substring(0,150) }
    '{0,-8} {1,-8} {2}' -f $v, $cur, $short.Trim()
  }
}
'================ TAIL 15 (the hang point) ================'
$t | Select-Object -Last 15
