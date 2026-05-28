import os
import re
from pathlib import Path

# Standard library modules (approximate list)
std_lib = {
    "abc", "argparse", "asyncio", "base64", "collections", "concurrent", "contextlib",
    "contextvars", "copy", "csv", "dataclasses", "datetime", "decimal", "enum", "errno",
    "fnmatch", "functools", "hashlib", "inspect", "io", "itertools", "json", "logging",
    "math", "os", "pathlib", "platform", "random", "re", "shlex", "shutil", "signal",
    "socket", "sqlite3", "string", "subprocess", "sys", "tempfile", "threading", "time",
    "traceback", "typing", "unittest", "urllib", "uuid", "webbrowser", "xml", "pickle",
    "glob", "fnmatch", "bisect", "heapq", "array", "weakref", "types", "gc", "sysconfig",
    "importlib", "zipfile", "tarfile", "tempfile", "shutil", "glob", "fnmatch", "stat",
    "filecmp", "linecache", "tokenize", "tabnanny", "pyclbr", "ast", "symtable", "symbol",
    "token", "keyword", "inspect", "dis", "pickle", "copyreg", "shelve", "marshal",
    "dbm", "gdbm", "hmac", "secrets", "hashlib", "crypt", "getpass", "termios", "tty",
    "pty", "select", "selectors", "asyncore", "asynchat", "mmap", "readline", "rlcompleter",
    "smtplib", "smtpd", "nntplib", "ftplib", "telnetlib", "poplib", "imaplib", "mailbox",
    "mailcap", "mimetypes", "base64", "binhex", "binascii", "quopri", "uu", "html",
    "xmlrpc", "cgi", "cgitb", "wsgiref", "urllib", "http", "ftplib", "getopt", "optparse",
    "gettext", "locale", "warnings", "contextlib", "abc", "atexit", "traceback", "__future__"
}

# Known dependencies from pyproject.toml (mapped to their import names)
deps_mapping = {
    "GitPython": "git",
    "Requests": "requests",
    "aiofiles": "aiofiles",
    "click": "click",
    "firecrawl-py": "firecrawl",
    "httpx": "httpx",
    "keyring": "keyring",
    "keyrings.alt": "keyrings",
    "langchain": "langchain",
    "langchain-anthropic": "langchain_anthropic",
    "langchain-community": "langchain_community",
    "langchain-core": "langchain_core",
    "langchain-mcp-adapters": "langchain_mcp_adapters",
    "langgraph": "langgraph",
    "nest_asyncio": "nest_asyncio",
    "numpy": "numpy",
    "pandas": "pandas",
    "psutil": "psutil",
    "pydantic": "pydantic",
    "litellm": "litellm",
    "lxml": "lxml",
    "rich": "rich",
    "semver": "semver",
    "setuptools": "setuptools",
    "starlette": "starlette",
    "pytest": "pytest",
    "pytest-cov": "pytest_cov",
    "boto3": "boto3",
    "google-cloud-aiplatform": "google",
    "openai": "openai",
    "pillow-heif": "pillow_heif",
    "Pillow": "PIL",
    "textual": "textual",
    "python-dotenv": "dotenv",
    "PyYAML": "yaml",
    "jsonschema": "jsonschema",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "websockets": "websockets",
    "watchdog": "watchdog",
    "tiktoken": "tiktoken",
    "filelock": "filelock"
}

deps_import_names = set(deps_mapping.values())

imported_packages = set()
broken_local_references = []

std_lib.update({"difflib", "textwrap", "tomllib", "any"})

for py_file in Path("pdd").rglob("*.py"):
    with open(py_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Simple regex for imports
    matches = re.findall(r"^(?:import|from)\s+([a-zA-Z0-9_]+)", content, re.MULTILINE)
    for match in matches:
        if match not in std_lib and match != "pdd" and not match.startswith("_"):
            # Check if it's a local module in the same directory
            if (py_file.parent / f"{match}.py").exists() or (py_file.parent / match / "__init__.py").exists():
                continue
            # Check if it's a top-level module in pdd/
            if (Path("pdd") / f"{match}.py").exists() or (Path("pdd") / match / "__init__.py").exists():
                continue
            
            imported_packages.add(match)

# Check for missing dependencies
missing = []
for pkg in imported_packages:
    if pkg not in deps_import_names:
        missing.append(pkg)

# Check for unused dependencies
unused = []
# Actually check if any file imports them
all_imports = set()
for py_file in Path("pdd").rglob("*.py"):
    with open(py_file, "r", encoding="utf-8") as f:
        content = f.read()
    matches = re.findall(r"^(?:import|from)\s+([a-zA-Z0-9_]+)", content, re.MULTILINE)
    all_imports.update(matches)

for dep_pkg, import_name in deps_mapping.items():
    if import_name not in all_imports:
        unused.append(dep_pkg)

print("### Missing Dependencies")
for m in sorted(missing):
    print(f"- {m}")

print("\n### Unused Dependencies")
for u in sorted(unused):
    print(f"- {u}")
