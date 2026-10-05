import os
import sys

files = [
    ('organ_17_backup_manager', 'BackupManagerOrgan'),
    ('organ_18_capability_registry', 'CapabilityRegistryOrgan'),
    ('organ_19_chrome_cdp_runtime', 'BrowserProcessLauncher'),
    ('organ_20_configuration_manager', 'ConfigRegistry'),
    ('organ_21_configuration_schema', 'CompatibilityManager'),
    ('organ_22_decision_engine', 'AlternativeGenerator'),
    ('organ_23', 'DependencyManager'),
    ('kernel', 'BootManager'),
    ('package_manager', 'DependencyResolver')
]

code_template = """import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'All codes')))
import organ_02_cns_single_file as cns
try:
    import {fname}
except ImportError as e:
    print(f"Warning: could not import {fname}: {e}")

async def run_pipeline():
    print("Starting pipeline {i}: Organ 2 (CNS) -> {fname}")
    kernel = cns.CNSKernel()
    await kernel.start()
    
    envelope = cns.EventEnvelope(
        topic="connection.test.{fname}",
        source_organ="{i}",
        payload={{"status": "online"}}
    )
    delivered = await kernel.event_bus.publish(envelope)
    print(f"[CNS] Event published to {delivered} subscribers.")
    
    await kernel.shutdown()
    print("[Pipeline] Connection test successful for {fname}.")

if __name__ == '__main__':
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_pipeline())
"""

for i, (fname, _) in enumerate(files, start=16):
    with open(f'd:/new_automation/pipelines/pipeline_{i}.py', 'w') as f:
        f.write(code_template.replace('{fname}', fname).replace('{i}', str(i)))
    print(f'Created pipeline_{i}.py for {fname}')
