# Review Findings - Step 11 (Iteration 2)

## 1. Architecture Issues
- **Duplicate Interface Methods**: In `architecture.json`, the module `get_jwt_token_python.prompt` contains two duplicate entries for the `__init__` method with different signatures. Python does not support constructor overloading in this manner; these should be merged or the correct one selected.
- **False Positive Missing Files**: Step 10 reported several files (e.g., `pdd/llm_invoke.py`, `pdd/auth_service.py`) as missing from disk, but they are present. This indicates a potential race condition or misconfiguration in the orchestrator's post-check.

## 2. Implementation Issues (pdd/agentic_common.py)
- **Inconsistent Subprocess Usage**: The new functions `_find_state_comment` and `_find_all_state_comments` use `subprocess.run` directly. They should be updated to use the `_subprocess_run` wrapper for consistent timeout handling and process group cleanup (Issue #830).
- **Imprecise Steering Filter**: In `drain_issue_steers`, the regex `re.search(r"## Step \d+/\d+:", body)` is used to filter progress comments. To strictly adhere to the requirement "any line starting with", it should use `re.MULTILINE` with `^` or `re.match` on individual lines.
- **Missing Marker Filter**: `drain_issue_steers` filters `GITHUB_STATE_MARKER_START` but does not explicitly filter `GITHUB_STATE_MARKER_END`.

## 3. Documentation Issues
- **Silent Drop of docs/source.md**: Step 10 reported a silent drop for `docs/source.md`. This file does not exist on disk, which may indicate it was intended to be created or synced but was missed.

## 4. Test Regressions
- **Environment Sensitivity**: Several tests in `tests/test_agentic_common.py` (e.g., `test_run_agentic_task_anthropic_success_env_check`) are failing because they do not mock `get_agent_provider_preference()` or set `PDD_AGENTIC_PROVIDER`. In environments where `PDD_AGENTIC_PROVIDER=google` is set, these tests exclude the mocked `anthropic` provider, leading to "No agent providers are available" errors.
