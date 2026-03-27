"""CLI entry point for vtinker."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vtinker import beads
from vtinker.config import Check, load_config, load_state
from vtinker.orchestrator import VtinkerError, Orchestrator


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vtinker",
        description="Autonomous coding orchestrator (OpenCode + Beads)",
    )
    sub = parser.add_subparsers(dest="command")

    # vtinker start
    p_start = sub.add_parser("start", help="Start a new vtinker session")
    p_start.add_argument("--config", type=Path, help="Path to vtinker.json")
    p_start.add_argument("--dir", type=Path, default=Path("."), help="Working directory")
    p_start.add_argument(
        "--from", dest="from_file", type=Path,
        help="Skip DIALOG: read epic definition from a .md file with ```epic block",
    )
    p_start.add_argument("--title", help="Skip DIALOG: quick start with title (use with --desc)")
    p_start.add_argument("--desc", help="Skip DIALOG: task description")

    # vtinker resume [epic-id]
    p_resume = sub.add_parser("resume", help="Resume an existing epic")
    p_resume.add_argument("epic_id", nargs="?", help="Beads epic ID (auto-detected if omitted)")
    p_resume.add_argument("--config", type=Path, help="Path to vtinker.json")
    p_resume.add_argument("--dir", type=Path, default=Path("."), help="Working directory")

    # vtinker status [epic-id]
    p_status = sub.add_parser("status", help="Show epic status from beads")
    p_status.add_argument("epic_id", nargs="?", help="Beads epic ID (auto-detected if omitted)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "status":
        _handle_status(args)
        return

    config = load_config(getattr(args, "config", None))
    workdir = getattr(args, "dir", Path(".")).resolve()
    config.workdir = workdir

    try:
        if args.command == "start":
            orch = Orchestrator(config)
            epic_def = _resolve_headless_epic(args)
            if epic_def:
                orch.start_headless(epic_def)
            else:
                orch.start()

        elif args.command == "resume":
            epic_id = args.epic_id

            state = load_state(workdir)
            if not epic_id and state:
                epic_id = state.epic_id
                saved_workdir = Path(state.workdir)
                if saved_workdir.is_dir():
                    config.workdir = saved_workdir
                if not config.checks and state.checks:
                    config.checks = [Check(c["name"], c["command"]) for c in state.checks]
                print(f"Resuming epic {epic_id} (from state file)", file=sys.stderr)

            if not epic_id:
                print("Error: no epic_id provided and no .vtinker/state.json found", file=sys.stderr)
                sys.exit(1)

            orch = Orchestrator(config)
            if state and state.branch_base:
                orch.branch_base = state.branch_base
            orch.resume(epic_id)

    except VtinkerError as e:
        print(f"\n[vtinker] STOPPED: {e}", file=sys.stderr)
        sys.exit(1)


def _resolve_headless_epic(args) -> "EpicDef | None":
    """Build an EpicDef from --from file or --title/--desc flags."""
    from vtinker.parse import EpicDef, extract_epic

    from_file = getattr(args, "from_file", None)
    title = getattr(args, "title", None)

    if from_file:
        text = from_file.read_text()
        epic = extract_epic(text)
        if epic and epic.title:
            return epic
        # If no ```epic block, treat entire file as description
        return EpicDef(
            title=from_file.stem.replace("-", " ").replace("_", " "),
            description=text,
        )

    if title:
        desc = getattr(args, "desc", None) or ""
        return EpicDef(title=title, description=desc)

    return None


def _handle_status(args) -> None:
    workdir = Path(".").resolve()
    beads.set_workdir(workdir)

    epic_id = args.epic_id
    if not epic_id:
        state = load_state(workdir)
        if state:
            epic_id = state.epic_id
        else:
            print("Error: no epic_id provided and no .vtinker/state.json found", file=sys.stderr)
            sys.exit(1)

    _print_status(epic_id)


def _print_status(epic_id: str) -> None:
    epic = beads.show(epic_id)
    print(f"Epic: {epic.get('title', epic_id)}")
    print(f"Status: {epic.get('status', '?')}")
    print()

    all_children = beads.children(epic_id)
    if not all_children:
        print("No tasks yet.")
        return

    for child in all_children:
        status = child.get("status", "?")
        title = child.get("title", child["id"])
        marker = "x" if status == "closed" else " "
        print(f"  [{marker}] {child['id']}: {title}")

    total = len(all_children)
    done = sum(1 for c in all_children if c.get("status") == "closed")
    print(f"\n{done}/{total} tasks complete")
