import os
import glob

def fix_future_imports(directory):
    for filepath in glob.glob(os.path.join(directory, '**', '*.py'), recursive=True):
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        future_import_index = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('from __future__ import'):
                future_import_index = i
                break
                
        if future_import_index > 0:
            # Check if there's anything other than comments/docstrings before it
            # To be safe, we can just move it to line 0 if it's not already at line 0 or right after a docstring
            import_line = lines.pop(future_import_index)
            # Find the end of the module docstring if it exists
            insert_idx = 0
            in_docstring = False
            for i, line in enumerate(lines):
                if line.strip().startswith('"""') or line.strip().startswith("'''"):
                    if not in_docstring:
                        in_docstring = True
                        if line.strip().count('"""') == 2 or line.strip().count("'''") == 2:
                            in_docstring = False # single line docstring
                            insert_idx = i + 1
                            break
                    else:
                        in_docstring = False
                        insert_idx = i + 1
                        break
                elif not in_docstring and line.strip() and not line.strip().startswith('#'):
                    # Found code, insert before it
                    insert_idx = i
                    break
            
            lines.insert(insert_idx, import_line)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            print(f"Fixed {filepath}")

if __name__ == '__main__':
    fix_future_imports('d:\\new_automation\\All codes')
