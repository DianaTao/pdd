import ast
import os
import sys
from pathlib import Path

def find_broken_imports():
    src_dirs = [Path("pdd"), Path("tests")]
    broken = []
    
    # gather all valid module names within the project (simplistic)
    # real check would trace exact paths
    for root_dir in src_dirs:
        for py_file in root_dir.rglob("*.py"):
            if "fixtures" in py_file.parts or "data" in py_file.parts: continue
            
            with open(py_file, "r", encoding="utf-8") as f:
                try:
                    tree = ast.parse(f.read(), filename=str(py_file))
                except SyntaxError:
                    continue
            
            # Very basic check for relative imports
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level > 0:
                        # relative import
                        # level 1 = current dir, level 2 = parent, etc.
                        module_parts = ()
                        if node.module:
                            module_parts = tuple(node.module.split('.'))
                        
                        target_dir = py_file.parent
                        for _ in range(node.level - 1):
                            target_dir = target_dir.parent
                            
                        # Target could be a package (dir with __init__.py) or a module (.py)
                        if len(module_parts) > 0:
                            # e.g., from .foo import bar
                            pkg_path = target_dir.joinpath(*module_parts)
                            mod_path = target_dir.joinpath(*module_parts[:-1], module_parts[-1] + ".py")
                            if not (pkg_path.is_dir() or mod_path.is_file()):
                                broken.append((str(py_file), f"{'.' * node.level}{node.module}"))
                    elif node.module:
                        # absolute import
                        parts = node.module.split('.')
                        if parts[0] == "pdd":
                            pkg_path = Path(*parts)
                            mod_path = Path(*parts[:-1], parts[-1] + ".py")
                            if not (pkg_path.is_dir() or mod_path.is_file()):
                                broken.append((str(py_file), node.module))

    return broken

if __name__ == "__main__":
    broken = find_broken_imports()
    if not broken:
        print("No broken local imports found!")
    else:
        for f, imp in broken:
            print(f"File: {f} -> Broken import: {imp}")
