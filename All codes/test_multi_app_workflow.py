"""
Test Multi-App Workflow - Gmail + Notepad + Chrome

This test demonstrates Hojaiga's enhanced DAP multi-session capabilities:
- Session multiplexing (multiple apps simultaneously)
- Smooth app switching
- Copy-paste-free data transfer
- Parallel execution
"""

import asyncio
import sys
import os
import time
import logging

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_24_dap import DAPRuntimeCore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_multi_app")


async def test_multi_app_workflow():
    """Test multi-app workflow with Gmail, Notepad, and Chrome."""
    
    logger.info("=" * 60)
    logger.info("Starting Multi-App Workflow Test")
    logger.info("=" * 60)
    
    # Initialize DAP Runtime
    dap = DAPRuntimeCore()
    await dap.initialize()
    
    try:
        # Test 1: Create sessions for multiple apps
        logger.info("\n[Test 1] Creating sessions for multiple apps...")
        
        try:
            gmail_session = await dap.session_create("Gmail")
            logger.info(f"✓ Gmail session created: {gmail_session.get('session_id')}")
        except Exception as e:
            logger.warning(f"✗ Gmail session failed: {e}")
            gmail_session = None
        
        try:
            notepad_session = await dap.session_create("Notepad")
            logger.info(f"✓ Notepad session created: {notepad_session.get('session_id')}")
        except Exception as e:
            logger.warning(f"✗ Notepad session failed: {e}")
            notepad_session = None
        
        try:
            chrome_session = await dap.session_create("Chrome")
            logger.info(f"✓ Chrome session created: {chrome_session.get('session_id')}")
        except Exception as e:
            logger.warning(f"✗ Chrome session failed: {e}")
            chrome_session = None
        
        # Test 2: List all sessions
        logger.info("\n[Test 2] Listing all sessions...")
        sessions = await dap.session_list()
        logger.info(f"Active sessions: {sessions['count']}")
        for session in sessions['sessions']:
            logger.info(f"  - {session['session_id']}: {session['app_name']} ({session['window_title']})")
        
        # Test 3: Switch between sessions
        logger.info("\n[Test 3] Switching between sessions...")
        
        if gmail_session:
            await dap.session_switch(gmail_session['session_id'])
            logger.info(f"✓ Switched to Gmail")
            await asyncio.sleep(1)
        
        if notepad_session:
            await dap.session_switch(notepad_session['session_id'])
            logger.info(f"✓ Switched to Notepad")
            await asyncio.sleep(1)
        
        if chrome_session:
            await dap.session_switch(chrome_session['session_id'])
            logger.info(f"✓ Switched to Chrome")
            await asyncio.sleep(1)
        
        # Test 4: Switch with state preservation
        logger.info("\n[Test 4] Switching with state preservation...")
        
        if gmail_session and notepad_session:
            result = await dap.switch_with_state(
                gmail_session['session_id'],
                notepad_session['session_id']
            )
            logger.info(f"✓ State-preserving switch: {result['switched']}")
            await asyncio.sleep(1)
        
        # Test 5: Parallel execution simulation
        logger.info("\n[Test 5] Testing parallel execution...")
        
        tasks = []
        if gmail_session:
            tasks.append({
                "session_id": gmail_session['session_id'],
                "action": "focus",
                "params": {}
            })
        if notepad_session:
            tasks.append({
                "session_id": notepad_session['session_id'],
                "action": "focus",
                "params": {}
            })
        if chrome_session:
            tasks.append({
                "session_id": chrome_session['session_id'],
                "action": "focus",
                "params": {}
            })
        
        if tasks:
            result = await dap.execute_parallel(tasks)
            logger.info(f"✓ Parallel execution: {result['tasks']} tasks completed")
            for r in result['results']:
                logger.info(f"  - Session {r['session_id']}: {'Success' if r['success'] else 'Failed'}")
        
        # Test 6: Data transfer (copy-paste-free)
        logger.info("\n[Test 6] Testing copy-paste-free data transfer...")
        
        if gmail_session and notepad_session:
            result = await dap.data_transfer(
                gmail_session['session_id'],
                notepad_session['session_id'],
                "selector1",  # Placeholder selector
                "selector2"   # Placeholder selector
            )
            logger.info(f"✓ Data transfer: {result['transferred']}")
        
        # Test 7: Close sessions
        logger.info("\n[Test 7] Closing sessions...")
        
        if gmail_session:
            await dap.session_close(gmail_session['session_id'])
            logger.info(f"✓ Gmail session closed")
        
        if notepad_session:
            await dap.session_close(notepad_session['session_id'])
            logger.info(f"✓ Notepad session closed")
        
        if chrome_session:
            await dap.session_close(chrome_session['session_id'])
            logger.info(f"✓ Chrome session closed")
        
        # Final session list
        sessions = await dap.session_list()
        logger.info(f"\nFinal session count: {sessions['count']}")
        
        logger.info("\n" + "=" * 60)
        logger.info("Multi-App Workflow Test Completed")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
    
    finally:
        await dap.shutdown()


async def test_basic_functionality():
    """Test basic DAP functionality before multi-session tests."""
    
    logger.info("\n" + "=" * 60)
    logger.info("Testing Basic DAP Functionality")
    logger.info("=" * 60)
    
    dap = DAPRuntimeCore()
    await dap.initialize()
    
    try:
        # Test window enumeration
        logger.info("\n[Test] Enumerating windows...")
        windows = await dap.window_enumerate(include_child_windows=False)
        logger.info(f"✓ Found {len(windows)} top-level windows")
        
        # Show first 5 windows
        for i, win in enumerate(windows[:5]):
            logger.info(f"  {i+1}. {win.get('class_name', 'Unknown')} - {win.get('name', 'No title')}")
        
        logger.info("\n" + "=" * 60)
        logger.info("Basic Functionality Test Completed")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Basic test failed: {e}", exc_info=True)
    
    finally:
        await dap.shutdown()


async def main():
    """Run all tests."""
    
    # Test basic functionality first
    await test_basic_functionality()
    
    # Wait a bit
    await asyncio.sleep(2)
    
    # Test multi-app workflow
    await test_multi_app_workflow()


if __name__ == "__main__":
    asyncio.run(main())
