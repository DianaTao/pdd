import re

with open('pdd/__init__.py', 'r') as f:
    lines = f.readlines()

new_lines = []
import_lines = []
other_lines = []

# Standard library imports and from __future__ stay at the top
top_imports = []
in_internal_imports = False

for line in lines:
    if line.startswith('from .') or line.startswith('from pdd.'):
        # Apply 'as name'
        def repl(match):
            name = match.group(0)
            if ' as ' in name: return name
            return f"{name} as {name}"
        
        # This is a bit simple but should work for the current file structure
        processed_line = re.sub(r'\b(?<! as )(?<!\.)([a-zA-Z_]\w*)(?! as)\b', repl, line.replace('from ', 'TEMP_FROM ').replace(' import ', ' TEMP_IMPORT ')).replace('TEMP_FROM ', 'from ').replace(' TEMP_IMPORT ', ' import ')
        import_lines.append(processed_line)
    elif line.startswith('from ') or line.startswith('import '):
        top_imports.append(line)
    elif line.strip() == '' and not other_lines and not import_lines:
        # Skip empty lines at the very top
        continue
    else:
        other_lines.append(line)

# Reconstruct
final_lines = []
if lines[0].startswith('"""'):
    final_lines.append(lines[0])
    if len(lines) > 1 and lines[1].strip() == '':
        final_lines.append('\n')
    start_idx = 1 if lines[1].strip() != '' else 2
else:
    start_idx = 0

# Actually, let's just do it manually to be safe.
# Top: Docstring, __future__, stdlib, then internal imports, then rest.
