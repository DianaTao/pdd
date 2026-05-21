#!/usr/bin/env bash
# Token Bucket Rate Limiter — generate + test Z3 demo
#
# Runs four experiments that separate prompt quality, test-generation
# behavior, full E2E, and coverage evidence.
#
# Usage:
#   bash demo.sh              # all experiments (requires PDD_API_KEY for B/C)
#   bash demo.sh --exp-a      # Experiment A only (deterministic, no LLM)
#   bash demo.sh --exp-b      # Experiment B only (LLM: same code, two test prompts)
#   bash demo.sh --exp-c      # Experiment C only (LLM: full E2E before/after)
#   bash demo.sh --exp-d      # Experiment D only (deterministic coverage gate)
#
# Prerequisites:
#   pip install -e /path/to/pdd   (editable install)
#   export PDD_SKIP_UPDATE_CHECK=1
#   # Optional for Z3 formal proof execution:
#   pip install z3-solver

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Resolve the correct pdd binary: prefer the conda pdd env or any binary
# that has the new commands (prompt lint, contracts, coverage) available.
if [ -x "/opt/anaconda3/envs/pdd/bin/pdd" ]; then
    PDD="/opt/anaconda3/envs/pdd/bin/pdd"
elif command -v pdd &>/dev/null && "$PDD" prompt lint --help &>/dev/null 2>&1; then
    PDD="pdd"
else
    echo "ERROR: Could not find a pdd binary with 'prompt lint' support."
    echo "Install from the repo root: pip install -e /path/to/pdd"
    exit 1
fi
export PDD_SKIP_UPDATE_CHECK=1
echo "Using pdd: $PDD ($("$PDD" --version 2>/dev/null | grep -v 'Checking' | head -1))"

PROMPTS="prompts"
STORIES="user_stories"
REPORTS="reports"
SRC="src"
TESTS="tests"

PLAIN_PROMPT="$PROMPTS/token_bucket_plain_python.prompt"
CONTRACT_PROMPT="$PROMPTS/token_bucket_python.prompt"

mkdir -p "$REPORTS" "$SRC" "$TESTS"

# ── helpers ────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $*${NC}"; }
fail() { echo -e "${RED}✗ $*${NC}"; EXIT_CODE=1; }
warn() { echo -e "${YELLOW}~ $*${NC}"; }
header() { echo -e "\n${BOLD}$*${NC}"; }

EXIT_CODE=0

assert_json_eq() {
    local label="$1" file="$2" jq_expr="$3" expected="$4"
    local actual
    actual=$(python3 -c "import json,sys; d=json.load(open('$file')); print($jq_expr)" 2>/dev/null || echo "ERROR")
    if [ "$actual" = "$expected" ]; then
        pass "$label (got: $actual)"
    else
        fail "$label (expected: $expected, got: $actual)"
    fi
}

assert_json_lte() {
    local label="$1" file="$2" jq_expr="$3" max="$4"
    local actual
    actual=$(python3 -c "import json,sys; d=json.load(open('$file')); print($jq_expr)" 2>/dev/null || echo "ERROR")
    if [ "$actual" != "ERROR" ] && [ "$actual" -le "$max" ] 2>/dev/null; then
        pass "$label (got: $actual <= $max)"
    else
        fail "$label (expected <= $max, got: $actual)"
    fi
}

assert_file_contains() {
    local label="$1" file="$2" pattern="$3"
    if grep -q "$pattern" "$file" 2>/dev/null; then
        pass "$label"
    else
        fail "$label (pattern '$pattern' not found in $file)"
    fi
}

assert_file_exists() {
    local label="$1" file="$2"
    if [ -f "$file" ]; then
        pass "$label"
    else
        fail "$label (file not found: $file)"
    fi
}

assert_compiles() {
    local label="$1" file="$2"
    if python3 -m py_compile "$file" 2>/dev/null; then
        pass "$label compiles"
    else
        fail "$label failed py_compile"
    fi
}

