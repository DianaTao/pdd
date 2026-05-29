## Summary

This PR extends the architecture metadata in `architecture.json` to include contract rules, capabilities, story links, and evidence status. These fields are automatically extracted from prompts, stories, and evidence during the architecture sync process, enabling a more complete specification system and better visibility into module obligations and coverage.

Closes #35

## Changes Made

### Prompts Modified
- `pdd/prompts/architecture_sync_python.prompt` - Added extraction logic for contract rules, capabilities, story links, and evidence status.
- `pdd/prompts/commands/maintenance_python.prompt` - Updated architecture sync output to display summary statistics and warnings.
- `pdd/prompts/contract_ir_python.prompt` - Updated contract IR logic.
- `pdd/prompts/coverage_contracts_python.prompt` - Updated coverage contract logic.
- `pdd/prompts/frontend/api_typescript.prompt` - Updated API models to include contract summary.
- `pdd/prompts/frontend/components/ModuleNode_typescriptreact.prompt` - Added visual status badges and tooltips to the architecture graph.
- `pdd/prompts/frontend/components/SyncFromPromptModal_typescriptreact.prompt` - Updated diff view to show contract-level metadata.
- `pdd/prompts/frontend/types_typescript.prompt` - Defined `ContractSummary` and updated `ArchitectureModule` types.
- `pdd/prompts/server/routes/architecture_python.prompt` - Updated FastAPI models for architecture modules.

### Code Updated
- `pdd/architecture_sync.py` - Implemented extraction and sync logic.
- `pdd/commands/maintenance.py` - Updated CLI command handling.
- `pdd/sync_order.py` - Updated sync order logic.
- `architecture.json` - Updated with new metadata fields.

## Review Checklist

- [ ] Prompt syntax is valid
- [ ] PDD conventions followed
- [ ] Documentation is up to date

## Next Steps After Merge

1. Regenerate code from modified prompts in dependency order:
   ```bash
   ./sync_order.sh
   ```
   Or manually:
   ```
   pdd sync api
pdd sync ModuleNode
pdd sync SyncFromPromptModal
pdd sync types
pdd sync architecture_sync
pdd sync architecture_include_validation
pdd sync architecture
pdd sync code_generator_main
pdd sync sync_order
pdd sync incremental_prd_architecture
pdd sync auto_deps_architecture
pdd sync agentic_sync_runner
pdd sync misc
pdd sync one_session_sync
pdd sync preprocess_main
pdd sync durable_sync_runner
pdd sync prompts
pdd sync sync_main
pdd sync agentic_sync
pdd sync checkup
pdd sync ci_drift_heal
pdd sync connect
pdd sync generate
pdd sync maintenance
pdd sync update_main
pdd sync agentic_checkup
pdd sync modify
pdd sync pin_example_hack
pdd sync sync_orchestration
   ```
2. Run tests to verify functionality
3. Deploy if applicable

---
*Created by pdd change workflow*
