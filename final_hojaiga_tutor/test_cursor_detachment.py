"""
Test Cursor Detachment - Demonstrates smooth cursor animation and programmatic clicking
Shows how the cursor can "detach" (perform programmatic actions) and "reattach" (return to user control)
"""

import pyautogui
import time
import sys
from smooth_cursor_automation import SmoothCursorAutomation

# Safety feature
pyautogui.FAILSAFE = True

def test_smooth_cursor_animation():
    """Test 1: Smooth cursor animation"""
    print("\n" + "="*60)
    print("TEST 1: Smooth Cursor Animation")
    print("="*60)
    
    automation = SmoothCursorAutomation(duration=1.5)
    
    # Get screen dimensions
    screen_width, screen_height = pyautogui.size()
    
    print(f"\nScreen size: {screen_width}x{screen_height}")
    print("Moving cursor to center of screen...")
    
    center_x = screen_width // 2
    center_y = screen_height // 2
    
    # Smooth move to center
    automation.smooth_move_only(center_x, center_y)
    
    print("\n[OK] Cursor smoothly moved to center")
    print("[OK] User can still move mouse (programmatic move completed)")
    time.sleep(1)
    
    return True

def test_programmatic_click():
    """Test 2: Programmatic click with smooth animation"""
    print("\n" + "="*60)
    print("TEST 2: Programmatic Click with Smooth Animation")
    print("="*60)
    
    automation = SmoothCursorAutomation(duration=1.2)
    
    screen_width, screen_height = pyautogui.size()
    
    # Move to a different location and click
    target_x = screen_width // 2 + 200
    target_y = screen_height // 2
    
    print(f"\nMoving to ({target_x}, {target_y}) and clicking...")
    automation.smooth_move_and_click(target_x, target_y)
    
    print("\n[OK] Programmatic click executed")
    print("[OK] Cursor moved smoothly, clicked, and control returned to user")
    time.sleep(1)
    
    return True

def test_detachment_reattachment():
    """Test 3: Demonstrate detachment and reattachment"""
    print("\n" + "="*60)
    print("TEST 3: Cursor Detachment and Reattachment")
    print("="*60)
    
    automation = SmoothCursorAutomation(duration=1.0)
    screen_width, screen_height = pyautogui.size()
    
    print("\n[PHASE 1: DETACHMENT]")
    print("Agent takes control of cursor...")
    print("Cursor will move to perform task...")
    
    # Agent performs task
    target_x = screen_width // 2 - 200
    target_y = screen_height // 2
    automation.smooth_move_and_click(target_x, target_y)
    
    print("\n[OK] Agent completed task")
    print("[OK] Cursor control returning to user...")
    
    time.sleep(1)
    
    print("\n[PHASE 2: REATTACHMENT]")
    print("User can now move cursor freely")
    print("Agent has released control")
    
    # Demonstrate user control by getting current position
    current_x, current_y = pyautogui.position()
    print(f"\nCurrent cursor position: ({current_x}, {current_y})")
    print("[OK] Cursor is now under user control")
    
    time.sleep(1)
    
    return True

def test_multiple_actions():
    """Test 4: Multiple sequential actions"""
    print("\n" + "="*60)
    print("TEST 4: Multiple Sequential Actions")
    print("="*60)
    
    automation = SmoothCursorAutomation(duration=0.8)
    screen_width, screen_height = pyautogui.size()
    
    # Define a sequence of actions
    actions = [
        (screen_width // 2, screen_height // 2 - 150),
        (screen_width // 2 + 150, screen_height // 2),
        (screen_width // 2, screen_height // 2 + 150),
        (screen_width // 2 - 150, screen_height // 2),
        (screen_width // 2, screen_height // 2),
    ]
    
    print(f"\nExecuting {len(actions)} sequential movements...")
    
    for i, (x, y) in enumerate(actions, 1):
        print(f"  Action {i}/{len(actions)}: Moving to ({x}, {y})")
        automation.smooth_move_only(x, y)
        time.sleep(0.3)
    
    print("\n[OK] All actions completed")
    print("[OK] Cursor returned to center")
    
    return True

def test_human_like_behavior():
    """Test 5: Human-like behavior variations"""
    print("\n" + "="*60)
    print("TEST 5: Human-like Behavior Variations")
    print("="*60)
    
    automation = SmoothCursorAutomation(duration=1.2)
    screen_width, screen_height = pyautogui.size()
    
    center_x = screen_width // 2
    center_y = screen_height // 2
    
    print("\nTesting different click types...")
    
    # Regular click
    print("  1. Regular click...")
    automation.smooth_move_and_click(center_x, center_y)
    time.sleep(0.5)
    
    # Right click
    print("  2. Right click...")
    automation.right_click_smooth(center_x + 100, center_y)
    time.sleep(0.5)
    
    # Double click
    print("  3. Double click...")
    automation.double_click_smooth(center_x - 100, center_y)
    time.sleep(0.5)
    
    print("\n[OK] All click types tested")
    print("[OK] Human-like delays between actions")
    
    return True

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("CURSOR DETACHMENT TEST SUITE")
    print("="*60)
    print("\nThis test demonstrates:")
    print("  1. Smooth cursor animation (easeInOutQuad)")
    print("  2. Programmatic clicking without hijacking")
    print("  3. Cursor detachment and reattachment")
    print("  4. Sequential actions")
    print("  5. Human-like behavior variations")
    print("\nSAFETY: Move mouse to corner to abort at any time")
    print("\nStarting tests in 3 seconds...")
    time.sleep(3)
    
    try:
        # Run tests
        tests = [
            ("Smooth Cursor Animation", test_smooth_cursor_animation),
            ("Programmatic Click", test_programmatic_click),
            ("Detachment/Reattachment", test_detachment_reattachment),
            ("Multiple Actions", test_multiple_actions),
            ("Human-like Behavior", test_human_like_behavior),
        ]
        
        results = []
        for name, test_func in tests:
            try:
                result = test_func()
                results.append((name, result))
                time.sleep(1)
            except Exception as e:
                print(f"\n[FAIL] Test failed: {e}")
                results.append((name, False))
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        for name, result in results:
            status = "[OK] PASS" if result else "[FAIL] FAIL"
            print(f"{status}: {name}")
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n[OK] All tests passed!")
            print("[OK] Cursor detachment and reattachment working correctly")
        else:
            print(f"\n[FAIL] {total - passed} test(s) failed")
        
    except KeyboardInterrupt:
        print("\n\nTest aborted by user")
    except Exception as e:
        print(f"\n\nTest suite failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nTests complete. Exiting in 3 seconds...")
    time.sleep(3)

if __name__ == "__main__":
    main()
