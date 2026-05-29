## Interface Check (Iteration 3)

### 1. Module Interface Verification
*   **pdd/gate_main.py**: Verified interfaces against source. Found that `architecture.json` contains extra parameters (`policy_path`, `target`) in `run_gate_policy` and `evaluate_manifest` that are NOT in the actual source code. Also found incorrect return types for `prompt_freshness` and `output_freshness` in `architecture.json`.
*   **pdd/gate_policy.py**: Verified interfaces match `architecture.json`.
*   **pdd/evidence_store.py**: Verified exports match `gate_main.py` imports.
*   **pdd/checkup_gates.py**: Verified `discover_gates`, `Gate`, and `GateResult` match `architecture.json`.

### 2. Cross-Module Dependencies & Compatibility
*   Verified that the reported issue #825 (Effective `allow.skipped_verify` policy) is indeed fixed in the current iteration. `pdd/gate_main.py` correctly handles skip statuses when the policy allows them.
*   Confirmed that `gate_cmd` in `pdd/commands/gate.py` correctly interfaces with `run_gate_policy`.

### 3. Frontend Check
*   **TypeScript Error Fixed**: Resolved a critical type mismatch in `pdd/frontend/components/DependencyViewer.tsx` (TS2322: Type mismatch in ReactFlow Node position). Added explicit casts and fixed `dagre` and `yaml` imports.
*   **Navigation Reachability**: Verified all views (`devunits`, `bug`, `fix`, `change`, `settings`) are reachable via the sidebar. Checked for orphan components and found `ProjectSettings` is correctly integrated.
*   **API Consistency**: Verified Frontend -> Backend API call consistency. Found that `ArchitectureModule` Pydantic model in the backend was missing the `position` field, which I have now added to ensure consistency with `architecture.json` and the frontend.

### 4. Integration & Consistency
*   **Backend Linting**: Fixed multiple `E402` (Module level import not at top of file) errors in `pdd/server/routes/commands.py`.
*   **Architecture Model**: Synchronized the `ArchitectureModule` Pydantic model with the actual data structure used in the frontend and `architecture.json`.