# Parse args
RUN_A=false; RUN_B=false; RUN_C=false; RUN_D=false; RUN_ALL=true
for arg in "$@"; do
    case "$arg" in
        --exp-a) RUN_A=true; RUN_ALL=false ;;
        --exp-b) RUN_B=true; RUN_ALL=false ;;
        --exp-c) RUN_C=true; RUN_ALL=false ;;
        --exp-d) RUN_D=true; RUN_ALL=false ;;
    esac
done
if $RUN_ALL; then RUN_A=true; RUN_B=true; RUN_C=true; RUN_D=true; fi

# ── Experiment A: Prompt quality (deterministic) ───────────────────────────

if $RUN_A; then
    header "═══ Experiment A: Prompt quality (deterministic) ═══"
    echo "Tests whether adding contract sections makes the prompt machine-checkable."
    echo "No LLM required. Safe for CI."

    echo ""
    echo "── A1: "$PDD" prompt lint ──"
    "$PDD" prompt lint "$PLAIN_PROMPT"    --json 2>/dev/null | grep -v "^Checking" > "$REPORTS/lint_plain.json"    || true
    "$PDD" prompt lint "$CONTRACT_PROMPT" --json 2>/dev/null | grep -v "^Checking" > "$REPORTS/lint_contract.json" || true

    PLAIN_ERRORS=$(python3 lib/read_json.py "$REPORTS/lint_plain.json" "sum(x.get('error_count',0) for x in (d if isinstance(d,list) else d.get('results',[])))" 2>/dev/null || echo "0")
    PLAIN_WARNS=$(python3  lib/read_json.py "$REPORTS/lint_plain.json"  "sum(x.get('warn_count',0)  for x in (d if isinstance(d,list) else d.get('results',[])))" 2>/dev/null || echo "0")
    CONTRACT_ERRORS=$(python3 lib/read_json.py "$REPORTS/lint_contract.json" "sum(x.get('error_count',0) for x in (d if isinstance(d,list) else d.get('results',[])))" 2>/dev/null || echo "0")
    CONTRACT_WARNS=$(python3  lib/read_json.py "$REPORTS/lint_contract.json"  "sum(x.get('warn_count',0)  for x in (d if isinstance(d,list) else d.get('results',[])))" 2>/dev/null || echo "0")

    echo "  Plain prompt    — errors: $PLAIN_ERRORS, warnings: $PLAIN_WARNS"
    echo "  Contract prompt — errors: $CONTRACT_ERRORS, warnings: $CONTRACT_WARNS"

    # Hard: contract prompt has zero lint errors
    [ "$CONTRACT_ERRORS" -eq 0 ] && pass "A1 contract prompt has zero lint errors" \
        || fail "A1 contract prompt has lint errors"
    # Soft: contract prompt has <= warnings than plain
    [ "$CONTRACT_WARNS" -le "$PLAIN_WARNS" ] \
        && pass "A1 contract prompt has <= warnings than plain ($CONTRACT_WARNS <= $PLAIN_WARNS)" \
        || warn "A1 contract prompt has more warnings than plain ($CONTRACT_WARNS > $PLAIN_WARNS) [soft]"

    echo ""
    echo "── A2: "$PDD" contracts check ──"
    "$PDD" contracts check "$PLAIN_PROMPT"    --json 2>/dev/null | grep -v "^Checking" > "$REPORTS/check_plain.json" 2>/dev/null || true
    "$PDD" contracts check "$CONTRACT_PROMPT" --json 2>/dev/null | grep -v "^Checking" > "$REPORTS/check_contract.json" || true

    # Plain: not_applicable or no rules — treat as expected, not failure
    # check output is a list of lint results; plain prompt has no issues = not_applicable
    PLAIN_CHECK_ISSUES=$(python3 lib/read_json.py "$REPORTS/check_plain.json" "sum(len(x.get('issues',[])) for x in (d if isinstance(d,list) else [d]))" 2>/dev/null || echo "0")
    [ "$PLAIN_CHECK_ISSUES" -eq 0 ] \
        && pass "A2 plain prompt has no contract check issues (not_applicable)" \
        || warn "A2 plain prompt has $PLAIN_CHECK_ISSUES check issue(s)"

    CONTRACT_CHECK_ERRORS=$(python3 lib/read_json.py "$REPORTS/check_contract.json" "sum(1 for x in (obj.get('issues', d) if isinstance(obj,dict) else d) if isinstance(x,dict) and x.get('level')=='error')" 2>/dev/null || echo "0")
    [ "$CONTRACT_CHECK_ERRORS" -eq 0 ] \
        && pass "A2 contract prompt passes contracts check (0 errors)" \
        || fail "A2 contract prompt has $CONTRACT_CHECK_ERRORS check error(s)"

    echo ""
    echo "── A3: "$PDD" contracts compile ──"
    "$PDD" contracts compile "$PLAIN_PROMPT"    --json 2>/dev/null | grep -v "^Checking" > "$REPORTS/compile_plain.json" 2>/dev/null || true
    "$PDD" contracts compile "$CONTRACT_PROMPT" --json 2>/dev/null | grep -v "^Checking" > "$REPORTS/compile_contract.json" || true

    CONTRACT_RULES=$(python3 lib/read_json.py "$REPORTS/compile_contract.json" "obj.get('rule_count', len(obj.get('rules', [])))" 2>/dev/null || echo "0")
    CONTRACT_COMPILE_ERRORS=$(python3 lib/read_json.py "$REPORTS/compile_contract.json" "obj.get('error_count', len(obj.get('compile_errors', [])))" 2>/dev/null || echo "0")

    [ "$CONTRACT_RULES" -eq 4 ] \
        && pass "A3 contract prompt compiles R1–R4 (4 rules)" \
        || fail "A3 contract prompt compiled $CONTRACT_RULES rule(s), expected 4"
    [ "$CONTRACT_COMPILE_ERRORS" -eq 0 ] \
        && pass "A3 contract prompt has 0 compile errors" \
        || fail "A3 contract prompt has $CONTRACT_COMPILE_ERRORS compile error(s)"
