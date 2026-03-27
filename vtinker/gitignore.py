"""Ensure vtinker artifacts are in .gitignore."""
from __future__ import annotations

from pathlib import Path

VTINKER_ENTRIES = [
    ".vtinker/",
    ".vtinker-*",
]


def ensure_gitignore(workdir: Path) -> None:
    """Add .vtinker/ to .gitignore if not already present."""
    gitignore = workdir / ".gitignore"
    existing = ""
    if gitignore.exists():
        existing = gitignore.read_text()

    missing = [e for e in VTINKER_ENTRIES if e not in existing]
    if not missing:
        return

    with open(gitignore, "a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write("\n# vtinker orchestrator\n")
        for entry in missing:
            f.write(entry + "\n")
