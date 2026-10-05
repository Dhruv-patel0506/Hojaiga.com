import os
import json
import ast
from pathlib import Path

def generate_graph_data():
    base_dir = Path(r"d:\new_automation\All codes")
    
    graph = {
        "target": {
            "groups": [
                {"id": "g1", "title": "INPUT / INGESTION", "bounds": {"x": 50, "y": 50, "w": 320, "h": 200}},
                {"id": "g2", "title": "COGNITION", "bounds": {"x": 450, "y": 50, "w": 320, "h": 400}},
                {"id": "g3", "title": "ORCHESTRATION", "bounds": {"x": 850, "y": 50, "w": 320, "h": 300}},
                {"id": "g4", "title": "EXECUTION & CONTROLLERS", "bounds": {"x": 1250, "y": 50, "w": 320, "h": 500}}
            ],
            "nodes": [],
            "edges": []
        },
        "runtime": {
            "groups": [
                {"id": "g1", "title": "INPUT / INGESTION", "bounds": {"x": 50, "y": 50, "w": 320, "h": 200}},
                {"id": "g2", "title": "COGNITION", "bounds": {"x": 450, "y": 50, "w": 320, "h": 400}},
                {"id": "g3", "title": "ORCHESTRATION", "bounds": {"x": 850, "y": 50, "w": 320, "h": 300}},
                {"id": "g4", "title": "EXECUTION & CONTROLLERS", "bounds": {"x": 1250, "y": 50, "w": 320, "h": 500}}
            ],
            "nodes": [],
            "edges": []
        }
    }
    
    # Discovery logic
    files = list(base_dir.rglob("*.py"))
    
    organs = []
    
    for f in files:
        if "organ_" in f.name:
            organs.append(f)
            
    # Mock assignments for the groups
    y_offsets = [100, 220, 340, 460, 580]
    idx_1 = 0
    idx_2 = 0
    idx_3 = 0
    idx_4 = 0
    
    for f in organs:
        node_id = f.stem
        name = f.stem.replace("organ_", "").replace("_single_file", "").replace("_", " ").title()
        
        # Simple heuristic mapping for groups
        if any(k in name.lower() for k in ["interface", "input"]):
            group_x = 70
            group_y = y_offsets[idx_1 % len(y_offsets)]
            idx_1 += 1
        elif any(k in name.lower() for k in ["brain", "memory", "knowledge", "learning", "compiler"]):
            group_x = 470
            group_y = y_offsets[idx_2 % len(y_offsets)]
            idx_2 += 1
        elif any(k in name.lower() for k in ["cns", "orchestrator", "state", "manifest"]):
            group_x = 870
            group_y = y_offsets[idx_3 % len(y_offsets)]
            idx_3 += 1
        else:
            group_x = 1270
            group_y = y_offsets[idx_4 % len(y_offsets)]
            idx_4 += 1
            
        icon = "⚙️"
        if "brain" in name.lower(): icon = "🧠"
        elif "cns" in name.lower(): icon = "⚡"
        elif "agent" in name.lower(): icon = "🤖"
        elif "memory" in name.lower(): icon = "💾"
        elif "cdp" in name.lower(): icon = "🌐"
        
        node = {
            "id": node_id,
            "x": group_x,
            "y": group_y,
            "name": name,
            "desc": "Extracted from source",
            "icon": icon,
            "file": f.name,
            "status": "IDLE"
        }
        
        graph["target"]["nodes"].append(node)
        graph["runtime"]["nodes"].append(node.copy())
        
    # Basic mocked edges for Target
    target_edges = [
        {"source": "organ_11_interface", "target": "organ_01_brain", "label": "user_input"},
        {"source": "organ_01_brain", "target": "organ_36_workflow_compiler", "label": "intent"},
        {"source": "organ_36_workflow_compiler", "target": "organ_02_cns_single_file", "label": "compiled_dag"},
        {"source": "organ_02_cns_single_file", "target": "organ_38_task_orchestrator", "label": "dispatch"},
        {"source": "organ_38_task_orchestrator", "target": "organ_10_agents", "label": "delegate"}
    ]
    
    # Filter edges to ensure nodes exist
    valid_node_ids = {n["id"] for n in graph["target"]["nodes"]}
    for edge in target_edges:
        if edge["source"] in valid_node_ids and edge["target"] in valid_node_ids:
            graph["target"]["edges"].append(edge)
            
    # Mocking Runtime differences (Bypass detected)
    sysboot_node = {
        "id": "system_boot",
        "x": 70,
        "y": 250,
        "name": "System Boot",
        "desc": "Bypassing architecture",
        "icon": "🚀",
        "file": "system_boot.py",
        "status": "IDLE"
    }
    graph["runtime"]["nodes"].append(sysboot_node)
    
    runtime_edges = [
        {"source": "organ_11_interface", "target": "system_boot", "label": "direct_execution", "error": True},
        {"source": "system_boot", "target": "organ_38_task_orchestrator", "label": "BYPASS_DETECTED", "error": True},
        {"source": "organ_38_task_orchestrator", "target": "organ_10_agents", "label": "delegate"}
    ]
    
    for edge in runtime_edges:
        if edge["source"] in valid_node_ids or edge["source"] == "system_boot":
            if edge["target"] in valid_node_ids or edge["target"] == "system_boot":
                graph["runtime"]["edges"].append(edge)
    
    with open(r"d:\new_automation\graph_data.json", "w") as f:
        json.dump(graph, f, indent=4)
        
    print("Graph data generated successfully at d:\\new_automation\\graph_data.json")

if __name__ == "__main__":
    generate_graph_data()