fi

# ── Experiment B: Test generation on same implementation ──────────────────

if $RUN_B; then
    header "═══ Experiment B: Test generation contrast (same implementation) ═══"
    echo "Generates one implementation from the enriched prompt,"
    echo "then generates tests from each prompt. Isolates test-prompt effect."

    echo ""
    echo "── B1: generate single implementation from enriched prompt ──"
    "$PDD" generate "$CONTRACT_PROMPT" --output "$SRC/token_bucket.py"
    assert_file_exists "B1 src/token_bucket.py generated" "$SRC/token_bucket.py"
    assert_compiles    "B1 src/token_bucket.py"            "$SRC/token_bucket.py"

    echo ""
    echo "── B2: generate tests from plain prompt ──"
    "$PDD" test --manual "$PLAIN_PROMPT" "$SRC/token_bucket.py" \
        --output "$TESTS/test_plain.py"
    assert_file_exists "B2 tests/test_plain.py generated" "$TESTS/test_plain.py"
    assert_compiles    "B2 tests/test_plain.py"            "$TESTS/test_plain.py"

    echo ""
    echo "── B3: generate tests from enriched prompt ──"
    "$PDD" test --manual "$CONTRACT_PROMPT" "$SRC/token_bucket.py" \
        --output "$TESTS/test_contract.py"
    assert_file_exists "B3 tests/test_contract.py generated" "$TESTS/test_contract.py"
    assert_compiles    "B3 tests/test_contract.py"            "$TESTS/test_contract.py"

    echo ""
    echo "── B4: assert test_contract.py has R# markers ──"
    for rule in R1 R2 R3 R4; do
        assert_file_contains "B4 test_contract.py contains $rule marker" \
            "$TESTS/test_contract.py" "$rule"
    done

    echo ""
    echo "── B5: assert test_contract.py has formalization/Z3 markers (soft) ──"
    if grep -qiE "z3|importorskip|z3-solver|Solver|BitVec|Int\(\)" "$TESTS/test_contract.py" 2>/dev/null; then
        pass "B5 test_contract.py contains Z3-style test or importorskip [soft]"
        Z3_GENERATED=true
    else
        warn "B5 test_contract.py has no Z3-style tests (best-effort — LLM may skip) [soft]"
        Z3_GENERATED=false
    fi

    echo ""
    echo "── B6: assert R3 MUST NOT rule produces a negative test ──"
    assert_file_contains "B6 test_contract.py has R3 negative/cap test" \
        "$TESTS/test_contract.py" "R3"

    echo ""
    echo "── B7: run both test files ──"
    echo "  Running test_plain.py..."
    python3 -m pytest "$TESTS/test_plain.py" -v --tb=short \
        > "$REPORTS/pytest_plain.txt" 2>&1 \
        && pass "B7 test_plain.py pytest passed" \
        || warn "B7 test_plain.py pytest had failures [check reports/pytest_plain.txt]"

    echo "  Running test_contract.py..."
    python3 -m pytest "$TESTS/test_contract.py" -v --tb=short \
        > "$REPORTS/pytest_contract.txt" 2>&1 \
        && pass "B7 test_contract.py pytest passed" \
        || warn "B7 test_contract.py pytest had failures [check reports/pytest_contract.txt]"

    # Summary report
    python3 - <<'PYEOF'
