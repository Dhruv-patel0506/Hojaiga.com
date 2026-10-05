import json
import os

def create_base_layout(cols=20, rows=20):
    # TileTypes: 0=WALL, 255=VOID, 1=FLOOR_1, 2=FLOOR_2
    tiles = []
    tileColors = []
    for r in range(rows):
        for c in range(cols):
            if r == 0 or r == rows - 1 or c == 0 or c == cols - 1:
                tiles.append(0) # Wall
                tileColors.append(None)
            else:
                tiles.append(1) # Floor 1
                tileColors.append({"h": 35, "s": 20, "b": 10, "c": 0})
    return {
        "version": 1,
        "cols": cols,
        "rows": rows,
        "tiles": tiles,
        "tileColors": tileColors,
        "furniture": [],
        "pets": []
    }

def generate_reception():
    layout = create_base_layout()
    # Entrance (Slider door on extreme left)
    # We'll just make the wall open at row 10
    layout["tiles"][10 * 20 + 0] = 1 # Floor
    
    # Reception Desk
    # Furniture types: 'DESK_FRONT', 'WOODEN_CHAIR_FRONT', 'PLANT'
    layout["furniture"].append({
        "type": "DESK_FRONT",
        "col": 4,
        "row": 9,
        "orientation": "front",
        "label": "Reception Desk"
    })
    
    # Receptionist Chair
    layout["furniture"].append({
        "type": "WOODEN_CHAIR_FRONT",
        "col": 5,
        "row": 10,
        "orientation": "front",
        "label": "Receptionist"
    })

    # Passageway bottom right (door to CEO)
    layout["tiles"][19 * 20 + 18] = 1 # Floor

    return layout

def generate_core():
    layout = create_base_layout()
    # Left Office (CEO)
    layout["furniture"].append({
        "type": "DESK_FRONT",
        "col": 4, "row": 5, "orientation": "front", "label": "CEO Desk"
    })
    layout["furniture"].append({
        "type": "WOODEN_CHAIR_FRONT",
        "col": 5, "row": 6, "orientation": "front", "label": "CEO"
    })
    layout["furniture"].append({
        "type": "PLANT",
        "col": 2, "row": 5, "orientation": "front", "label": "CEO Plant"
    })

    # Right Office (Manager)
    layout["furniture"].append({
        "type": "DESK_FRONT",
        "col": 14, "row": 5, "orientation": "front", "label": "Manager Desk"
    })
    layout["furniture"].append({
        "type": "WOODEN_CHAIR_FRONT",
        "col": 15, "row": 6, "orientation": "front", "label": "Manager"
    })
    layout["furniture"].append({
        "type": "WHITEBOARD",
        "col": 13, "row": 5, "orientation": "front"
    })
    
    # Server Racks (Think Tank)
    layout["furniture"].append({
        "type": "BOOKSHELF",
        "col": 8, "row": 15, "orientation": "front", "label": "Server Rack"
    })
    layout["furniture"].append({
        "type": "BOOKSHELF",
        "col": 11, "row": 15, "orientation": "front", "label": "Server Rack"
    })
    return layout

def generate_execution():
    layout = create_base_layout()
    # Row of desks for execution agents
    for i in range(3):
        layout["furniture"].append({
            "type": "DESK_FRONT",
            "col": 4 + (i*5), "row": 10, "orientation": "front"
        })
        layout["furniture"].append({
            "type": "PC_FRONT_OFF",
            "col": 4 + (i*5), "row": 10, "orientation": "front"
        })
    return layout

def generate_agent_room():
    layout = create_base_layout()
    # Dense desk layout for interns/agents
    for r in [5, 12]:
        for c in [3, 8, 13]:
            layout["furniture"].append({
                "type": "DESK_FRONT",
                "col": c, "row": r, "orientation": "front"
            })
            layout["furniture"].append({
                "type": "WOODEN_CHAIR_FRONT",
                "col": c+1, "row": r+1, "orientation": "front"
            })
    return layout

def main():
    target_dir = r"D:\new_automation\hojaiga_pixel_automation\webview-ui\public\assets"
    os.makedirs(target_dir, exist_ok=True)
    
    zones = {
        "zone1_reception.json": generate_reception(),
        "zone2_core.json": generate_core(),
        "zone3_execution.json": generate_execution(),
        "zone4_agent.json": generate_agent_room(),
    }
    
    for filename, layout in zones.items():
        path = os.path.join(target_dir, filename)
        with open(path, "w") as f:
            json.dump(layout, f, indent=2)
        print(f"Generated {path}")

if __name__ == "__main__":
    main()
