$ErrorActionPreference = 'SilentlyContinue'
foreach ($f in @('D:\new_automation\scratch\suite_console.log','D:\new_automation\scratch\overnight_console.log')) {
  '============================================================'
  $f
  if (Test-Path $f) {
    $t = Get-Content $f
    'LINES: ' + $t.Count
    '--- tail 50 ---'
    $t | Select-Object -Last 50
  } else { 'MISSING' }
}