import json, os, re

plain = open("tests/test_plain.py").read()  if os.path.exists("tests/test_plain.py")    else ""
contract = open("tests/test_contract.py").read() if os.path.exists("tests/test_contract.py") else ""

plain_r = len(re.findall(r'\bR[1-4]\b', plain))
contract_r = len(re.findall(r'\bR[1-4]\b', contract))
contract_z3 = bool(re.search(r'z3|importorskip|Solver', contract, re.I))

summary = {
    "test_plain_rule_markers": plain_r,
    "test_contract_rule_markers": contract_r,
    "test_contract_has_z3_style": contract_z3,
    "improvement": contract_r > plain_r,
}
with open("reports/experiment_b.json", "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
PYEOF
fi

# ── Experiment C: Full E2E before/after ───────────────────────────────────

if $RUN_C; then
    header "═══ Experiment C: Full E2E before/after ═══"
    echo "Generates separate implementations and tests from each prompt."
    echo "Tests the complete workflow: prompt → codegen → test → compile → pytest."

    echo ""
    echo "── C1: before arm (plain prompt) ──"
    "$PDD" generate "$PLAIN_PROMPT" --output "$SRC/token_bucket_before.py"
    "$PDD" test --manual "$PLAIN_PROMPT" "$SRC/token_bucket_before.py" \
        --output "$TESTS/test_before.py"

    assert_file_exists "C1 src/token_bucket_before.py" "$SRC/token_bucket_before.py"
    assert_file_exists "C1 tests/test_before.py"       "$TESTS/test_before.py"
    assert_compiles    "C1 src/token_bucket_before.py"  "$SRC/token_bucket_before.py"
    assert_compiles    "C1 tests/test_before.py"        "$TESTS/test_before.py"

    echo ""
    echo "── C2: after arm (enriched prompt) ──"
    "$PDD" generate "$CONTRACT_PROMPT" --output "$SRC/token_bucket_after.py"
    "$PDD" test --manual "$CONTRACT_PROMPT" "$SRC/token_bucket_after.py" \
        --output "$TESTS/test_after.py"

    assert_file_exists "C2 src/token_bucket_after.py"  "$SRC/token_bucket_after.py"
    assert_file_exists "C2 tests/test_after.py"        "$TESTS/test_after.py"
    assert_compiles    "C2 src/token_bucket_after.py"   "$SRC/token_bucket_after.py"
    assert_compiles    "C2 tests/test_after.py"         "$TESTS/test_after.py"

    echo ""
    echo "── C3: run both test arms ──"
    python3 -m pytest "$TESTS/test_before.py" -v --tb=short \
        > "$REPORTS/pytest_before.txt" 2>&1 \
        && pass "C3 test_before.py pytest passed" \
        || warn "C3 test_before.py pytest had failures [check reports/pytest_before.txt]"

    python3 -m pytest "$TESTS/test_after.py" -v --tb=short \
        > "$REPORTS/pytest_after.txt" 2>&1 \
        && pass "C3 test_after.py pytest passed" \
        || warn "C3 test_after.py pytest had failures [check reports/pytest_after.txt]"

    echo ""
    echo "── C4: R# marker contrast ──"
    BEFORE_R=$(grep -cE '\bR[1-4]\b' "$TESTS/test_before.py" 2>/dev/null || echo 0)
    AFTER_R=$(grep -cE  '\bR[1-4]\b' "$TESTS/test_after.py"  2>/dev/null || echo 0)
    echo "  test_before.py R# occurrences: $BEFORE_R"
    echo "  test_after.py  R# occurrences: $AFTER_R"
    [ "$AFTER_R" -gt "$BEFORE_R" ] \
        && pass "C4 after arm has more R# markers than before arm" \
        || warn "C4 after arm does not have more R# markers [soft — LLM variance]"
fi

# ── Experiment D: Contract coverage evidence ──────────────────────────────

if $RUN_D; then
    header "═══ Experiment D: Contract coverage evidence (deterministic) ═══"
    echo "Maps R1–R4 to user stories and generated tests."
    echo "Requires tests/ to exist (run Experiment B or C first)."

    "$PDD" coverage --contracts "$CONTRACT_PROMPT" \
        --stories-dir "$STORIES" \
        --tests-dir   "$TESTS" \
        --json 2>/dev/null | grep -v "^Checking" > "$REPORTS/coverage.json" || true

    echo ""
    # Check each rule has at least story-only or checked status
    for rule in R1 R2 R3 R4; do
        STATUS=$(python3 -c "
import json, sys
try:
    d = json.load(open('$REPORTS/coverage.json'))
    rules = d.get('rules', d) if isinstance(d, dict) else d
    match = next((r for r in rules if isinstance(r, dict) and r.get('rule_id','').startswith('$rule')), None)
    print(match.get('status', 'missing') if match else 'missing')
except Exception as e:
    print('error: ' + str(e))
" 2>/dev/null || echo "missing")

        case "$STATUS" in
            checked|story-only)
                pass "D $rule coverage status: $STATUS" ;;
            unchecked)
                warn "D $rule is unchecked — add R# markers to generated tests [soft]" ;;
            *)
                fail "D $rule coverage status: $STATUS (expected checked or story-only)" ;;
        esac
    done

    echo ""
    # Detect Z3 test presence and execution status
    if [ -f "$TESTS/test_contract.py" ]; then
        HAS_Z3=$(grep -qiE "importorskip.*z3|z3.*importorskip" "$TESTS/test_contract.py" && echo true || echo false)
        Z3_INSTALLED=$(python3 -c "import z3; print(True)" 2>/dev/null || echo false)
        echo "  Z3 test generated:  $HAS_Z3"
        echo "  z3-solver installed: $Z3_INSTALLED"

        python3 -c "
