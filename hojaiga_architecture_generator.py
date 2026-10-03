import os
import ast
import json
import re
from pathlib import Path
from datetime import datetime

# Hojaiga Architecture Generator
# Automatically maintains visual documentation system for Hojaiga

ROOT_DIR = Path(r"d:\new_automation")
CODE_DIR = ROOT_DIR / "All codes"
DIAGRAMS_DIR = ROOT_DIR / "diagrams"
ARCH_DIR = ROOT_DIR / "architecture"

def setup_directories():
    DIAGRAMS_DIR.mkdir(exist_ok=True)
    ARCH_DIR.mkdir(exist_ok=True)
    (DIAGRAMS_DIR / "components").mkdir(exist_ok=True)

def parse_python_file(filepath):
    """Parse a python file using AST to extract components, dependencies, inputs, outputs, etc."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
    except Exception as e:
        return {"error": str(e), "filepath": str(filepath)}

    imports = []
    classes = []
    functions = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)
            
    # Extract organ number and name
    filename = filepath.name
    organ_match = re.match(r'(?:test_)?organ_(\d+)_?(.*)\.py', filename)
    organ_id = None
    organ_name = None
    if organ_match:
        organ_id = int(organ_match.group(1))
        organ_name = organ_match.group(2).replace('_', ' ').title() if organ_match.group(2) else f"Unknown Organ {organ_id}"

    return {
        "filepath": str(filepath.relative_to(ROOT_DIR)),
        "filename": filename,
        "imports": list(set(imports)),
        "classes": classes,
        "functions": functions,
        "organ_id": organ_id,
        "organ_name": organ_name,
        "content": content
    }

def scan_repository():
    inventory = []
    for filepath in CODE_DIR.rglob("*.py"):
        if filepath.name == "__init__.py" or "site-packages" in str(filepath):
            continue
        info = parse_python_file(filepath)
        if "error" not in info:
            inventory.append(info)
    return inventory

def generate_inventory_json(inventory):
    # Filter known organs
    organs = [i for i in inventory if i.get("organ_id") is not None]
    
    arch_inventory = {
        "organs": sorted([{"id": o["organ_id"], "name": o["organ_name"], "file": o["filepath"]} for o in organs], key=lambda x: x["id"]),
        "core_files": [{"file": i["filepath"]} for i in inventory if i.get("organ_id") is None],
        "last_updated": datetime.now().isoformat()
    }
    
    with open(ARCH_DIR / "architecture_inventory.json", 'w', encoding='utf-8') as f:
        json.dump(arch_inventory, f, indent=4)
        
    # Dummy socket registry for now
    socket_registry = {
        "sockets": [],
        "events": [],
        "last_updated": datetime.now().isoformat()
    }
    with open(ARCH_DIR / "socket_registry.json", 'w', encoding='utf-8') as f:
        json.dump(socket_registry, f, indent=4)
        
def generate_master_diagram():
    mermaid = """```mermaid
graph TD
    %% MASTER ARCHITECTURE
    USER((USER)) -->|Natural Language| INTERFACE[INTERFACE]
    INTERFACE --> BRAIN{BRAIN}
    BRAIN -->|Query| MEMORY[(MEMORY)]
    BRAIN -->|Query| KNOWLEDGE[(KNOWLEDGE)]
    BRAIN --> LLM_GATEWAY[LLM GATEWAY]
    LLM_GATEWAY --> COMPILER[WORKFLOW COMPILER]
    COMPILER --> CNS[CNS]
    CNS --> DECISION[DECISION ENGINE]
    DECISION --> AGENTS[AGENT ORCHESTRATION]
    AGENTS --> CONTROLLERS[CONTROLLERS]
    CONTROLLERS --> EXECUTION[PHYSICAL EXECUTION]
    CONTROLLERS -.-> PERCEPTION[APP SCANNER / PERCEPTION]
    PERCEPTION -.->|Feedback| CONTROLLERS
    EXECUTION --> CHECKPOINT{CHECKPOINT}
    CHECKPOINT -->|Pass| NEXT_STEP[NEXT STEP]
    CHECKPOINT -->|Fail| RECOVERY[RECOVERY / REPLANNING]
    RECOVERY -.-> CNS
    
    %% Observations
    AUDIT[(AUDIT)] -.->|Observes| CNS
    STATE[(STATE)] -.->|Observes| CNS
    VISUALIZATION[VISUALIZATION] -.->|Observes| CNS
```"""
    with open(DIAGRAMS_DIR / "00_master_architecture.md", 'w', encoding='utf-8') as f:
        f.write("# Master Architecture Diagram\n\n" + mermaid + "\n")

def generate_n8n_diagram():
    mermaid = """```mermaid
graph LR
    %% N8N STYLE WORKFLOW
    subgraph G1 [GROUP 1 - USER INPUT]
        start([Trigger: User Input])
    end
    
    subgraph G2 [GROUP 3 - BRAIN]
        brain([AI: Brain Intent])
    end
    
    subgraph G3 [GROUP 6 - WORKFLOW COMPILER]
        compiler([Code: Compiler])
    end
    
    subgraph G4 [GROUP 7 - CNS]
        cns([Event: CNS])
    end
    
    subgraph G5 [GROUP 9 - AGENTS]
        agents([Agent: Orchestration])
    end
    
    start --> brain
    brain --> compiler
    compiler --> cns
    cns --> agents
```"""
    with open(DIAGRAMS_DIR / "12_n8n_master_workflow.md", 'w', encoding='utf-8') as f:
        f.write("# n8n Master Workflow (Observability Model)\n\n" + mermaid + "\n")

def update_python_docstrings(inventory):
    # Inject docstrings to files
    for item in inventory:
        filepath = ROOT_DIR / item["filepath"]
        content = item["content"]
        
        # Check if the three-layer doc is already there
        # If it is, we remove the old one so we can inject the new advanced one
        if "HOJAIGA AUTOMATION ARCHITECTURE DOC" in content:
            # simple removal of old block (assuming it ends at the first empty string block or similar)
            content = re.sub(r'\"\"\"\nHOJAIGA AUTOMATION ARCHITECTURE DOC.*?\"\"\"\n', '', content, flags=re.DOTALL)
            
        mermaid_structural = f"""```mermaid
graph TD
    classDef default fill:#1e1e1e,stroke:#333,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#569cd6,stroke-width:2px,color:#d4d4d4;
    
    UPSTREAM[UPSTREAM INPUT]
    
    UPSTREAM -- event/socket --> COMPONENT
    
    subgraph COMPONENT [{item.get("organ_name") or item["filename"]}]
        direction TB
        IN[Inputs] --> PROC[Processing]
        PROC --> OUT[Outputs]
    end
    
    COMPONENT -- event/socket --> DOWNSTREAM_A[CONSUMER A]
    COMPONENT -- event/socket --> DOWNSTREAM_B[CONSUMER B]
    
    class COMPONENT component;
```"""

        docstring = f'''"""
