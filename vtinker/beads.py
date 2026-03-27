"""Thin wrapper around the bd (Beads) CLI."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class BeadsError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

_workdir: Path | None = None


def set_workdir(path: Path) -> None:
    global _workdir
    _workdir = path


def _run(*args: str, json_output: bool = True) -> Any:
    cmd = ["bd", *args]
    if json_output:
        cmd.append("--json")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=_workdir)
    if result.returncode != 0:
        raise BeadsError(f"bd {' '.join(args)}: {result.stderr.strip()}")
    if not json_output or not result.stdout.strip():
        return result.stdout.strip()
    # bd --json may return a single object or an array
    text = result.stdout.strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init(workdir: Path | None = None) -> None:
    """Initialize beads in the given directory if not already done."""
    wd = workdir or _workdir
    subprocess.run(["bd", "init"], cwd=wd, capture_output=True, text=True)


def create_epic(title: str, description: str = "") -> str:
    """Create a top-level epic. Returns the bead ID."""
    args = ["create", "--type", "epic", title]
    if description:
        args += ["-d", description]
    result = _run(*args)
    return result["id"]


def create_task(
    parent_id: str,
    title: str,
    description: str = "",
    acceptance: str = "",
    deps: list[str] | None = None,
) -> str:
    """Create a task under a parent epic/task. Returns the bead ID."""
    args = ["create", "--parent", parent_id, title]
    if description:
        args += ["-d", description]
    if acceptance:
        args += ["--acceptance", acceptance]
    if deps:
        args += ["--deps", ",".join(deps)]
    result = _run(*args)
    return result["id"]


def ready(parent: str | None = None, limit: int = 20) -> list[dict]:
    """Return tasks ready to work on (open, no active blockers)."""
    args = ["ready", "-n", str(limit)]
    if parent:
        args += ["--parent", parent]
    result = _run(*args)
    if isinstance(result, list):
        return result
    # Some bd versions return an object with an "issues" key
    if isinstance(result, dict):
        return result.get("issues", result.get("items", []))
    return []


def show(bead_id: str) -> dict:
    """Get full details of a single bead."""
    result = _run("show", bead_id)
    # bd show returns a list even for a single ID
    if isinstance(result, list):
        return result[0] if result else {}
    return result


def close(bead_id: str, reason: str = "") -> None:
    """Mark a bead as closed/done."""
    args = ["close", bead_id]
    if reason:
        args += ["-r", reason]
    _run(*args, json_output=False)


def update(
    bead_id: str,
    description: str | None = None,
    notes: str | None = None,
    acceptance: str | None = None,
    title: str | None = None,
    status: str | None = None,
) -> None:
    """Update fields on a bead."""
    args = ["update", bead_id]
    if description is not None:
        args += ["-d", description]
    if notes is not None:
        args += ["--notes", notes]
    if acceptance is not None:
        args += ["--acceptance", acceptance]
    if title is not None:
        args += ["--title", title]
    if status is not None:
        args += ["-s", status]
    if len(args) <= 2:
        return  # nothing to update
    _run(*args, json_output=False)


def children(bead_id: str) -> list[dict]:
    """List all children of a parent bead (includes closed)."""
    result = _run("children", bead_id)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("issues", result.get("items", []))
    return []


def epic_status(epic_id: str) -> dict:
    """Get epic completion status."""
    return _run("epic", "status", epic_id)
