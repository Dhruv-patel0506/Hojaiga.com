/**
 * Direct panel opener - bypasses hotkeys
 * Run this while Clicky is running
 */

const { app, BrowserWindow } = require('electron');

console.log('=== Direct Panel Opener ===\n');
console.log('This script attempts to find and show the Clicky panel window directly.');
console.log('\nPrerequisites:');
console.log('1. Clicky must be running (npm start)');
console.log('2. Ollama must be running (ollama serve)');
console.log('\nStarting...\n');

// Since we can't easily access the running Electron instance from Node,
// let's provide manual instructions instead

console.log('=== MANUAL PANEL ACCESS ===\n');
console.log('Since hotkeys aren\'t working, try these alternatives:\n');

console.log('1. CHECK SYSTEM TRAY:');
console.log('   - Look at bottom-right corner of your screen');
console.log('   - Find Clicky icon (might be a robot or C icon)');
console.log('   - Right-click it');
console.log('   - Select "Show Panel" or "Open Panel"\n');

console.log('2. CHECK TASKBAR:');
console.log('   - Look for Clicky in your taskbar');
console.log('   - Click on it to bring it to front\n');

console.log('3. CHECK MINIMIZED WINDOWS:');
console.log('   - Press Alt+Tab to see all open windows');
console.log('   - Look for "Clicky" or "Electron"');
console.log('   - Select it to bring to front\n');

console.log('4. CHECK OVERLAY:');
console.log('   - Clicky creates a transparent overlay window');
console.log('   - It might be covering your screen but transparent');
console.log('   - Try pressing Ctrl+Shift+X to clear it\n');

console.log('=== IF PANEL NOT FOUND ===\n');
console.log('Clicky might be crashing on startup. To fix:');
console.log('1. Stop Clicky (close Electron window)');
console.log('2. Check for errors in the terminal');
console.log('3. Try running: npm run build');
console.log('4. Then: npm start\n');

console.log('=== ALTERNATIVE: USE CLI ===\n');
console.log('Since the panel has issues, you can test the vision teaching');
console.log('directly via Node without the Electron UI:');
console.log('\n1. Create a test script that uses the vision platform');
console.log('2. Call it directly from Node');
console.log('3. This bypasses the Electron panel entirely\n');

console.log('=== NEXT STEPS ===\n');
console.log('Please check:');
console.log('- System tray for Clicky icon');
console.log('- Taskbar for Clicky window');
console.log('- Alt+Tab for hidden windows');
console.log('- Terminal for error messages');
