"""
HOJAIGA AUTOMATION SYSTEM - NAMING UPDATE SCRIPT

This script updates all CrewAI references to Hojaiga throughout the codebase
while maintaining functionality for internal reference only.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

# Configuration
CODEBASE_ROOT = Path(r"D:\new_automation\All codes")
LOG_FILE = Path(r"D:\new_automation\naming_update_log.txt")

# Mapping of CrewAI references to Hojaiga references
NAMING_MAPPINGS = {
    # External naming (for user-facing display)
    "CrewAI": "Hojaiga",
    "crewai": "hojaiga",
    "CrewAI Engine": "Hojaiga Intelligence Engine",
    "CrewAI Framework": "Hojaiga Framework",
    
    # Internal references (keep for functionality)
    # These should NOT be changed as they refer to the actual library
    # "from crewai import" -> Keep as is (library import)
    # "crewai.Agent" -> Keep as is (library class)
}

# Patterns to update (external-facing only)
PATTERNS_TO_UPDATE = [
    # Comments and docstrings (user-facing)
    (r'# .*CrewAI', lambda m: m.group(0).replace('CrewAI', 'Hojaiga')),
    (r'""".*CrewAI.*"""', lambda m: m.group(0).replace('CrewAI', 'Hojaiga')),
    (r"'''.*CrewAI.*'''", lambda m: m.group(0).replace('CrewAI', 'Hojaiga')),
    
    # Logger names (internal reference only)
    (r'logger.*crewai', lambda m: m.group(0).replace('crewai', 'hojaiga')),
    
    # Variable names (external-facing)
    (r'crewai_engine', 'hojaiga_engine'),
    (r'crewai_agent', 'hojaiga_agent'),
    (r'crewai_task', 'hojaiga_task'),
    
    # String literals in messages (user-facing)
    (r'"[^"]*CrewAI[^"]*"', lambda m: m.group(0).replace('CrewAI', 'Hojaiga')),
    (r"'[^']*CrewAI[^']*'", lambda m: m.group(0).replace('CrewAI', 'Hojaiga')),
]

# Patterns to preserve (library imports, functionality)
PATTERNS_TO_PRESERVE = [
    r'from crewai import',
    r'import crewai',
    r'crewai\.Agent',
    r'crewai\.Task',
    r'crewai\.Crew',
    r'crewai\.Tool',
]

def should_preserve_line(line: str) -> bool:
    """Check if a line should be preserved (library import)."""
    for pattern in PATTERNS_TO_PRESERVE:
        if re.search(pattern, line):
            return True
    return False

def update_file(file_path: Path) -> Tuple[int, int]:
    """
    Update a single file.
    
    Returns:
        (changes_made, lines_processed)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        lines = content.split('\n')
        updated_lines = []
        changes_made = 0
        
        for line in lines:
            # Skip library imports
            if should_preserve_line(line):
                updated_lines.append(line)
                continue
            
            # Apply naming updates
            updated_line = line
            for pattern, replacement in PATTERNS_TO_UPDATE:
                if callable(replacement):
                    updated_line = re.sub(pattern, replacement, updated_line)
                else:
                    updated_line = re.sub(pattern, replacement, updated_line)
            
            if updated_line != line:
                changes_made += 1
            
            updated_lines.append(updated_line)
        
        if changes_made > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(updated_lines))
        
        return changes_made, len(lines)
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0, 0

def update_clicky_references(file_path: Path) -> int:
    """
    Update 'clicky' references to 'Hojaiga Clicky Mode' for clarity.
    
    Returns:
        Number of changes made
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Update clicky references
        content = re.sub(r'"clicky"', '"hojaiga_clicky"', content)
        content = re.sub(r"'clicky'", "'hojaiga_clicky'", content)
        content = re.sub(r'MouseMode\.CLICKY', 'MouseMode.HOJAIGA_CLICKY', content)
        content = re.sub(r'clicky mode', 'Hojaiga Clicky mode', content, flags=re.IGNORECASE)
        
        changes_made = 1 if content != original_content else 0
        
        if changes_made > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        return changes_made
        
    except Exception as e:
        print(f"Error processing clicky references in {file_path}: {e}")
        return 0

def main():
    """Main function to update naming throughout the codebase."""
    print("=" * 80)
    print("HOJAIGA NAMING UPDATE SCRIPT")
    print("=" * 80)
    print()
    
    # Find all Python files
    python_files = list(CODEBASE_ROOT.rglob("*.py"))
    print(f"Found {len(python_files)} Python files to process")
    print()
    
    total_changes = 0
    total_files_changed = 0
    total_clicky_changes = 0
    
    log_entries = []
    
    for file_path in python_files:
        # Skip certain files
        if any(skip in str(file_path) for skip in ['__pycache__', '.git', 'venv']):
            continue
        
        # Update CrewAI references
        changes, lines = update_file(file_path)
        if changes > 0:
            total_changes += changes
            total_files_changed += 1
            log_entries.append(f"Updated {file_path}: {changes} changes")
            print(f"✓ Updated {file_path.name}: {changes} changes")
        
        # Update clicky references
        clicky_changes = update_clicky_references(file_path)
        if clicky_changes > 0:
            total_clicky_changes += clicky_changes
            log_entries.append(f"Updated clicky in {file_path}: {clicky_changes} changes")
            print(f"✓ Updated clicky in {file_path.name}: {clicky_changes} changes")
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total files processed: {len(python_files)}")
    print(f"Files with changes: {total_files_changed}")
    print(f"Total CrewAI→Hojaiga changes: {total_changes}")
    print(f"Total clicky naming changes: {total_clicky_changes}")
    print()
    
    # Write log
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write("HOJAIGA NAMING UPDATE LOG\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Total files processed: {len(python_files)}\n")
        f.write(f"Files with changes: {total_files_changed}\n")
        f.write(f"Total CrewAI→Hojaiga changes: {total_changes}\n")
        f.write(f"Total clicky naming changes: {total_clicky_changes}\n\n")
        f.write("CHANGES:\n")
        f.write("-" * 80 + "\n")
        for entry in log_entries:
            f.write(entry + "\n")
    
    print(f"Log saved to: {LOG_FILE}")
    print()
    print("NOTE: Library imports (from crewai import) were preserved for functionality.")
    print("      Only user-facing naming was updated to Hojaiga.")
    print()

if __name__ == "__main__":
    main()
