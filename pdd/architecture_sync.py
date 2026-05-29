from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Internal relative imports (module level)
try:
    from .construct_paths import resolve_effective_config
except ImportError:
    resolve_effective_config = None

try:
    from .architecture_sync_helper import filepath_to_prompt_filename
except ImportError:
    # Fallback for standalone/testing
    def filepath_to_prompt_filename(filepath: str, language: str) -> str:
        return filepath.replace("/", "_").replace(".", "_") + f"_{language}.prompt"

try:
    from .contract_ir import extract_rules, extract_sections
except ImportError:
    def extract_rules(content: str) -> List[Any]: return []
    def extract_sections(content: str) -> Dict[str, Any]: return {}

try:
    from .coverage_contracts import build_coverage
except ImportError:
    def build_coverage(path: str) -> Dict[str, Any]: return {}

try:
    from .evidence_manifest import _sha256_file
except ImportError:
    def _sha256_file(path: str) -> str: return ""

def find_project_root(start_dir: Path) -> Path:
    """Find the project root by looking for architecture.json or .git."""
    curr = start_dir.resolve()
    nearest_arch = None
    for _ in range(15):  # limit search depth
        if (curr / ".git").exists():
            return curr
        if nearest_arch is None and (curr / "architecture.json").exists():
            nearest_arch = curr
        if curr.parent == curr:
            break
        curr = curr.parent
    return nearest_arch or start_dir.resolve()

# We'll use these as fallbacks if no environment-specific path is found
# Resolved relative to Path.cwd() as per Requirement 15
ARCHITECTURE_JSON_PATH = Path.cwd() / "architecture.json"
PROMPTS_DIR = Path.cwd() / "prompts"

_EXT_TO_LANGUAGE = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScriptReact",
    ".js": "JavaScript",
    ".jsx": "JavaScriptReact",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".cpp": "CPlusPlus",
    ".c": "C",
    ".cs": "CSharp",
    ".rb": "Ruby",
    ".php": "PHP",
    ".prisma": "Prisma",
}

def has_pdd_tags(prompt_content: str) -> bool:
    """
    True if prompt contains PDD metadata tags.
    """
    return bool(re.search(r"<pdd-(reason|interface|dependency)[^>]*>", prompt_content))

def parse_prompt_tags(prompt_content: str) -> Dict[str, Any]:
    """
    Parse PDD metadata tags from prompt content using lxml with lenient recovery.
    """
    result = {"reason": None, "interface": None, "dependencies": [], "has_dependency_tags": False}
    
    # Requirement 1: Extract only header section before first `%` line
    # Regression for issue #566: strip code fences to avoid example tags
    content = re.sub(r"```xml.*?```", "", prompt_content, flags=re.DOTALL)
    # Also handle other common code fence types just in case
    content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    
    # Skip YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2]
            
    header_lines = []
    seen_pdd_tag_or_content = False
    for line in content.splitlines():
        stripped = line.strip()
        if line.startswith("%") and seen_pdd_tag_or_content:
            break
        header_lines.append(line)
        if stripped and not line.startswith("%"):
             seen_pdd_tag_or_content = True
    header_content = "\n".join(header_lines)

    # Requirement 2: Support double-brace escaped JSON as fallback
    # We do this replacement before parsing to handle them as normal text for lxml
    # then json.loads handles the rest.
    header_content_clean = header_content.replace("{{{{", "{{").replace("}}}}", "}}")

    try:
        from lxml import etree
        from rich.console import Console
    except ImportError:
        return result

    # Wrap in dummy root for lxml parsing
    xml_str = f"<root>{header_content_clean}</root>"
    parser = etree.XMLParser(recover=True)
    try:
        root = etree.fromstring(xml_str.encode("utf-8"), parser=parser)
    except Exception:
        return result

    if root is not None:
        reason_elem = root.find(".//pdd-reason")
        if reason_elem is not None and reason_elem.text:
            result["reason"] = reason_elem.text.strip().replace("\n", " ")
            
        interface_elem = root.find(".//pdd-interface")
        if interface_elem is not None and interface_elem.text:
            itxt = interface_elem.text.strip()
            # Requirement 2 fallback for double-braces in interface
            itxt_clean = itxt.replace("{{", "{").replace("}}", "}")
            try:
                result["interface"] = json.loads(itxt_clean)
            except json.JSONDecodeError as e:
                try:
                    result["interface"] = json.loads(itxt)
                except json.JSONDecodeError:
                    result["interface_parse_error"] = f"Invalid JSON: {e}"
                
        dependency_elems = root.findall(".//pdd-dependency")
        if dependency_elems:
            result["has_dependency_tags"] = True
            for elem in dependency_elems:
                if elem.text:
                    dep = elem.text.strip()
                    # Requirement 3: Sanitize dependency values
                    if "\n" not in dep and len(dep) <= 100:
                        if dep.endswith(".prompt") or "." not in dep:
                            result["dependencies"].append(dep)
                else:
                    # Empty tag <pdd-dependency></pdd-dependency> is explicit clear
                    pass

    return result

