import os
import subprocess
import sys

for i in range(16, 25):
    pipeline_file = f'd:/new_automation/pipelines/pipeline_{i}.py'
    if os.path.exists(pipeline_file):
        print(f'=== Running pipeline_{i}.py ===')
        result = subprocess.run([sys.executable, pipeline_file], capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f'Error running pipeline_{i}.py:')
            print(result.stderr)
