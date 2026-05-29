from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, List
from dataclasses import dataclass, field

# Regex to match list items typically found under a "## Covers" heading.
# It matches bullet points at the start of a line to avoid incidental mentions in prose.
COVERAGE_REF_RE = re.compile(r"^[-*]\s+(.+)$", re.MULTILINE)

@dataclass
class Rule:
    text: str

@dataclass
class Waiver:
    text: str

@dataclass
class PromptContractIR:
    rules: list[Rule] = field(default_factory=list)
    waivers: list[Waiver] = field(default_factory=list)
    coverage: str = ""
    vocabulary: str = ""
    capabilities: str = ""
    non_responsibilities: str = ""

# Terms considered vague in contract rules.
VAGUE_TERMS = [
    "efficient", "fast", "performant", "optimal", "best", "proper", "properly",
    "appropriate", "appropriately", "correct", "correctly", "good", "better",
    "scalable", "robust", "clean", "simple", "easy", "complex", "flexible",
    "standard", "customary", "usual", "normally", "generally", "typical",
    "typically", "effective", "effectively", "quality", "high-quality",
    "professional", "enterprise", "modern", "advanced", "state-of-the-art",
    "reliable", "secure", "safe", "stable", "intuitive", "user-friendly",
    "comprehensive", "complete", "sufficient", "enough", "minimal", "minimum",
    "maximal", "maximum", "various", "multiple", "several", "many", "few",
    "some", "significant", "considerable", "substantial", "slight", "slightly",
    "clear", "clearly", "easy-to-use", "powerful", "scalable", "modular",
    "maintainable", "extensible", "consistent", "standardized", "seamless",
    "integrated", "optimized", "enhanced", "streamlined", "intuitive",
    "intelligent", "smart", "automated", "autonomous", "cutting-edge",
    "world-class", "industry-standard", "best-in-class", "best-practice",
]

def extract_sections(text: str) -> dict:
    """
    Extracts specific XML-like sections from the provided text.
    Sections include: contract_rules, coverage, waivers, vocabulary,
    capabilities, and non_responsibilities.
    """
    sections = [
        "contract_rules", 
        "coverage", 
        "waivers", 
        "vocabulary", 
        "capabilities", 
        "non_responsibilities"
    ]
    extracted = {}
    for sec in sections:
        pattern = rf"<{sec}>(.*?)</{sec}>"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            extracted[sec] = match.group(1).strip()
        else:
            extracted[sec] = ""
    return extracted

def extract_rules(text: str) -> list[Rule]:
    """
    Extracts individual rules from the text block.
    Assumes rules might be bulleted or newline separated.
    """
    if not text.strip():
        return []
    
    rules = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            # Strip leading bullets if present
            line = re.sub(r"^[-*]\s+", "", line)
            rules.append(Rule(text=line))
    return rules

def extract_waivers(text: str) -> list[Waiver]:
    """
    Extracts individual waivers from the text block.
    Assumes waivers might be bulleted or newline separated.
    """
    if not text.strip():
        return []
    
    waivers = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            # Strip leading bullets if present
            line = re.sub(r"^[-*]\s+", "", line)
            waivers.append(Waiver(text=line))
    return waivers

def parse_prompt_contracts(path: Path) -> PromptContractIR:
    """
    Parses a prompt file at the given path and returns a PromptContractIR.
    """
    try:
        from rich.console import Console
        console = Console()
    except ImportError:
        console = None

    if not path.exists():
        if console:
            console.print(f"[red]Error: Prompt file not found at {path}[/red]")
        raise FileNotFoundError(f"Prompt file not found at {path}")

    text = path.read_text(encoding="utf-8")
    sections = extract_sections(text)
    
    ir = PromptContractIR(
        rules=extract_rules(sections.get("contract_rules", "")),
        waivers=extract_waivers(sections.get("waivers", "")),
        coverage=sections.get("coverage", ""),
        vocabulary=sections.get("vocabulary", ""),
        capabilities=sections.get("capabilities", ""),
        non_responsibilities=sections.get("non_responsibilities", "")
    )
    
    return ir

def iter_covers_refs(story_text: str) -> Iterator[str]:
    """
    Iterates over coverage references found within a story text.
    Looks for a '## Covers' section and extracts bullet points.
    """
    # Find the block under ## Covers
    covers_match = re.search(r"##\s*Covers\s*\n(.*?)(?=\n##|$)", story_text, re.DOTALL | re.IGNORECASE)
    if covers_match:
        covers_block = covers_match.group(1)
        for match in COVERAGE_REF_RE.finditer(covers_block):
            yield match.group(1).strip()