def _merge_function_signature(old_sig: str, new_sig: str, name: str = "") -> Tuple[str, List[str]]:
    """Merge Python signatures using ast, keeping old parameters if removed."""
    warnings = []
    if not old_sig or not new_sig:
        return (new_sig or old_sig), warnings
    
    # Pre-process signatures to handle 'def name(args) -> ret' format
    def clean_sig(sig: str) -> str:
        s = sig.strip()
        # Remove 'def name' or 'async def name'
        s = re.sub(r"^(async\s+)?def\s+\w+", "", s)
        # Extract everything up to the last colon (if any) or just the (args) part
        match = re.search(r"(\(.*\))", s)
        if match:
            return match.group(1)
        return s

    def get_return_annotation(sig: str) -> Optional[str]:
        match = re.search(r"->\s*([^:]+)$", sig.strip())
        if match:
            return match.group(1).strip()
        return None

    def is_async(sig: str) -> bool:
        return sig.strip().startswith("async ")

    c_old = clean_sig(old_sig)
    c_new = clean_sig(new_sig)
    
    try:
        old_tree = ast.parse(f"def func{c_old}: pass")
        new_tree = ast.parse(f"def func{c_new}: pass")
        
        old_args = old_tree.body[0].args
        new_args = new_tree.body[0].args
        
        old_arg_names = [a.arg for a in old_args.args]
        new_arg_names = [a.arg for a in new_args.args]
        
        # Requirement 5: Guard against cross-class contamination
        shared = set(old_arg_names).intersection(new_arg_names) - {"self", "cls"}
        if old_arg_names and new_arg_names and not shared:
            if "self" in old_arg_names or "cls" in old_arg_names:
                warnings.append(f"Merge rejected for {name}: cross-class contamination suspected")
                return old_sig, warnings
            
        missing = [p for p in old_arg_names if p not in new_arg_names]
        if not missing:
            return new_sig, warnings
            
        warnings.append(f"Preserved removed parameters in {name}: {', '.join(missing)}")
        
        # Merge: Start with old arguments, append any new ones from new_sig
        def get_arg_info(args_obj):
            info = []
            for i, arg in enumerate(args_obj.args):
                default = None
                d_idx = i - (len(args_obj.args) - len(args_obj.defaults))
                if d_idx >= 0:
                    default = args_obj.defaults[d_idx]
                info.append((arg.arg, arg, default))
            return info

        old_info = get_arg_info(old_args)
        new_info = get_arg_info(new_args)
        
        merged_names = [item[0] for item in old_info]
        new_only = [item for item in new_info if item[0] not in merged_names]
        
        final_info = old_info + new_only
        
        # Update new_args object
        new_args.args = [item[1] for item in final_info]
        # defaults must be right-aligned. We need to find the first argument that has a default
        # and from then on, all arguments must have a default.
        first_default_idx = -1
        for i, item in enumerate(final_info):
            if item[2] is not None:
                first_default_idx = i
                break
        
        if first_default_idx != -1:
            new_args.defaults = []
            for i in range(first_default_idx, len(final_info)):
                default = final_info[i][2]
                if default is None:
                    # Provide a placeholder default
                    default = ast.Constant(value=None)
                new_args.defaults.append(default)
        else:
            new_args.defaults = []

        new_tree.body[0].args = new_args
        # Restore return annotation if present in new_sig
        ret_ann = get_return_annotation(new_sig)
        if ret_ann:
             try:
                 new_tree.body[0].returns = ast.parse(ret_ann, mode='eval').body
             except Exception:
                 pass
                 
        merged_sig_full = ast.unparse(new_tree.body[0])
        # Requirement 5: Ensure PEP 8 spaces around = for annotated defaults
        merged_sig_full = re.sub(r":\s*([^=,\s\)]+)=([^,\s\)]+)", r": \1 = \2", merged_sig_full)
        # merged_sig_full is "def func(sig) -> ret: ..."
        
        # Re-construct original style (def/async def and name)
        prefix = ""
        if is_async(new_sig) or (is_async(old_sig) and not "def " in new_sig):
            prefix = "async "
        
        if "def " in new_sig or "def " in old_sig:
            prefix += "def "
            fname = name or "func"
            # Rebuild using ast.unparse result but fix name and prefix
            match = re.search(r"def func(\(.*\)\s*(->\s*[^:]+)?):", merged_sig_full)
            if match:
                return f"{prefix}{fname}{match.group(1)}", warnings
        else:
            # Just return the (args) part
            match = re.search(r"def func(\(.*\)\s*(->\s*[^:]+)?):", merged_sig_full)
            if match:
                return match.group(1), warnings
            
        return new_sig, warnings
    except Exception as e:
        # If merging fails (e.g. unparseable signature), keep the old one if it exists
        if old_sig:
            return old_sig, [f"Signature for {name} could not be parsed (kept existing): {e}"]
        return new_sig, [f"Signature for {name} could not be parsed: {e}"]

