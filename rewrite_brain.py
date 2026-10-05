import sys
import re

content = open('D:/new_automation/All codes/core_organs/organ_01_brain.py', 'r', encoding='utf-8').read()

target = '''class PromptCompiler:
    """Task Compilation — converts raw task text into decomposed
    autonomous agent definitions based on intelligence layer JSON structure."""

    _SYSTEM_PROMPT = (
        "You are the Hojaiga Brain intelligence engine. Your task is to decode unstructured, informal, or rambling user intent "
        "and confidently compile it into a strict JSON Execution Plan. You MUST NOT ask for clarification or pause for verification. "
        "Rely on your own logic and context to deduce the intent.\\n\\n"
        "You must distribute the global task across the 4 core Permanent Agents: 'BrowserAgent', 'SystemAgent', 'FileAgent', and 'AnalysisAgent'.\\n"
        "For each agent needed, provide a high-level objective and detailed instructions.\\n\\n"
        "{\\n"
        "  \\"intent_analysis\\": \\"[Detailed reasoning about what the human truly wants, avoiding clarifying questions.]\\",\\n"
        "  \\"checkpoints_enforced\\": true,\\n"
        "  \\"controller_access\\": [\\"browser\\", \\"desktop\\", \\"os\\"],\\n"
        "  \\"agent_tasks\\": [\\n"
        "    {\\n"
        "      \\"agent_id\\": \\"BrowserAgent\\",\\n"
        "      \\"objective\\": \\"[High-level objective for this Permanent Agent]\\",\\n"
        "      \\"instructions\\": \\"{\\\\\\"action\\\\\\": \\\\\\"NAVIGATE\\\\\\", \\\\\\"parameters\\\\\\": {\\\\\\"url\\\\\\": \\\\\\"https://youtube.com\\\\\\"}}\\",\\n"
        "      \\"search_queries\\": [\\"[Query 1]\\"],\\n"
        "      \\"wait_seconds\\": 0\\n"
        "    }\\n"
        "  ]\\n"
        "}\\n\\n"
        "Rules:\\n"
        "- NEVER ask questions. Autonomously decide the best path.\\n"
        "- Only assign tasks to the permanent agents: BrowserAgent, SystemAgent, FileAgent, AnalysisAgent.\\n"
        "- The 'instructions' field MUST be a stringified JSON object with 'action' (e.g. NAVIGATE, INTERACT, GET_DOM_TREE) and 'parameters'.\\n"
        "- Output ONLY raw JSON, no backticks, no explanatory text."
    )

    def __init__(self) -> None:
        self._gateway = LLMGateway()

    def compile(self, task: TaskRequest, context_summary: str) -> ExecutionPlan:
        user_prompt = (
            f"Task: {task.raw_text}\\n\\n"
            f"Known context:\\n{context_summary or '(none)'}\\n\\n"
            "Produce the structured JSON execution plan now."
        )
        raw = self._gateway.execute_inference(
            system=self._SYSTEM_PROMPT,
            prompt=user_prompt,
            timeout=CONFIG.big_brain_timeout_seconds,
        )
        return self._parse(raw, task)

    def _parse(self, raw: str, task: TaskRequest) -> ExecutionPlan:
        try:
            # Clean up potential markdown formatting from LLM
            clean_raw = raw.strip()
            if clean_raw.startswith("```json"):
                clean_raw = clean_raw[7:]
            if clean_raw.startswith("```"):
                clean_raw = clean_raw[3:]
            if clean_raw.endswith("```"):
                clean_raw = clean_raw[:-3]
            clean_raw = clean_raw.strip()

            data = json.loads(clean_raw)
        except json.JSONDecodeError as e:
            raise InvalidTaskError(f"Brain produced invalid JSON: {e}\\nRaw Output: {raw}")

        intent_analysis = data.get("intent_analysis", "")
        checkpoints_enforced = data.get("checkpoints_enforced", False)
        controller_access = data.get("controller_access", [])
        raw_tasks = data.get("agent_tasks", [])

        agent_tasks = []
        for idx, t in enumerate(raw_tasks):
            agent_tasks.append(AgentTask(
                agent_id=str(t.get("agent_id", idx + 1)),
                objective=t.get("objective", ""),
                instructions=t.get("instructions", ""),
                search_queries=t.get("search_queries", []),
                agent_tier="permanent"
            ))

        if not agent_tasks:
            raise InvalidTaskError("Could not find any structured AGENT blocks in JSON.")

        # Fallback empty steps array since we transitioned away from PhaseStep
        steps = [PhaseStep(phase="DECIDE", instruction=f"Launch {len(agent_tasks)} agents.")]

        return ExecutionPlan(
            task_id=task.task_id,
            steps=steps,
            agent_tasks=agent_tasks,
            raw_plan_text=raw,
            risk_report=RiskReport(level=RiskLevel.LOW, notes="Multi-agent JSON plan generated."),
            requires_escalation=False,
            intent_analysis=intent_analysis,
            checkpoints_enforced=checkpoints_enforced,
            controller_access=controller_access,
        )'''