HOJAIGA AUTOMATION ARCHITECTURE DOC

============================================================
1. MASTER ARCHITECTURE CONTEXT
============================================================
This component is part of the Hojaiga Automation Architecture.
Component Type: {"Organ " + str(item["organ_id"]) if item["organ_id"] else "Core File"}
Name: {item.get("organ_name") or item["filename"]}

============================================================
2. ORGAN/COMPONENT DIAGRAM
============================================================
{mermaid_structural}

Inputs: Discovered from runtime
Outputs: Discovered from runtime
Dependencies: {", ".join(item["imports"][:5])}...

============================================================
3. N8N-STYLE VISUAL WORKFLOW (MODEL)
============================================================
```mermaid
graph LR
    input([Input Node]) --> process([Code Node: {item["filename"]}]) --> output([Output Node])
```
"""'''
        
        new_content = docstring + "\n" + content
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

def main():
    print("Setting up directories...")
    setup_directories()
    print("Scanning repository...")
    inventory = scan_repository()
    print(f"Discovered {len(inventory)} components.")
    
    print("Generating JSON inventory...")
    generate_inventory_json(inventory)
    
    print("Generating master architecture diagram...")
    generate_master_diagram()
    
    print("Generating n8n workflow diagram...")
    generate_n8n_diagram()
    
    print("Injecting documentation into Python files...")
    update_python_docstrings(inventory)
    
    print("Documentation system generated successfully.")

if __name__ == "__main__":
    main()
