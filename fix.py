import sys
import json
import re

content = open('D:/new_automation/All codes/core_organs/organ_10_agents.py', 'r', encoding='utf-8').read()

target = '''        try:
            await asyncio.wait_for(self.pending_tasks[task_id].wait(), timeout=10.0)
                            break
                parameters["payload"]["url"] = url'''

replacement = '''        try:
            await asyncio.wait_for(self.pending_tasks[task_id].wait(), timeout=10.0)
        except asyncio.TimeoutError:
            log.error(f"Task {task_id} timed out waiting for browser launch.")
            
        task_failed = False
            
        # Start each agent task sequentially
        for at in agent_tasks:
            agent_id = at.get("agent_id")
            await self.cns.publish(EventEnvelope(
                topic="AGENT_ASSIGNED",
                source_organ="organ_10",
                payload={"task_id": task_id, "agent_id": agent_id}
            ))
            await self.cns.publish(EventEnvelope(
                topic="sys.events",
                source_organ="organ_10",
                payload={"event_type": "AGENT_ASSIGNED", "task_id": task_id, "agent_id": agent_id}
            ))
            
            # Parse structured instructions
            instructions_raw = at.get("instructions", "{}")
            print(f"!!! DEBUG ORGAN_10 INSTRUCTIONS: {instructions_raw}")
            action = None
            parameters = {}
            
            try:
                import json
                if isinstance(instructions_raw, dict):
                    instr_data = instructions_raw
                else:
                    instr_data = json.loads(instructions_raw)
                action = instr_data.get("action")
                parameters = instr_data.get("parameters", {})
            except Exception as e:
                log.error(f"Failed to parse instructions as JSON: {e}")
                if "search" in str(instructions_raw).lower():
                    action = "RESEARCH"
                    parameters = {"payload": {"query": str(instructions_raw)}}
            
            # The controller returns `session_id` when LAUNCH_BROWSER completes
            session_id = self.results.get(task_id, {}).get("session_id", "DEFAULT")
            # Move any top-level parameters into payload for the controller
            parameters["payload"] = parameters.get("payload", {})
            for k, v in list(parameters.items()):
                if k != "payload":
                    parameters["payload"][k] = v
            
            parameters["payload"]["session_id"] = session_id
            
            # Extract url/selector from the raw intent if missing
            if action == "NAVIGATE" and not parameters["payload"].get("url"):
                url = at.get("url", "")
                if not url:
                    # Attempt to extract from objective
                    words = at.get("objective", "").split()
                    for w in words:
                        if w.lower().startswith("http"):
                            url = w.strip(",.;\\n\\r")
                            break
                parameters["payload"]["url"] = url'''

if target in content:
    content = content.replace(target, replacement)
    open('D:/new_automation/All codes/core_organs/organ_10_agents.py', 'w', encoding='utf-8').write(content)
    print('Successfully restored organ_10_agents.py')
else:
    print('Target string not found in organ_10_agents.py')
    sys.exit(1)
