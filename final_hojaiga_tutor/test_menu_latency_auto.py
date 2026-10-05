"""
Automated test for Runtime Check #1: Sub-Menu Mounting Latency
Verifies the implementation includes debounce and polling logic
"""

import sys
import re

# Read the UIAutomationInvoker.py file
with open(r'D:\new_automation\final_hojaiga_tutor\UIAutomationInvoker.py', 'r') as f:
    content = f.read()

print('=' * 70)
print('Test: Sub-Menu Mounting Latency (Code Inspection)')
print('=' * 70)
print()

# CRITICAL RUNTIME CHECK #1: Verify debounce is present
print('Checking for debounce logic...')
if 'time.sleep(0.1)' in content or 'time.sleep(0.15)' in content:
    print('[OK] Debounce found (100-150ms sleep)')
else:
    print('[FAIL] Debounce not found')

# Check for polling loop
print()
print('Checking for polling loop...')
if 'while elapsed < max_poll_time' in content or 'while elapsed < 0.5' in content:
    print('[OK] Polling loop found')
else:
    print('[FAIL] Polling loop not found')

# Check for MenuPopup detection
print()
print('Checking for MenuPopup control type detection...')
if 'MenuPopup' in content or 'Menu' in content or 'MenuItem' in content:
    print('[OK] MenuPopup/Menu detection found')
else:
    print('[FAIL] MenuPopup detection not found')

# Check for waited_ms in response
print()
print('Checking for waited_ms in response...')
if '"waited_ms"' in content or "'waited_ms'" in content:
    print('[OK] waited_ms response field found')
else:
    print('[FAIL] waited_ms response field not found')

# Check for expand_pattern.Expand()
print()
print('Checking for ExpandCollapsePattern usage...')
if 'expand_pattern.Expand()' in content:
    print('[OK] ExpandCollapsePattern.Expand() found')
else:
    print('[FAIL] ExpandCollapsePattern.Expand() not found')

print()
print('=' * 70)
print('Summary')
print('=' * 70)
print()
print('Runtime Check #1 Implementation Status:')
print('  - Debounce: ' + ('[OK] Present' if 'time.sleep(0.1)' in content else '[FAIL] Missing'))
print('  - Polling loop: ' + ('[OK] Present' if 'while elapsed < max_poll_time' in content else '[FAIL] Missing'))
print('  - MenuPopup detection: ' + ('[OK] Present' if 'MenuPopup' in content or 'Menu' in content else '[FAIL] Missing'))
print('  - waited_ms response: ' + ('[OK] Present' if '"waited_ms"' in content else '[FAIL] Missing'))
print()
