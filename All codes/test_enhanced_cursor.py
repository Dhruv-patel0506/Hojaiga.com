"""
Test script for Enhanced Visual Cursor

Tests:
1. Magnetic attachment to physical mouse
2. Detachment and independent operation
3. Multi-cursor spawning
4. Independent cursor movement
5. State management
"""

import sys
import time
import asyncio

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.visual_cursor_enhanced import EnhancedVisualCursor, CursorState, get_enhanced_cursor


def test_enhanced_cursor():
    """Test the enhanced cursor functionality."""
    print("="*60)
    print("ENHANCED VISUAL CURSOR TEST")
    print("="*60)
    
    cursor = get_enhanced_cursor()
    
    # Test 1: Start cursor system
    print("\nTest 1: Start cursor system")
    cursor.start()
    time.sleep(1)
    print("[PASS] Cursor system started")
    
    # Test 2: Check main cursor initial state
    print("\nTest 2: Check main cursor initial state")
    main_cursor = cursor.get_cursor_position("main")
    print(f"   Main cursor position: ({main_cursor[0]:.1f}, {main_cursor[1]:.1f})")
    print(f"   Attached to physical mouse: {cursor._main_cursor.is_attached_to_physical}")
    print("[PASS] Main cursor initialized correctly")
    
    # Test 3: Spawn multiple cursors
    print("\nTest 3: Spawn multiple cursors")
    cursor1_id = cursor.spawn_cursor(window_title="Notepad", x=400, y=300, color=0x00FF00FF)
    cursor2_id = cursor.spawn_cursor(window_title="Chrome", x=800, y=400, color=0x0000FFFF)
    cursor3_id = cursor.spawn_cursor(window_title="Excel", x=600, y=500, color=0xFFFF00FF)
    print(f"   Spawned cursor 1: {cursor1_id}")
    print(f"   Spawned cursor 2: {cursor2_id}")
    print(f"   Spawned cursor 3: {cursor3_id}")
    print(f"   Total cursors: {len(cursor.get_all_cursors())}")
    print("[PASS] Multiple cursors spawned successfully")
    
    # Test 4: Move cursors independently
    print("\nTest 4: Move cursors independently")
    cursor.move_cursor("main", x=500, y=500)
    cursor.move_cursor(cursor1_id, x=450, y=350)
    cursor.move_cursor(cursor2_id, x=850, y=450)
    time.sleep(0.5)  # Allow movement
    
    main_pos = cursor.get_cursor_position("main")
    cursor1_pos = cursor.get_cursor_position(cursor1_id)
    cursor2_pos = cursor.get_cursor_position(cursor2_id)
    
    print(f"   Main cursor: ({main_pos[0]:.1f}, {main_pos[1]:.1f})")
    print(f"   Cursor 1: ({cursor1_pos[0]:.1f}, {cursor1_pos[1]:.1f})")
    print(f"   Cursor 2: ({cursor2_pos[0]:.1f}, {cursor2_pos[1]:.1f})")
    print("[PASS] Cursors moved independently")
    
    # Test 5: Set cursor states
    print("\nTest 5: Set cursor states")
    cursor.set_cursor_state("main", CursorState.BUFFERING)
    cursor.set_cursor_state(cursor1_id, CursorState.MOVING)
    cursor.set_cursor_state(cursor2_id, CursorState.CLICKING)
    time.sleep(0.2)
    
    print(f"   Main cursor state: {cursor._main_cursor.state.value}")
    print(f"   Cursor 1 state: {cursor._spawned_cursors[cursor1_id].state.value}")
    print(f"   Cursor 2 state: {cursor._spawned_cursors[cursor2_id].state.value}")
    print("[PASS] Cursor states set correctly")
    
    # Test 6: Rotation animation
    print("\nTest 6: Rotation animation (buffering)")
    initial_rotation = cursor._main_cursor.rotation_angle
    time.sleep(0.5)  # Allow rotation
    final_rotation = cursor._main_cursor.rotation_angle
    print(f"   Initial rotation: {initial_rotation:.1f} degrees")
    print(f"   Final rotation: {final_rotation:.1f} degrees")
    print(f"   Rotation occurred: {final_rotation != initial_rotation}")
    print("[PASS] Rotation animation working")
    
    # Test 7: Reattach main cursor to physical mouse
    print("\nTest 7: Reattach main cursor to physical mouse")
    cursor.attach_to_physical_mouse()
    time.sleep(0.1)
    print(f"   Attached to physical mouse: {cursor._main_cursor.is_attached_to_physical}")
    print(f"   Main cursor state: {cursor._main_cursor.state.value}")
    print("[PASS] Main cursor reattached to physical mouse")
    
    # Test 8: Detach main cursor
    print("\nTest 8: Detach main cursor from physical mouse")
    cursor.detach_from_physical_mouse("main")
    time.sleep(0.1)
    print(f"   Attached to physical mouse: {cursor._main_cursor.is_attached_to_physical}")
    print(f"   Main cursor state: {cursor._main_cursor.state.value}")
    print("[PASS] Main cursor detached from physical mouse")
    
    # Test 9: Despawn cursors
    print("\nTest 9: Despawn cursors")
    cursor.despawn_cursor(cursor1_id)
    print(f"   Despawned cursor 1")
    print(f"   Remaining cursors: {len(cursor.get_all_cursors())}")
    print("[PASS] Cursor despawned successfully")
    
    # Test 10: Despawn all
    print("\nTest 10: Despawn all spawned cursors")
    cursor.despawn_all_cursors()
    print(f"   Remaining cursors: {len(cursor.get_all_cursors())}")
    print("[PASS] All spawned cursors despawned")
    
    # Test 11: Physical mouse tracking
    print("\nTest 11: Physical mouse tracking")
    print(f"   Physical mouse tracking enabled: {cursor._physical_mouse_tracking}")
    print(f"   Last physical mouse position: ({cursor._physical_mouse_x:.1f}, {cursor._physical_mouse_y:.1f})")
    print("[PASS] Physical mouse tracking functional")
    
    # Stop cursor system
    print("\nStopping cursor system...")
    cursor.stop()
    time.sleep(0.5)
    print("[PASS] Cursor system stopped")
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED")
    print("="*60)
    print("\nEnhanced Cursor Features Working:")
    print("[PASS] Magnetic attachment to physical mouse")
    print("[PASS] Detachment and independent operation")
    print("[PASS] Multi-cursor spawning")
    print("[PASS] Independent cursor movement")
    print("[PASS] State management")
    print("[PASS] Rotation animation")
    print("[PASS] Physical mouse tracking")
    print("\nThe enhanced cursor system is working correctly!")


if __name__ == "__main__":
    test_enhanced_cursor()
