"""Monitor vtinker runs by tailing .vtinker/log.jsonl files."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator


@dataclass
class TaskInfo:
    id: str
    title: str = ""
    status: str = "open"  # open, in_progress, closed, blocked
    fix_attempts: int = 0
    start_time: str | None = None
    end_time: str | None = None


@dataclass
class RunInfo:
    """Represents a vtinker run, parsed from .vtinker/log.jsonl + state.json."""
    workdir: str
    epic_id: str = ""
    epic_title: str = ""
    status: str = "unknown"  # planning, running, complete, blocked, budget_exhausted
    tasks: dict[str, TaskInfo] = field(default_factory=dict)
    total_tasks: int = 0
    done_tasks: int = 0
    fix_count: int = 0
    replan_count: int = 0
    tokens_total: int = 0
    cost: float = 0.0
    start_time: str | None = None
    current_task: str | None = None
    models: dict[str, str] = field(default_factory=dict)
    log_lines: int = 0  # track how many lines we've read


def discover_runs(search_dirs: list[Path]) -> list[RunInfo]:
    """Find all vtinker runs in the given directories."""
    runs = []
    seen = set()
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        # Look for .vtinker/state.json in subdirectories
        for candidate in search_dir.iterdir():
            if not candidate.is_dir():
                continue
            state_file = candidate / ".vtinker" / "state.json"
            log_file = candidate / ".vtinker" / "log.jsonl"
            if state_file.exists() or log_file.exists():
                real = str(candidate.resolve())
                if real not in seen:
                    seen.add(real)
                    runs.append(parse_run(candidate))
    return sorted(runs, key=lambda r: r.start_time or "", reverse=True)


def parse_run(workdir: Path) -> RunInfo:
    """Parse a vtinker run from its .vtinker directory."""
    run = RunInfo(workdir=str(workdir))

    # Read state.json
    state_file = workdir / ".vtinker" / "state.json"
    if state_file.exists():
        try:
            with open(state_file) as f:
                state = json.load(f)
            run.epic_id = state.get("epic_id", "")
        except (json.JSONDecodeError, OSError):
            pass

    # Read config
    config_file = workdir / ".vtinker" / "config.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                cfg = json.load(f)
            oc = cfg.get("opencode", {})
            models = cfg.get("models", {})
            run.models = {
                "plan": models.get("plan", oc.get("model", "?")),
                "execute": models.get("execute", oc.get("model", "?")),
                "review": models.get("review", oc.get("model", "?")),
            }
        except (json.JSONDecodeError, OSError):
            pass

    # Parse log.jsonl
    log_file = workdir / ".vtinker" / "log.jsonl"
    if log_file.exists():
        _parse_log(log_file, run)

    return run


def _parse_log(log_file: Path, run: RunInfo) -> None:
    """Parse log.jsonl to extract run state."""
    try:
        with open(log_file) as f:
            lines = f.readlines()
    except OSError:
        return

    run.log_lines = len(lines)

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        event = entry.get("event", "")
        ts = entry.get("ts", "")

        if event == "epic_created":
            run.epic_id = entry.get("epic_id", "")
            run.epic_title = entry.get("title", "")
            run.start_time = ts
            run.status = "planning"

        elif event == "plan_created":
            run.total_tasks = entry.get("task_count", 0)
            run.status = "running"

        elif event == "task_start":
            task_id = entry.get("task_id", "")
            title = entry.get("title", "")
            if task_id not in run.tasks:
                run.tasks[task_id] = TaskInfo(id=task_id, title=title)
            run.tasks[task_id].status = "in_progress"
            run.tasks[task_id].start_time = ts
            run.current_task = task_id

        elif event == "task_done":
            task_id = entry.get("task_id", "")
            if task_id in run.tasks:
                run.tasks[task_id].status = "closed"
                run.tasks[task_id].end_time = ts
            run.done_tasks = sum(1 for t in run.tasks.values() if t.status == "closed")

        elif event == "task_max_retries":
            task_id = entry.get("task_id", "")
            if task_id in run.tasks:
                run.tasks[task_id].status = "blocked"
            run.status = "blocked"

        elif event == "review":
            if not entry.get("verdict") == "PASS":
                run.fix_count += 1

        elif event == "replan_start":
            run.replan_count += 1

        elif event == "replan_done":
            new_count = entry.get("new_task_count", 0)
            run.total_tasks = run.done_tasks + new_count
            run.status = "running"

        elif event == "final_review":
            if entry.get("verdict") == "COMPLETE":
                run.status = "complete"

        elif event == "token_summary":
            run.tokens_total = entry.get("total", 0)
            run.cost = entry.get("cost", 0.0)

    # Update total tasks from actual task count if log didn't have plan_created
    if not run.total_tasks and run.tasks:
        run.total_tasks = len(run.tasks)


def tail_log(log_file: Path, from_line: int = 0) -> list[dict]:
    """Read new lines from log.jsonl starting from from_line."""
    try:
        with open(log_file) as f:
            lines = f.readlines()
    except OSError:
        return []

    new_entries = []
    for line in lines[from_line:]:
        line = line.strip()
        if not line:
            continue
        try:
            new_entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return new_entries


def read_output_log(workdir: Path, last_n: int = 100) -> list[str]:
    """Read the last N lines from output.log (stderr capture)."""
    log_file = workdir / "output.log"
    if not log_file.exists():
        # Try .vtinker/output.log
        log_file = workdir / ".vtinker" / "output.log"
    if not log_file.exists():
        return []
    try:
        with open(log_file) as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-last_n:]]
    except OSError:
        return []
