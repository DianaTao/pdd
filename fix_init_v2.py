import re

with open('pdd/__init__.py', 'r') as f:
    content = f.read()

def process_items(items_str):
    # This function handles the comma separated items
    # It preserves indentation and comments as much as possible
    
    def item_replacer(match):
        item = match.group(0)
        # If it's already an alias or 'import' or 'from' or 'as', leave it
        if ' as ' in item or item in ['import', 'from', 'as']:
            return item
        # If it's a word, turn it into 'word as word'
        return f"{item} as {item}"

    # We only want to replace words that are actual names being imported
    # Names are \w+ and are usually separated by commas, spaces, or newlines
    
    # Use a regex that finds identifiers but skips 'as'
    res = re.sub(r'\b(?<! as )(?<!\.)([a-zA-Z_]\w*)(?! as)\b', item_replacer, items_str)
    return res

def multiline_replacer(match):
    module = match.group(1)
    # Only process internal imports
    if not (module.startswith('.') or module.startswith('pdd')):
        return match.group(0)
    
    items_str = match.group(2)
    return f"from {module} import ({process_items(items_str)})"

def singleline_replacer(match):
    module = match.group(1)
    if not (module.startswith('.') or module.startswith('pdd')):
        return match.group(0)
    
    items_str = match.group(2)
    return f"from {module} import {process_items(items_str)}"

# Handle multiline imports with parentheses
new_content = re.sub(r'from ([\.\w]+) import \((.*?)\)', multiline_replacer, content, flags=re.DOTALL)

# Handle single line imports
new_content = re.sub(r'^from ([\.\w]+) import ([^\(\n]+)$', singleline_replacer, new_content, flags=re.MULTILINE)

with open('pdd/__init__.py', 'w') as f:
    f.write(new_content)
