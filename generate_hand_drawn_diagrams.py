import os
import matplotlib.pyplot as plt

base_dir = r"d:\new_automation\diagrams"
os.makedirs(base_dir, exist_ok=True)

# Turn on xkcd style for hand-drawn look
plt.xkcd()

def create_diagram(filename, title, text):
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Hide axes
    ax.spines['right'].set_color('none')
    ax.spines['top'].set_color('none')
    ax.spines['left'].set_color('none')
    ax.spines['bottom'].set_color('none')
    ax.set_xticks([])
    ax.set_yticks([])
    
    # Add title and text
    plt.title(title, fontsize=16)
    plt.text(0.5, 0.5, text, ha='center', va='center', fontsize=14, wrap=True)
    
    # Draw a hand-drawn looking box around the text
    import matplotlib.patches as patches
    rect = patches.Rectangle((0.1, 0.3), 0.8, 0.4, linewidth=2, edgecolor='black', facecolor='none')
    ax.add_patch(rect)
    
    filepath = os.path.join(base_dir, filename)
    plt.savefig(filepath, bbox_inches='tight')
    plt.close()

for i in range(5, 36):
    pipeline = f"{i:02d}"
    organ = i + 1
    
    # 1. Before connection
    create_diagram(
        f"diagram_{pipeline}_before_connection.png",
        f"Pipeline {pipeline} (Organ {organ})",
        "BEFORE CONNECTION\n[Isolated Organ State]"
    )
    
    # 2. After connection
    create_diagram(
        f"diagram_{pipeline}_after_connection.png",
        f"Pipeline {pipeline} (Organ {organ})",
        "AFTER CONNECTION\n[Linked to System]"
    )
    
    # 3. System build
    create_diagram(
        f"diagram_{pipeline}_system_build.png",
        f"Pipeline {pipeline} (Organ {organ})",
        "SYSTEM BUILD\n[Cumulative Architecture]"
    )
    print(f"Generated images for pipeline {pipeline}")

print("All diagram images generated successfully.")
