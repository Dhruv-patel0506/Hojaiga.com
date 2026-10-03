import os

base_dir = r"d:\new_automation\diagrams"
os.makedirs(base_dir, exist_ok=True)

template = """# HOJAIGA - PIPELINE {pipeline} CONNECTION STATUS DIAGRAMS (Organ {organ})

## DIAGRAM 1: BEFORE CONNECTION
![Before Connection](diagram_{pipeline}_before_connection.png)

## DIAGRAM 2: AFTER CONNECTION
![After Connection](diagram_{pipeline}_after_connection.png)

## DIAGRAM 3: SYSTEM BUILD (CUMULATIVE ARCHITECTURE)
![System Build](diagram_{pipeline}_system_build.png)
"""

for i in range(5, 36):
    pipeline = f"{i:02d}"
    organ = i + 1
    content = template.format(pipeline=pipeline, organ=organ)
    
    file_path = os.path.join(base_dir, f"diagram_{pipeline}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

print("Generated diagram files 05 to 35.")
