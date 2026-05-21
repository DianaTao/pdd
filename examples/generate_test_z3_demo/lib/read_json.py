"""
Extract the first valid JSON object or array from a file that may contain
leading/trailing non-JSON lines (e.g. 'Checking for updates...' or
'--- Command Execution Summary ---' appended by pdd).

Usage:
    python3 lib/read_json.py <file> [<python-expr>]

The expression is evaluated with:
    d   = parsed JSON (list or dict)
    obj = d[0] if list else d
"""
import json
import sys


def extract_json(path: str):
    raw = open(path, encoding="utf-8", errors="replace").read()
    # Find outermost array or object using bracket matching
    for open_c, close_c in (("[", "]"), ("{", "}")):
        start = raw.find(open_c)
        if start == -1:
            continue
        # Find matching close by scanning from the end
        end = raw.rfind(close_c)
        if end == -1 or end < start:
            continue
        candidate = raw[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


if __name__ == "__main__":
    path = sys.argv[1]
    expr = sys.argv[2] if len(sys.argv) > 2 else "d"
    data = extract_json(path)
    if data is None:
        print("ERROR: no JSON found")
        sys.exit(1)
    d = data
    obj = d[0] if isinstance(d, list) and d else d
    print(eval(expr))  # noqa: S307