def _merge_interface_signatures(old_interface: Optional[Dict[str, Any]], new_interface: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Merge interface signatures rather than replacing them."""
    warnings = []
    if not old_interface or not isinstance(old_interface, dict):
        return new_interface, warnings
    
    if old_interface.get("type") != new_interface.get("type"):
        return new_interface, warnings
        
    if new_interface.get("type") == "module" and "module" in new_interface:
        # Use deep copy to avoid mutating inputs and ensure change detection works
        merged = json.loads(json.dumps(new_interface))
        old_functions = {f["name"]: f for f in old_interface.get("module", {}).get("functions", [])}
        new_functions = merged["module"].get("functions", [])
        
        for i, new_func in enumerate(new_functions):
            name = new_func["name"]
            if name in old_functions:
                old_sig = old_functions[name].get("signature", "")
                new_sig = new_func.get("signature", "")
                m_sig, m_warns = _merge_function_signature(old_sig, new_sig, name)
                merged["module"]["functions"][i]["signature"] = m_sig
                warnings.extend(m_warns)
        return merged, warnings
        
    return new_interface, warnings

def _extract_contract_summary(content: str, filepath: str) -> Dict[str, Any]:
    """
    Requirement 22: Extract contract summary from content.
    """
    rules = extract_rules(content)
    sections = extract_sections(content)
    
    rule_ids = []
    critical_rules = []
    for r in rules:
        rid = getattr(r, "id", getattr(r, "raw_id", None))
        text = getattr(r, "text", "")
        if rid:
            rule_ids.append(rid)
            if any(m in text.upper() for m in ["MUST", "SHALL", "REQUIRED"]):
                critical_rules.append(rid)
    
    return {
        "rule_ids": rule_ids,
        "critical_rules": critical_rules,
        "capabilities": sections.get("capabilities", []),
        "story_links": sections.get("stories", []),
        "evidence_status": "present" if sections.get("evidence") else "missing",
        "coverage_status": "present" if sections.get("tests") else "missing",
        "waived_rules": sections.get("waived", [])
    }

def _normalize_dependencies(dependencies: List[str], arch_data: List[Dict[str, Any]]) -> List[str]:
    """
    Requirement 20: Normalize dependency tags to existing architecture filenames.
    """
    if not dependencies:
        return []
        
    existing_filenames = {e.get("filename") for e in arch_data if "filename" in e}
    normalized = []
    
    for dep in dependencies:
        if dep in existing_filenames:
            normalized.append(dep)
            continue
            
        # Case-insensitive exact match
        found = False
        for fname in existing_filenames:
            if fname.lower() == dep.lower():
                normalized.append(fname)
                found = True
                break
        if found: continue
            
        # Unique suffix match (case-insensitive)
        matches = [f for f in existing_filenames if f.lower().endswith(dep.lower())]
        if len(matches) == 1:
            normalized.append(matches[0])
            continue
            
        # Unique basename match (case-insensitive)
        basename_lower = Path(dep).name.lower()
        matches = [f for f in existing_filenames if Path(f).name.lower() == basename_lower]
        if len(matches) == 1:
            normalized.append(matches[0])
            continue
            
        # Clean bare module stem match (e.g. 'api' -> 'api_python.prompt')
        if "." not in dep:
            matches = [f for f in existing_filenames if f.startswith(f"{dep}_") or f"/{dep}_" in f]
            if len(matches) == 1:
                normalized.append(matches[0])
                continue
                
        # Ambiguous or unresolved
        normalized.append(dep)
        
    # Deduplicate while preserving order
    seen = set()
    result = []
    for d in normalized:
        if d not in seen:
            result.append(d)
            seen.add(d)
    return result

def _find_renamed_prompt_file(prompt_filename: str, prompts_dir: Path) -> Optional[Path]:
    """
    Requirement 11: search for step-number variant (e.g., step4 -> step5).
    """
    match = re.search(r"step(\d+)", prompt_filename)
    if not match:
        return None
        
    step_num = match.group(1)
    # Pattern to match other steps
    pattern = prompt_filename.replace(f"step{step_num}", "step*")
    
    matches = list(prompts_dir.rglob(pattern))
    if len(matches) == 1:
        return matches[0]
    return None

def _infer_filepath(rel_path: str) -> str:
    """
    Requirement 18: Path-aware inference for PascalCase and legacy lowercase.
    """
    # LLM prompt rule
    if rel_path.endswith("_LLM.prompt"):
        return f"prompts/{rel_path}"

    # Legacy rule for cli_detector
    if rel_path == "cli_detector_python.prompt":
        return "pdd/cli_detector.py"
        
    # Path-aware PascalCase and qualified suffixes
    filepath = rel_path
    for ext, lang in _EXT_TO_LANGUAGE.items():
        suffix = f"_{lang}.prompt"
        if rel_path.endswith(suffix):
            filepath = rel_path[:-len(suffix)] + ext
            return filepath
            
    # Legacy lowercase fallbacks
    filepath = rel_path.replace("_python.prompt", ".py").replace("_typescript.prompt", ".ts")
    return filepath

def _infer_module_tags(rel_path: str) -> List[str]:
    """Infer tags for Python and LLM prompts."""
    if "_LLM.prompt" in rel_path:
        return ["llm"]
    if "_Python.prompt" in rel_path or "_python.prompt" in rel_path:
        return ["module", "python"]
    return []

def _resolve_sync_paths(
    prompts_dir: Optional[Path], 
    architecture_path: Optional[Path]
) -> Tuple[Path, Path]:
    """
    Requirement 17: Default path resolution walking upward from CWD.
    """
    cwd = Path.cwd()
    boundary = find_project_root(cwd)
    
    if prompts_dir is None:
        curr = cwd
        while True:
            if (curr / "prompts").is_dir():
                prompts_dir = curr / "prompts"
                break
            if curr == boundary or curr.parent == curr:
                break
            curr = curr.parent
        if prompts_dir is None:
            prompts_dir = cwd / "prompts"
    elif not prompts_dir.is_absolute():
        prompts_dir = (cwd / prompts_dir).resolve()

    if architecture_path is None:
        curr = cwd
        while True:
            if (curr / "architecture.json").exists():
                architecture_path = curr / "architecture.json"
                break
            if curr == boundary or curr.parent == curr:
                break
            curr = curr.parent
        if architecture_path is None:
            architecture_path = cwd / "architecture.json"
    elif not architecture_path.is_absolute():
        architecture_path = (cwd / architecture_path).resolve()
            
    return prompts_dir, architecture_path

def _load_architecture(path: Path) -> Tuple[Any, List[Dict[str, Any]]]:
    """Load architecture and return both full data and entries list (reference)."""
    if not path.exists():
        return [], []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], []
        
    if isinstance(data, list):
        return data, data
    if isinstance(data, dict):
        for key in ["modules", "entries", "components"]:
            if key in data and isinstance(data[key], list):
                return data, data[key]
        # If no standard list key found, return empty list of entries but keep dict
        return data, []
    return data, []

def update_architecture_from_prompt(
    prompt_filename: str, 
    prompts_dir: Path = PROMPTS_DIR, 
    architecture_path: Path = ARCHITECTURE_JSON_PATH, 
    dry_run: bool = False, 
    prompt_content_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update architecture.json entries from prompt file tags.
    """
    result = {"success": False, "updated": False, "changes": {}, "error": None, "warnings": []}
    
    # Capture print output using rich if possible
    try:
        from rich.console import Console
        console = Console()
    except ImportError:
        console = None

    arch_full, arch_entries = _load_architecture(architecture_path)

    # Get content and handle auto-rename if file not found
    final_prompt_filename = prompt_filename
    if prompt_content_override is not None:
        content = prompt_content_override
    else:
        prompt_path = prompts_dir / prompt_filename
        if not prompt_path.exists():
            # Requirement 11: Auto-rename search when file not found
            renamed_path = _find_renamed_prompt_file(prompt_filename, prompts_dir)
            if renamed_path:
                final_prompt_filename = str(renamed_path.relative_to(prompts_dir))
                prompt_path = renamed_path
            else:
                result["error"] = f"Prompt file not found: {prompt_filename}"
                return result
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()

    # Find entry
    entry = None
    for e in arch_entries:
        if e.get("filename") == prompt_filename:
            entry = e
            break
            
    if not entry:
        # Requirement 11: Auto-rename search (if not already found)
        # Search for an entry in arch_entries that matches a step-number variant of the filename
        match = re.search(r"step(\d+)", prompt_filename)
        if match:
            step_num = match.group(1)
            # Create a regex to match other steps
            # Escape filename and replace stepN with step\d+
            escaped_f = re.escape(prompt_filename).replace(f"step{step_num}", r"step\d+")
            pattern = f"^{escaped_f}$"
            for e in arch_entries:
                if "filename" in e and re.match(pattern, e["filename"]):
                    entry = e
                    # We found the entry! We want to update it to the new filename.
                    final_prompt_filename = prompt_filename
                    break

    if not entry:
        # Basename fallback if still not found
        basename = Path(prompt_filename).name
        for e in arch_entries:
            if Path(e.get("filename", "")).name == basename:
                entry = e
                break

    if not entry:
        # Original logic: search DISK if the requested file was missing
        # (Though we already handled that above, this is for completeness)
        renamed_path = _find_renamed_prompt_file(prompt_filename, prompts_dir)
        if renamed_path:
            rel_renamed = str(renamed_path.relative_to(prompts_dir))
            for e in arch_entries:
                if e.get("filename") == rel_renamed:
                    entry = e
                    final_prompt_filename = prompt_filename
                    break

    if not entry:
        result["error"] = f"No architecture entry found for {prompt_filename}"
        return result

    # Update filename if it differs from final_prompt_filename
    if entry.get("filename") != final_prompt_filename:
        old_fname = entry["filename"]
        entry["filename"] = final_prompt_filename
        result["changes"]["filename"] = {"old": old_fname, "new": final_prompt_filename}
        
        # Also update filepath if it was pointing to the old prompt file
        old_path = entry.get("filepath", "")
        if old_path and old_fname and old_fname in old_path:
            new_path = old_path.replace(old_fname, final_prompt_filename)
            entry["filepath"] = new_path
            result["changes"]["filepath"] = {"old": old_path, "new": new_path}
            
        result["updated"] = True

    tags = parse_prompt_tags(content)
    if "interface_parse_error" in tags:
        result["warnings"].append(f"Interface parse error in {prompt_filename}: {tags['interface_parse_error']}")
    
    if tags["reason"] is not None and entry.get("reason") != tags["reason"]:
        old_val = entry.get("reason")
        entry["reason"] = tags["reason"]
        result["changes"]["reason"] = {"old": old_val, "new": tags["reason"]}
        result["updated"] = True
        
    if tags["interface"] is not None:
        old_interface = entry.get("interface")
        merged_interface, m_warns = _merge_interface_signatures(old_interface, tags["interface"])
        result["warnings"].extend(m_warns)
        if old_interface != merged_interface:
            entry["interface"] = merged_interface
            result["changes"]["interface"] = {"old": old_interface, "new": merged_interface}
            result["updated"] = True

    # Requirement 4 & 8: Dependency update rules
    if tags["has_dependency_tags"]:
        old_deps = entry.get("dependencies", [])
        normalized_deps = _normalize_dependencies(tags["dependencies"], arch_entries)
        if old_deps != normalized_deps:
            entry["dependencies"] = normalized_deps
            result["changes"]["dependencies"] = {"old": old_deps, "new": normalized_deps}
            result["updated"] = True
    # Else preserve existing dependencies (Requirement 4)

    # Requirement 22: Contract summary
    summary = _extract_contract_summary(content, entry.get("filepath", ""))
    # Legacy-friendly: only update if it has contracts OR already existed
    has_meaningful = any(summary.get(k) for k in ["rule_ids", "capabilities", "waived_rules"])
    
    if entry.get("contract_summary") != summary:
        if entry.get("contract_summary") is None and not has_meaningful:
            pass
        else:
            old_summary = entry.get("contract_summary")
            entry["contract_summary"] = summary
            result["changes"]["contract_summary"] = {"old": old_summary, "new": summary}
            result["updated"] = True

    if result["updated"] and not dry_run:
        with open(architecture_path, "w", encoding="utf-8") as f:
            json.dump(arch_full, f, indent=2)

    result["success"] = True
    return result

def register_untracked_prompts(
    prompts_dir: Path = PROMPTS_DIR, 
    architecture_path: Path = ARCHITECTURE_JSON_PATH, 
    dry_run: bool = False, 
    only_files: Optional[set] = None
) -> Dict[str, Any]:
    """
    Requirement 12: Discovers prompt files with PDD tags that have no architecture.json entry.
    """
    result = {"registered": [], "skipped": [], "errors": []}
    if not prompts_dir.exists():
        return result

    arch_full, arch_entries = _load_architecture(architecture_path)
    existing_filenames = {e.get("filename") for e in arch_entries if "filename" in e}

    # Requirement 17: Scoping logic for auto-registration
    prompts_owner = prompts_dir.resolve().parent
    arch_owner = architecture_path.resolve().parent
    # We restrict if prompts are NOT in the architecture directory 
    # AND NOT in a 'prompts' subdirectory of the architecture directory
    restrict_to_existing = (prompts_owner != arch_owner) and (prompts_dir.resolve() != arch_owner) and (only_files is None)

    for prompt_file in prompts_dir.rglob("*.prompt"):
        rel_path = str(prompt_file.relative_to(prompts_dir))

        # Requirement 12: member of only_files if provided
        if only_files is not None and rel_path not in only_files:
            continue

        if rel_path in existing_filenames:
            continue

        # Requirement 11: Skip registration if a step-number variant already exists
        match = re.search(r"step(\d+)", rel_path)
        if match:
            step_num = match.group(1)
            escaped_f = re.escape(rel_path).replace(f"step{step_num}", r"step\d+")
            pattern = f"^{escaped_f}$"
            found_variant = False
            for fname in existing_filenames:
                if re.match(pattern, fname):
                    found_variant = True
                    break
            if found_variant:
                continue

        # Requirement 17 restriction
        if restrict_to_existing and rel_path not in existing_filenames:
            result["skipped"].append(rel_path)
            continue

        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        if has_pdd_tags(content):
            tags = parse_prompt_tags(content)

            # Requirement 19: .pddrc context-aware inference
            filepath = None
            if resolve_effective_config:
                try:
                    # Resolve context for this prompt file
                    # We pass cwd=prompts_dir to ensure it finds the local .pddrc
                    _, pddrc_path, context_config, _, _ = resolve_effective_config(
                        prompt_file=str(prompt_file), 
                        cwd=prompts_dir, 
                        quiet=True
                    )

                    # Keys might be at top level of context or under "defaults"
                    p_dir_ctx = context_config.get("prompts_dir") or context_config.get("defaults", {}).get("prompts_dir")
                    g_path = context_config.get("generate_output_path") or context_config.get("defaults", {}).get("generate_output_path")

                    # Requirement 19: Do not apply root catch-all "prompts" context for path-aware inference
                    if pddrc_path and p_dir_ctx and g_path and p_dir_ctx != "prompts":
                        p_dir_abs = (pddrc_path.parent / p_dir_ctx).resolve()
                        prompt_abs = prompt_file.resolve()

                        try:
                            rel_to_ctx = prompt_abs.relative_to(p_dir_abs)
                            # Success! Use the context's generate_output_path
                            filepath = os.path.join(g_path, _infer_filepath(str(rel_to_ctx)))
                            filepath = filepath.replace("\\", "/").replace("//", "/")
                            if filepath.startswith("./"):
                                filepath = filepath[2:]
                        except ValueError:
                            pass
                except Exception:
                    pass

            if not filepath:
                filepath = _infer_filepath(rel_path)

            new_entry = {
                "filename": rel_path,
                "filepath": filepath,
                "reason": tags["reason"] or "",
                "dependencies": _normalize_dependencies(tags["dependencies"], arch_entries),
                "interface": tags["interface"] or {}
            }

            # Requirement 18: Python PascalCase tags
            m_tags = _infer_module_tags(rel_path)
            if m_tags:
                new_entry["tags"] = m_tags

            arch_entries.append(new_entry)
            result["registered"].append(rel_path)
        else:
            result["skipped"].append(rel_path)

    if result["registered"] and not dry_run:
        with open(architecture_path, "w", encoding="utf-8") as f:
            json.dump(arch_full, f, indent=2)

    return result


def sync_prompts_to_architecture(
    filenames: Optional[List[str]] = None,
    prompts_dir: Optional[Path] = None,
    architecture_path: Optional[Path] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Sync selected prompt metadata tags into architecture.json.
    """
    prompts_dir, architecture_path = _resolve_sync_paths(prompts_dir, architecture_path)
    only_files = set(filenames) if filenames else None
    
    reg_result = register_untracked_prompts(prompts_dir, architecture_path, dry_run, only_files)
    
    result = {
        "success": True, 
        "updated_count": 0, 
        "skipped_count": 0, 
        "results": {}, 
        "errors": [], 
        "registered": reg_result["registered"]
    }

    # Load arch data for scoping and existing filenames
    arch_full, arch_entries = _load_architecture(architecture_path)
    existing_filenames = {e.get("filename") for e in arch_entries if "filename" in e}

    # Requirement 17: Scoping logic for targeting
    prompts_owner = prompts_dir.resolve().parent
    arch_owner = architecture_path.resolve().parent
    # We restrict if prompts are NOT in the architecture directory 
    # AND NOT in a 'prompts' subdirectory of the architecture directory
    restrict_to_existing = (prompts_owner != arch_owner) and (prompts_dir.resolve() != arch_owner) and (filenames is None)

    targets = []
    if filenames:
        for f in filenames:
            p = prompts_dir / f
            if not p.exists() and f.startswith("prompts/"):
                p_alt = prompts_dir / f[len("prompts/"):]
                if p_alt.exists():
                    p = p_alt
            targets.append((f, p))
    else:
        for p in prompts_dir.rglob("*.prompt"):
            rel_p = str(p.relative_to(prompts_dir))
            if restrict_to_existing and rel_p not in existing_filenames:
                continue
            targets.append((rel_p, p))

    for original_f, prompt_file in targets:
        if not prompt_file.exists():
            result["success"] = False
            result["errors"].append(f"{original_f}: Prompt file not found: {original_f}")
            continue
            
        rel_path = str(prompt_file.relative_to(prompts_dir))
        
        update_res = update_architecture_from_prompt(
            prompt_filename=rel_path,
            prompts_dir=prompts_dir,
            architecture_path=architecture_path,
            dry_run=dry_run
        )
        
        if not update_res.get("success"):
            # In dry_run, newly registered prompts won't be in the file
            if dry_run and rel_path in reg_result["registered"]:
                result["updated_count"] += 1
                result["results"][rel_path] = {"success": True, "updated": True, "changes": {"registered": {"old": None, "new": True}}}
                continue
            
            result["success"] = False
            result["errors"].append(f"{rel_path}: {update_res.get('error', 'Unknown error')}")
        else:
            result["results"][rel_path] = update_res
            if update_res.get("updated"):
                result["updated_count"] += 1
            else:
                result["skipped_count"] += 1

    # Add validation result
    _, arch_entries_updated = _load_architecture(architecture_path)
    result["validation"] = validate_architecture_modules(arch_entries_updated)

    return result

def sync_all_prompts_to_architecture(
    prompts_dir: Path = PROMPTS_DIR, 
    architecture_path: Path = ARCHITECTURE_JSON_PATH, 
    dry_run: bool = False, 
    only_files: Optional[set] = None
) -> Dict[str, Any]:
    """
    Syncs all prompts to the architecture file.
    """
    reg_result = register_untracked_prompts(prompts_dir, architecture_path, dry_run, only_files)
    
    result = {
        "success": True, 
        "updated_count": 0, 
        "skipped_count": 0, 
        "results": {}, 
        "errors": [], 
        "registered": reg_result["registered"]
    }
    
    if not prompts_dir.exists():
        return result

    for prompt_file in prompts_dir.rglob("*.prompt"):
        rel_path = str(prompt_file.relative_to(prompts_dir))
        if only_files is not None and rel_path not in only_files:
            result["skipped_count"] += 1
            continue
            
        update_res = update_architecture_from_prompt(
            prompt_filename=rel_path,
            prompts_dir=prompts_dir,
            architecture_path=architecture_path,
            dry_run=dry_run
        )
        
        result["results"][rel_path] = update_res
        if update_res.get("updated"):
            result["updated_count"] += 1
        elif update_res.get("error"):
            result["errors"].append(update_res["error"])
        else:
            result["skipped_count"] += 1

    return result

def validate_dependencies(dependencies: List[str], prompts_dir: Path = PROMPTS_DIR) -> Dict[str, Any]:
    """Requirement 9: Validate dependencies exist and have no duplicates."""
    result = {"valid": True, "missing": [], "duplicates": []}
    seen = set()
    
    for dep in dependencies:
        if dep in seen:
            result["duplicates"].append(dep)
            result["valid"] = False
        seen.add(dep)
        
        dep_path = prompts_dir / dep
        if not dep_path.exists():
            result["missing"].append(dep)
            result["valid"] = False
            
    return result

def validate_interface_structure(interface: Dict[str, Any]) -> Dict[str, Any]:
    """Requirement 9: Validate interface dictionary structure."""
    result = {"valid": True, "errors": []}
    if not isinstance(interface, dict):
        result["valid"] = False
        result["errors"].append("Interface must be a dictionary")
        return result
        
    allowed_types = {"module", "cli", "command", "frontend"}
    if "type" not in interface or interface["type"] not in allowed_types:
        result["valid"] = False
        result["errors"].append(f"Invalid type. Must be one of {allowed_types}")
    else:
        # Check nested keys for module
        if interface["type"] == "module":
            if "module" not in interface:
                result["valid"] = False
                result["errors"].append("Missing 'module' key for type='module'")
            elif "functions" not in interface["module"]:
                result["valid"] = False
                result["errors"].append("Missing 'functions' key in module")
        
    return result

def validate_architecture_modules(arch_data: Any) -> Dict[str, Any]:
    """Validate architecture modules for consistency."""
    all_errors = []
    
    # Determine entries list
    if isinstance(arch_data, list):
        entries = arch_data
    elif isinstance(arch_data, dict):
        entries = []
        for key in ["modules", "entries", "components"]:
            if key in arch_data and isinstance(arch_data[key], list):
                entries = arch_data[key]
                break
    else:
        entries = []

    for entry in entries:
        if isinstance(entry, dict) and "interface" in entry and entry["interface"]:
            res = validate_interface_structure(entry["interface"])
            if not res["valid"]:
                all_errors.extend(res["errors"])
    return {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "warnings": []
    }

def get_architecture_entry_for_prompt(prompt_filename: str, architecture_path: Path = ARCHITECTURE_JSON_PATH) -> Optional[Dict[str, Any]]:
    """Requirement 14: Retrieve entry with exact match or basename fallback."""
    if not architecture_path.exists():
        return None
        
    _, arch_entries = _load_architecture(architecture_path)
        
    for entry in arch_entries:
        if entry.get("filename") == prompt_filename:
            return entry
            
    basename = Path(prompt_filename).name
    for entry in arch_entries:
        if Path(entry.get("filename", "")).name == basename:
            return entry
            
    return None

def generate_tags_from_architecture(arch_entry: Dict[str, Any]) -> str:
    """Requirement 10: Generate XML metadata tags from an architecture entry."""
    tags = []
    if "reason" in arch_entry and arch_entry["reason"]:
        tags.append(f"<pdd-reason>{arch_entry['reason']}</pdd-reason>")
        
    if "interface" in arch_entry and arch_entry["interface"]:
        interface_str = json.dumps(arch_entry["interface"], indent=2)
        tags.append(f"<pdd-interface>\n{interface_str}\n</pdd-interface>")
        
    if "dependencies" in arch_entry and isinstance(arch_entry["dependencies"], list):
        for dep in arch_entry["dependencies"]:
            tags.append(f"<pdd-dependency>{dep}</pdd-dependency>")
                
    return "\n\n".join(tags)

def normalize_architecture_filenames(arch_data: Any) -> None:
    """Requirement 13: Normalize architecture filenames based on filepath (mutates in place)."""
    # Determine entries list
    if isinstance(arch_data, list):
        entries = arch_data
    elif isinstance(arch_data, dict):
        entries = []
        for key in ["modules", "entries", "components"]:
            if key in arch_data and isinstance(arch_data[key], list):
                entries = arch_data[key]
                break
    else:
        return

    mapping = {}
    for entry in entries:
        old_filename = entry.get("filename")
        if "filepath" in entry and entry["filepath"]:
            ext = Path(entry["filepath"]).suffix
            if ext:
                language = _EXT_TO_LANGUAGE.get(ext, "Unknown")
                new_filename = filepath_to_prompt_filename(entry["filepath"], language)
                entry["filename"] = new_filename
                if old_filename:
                    mapping[old_filename] = new_filename
                    
    # Rewrite dependency references
    for entry in entries:
        if "dependencies" in entry and isinstance(entry["dependencies"], list):
            entry["dependencies"] = [mapping.get(d, d) for d in entry["dependencies"]]
