"""Thin wrapper around the bd (Beads) CLI."""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_DEBUG = os.environ.get("VTINKER_DEBUG", "").lower() in ("1", "true", "yes")


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _dbg(msg: str) -> None:
    if _DEBUG:
        from vtinker.colors import DEBUG, RESET
        print(f"  {DEBUG}{_ts()} beads: {msg}{RESET}", file=sys.stderr)


class BeadsError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

_workdir: Path | None = None


def set_workdir(path: Path) -> None:
    global _workdir
    _workdir = path
    _dbg(f"workdir={path}")


def _run(*args: str, json_output: bool = True, timeout: int = 30) -> Any:
    cmd = ["bd", *args]
    if json_output:
        cmd.append("--json")
    _dbg(f"RUN: {' '.join(cmd)}  cwd={_workdir}")
    t0 = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=_workdir, timeout=timeout)
    except subprocess.TimeoutExpired:
        _dbg(f"TIMEOUT after {timeout}s: bd {' '.join(args)}")
        raise BeadsError(f"bd {' '.join(args)}: timed out after {timeout}s")
    elapsed = time.monotonic() - t0
    _dbg(f"DONE in {elapsed:.1f}s: exit={result.returncode}")
    if result.returncode != 0:
        _dbg(f"STDERR: {result.stderr.strip()[:200]}")
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
    _dbg(f"bd init  cwd={wd}")
    t0 = time.monotonic()
    try:
        result = subprocess.run(["bd", "init"], cwd=wd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        _dbg("bd init TIMEOUT after 30s")
        return
    elapsed = time.monotonic() - t0
    _dbg(f"bd init done in {elapsed:.1f}s: exit={result.returncode}")
    if result.returncode != 0:
        _dbg(f"bd init stderr: {result.stderr.strip()[:200]}")


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


def close(bead_id: str, reason: str = "", force: bool = False) -> None:
    """Mark a bead as closed/done."""
    args = ["close", bead_id]
    if reason:
        args += ["-r", reason]
    if force:
        args.append("--force")
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
