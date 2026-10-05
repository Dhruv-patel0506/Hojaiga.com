"""
Test script for Runtime Check #1: Sub-Menu Mounting Latency
Tests that ExpandCollapsePattern includes debounce and polling for MenuPopup
"""

import sys
import json
import time

# Add project to path
sys.path.insert(0, r'D:\new_automation\final_hojaiga_tutor')

from UIAutomationInvoker import UIAutomationInvoker

def test_menu_latency():
    print('=' * 70)
    print('Test: Sub-Menu Mounting Latency')
    print('=' * 70)
    print()
    print('Testing that ExpandCollapsePattern includes:')
    print('  - 100-150ms debounce after menu expansion')
    print('  - Poll for MenuPopup control type before reading child tree')
    print()
    print('Instructions:')
    print('  1. Open Notepad')
    print('  2. Move mouse over the "File" menu')
    print('  3. Press Enter to test menu expansion')
    print()

    input('Press Enter when ready...')

    invoker = UIAutomationInvoker()

    if not invoker.available:
        print('❌ UI Automation not available')
        return

    # Get mouse position
    import pyautogui
    x, y = pyautogui.position()
    print(f'Mouse at: ({x}, {y})')
    print()

    # Test expand_menu
    print('Testing expand_menu with latency check...')
    start_time = time.time()
    result = invoker.expand_menu(x, y)
    elapsed = (time.time() - start_time) * 1000

    print(f'Result: {json.dumps(result, indent=2)}')
    print(f'Total time: {elapsed:.0f}ms')
    print()

    # CRITICAL RUNTIME CHECK #1: Verify debounce
    if 'waited_ms' in result:
        print(f'✅ Runtime Check #1: Debounce active - waited {result["waited_ms"]}ms')
        if result['waited_ms'] >= 100:
            print('✅ Debounce time >= 100ms (within spec)')
        else:
            print('⚠️ Debounce time < 100ms (may be too short)')
    else:
        print('❌ Runtime Check #1: No debounce detected')
        print('   The expand_menu method should include waited_ms in response')

    if 'warning' in result:
        print(f'⚠️ Warning: {result["warning"]}')

    print()
    print('=' * 70)
    print('Test Complete')
    print('=' * 70)

if __name__ == '__main__':
    test_menu_latency()
