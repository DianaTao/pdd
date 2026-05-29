import re

with open('pdd/__init__.py', 'r') as f:
    content = f.read()

def replacer(match):
    items_str = match.group(2)
    items = items_str.split(',')
    new_items = []
    for item in items:
        item = item.strip()
        if not item or ' as ' in item:
            new_items.append(item)
            continue
        new_items.append(f"{item} as {item}")
    
    # Preserve indentation and join
    # Find original indentation of first item if possible
    first_item_indent = re.search(r'\n(\s+)', items_str)
    indent = first_item_indent.group(1) if first_item_indent else '    '
    
    # We want to keep the original formatting as much as possible, but this is a bit tricky.
    # Simpler: just replace each word with "word as word"
    
    # Regex to find words that are not part of "as"
    def word_replacer(m):
        word = m.group(0)
        if word in ['as', 'import', 'from']:
            return word
        return f"{word} as {word}"

    # Actually, simpler:
    res = re.sub(r'\b(?<! as )(\w+)(?! as)\b', r'\1 as \1', items_str)
    # But wait, that might catch too much.
    return f"from {match.group(1)} import ({res})"

# Handle multiline imports with parentheses
new_content = re.sub(r'from ([\.\w]+) import \((.*?)\)', replacer, content, flags=re.DOTALL)

# Handle single line imports with parentheses
# (already handled by DOTALL)

# Handle single line imports without parentheses: from .module import name
def single_line_replacer(match):
    module = match.group(1)
    names_str = match.group(2)
    names = names_str.split(',')
    new_names = []
    for name in names:
        name = name.strip()
        if not name or ' as ' in name:
            new_names.append(name)
        else:
            new_names.append(f"{name} as {name}")
    return f"from {module} import {', '.join(new_names)}"

new_content = re.sub(r'^from ([\.\w]+) import ([^\(\n]+)$', single_line_replacer, new_content, flags=re.MULTILINE)

with open('pdd/__init__.py', 'w') as f:
    f.write(new_content)
