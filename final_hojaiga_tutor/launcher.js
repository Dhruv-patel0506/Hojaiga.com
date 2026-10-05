/**
 * Custom Electron Launcher
 * Attempts to load Electron correctly in the current environment
 */

const { spawn } = require('child_process');
const path = require('path');

console.log('=== Custom Electron Launcher ===\n');

// Try different methods to launch Electron
const methods = [
  {
    name: 'Method 1: Local electron executable',
    command: 'electron',
    args: ['dist/main.js'],
    cwd: __dirname
  },
  {
    name: 'Method 2: npx electron',
    command: 'npx',
    args: ['electron', 'dist/main.js'],
    cwd: __dirname
  },
  {
    name: 'Method 3: Full path to electron',
    command: path.join(__dirname, 'node_modules', '.bin', 'electron.cmd'),
    args: [path.join(__dirname, 'dist', 'main.js')],
    cwd: __dirname
  },
  {
    name: 'Method 4: Node with electron module',
    command: 'node',
    args: [path.join(__dirname, 'node_modules', 'electron', 'cli.js'), path.join(__dirname, 'dist', 'main.js')],
    cwd: __dirname
  }
];

async function tryLaunch(method) {
  console.log(`Trying: ${method.name}`);
  console.log(`Command: ${method.command}`);
  console.log(`Args: ${method.args.join(' ')}`);
  console.log(`CWD: ${method.cwd}\n`);

  return new Promise((resolve) => {
    const child = spawn(method.command, method.args, {
      cwd: method.cwd,
      stdio: 'inherit',
      shell: true
    });

    child.on('error', (error) => {
      console.error(`✗ ${method.name} failed:`, error.message);
      resolve(false);
    });

    child.on('exit', (code) => {
      if (code === 0) {
        console.log(`✓ ${method.name} succeeded!`);
        resolve(true);
      } else {
        console.log(`✗ ${method.name} exited with code ${code}`);
        resolve(false);
      }
    });

    // Give it 5 seconds to start
    setTimeout(() => {
      console.log(`⏱ ${method.name} timeout - moving to next method`);
      child.kill();
      resolve(false);
    }, 5000);
  });
}

async function main() {
  for (const method of methods) {
    const success = await tryLaunch(method);
    if (success) {
      console.log('\n=== SUCCESS ===');
      console.log(`Electron launched with: ${method.name}`);
      console.log('The app should now be running.\n');
      return;
    }
  }

  console.log('\n=== ALL METHODS FAILED ===');
  console.log('Please try:');
  console.log('1. Reinstall Electron: npm install electron@latest --save-dev');
  console.log('2. Check Node.js version: node --version');
  console.log('3. Try in a different terminal/cmd');
  console.log('4. Try on a different machine\n');
}

main().catch(console.error);
