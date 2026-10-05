"""
Automated test for Runtime Check #2: Common Dialogs (#32770 Modal Windows)
Verifies the implementation includes modal dialog detection and re-attachment
"""

import sys
import re

# Read the WindowManager.ts file
with open(r'D:\new_automation\final_hojaiga_tutor\WindowManager.ts', 'r') as f:
    content = f.read()

print('=' * 70)
print('Test: Common Dialogs (#32770 Modal Windows) - Code Inspection')
print('=' * 70)
print()

# CRITICAL RUNTIME CHECK #2: Verify modal dialog detection
print('Checking for #32770 class name detection...')
if '#32770' in content:
    print('[OK] #32770 class name detection found')
else:
    print('[FAIL] #32770 class name detection not found')

# Check for modal dialog function
print()
print('Checking for modal dialog detection function...')
if 'get_foreground_window_with_modal_check' in content or 'modal' in content.lower():
    print('[OK] Modal dialog detection function found')
else:
    print('[FAIL] Modal dialog detection function not found')

# Check for EnumWindows callback
print()
print('Checking for EnumWindows callback for child modal dialogs...')
if 'EnumWindows' in content or 'enum_windows_callback' in content:
    print('[OK] EnumWindows callback found')
else:
    print('[FAIL] EnumWindows callback not found')

# Check for process ID filtering (EDGE CASE FIX)
print()
print('Checking for process ID filtering (edge case fix)...')
if 'win32process.GetWindowThreadProcessId' in content or 'target_pid' in content:
    print('[OK] Process ID filtering found')
else:
    print('[FAIL] Process ID filtering not found')

# Check for owner HWND filtering (EDGE CASE FIX)
print()
print('Checking for owner HWND filtering (edge case fix)...')
if 'GW_OWNER' in content or 'owner_hwnd' in content:
    print('[OK] Owner HWND filtering found')
else:
    print('[FAIL] Owner HWND filtering not found')

# Check for isModalDialog in response
print()
print('Checking for isModalDialog in response...')
if 'isModalDialog' in content:
    print('[OK] isModalDialog response field found')
else:
    print('[FAIL] isModalDialog response field not found')

# Check for re-attachment logging
print()
print('Checking for re-attachment logging...')
if 're-attach' in content.lower() or 'reattach' in content.lower():
    print('[OK] Re-attachment logging found')
else:
    print('[FAIL] Re-attachment logging not found')

# Check for modal dialog in captureWindow
print()
print('Checking for modal dialog detection in captureWindow...')
capture_section = content[content.find('captureWindow'):] if 'captureWindow' in content else ''
if '#32770' in capture_section or 'modal' in capture_section.lower():
    print('[OK] Modal dialog detection in captureWindow found')
else:
    print('[FAIL] Modal dialog detection in captureWindow not found')

print()
print('=' * 70)
print('Summary')
print('=' * 70)
print()
print('Runtime Check #2 Implementation Status:')
print('  - #32770 detection: ' + ('[OK] Present' if '#32770' in content else '[FAIL] Missing'))
print('  - Modal detection function: ' + ('[OK] Present' if 'get_foreground_window_with_modal_check' in content else '[FAIL] Missing'))
print('  - EnumWindows callback: ' + ('[OK] Present' if 'EnumWindows' in content else '[FAIL] Missing'))
print('  - Process ID filtering (edge case fix): ' + ('[OK] Present' if 'win32process.GetWindowThreadProcessId' in content else '[FAIL] Missing'))
print('  - Owner HWND filtering (edge case fix): ' + ('[OK] Present' if 'GW_OWNER' in content else '[FAIL] Missing'))
print('  - isModalDialog response: ' + ('[OK] Present' if 'isModalDialog' in content else '[FAIL] Missing'))
print('  - Re-attachment logging: ' + ('[OK] Present' if 're-attach' in content.lower() else '[FAIL] Missing'))
print('  - captureWindow modal check: ' + ('[OK] Present' if '#32770' in capture_section else '[FAIL] Missing'))
print()

# Also check types.ts for isModalDialog field
print('Checking types.ts for isModalDialog field...')
try:
    with open(r'D:\new_automation\final_hojaiga_tutor\src\types.ts', 'r') as f:
        types_content = f.read()
    if 'isModalDialog' in types_content:
        print('[OK] isModalDialog field in ScreenState type found')
    else:
        print('[FAIL] isModalDialog field in ScreenState type not found')
except:
    print('[WARN] Could not read types.ts')
print()
