"""Parse structured output from model responses.

Uses ```epic and ```task fenced blocks for reliable extraction.
Multi-line fields are supported via the "field:" / blank-line convention.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from vtinker.config import Check

# Fields we recognize at the top level of a block.
# Only these get treated as section headers; anything else is content.
_KNOWN_FIELDS = frozenset({
    "title", "description", "acceptance", "depends",
    "branch", "worktree", "checks", "atomic",
})


@dataclass
class EpicDef:
    title: str = ""
    description: str = ""
    acceptance: str = ""
    branch: str = ""
    worktree: bool = False
    checks: list[Check] = field(default_factory=list)


@dataclass
class TaskDef:
    title: str = ""
    description: str = ""
    acceptance: str = ""
    depends: list[int] = field(default_factory=list)
    atomic: bool = False


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

def extract_epic(text: str) -> EpicDef | None:
    """Extract an ```epic fenced block from model output."""
    block = _extract_fenced_block(text, "epic")
    if not block:
        return None

    epic = EpicDef()
    sections = _parse_sections(block)

    epic.title = sections.get("title", "").strip()
    epic.description = sections.get("description", "").strip()
    epic.acceptance = sections.get("acceptance", "").strip()

    branch = sections.get("branch", "").strip()
    if branch and branch.lower() != "none":
        epic.branch = branch

    wt = sections.get("worktree", "").strip()
    epic.worktree = wt.lower() == "true"

    # Parse checks: lines like "- build: go build ./..."
    checks_text = sections.get("checks", "")
    for line in checks_text.splitlines():
        line = line.strip().lstrip("- ")
        if ":" in line:
            name, _, command = line.partition(":")
            epic.checks.append(Check(name=name.strip(), command=command.strip()))

    return epic


def extract_tasks(text: str) -> list[TaskDef]:
    """Extract all ```task fenced blocks from model output."""
    blocks = _extract_all_fenced_blocks(text, "task")
    tasks = []
    for block in blocks:
        sections = _parse_sections(block)
        task = TaskDef()
        task.title = sections.get("title", "").strip()
        task.description = sections.get("description", "").strip()
        task.acceptance = sections.get("acceptance", "").strip()

        deps_str = sections.get("depends", "").strip()
        if deps_str and deps_str.lower() != "none":
            task.depends = [
                int(d.strip()) for d in deps_str.split(",")
                if d.strip().isdigit()
            ]

        atomic_str = sections.get("atomic", "").strip()
        task.atomic = atomic_str.lower() == "true"

        if task.title:
            tasks.append(task)
    return tasks


def extract_verdict(text: str) -> tuple[str, str]:
    """Extract VERDICT: line and any ISSUES:/MISSING: section.

    Returns (verdict, details) where verdict is "PASS", "FAIL",
    "ATOMIC", "SPLIT", "COMPLETE", "INCOMPLETE", or "UNKNOWN".
    """
    matches = re.findall(r"VERDICT:\s*(\w+)", text, re.IGNORECASE)
    if not matches:
        return ("UNKNOWN", text[-500:])

    verdict = matches[-1].upper()

    details = ""
    for marker in ("ISSUES:", "MISSING:"):
        idx = text.rfind(marker)
        if idx != -1:
            details = text[idx + len(marker):].strip()
            break

    return (verdict, details)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _extract_fenced_block(text: str, block_type: str) -> str | None:
    """Extract content of the first ```<type> ... ``` block."""
    results = _extract_all_fenced_blocks(text, block_type)
    return results[0] if results else None


def _extract_all_fenced_blocks(text: str, block_type: str) -> list[str]:
    """Extract all ```<type> ... ``` blocks, handling nested fences.

    Tracks nesting depth so that inner ```go / ``` pairs don't
    prematurely close the outer ```task block.
    """
    opener = re.compile(rf"^```{re.escape(block_type)}\s*$", re.MULTILINE)
    fence_line = re.compile(r"^```", re.MULTILINE)

    results: list[str] = []
    search_start = 0

    while True:
        open_match = opener.search(text, search_start)
        if not open_match:
            break

        content_start = open_match.end() + 1  # skip the newline after opener
        depth = 1
        pos = content_start

        closed = False
        while depth > 0 and pos < len(text):
            fence_match = fence_line.search(text, pos)
            if not fence_match:
                break

            line_start = fence_match.start()
            line_end = text.find("\n", line_start)
            if line_end == -1:
                line_end = len(text)
            full_line = text[line_start:line_end].strip()

            if full_line == "```":
                depth -= 1
                if depth == 0:
                    results.append(text[content_start:line_start])
                    search_start = line_end + 1
                    closed = True
                    break
                pos = line_end + 1
            elif full_line.startswith("```"):
                depth += 1
                pos = line_end + 1
            else:
                pos = line_end + 1

        if not closed and depth > 0:
            # Unterminated block — take everything to end
            results.append(text[content_start:])
            break

    return results


def _parse_sections(block: str) -> dict[str, str]:
    """Parse a block of text into sections.

    Only lines matching a known field name (from _KNOWN_FIELDS) at the
    start of a line are treated as section headers. This prevents
    false positives from lines like "http: //example.com" inside a
    description field.

    Single-line fields: "key: value"
    Multi-line fields: "key:" followed by content lines until the
    next known field or end of block.
    """
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in block.splitlines():
        # Check if this line starts a known field
        field_match = re.match(r"^([a-z_-]+):\s*(.*)", line)
        if field_match and field_match.group(1) in _KNOWN_FIELDS:
            # Save previous field
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines)
            current_key = field_match.group(1)
            value = field_match.group(2)
            current_lines = [value] if value else []
        elif current_key is not None:
            current_lines.append(line)

    # Save last field
    if current_key is not None:
        sections[current_key] = "\n".join(current_lines)

    return sections
