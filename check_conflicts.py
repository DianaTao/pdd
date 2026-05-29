import sys

def parse_reqs(filename):
    deps = {}
    with open(filename) as f:
        for line in f:
            line = line.split('#')[0].strip()
            if not line: continue
            if '==' in line:
                pkg, ver = line.split('==')
                deps[pkg.strip()] = '==' + ver.strip()
            elif '>=' in line:
                pkg, ver = line.split('>=', 1)
                deps[pkg.strip().split('[')[0]] = '>=' + ver.strip()
            else:
                deps[line.strip()] = 'any'
    return deps

def main():
    
    reqs = parse_reqs("requirements.txt")
    import re
    with open("pyproject.toml") as f:
        content = f.read()
    
    # naive extraction
    in_deps = False
    pyproj_deps = {}
    for line in content.split('\n'):
        if line.strip() == 'dependencies = [':
            in_deps = True
            continue
        if in_deps:
            if line.strip() == ']':
                break
            dep = line.strip().strip('",')
            if '==' in dep:
                pkg, ver = dep.split('==')
                pyproj_deps[pkg.strip()] = '==' + ver.strip()
            elif '>=' in dep:
                pkg, ver = dep.split('>=', 1)
                pyproj_deps[pkg.strip().split('[')[0]] = '>=' + ver.strip()
            else:
                pyproj_deps[dep.strip()] = 'any'

    print("Conflicts:")
    for pkg, ver in reqs.items():
        if pkg in pyproj_deps:
            if pyproj_deps[pkg] != ver:
                print(f"{pkg}: requirements.txt has {ver}, pyproject.toml has {pyproj_deps[pkg]}")
        else:
            print(f"{pkg} is in requirements.txt but not in pyproject.toml")

    for pkg, ver in pyproj_deps.items():
        if pkg not in reqs:
            print(f"{pkg} is in pyproject.toml but not in requirements.txt")

if __name__ == "__main__":
    main()