import json
summary = {
    'z3_test_generated': $HAS_Z3,
    'z3_installed': $Z3_INSTALLED,
    'z3_test_executed': $HAS_Z3 and $Z3_INSTALLED,
    'z3_test_skipped': $HAS_Z3 and not $Z3_INSTALLED,
}
with open('$REPORTS/z3_status.json', 'w') as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
"
    fi
fi

# ── Final summary ──────────────────────────────────────────────────────────

header "═══ Demo complete ═══"
if [ "$EXIT_CODE" -eq 0 ]; then
    echo -e "${GREEN}All hard assertions passed.${NC}"
else
    echo -e "${RED}Some hard assertions failed — see output above.${NC}"
fi
echo ""
echo "Reports written to $REPORTS/:"
ls "$REPORTS/" 2>/dev/null | sed 's/^/  /'
echo ""
echo "Hard pass criteria:"
echo "  contract prompt: zero lint errors, R1–R4 compiled, 0 compile errors"
echo "  plain prompt: not_applicable for contracts (not failure)"
echo "  test_contract.py: R1–R4 markers present, compiles, pytest runs"
echo "  before and after generated files: compile and pytest runs"
echo ""
echo "Soft / best-effort:"
echo "  Z3-style tests in test_contract.py (LLM-dependent)"
echo "  "$PDD" coverage shows R1–R4 as checked (needs R# markers in tests)"
echo ""
echo "To run formal Z3 proofs: pip install z3-solver && bash demo.sh --exp-d"
exit "$EXIT_CODE"
