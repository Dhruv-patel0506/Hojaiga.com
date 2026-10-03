import os
for i in range(16, 25):
    path = f'd:/new_automation/pipelines/pipeline_{i}.py'
    if os.path.exists(path):
        with open(path, 'r') as f:
            content = f.read()
        content = content.replace('payload={{"status": "online"}}', 'payload={"status": "online"}')
        with open(path, 'w') as f:
            f.write(content)
        print(f'Fixed {path}')
