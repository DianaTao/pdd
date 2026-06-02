import os
import sys
import importlib

def check_imports(directory):
    success_count = 0
    fail_count = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".py") and file != "__init__.py":
                rel_path = os.path.relpath(os.path.join(root, file), directory)
                module_name = directory + "." + rel_path[:-3].replace(os.sep, ".")
                try:
                    importlib.import_module(module_name)
                    success_count += 1
                except Exception as e:
                    print(f"FAILED to import {module_name}: {e}")
                    fail_count += 1
    print(f"Summary: {success_count} succeeded, {fail_count} failed")

if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    check_imports("pdd")
