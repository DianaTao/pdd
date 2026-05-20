#!/usr/bin/env python3
\"\"\"
Example usage of the PromptLinter module.

This example demonstrates how to use the PromptLinter class to analyze PDD prompts
and user stories for linguistic ambiguity. The module provides:

1. PromptLinter - The core class for performing deterministic and LLM-based linting
2. lint_file - Convenience method to lint a file path
3. lint_content - Convenience method to lint raw string content

Usage:
    linter = PromptLinter()
    result = linter.lint_file(\"prompts/my_prompt_python.prompt\")
    if not result.is_valid:
        print(f\"Found {len(result.issues)} issues\")
\"\"\"

import os
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class LintIssue:
    term: str
    message: str
    line: int
    column: int
    section: str  # e.g., \"Requirements\", \"<contract_rules>\"
    suggestion: Optional[str] = None

@dataclass
class LintResult:
    is_valid: bool
    issues: List[LintIssue]
    content: str
    file_path: Optional[str] = None

class PromptLinter:
    \"\"\"
    The core linguistic engine for linting PDD prompts and stories.
    \"\"\"
    def __init__(self, llm_enabled: bool = False):
        self.llm_enabled = llm_enabled

    def lint_file(self, file_path: str, ambiguity: bool = True, stories: bool = False) -> LintResult:
        \"\"\"
        Analyze a PDD prompt or user story file.
        \"\"\"
        with open(file_path, \"r\") as f:
            content = f.read()
        return self.lint_content(content, file_path=file_path, ambiguity=ambiguity, stories=stories)

    def lint_content(self, content: str, file_path: Optional[str] = None, ambiguity: bool = True, stories: bool = False) -> LintResult:
        \"\"\"
        Analyze raw string content for linguistic ambiguity.
        \"\"\"
        issues = []
        # Simulate deterministic keyword matching
        if \"valid\" in content:
            issues.append(LintIssue(
                term=\"valid\",
                message=\"Ambiguous term: 'valid'. Define what constitutes a valid input in <vocabulary>.\",
                line=10,
                column=5,
                section=\"Requirements\"
            ))
        
        return LintResult(
            is_valid=len(issues) == 0,
            issues=issues,
            content=content,
            file_path=file_path
        )

def example_lint_prompt():
    \"\"\"
    Demonstrate linting a prompt file for ambiguity.
    \"\"\"
    linter = PromptLinter()
    # In a real scenario, this would be a path to a prompt file
    content = \"\"\"
% Requirements
1. The input must be valid.
\"\"\"
    result = linter.lint_content(content)
    print(f\"Linting result: {'Passed' if result.is_valid else 'Failed'}\")
    for issue in result.issues:
        print(f\"[{issue.section}] Line {issue.line}: {issue.message}\")

if __name__ == '__main__':
    example_lint_prompt()
