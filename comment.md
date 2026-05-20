## Step 9: Implement Changes

**Status:** Changes Applied

### Files Modified
FILES_MODIFIED: prompts/commands/__init___python.prompt, prompts/frontend/types_typescript.prompt, prompts/frontend/constants_typescript.prompt, prompts/server/routes/commands_python.prompt, prompts/server/click_executor_python.prompt, prompts/core/cli_python.prompt, prompts/core/duplicate_cli_guard_python.prompt, README.md, docs/prompting_guide.md

### Files Created
FILES_CREATED: prompts/core/prompt_linter_python.prompt, prompts/commands/prompt_python.prompt

### Summary of Changes

#### `README.md`
- Added `prompt lint` to the Command Overview under a new "Prompt Management" category.
- Added a detailed description in the Commands section (Section 23) documenting the `--ambiguity` and `--apply` flags.

#### `docs/prompting_guide.md`
- Added tip for using `pdd prompt lint --ambiguity` to automatically identify vague language in prompts.

#### `prompts/commands/__init___python.prompt`
- Added requirement to register `prompt_group` (imported from `.prompt`) in `register_commands`, positioned after `templates_group`.

#### `prompts/frontend/types_typescript.prompt`
- Added `PROMPT='prompt'` to the `CommandType` enum.

#### `prompts/frontend/constants_typescript.prompt`
- Added `PROMPT` command configuration to `COMMANDS`.

#### `prompts/server/routes/commands_python.prompt`
- Added `prompt` to `ALLOWED_COMMANDS` under Advanced.
- Added `prompt: ["args"]` to `POSITIONAL_ARGS`.

#### `prompts/server/click_executor_python.prompt`
- Updated `get_pdd_command` to support `prompt`.
- Added dependency to import `prompt_group` from `pdd.commands.prompt`.

#### `prompts/core/cli_python.prompt`
- Added a "Prompt Management" section to `format_help` highlighting `prompt` and other related commands.

#### `prompts/core/duplicate_cli_guard_python.prompt`
- Added `prompt` to the list of guarded subcommands to prevent redundant LLM-based linting runs.

#### `prompts/core/prompt_linter_python.prompt` (new)
- Created new prompt for implementing `PromptLinter` class with `lint_file` and `lint_content` methods.
- Includes 7 requirements covering deterministic parsing, vocabulary extraction, story support, LLM integration, and formatting.

#### `prompts/commands/prompt_python.prompt` (new)
- Created new prompt for implementing the `pdd prompt` command group and `lint` subcommand.
- Includes 4 requirements for option parsing, orchestration, and output formatting.

### Worktree Location
Changes are in: `/tmp/pdd_job_VEEEEgSrwCmbNrX4PGgG_nkdun5q5/.pdd/worktrees/change-issue-2`

### Next Steps
After review, run `pdd sync` on modified prompts to regenerate code.

---
*Proceeding to Step 10: Identify Issues*