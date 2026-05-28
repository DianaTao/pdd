import os
import re
import sys
from pathlib import Path

# Get all stdlib modules
import sysconfig
std_lib = set(sys.builtin_module_names)
# Add some common ones that might not be in builtin
std_lib.update(["os", "sys", "re", "json", "time", "datetime", "pathlib", "subprocess", "shutil", "tempfile", "hashlib", "base64", "typing", "collections", "abc", "argparse", "asyncio", "contextlib", "dataclasses", "enum", "functools", "inspect", "io", "logging", "math", "platform", "random", "shlex", "signal", "socket", "sqlite3", "string", "threading", "traceback", "unittest", "urllib", "uuid", "webbrowser", "xml", "pickle", "glob", "fnmatch", "bisect", "heapq", "array", "weakref", "types", "gc", "importlib", "zipfile", "tarfile", "stat", "filecmp", "linecache", "tokenize", "tabnanny", "pyclbr", "ast", "symtable", "symbol", "token", "keyword", "dis", "copyreg", "shelve", "marshal", "dbm", "hmac", "secrets", "crypt", "getpass", "termios", "tty", "pty", "select", "selectors", "mmap", "readline", "rlcompleter", "smtplib", "smtpd", "nntplib", "ftplib", "telnetlib", "poplib", "imaplib", "mailbox", "mailcap", "mimetypes", "binhex", "binascii", "quopri", "uu", "html", "xmlrpc", "cgi", "cgitb", "wsgiref", "getopt", "optparse", "gettext", "locale", "warnings", "atexit", "__future__", "difflib", "textwrap", "errno"])

# Try to get more from sysconfig
paths = sysconfig.get_paths()
purelib = paths.get("purelib")
if purelib:
    std_lib.update([p.stem for p in Path(purelib).glob("*.py")])

# Dependencies from pyproject.toml (import names)
deps_import_names = {
    "git", "requests", "aiofiles", "click", "firecrawl", "httpx",
    "keyring", "keyrings", "langchain", "langchain_anthropic", "langchain_community",
    "langchain_core", "langchain_mcp_adapters", "langgraph", "nest_asyncio", "numpy",
    "pandas", "psutil", "pydantic", "litellm", "lxml", "rich", "semver", "setuptools",
    "starlette", "pytest", "pytest_cov", "boto3", "google", "openai", "pillow_heif",
    "PIL", "textual", "dotenv", "yaml", "jsonschema", "fastapi", "uvicorn",
    "websockets", "watchdog", "tiktoken", "filelock"
}

std_lib.update({"tomllib", "any"})

imported_packages = set()

for py_file in Path("pdd").rglob("*.py"):
    with open(py_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Match any import
    matches = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_]+)", content, re.MULTILINE)
    for match in matches:
        if match in std_lib or match == "pdd" or match.startswith("_"):
            continue
        
        # Check if local
        if (py_file.parent / f"{match}.py").exists() or (py_file.parent / match / "__init__.py").exists():
            continue
        if (Path("pdd") / f"{match}.py").exists() or (Path("pdd") / match / "__init__.py").exists():
            continue
            
        imported_packages.add(match)

missing = []
for pkg in imported_packages:
    if pkg not in deps_import_names:
        missing.append(pkg)

print("### Missing Dependencies")
for m in sorted(missing):
    print(f"- {m}")
