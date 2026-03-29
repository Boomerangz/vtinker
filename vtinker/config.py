from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

VTINKER_DIR = ".vtinker"


@dataclass
class Check:
    name: str
    command: str


@dataclass
class Config:
    workdir: Path = field(default_factory=lambda: Path(".").resolve())
    branch_prefix: str = "vtinker/"
    use_worktree: bool = False
    max_retries: int = 10
    opencode_timeout: int = 900  # seconds per opencode call (15 min)
    checks: list[Check] = field(default_factory=list)
    opencode_model: str | None = None
    opencode_agent: str | None = None
    prompts_dir: Path | None = None
    # Per-phase model overrides (fall back to opencode_model if not set)
    model_research: str | None = None
    model_plan: str | None = None
    model_execute: str | None = None
    model_review: str | None = None


def _find_config(workdir: Path) -> Path | None:
    """Find vtinker config: .vtinker/config.json or vtinker.json (legacy)."""
    candidates = [
        workdir / VTINKER_DIR / "config.json",
        workdir / "vtinker.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def load_config(path: Path | None = None) -> Config:
    """Load config from .vtinker/config.json (or vtinker.json). Returns defaults if not found."""
    if path is None:
        path = _find_config(Path("."))
    elif path.is_dir():
        path = _find_config(path)

    if path is None or not path.exists():
        return Config()

    with open(path) as f:
        raw = json.load(f)

    checks = [Check(c["name"], c["command"]) for c in raw.get("checks", [])]
    oc = raw.get("opencode", {})
    prompts_dir = raw.get("prompts_dir")

    models = raw.get("models", {})

    return Config(
        workdir=Path(raw.get("workdir", ".")).resolve(),
        branch_prefix=raw.get("branch_prefix", "vtinker/"),
        use_worktree=raw.get("use_worktree", False),
        max_retries=raw.get("max_retries", 10),
        opencode_timeout=raw.get("opencode_timeout", 900),
        checks=checks,
        opencode_model=oc.get("model"),
        opencode_agent=oc.get("agent"),
        prompts_dir=Path(prompts_dir) if prompts_dir else None,
        model_research=models.get("research"),
        model_plan=models.get("plan"),
        model_execute=models.get("execute"),
        model_review=models.get("review"),
    )


# ---------------------------------------------------------------------------
# State file — persists epic_id, workdir, branch_base across interruptions
# ---------------------------------------------------------------------------


def _vtinker_dir(workdir: Path) -> Path:
    """Get or create the .vtinker directory."""
    d = workdir / VTINKER_DIR
    d.mkdir(exist_ok=True)
    return d


# Ordered phases — resume starts from the saved phase
PHASES = ("init", "epic", "prepare", "research", "plan", "execute", "final", "done")


@dataclass
class State:
    epic_id: str
    workdir: str
    phase: str = "init"
    branch_base: str | None = None
    checks: list[dict] | None = None


def save_state(state: State, workdir: Path) -> None:
    """Save run state so resume works after interruption."""
    path = _vtinker_dir(workdir) / "state.json"
    data = {
        "epic_id": state.epic_id,
        "workdir": state.workdir,
        "phase": state.phase,
        "branch_base": state.branch_base,
    }
    if state.checks:
        data["checks"] = state.checks
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_state(workdir: Path) -> State | None:
    """Load saved state. Returns None if no state file."""
    path = workdir / VTINKER_DIR / "state.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return State(
        epic_id=data["epic_id"],
        workdir=data["workdir"],
        phase=data.get("phase", "execute"),  # backward compat: old states had no phase
        branch_base=data.get("branch_base"),
        checks=data.get("checks"),
    )
