import ast
import os
import sys
from pathlib import Path

std_libs = set(sys.builtin_module_names)
std_libs.update(sys.modules.keys())
try:
    from stdlib_list import stdlib_list
    std_libs.update(stdlib_list(sys.version_info[:2]))
except:
    pass

std_libs.update([
    "os", "sys", "ast", "pkgutil", "pathlib", "json", "re", "logging", "typing", "collections", 
    "subprocess", "math", "datetime", "time", "random", "urllib", "requests", "http", "socket", 
    "io", "itertools", "functools", "unittest", "pytest", "argparse", "shutil", "glob", "tempfile", 
    "contextlib", "threading", "multiprocessing", "asyncio", "dataclasses", "enum", "uuid", "hashlib", 
    "hmac", "base64", "csv", "sqlite3", "zlib", "gzip", "tarfile", "zipfile", "html", "xml", "json", 
    "configparser", "traceback", "warnings", "weakref", "copy", "pprint", "inspect", "importlib", 
    "difflib", "doctest", "pydoc", "shlex", "typing_extensions", "concurrent", "cProfile", "profile", 
    "pstats", "timeit", "trace", "tracemalloc", "gc", "sysconfig", "site", "venv", "cmd", "code", 
    "codeop", "pty", "tty", "termios", "fcntl", "pwd", "grp", "spwd", "crypt", "resource", "nis", 
    "syslog", "getpass", "__future__", "contextvars", "platform", "py_compile", "signal", "tabnanny", 
    "textwrap", "tomllib", "webbrowser", "msvcrt", "secrets", "types"
])

pkg_map = {
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "bs4": "beautifulsoup4",
    "PIL": "pillow",
    "github": "pygithub",
    "git": "gitpython",
    "langchain_anthropic": "langchain-anthropic",
    "langchain_aws": "langchain-aws",
    "langchain_community": "langchain-community",
    "langchain_core": "langchain-core",
    "langchain_fireworks": "langchain-fireworks",
    "langchain_google_genai": "langchain-google-genai",
    "langchain_google_vertexai": "langchain-google-vertexai",
    "langchain_groq": "langchain-groq",
    "langchain_mcp_adapters": "langchain-mcp-adapters",
    "langchain_ollama": "langchain-ollama",
    "langchain_openai": "langchain-openai",
    "langchain_together": "langchain-together",
    "mcp": "mcp",
    "pillow_heif": "pillow-heif",
    "firecrawl": "firecrawl-py",
    "z3": "z3-solver",
    "keyrings": "keyrings.alt",
    "boto3": "boto3",
    "diffusers": "diffusers",
    "email_validator": "email-validator",
    "qrcode": "qrcode",
    "streamlit": "streamlit",
    "torch": "torch",
    "transformers": "transformers",
    "typer": "typer"
}

def get_declared_deps():
    deps = set()
    req_file = Path("requirements.txt")
    if req_file.exists():
        with open(req_file) as f:
            for line in f:
                line = line.split('#')[0].strip()
                if line:
                    deps.add(line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].split('[')[0].strip().replace('_', '-').lower())
    return deps

def get_imports(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return set(), set()
    
    imports = set()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                imports.add(node.module.split('.')[0])
                
    return imports

def main():
    declared = get_declared_deps()
    all_imports = set()
    
    src_dirs = [Path("pdd"), Path("tests")]
    for root_dir in src_dirs:
        for py_file in root_dir.rglob("*.py"):
            # skip tests/fixtures
            if "fixtures" in py_file.parts: continue
            if "data" in py_file.parts: continue
            all_imports.update(get_imports(py_file))
            
    # filter stdlib
    third_party = set()
    for imp in all_imports:
        if imp in std_libs: continue
        if imp == "pdd": continue
        if imp in pkg_map:
            third_party.add(pkg_map[imp].lower())
        else:
            third_party.add(imp.replace('_', '-').lower())
        
    missing = third_party - declared
    
    # unused should include mapping reverse
    used_deps = set()
    for imp in all_imports:
        if imp in pkg_map:
            used_deps.add(pkg_map[imp].lower())
        else:
            used_deps.add(imp.replace('_', '-').lower())
    
    ignored_unused = {
        "setuptools", "pytest", "pytest-cov", "pytest-testmon", "pytest-xdist", 
        "pytest-mock", "pytest-asyncio", "pytest-timeout", "build", "twine", 
        "google-cloud-aiplatform", "boto3", "firebase-admin", "watchdog", 
        "uvicorn", "litellm", "fastapi"
    }
    
    unused = declared - used_deps - ignored_unused
    
    print("MISSING:")
    for m in sorted(missing): print(m)
    print("UNUSED:")
    for u in sorted(unused): print(u)
    
if __name__ == "__main__":
    main()