commented_target = "# [2026-08-17] LEGACY PROMPT COMPILER DEPRECATED - REPLACED WITH HIERARCHICAL SWARM ARCHITECTURE\n" + "\n".join(["# " + line for line in target.split("\n")])

replacement = commented_target + '''

class PromptCompiler:
    """Task Compilation — converts raw task text into a hierarchical
    swarm (Permanent -> Sub -> Temporary agents)."""

    _SYSTEM_PROMPT = (
        "You are the Hojaiga Brain intelligence engine.\\n"
        "Your task is to compile user intent into a strict JSON 3-tier hierarchical swarm.\\n"
        "1. Permanent Agents (manage high-level checkpoints)\\n"
        "2. Sub-Agents (manage sub-checkpoints)\\n"
        "3. Temporary Agents (execute micro-instructions like 'use virtual mouse to scroll', 'use eye to analyze')\\n\\n"
        "{\\n"
        "  \\"intent_analysis\\": \\"Detailed reasoning\\",\\n"
        "  \\"checkpoints_enforced\\": true,\\n"
        "  \\"controller_access\\": [\\"browser\\", \\"desktop\\", \\"os\\"],\\n"
        "  \\"agent_tasks\\": [\\n"
        "    {\\n"
        "      \\"agent_id\\": \\"BrowserManager\\",\\n"
        "      \\"objective\\": \\"Oversee web research\\",\\n"
        "      \\"agent_tier\\": \\"permanent\\",\\n"
        "      \\"sub_agents\\": [\\n"
        "        {\\n"
        "          \\"agent_id\\": \\"GoogleSearchSubAgent\\",\\n"
        "          \\"objective\\": \\"Research Luxury Home Builders\\",\\n"
        "          \\"agent_tier\\": \\"sub_agent\\",\\n"
        "          \\"temporary_agents\\": [\\n"
        "            {\\n"
        "              \\"agent_id\\": \\"DataExtractorTemp\\",\\n"
        "              \\"objective\\": \\"Extract data from Google Maps\\",\\n"
        "              \\"instructions\\": \\"{\\\\\\"action\\\\\\": \\\\\\"RESEARCH\\\\\\", \\\\\\"parameters\\\\\\": {\\\\\\"query\\\\\\": \\\\\\"luxury home builders\\\\\\"}}\\",\\n"
        "              \\"search_queries\\": [\\"luxury home builders in Texas\\"],\\n"
        "              \\"agent_tier\\": \\"temporary\\"\\n"
        "            }\\n"
        "          ]\\n"
        "        }\\n"
        "      ]\\n"
        "    }\\n"
        "  ]\\n"
        "}\\n"
        "Output ONLY JSON."
    )

    def __init__(self) -> None:
        self._gateway = LLMGateway()

    def compile(self, task: TaskRequest, context_summary: str) -> ExecutionPlan:
        user_prompt = f"Task: {task.raw_text}\\nProduce the 3-tier JSON execution plan."
        raw = self._gateway.execute_inference(
            system=self._SYSTEM_PROMPT,
            prompt=user_prompt,
            timeout=CONFIG.big_brain_timeout_seconds,
        )
        return self._parse_and_format(raw, task)

    def _parse_and_format(self, raw: str, task: TaskRequest) -> ExecutionPlan:
        try:
            clean_raw = raw.strip()
            if clean_raw.startswith("```json"): clean_raw = clean_raw[7:]
            if clean_raw.startswith("```"): clean_raw = clean_raw[3:]
            if clean_raw.endswith("```"): clean_raw = clean_raw[:-3]
            clean_raw = clean_raw.strip()
            data = json.loads(clean_raw)
        except json.JSONDecodeError as e:
            raise InvalidTaskError(f"Brain produced invalid JSON: {e}\\nRaw: {raw}")

        intent_analysis = data.get("intent_analysis", "")
        raw_tasks = data.get("agent_tasks", [])
        
        flat_agent_tasks = []
        
        print(f"\\n{'='*60}\\n[ORCHESTRATOR] TASK COMPILATION COMPLETED. DEPLOYING SWARM...\\n{'='*60}")
        
        for idx, perm in enumerate(raw_tasks):
            p_id = perm.get("agent_id", f"PERM-{idx+1}")
            print(f"\\n========================= PERMANENT AGENT {idx+1}: {p_id} =========================")
            print(f"Objective: {perm.get('objective', 'Manage task')}")
            print("Checkpoints:")
            
            sub_agents = perm.get("sub_agents", [])
            for s_idx, sub in enumerate(sub_agents):
                print(f"  [ ] Spawn sub-agent for {sub.get('objective', 'Sub-task')}")
            
            for s_idx, sub in enumerate(sub_agents):
                s_id = sub.get("agent_id", f"SUB-{s_idx+1}")
                print(f"\\n    ========================= SUB-AGENT {idx+1}-{s_idx+1}: {s_id} =========================")
                print(f"    Objective: {sub.get('objective', 'Sub-task')}")
                print("    Checkpoints:")
                
                temp_agents = sub.get("temporary_agents", [])
                for t_idx, temp in enumerate(temp_agents):
                    print(f"      [ ] Spawn temporary agent for {temp.get('objective', 'Micro-task')}")
                
                for t_idx, temp in enumerate(temp_agents):
                    t_id = temp.get("agent_id", f"TEMP-{t_idx+1}")
                    print(f"\\n        ========================= TEMPORARY AGENT {idx+1}-{s_idx+1}-{t_idx+1}: {t_id} =========================")
                    print(f"        Objective: {temp.get('objective', 'Micro-task')}")
                    print(f"        Instructions: {temp.get('instructions', 'N/A')}")
                    print(f"        Search Queries: {temp.get('search_queries', [])}")
                    
                    flat_agent_tasks.append(AgentTask(
                        agent_id=t_id,
                        objective=temp.get("objective", ""),
                        instructions=temp.get("instructions", ""),
                        search_queries=temp.get("search_queries", []),
                        agent_tier="temporary"
                    ))

        if not flat_agent_tasks:
            raise InvalidTaskError("Could not find any structured AGENT blocks in JSON.")

        steps = [PhaseStep(phase="DECIDE", instruction=f"Launch {len(flat_agent_tasks)} temporary agents.")]

        return ExecutionPlan(
            task_id=task.task_id,
            steps=steps,
            agent_tasks=flat_agent_tasks,
            raw_plan_text=raw,
            risk_report=RiskReport(level=RiskLevel.LOW, notes="Multi-agent swarm plan generated."),
            requires_escalation=False,
            intent_analysis=intent_analysis,
            checkpoints_enforced=data.get("checkpoints_enforced", True),
            controller_access=data.get("controller_access", []),
        )'''

if target in content:
    content = content.replace(target, replacement)
    open('D:/new_automation/All codes/core_organs/organ_01_brain.py', 'w', encoding='utf-8').write(content)
    print('Successfully updated organ_01_brain.py')
else:
    print('Target string not found in organ_01_brain.py')
    sys.exit(1)
