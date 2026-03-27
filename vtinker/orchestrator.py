"""Main orchestrator: DIALOG → PREPARE → PLAN → loop(REFINE → EXECUTE → REVIEW → FIX) → FINAL."""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

from vtinker import beads, checks, opencode
from vtinker.config import VTINKER_DIR, Config, State, save_state
from vtinker.doom import DoomDetector
from vtinker.gitignore import ensure_gitignore
from vtinker.parse import EpicDef, extract_epic, extract_tasks, extract_verdict
from vtinker.prompts import load_prompts


class VtinkerError(RuntimeError):
    pass


class Orchestrator:
    def __init__(self, config: Config):
        self.config = config
        self.doom = DoomDetector(threshold=config.max_retries)
        self.epic_id: str | None = None
        self.workdir: Path = config.workdir
        self.branch_base: str | None = None
        self._log_file: Path | None = None
        self._prompts = load_prompts(config.prompts_dir)

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def start(self) -> None:
        beads.set_workdir(self.workdir)
        beads.init(self.workdir)
        ensure_gitignore(self.workdir)
        self._init_log()
        self._dialog()
        self._save_state()
        self._prepare()
        self._save_state()
        self._plan()
        self._execute_loop()
        self._final_review()

    def start_headless(self, epic_def: EpicDef) -> None:
        """Start without interactive DIALOG — epic already defined."""
        beads.set_workdir(self.workdir)
        beads.init(self.workdir)
        ensure_gitignore(self.workdir)
        self._init_log()
        self._create_epic_from_def(epic_def)
        self._save_state()
        self._prepare()
        self._save_state()
        self._plan()
        self._execute_loop()
        self._final_review()

    def resume(self, epic_id: str) -> None:
        self.epic_id = epic_id
        beads.set_workdir(self.workdir)
        ensure_gitignore(self.workdir)
        self._init_log()
        self._record_branch_base()
        self._execute_loop()
        self._final_review()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        if not self.epic_id:
            return
        state = State(
            epic_id=self.epic_id,
            workdir=str(self.workdir),
            branch_base=self.branch_base,
            checks=[{"name": c.name, "command": c.command} for c in self.config.checks],
        )
        save_state(state, self.workdir)
        self._audit("state_saved", {"epic_id": self.epic_id})

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def _init_log(self) -> None:
        dw_dir = self.workdir / VTINKER_DIR
        dw_dir.mkdir(exist_ok=True)
        self._log_file = dw_dir / "log.jsonl"

    def _audit(self, event: str, data: dict | None = None) -> None:
        if not self._log_file:
            return
        entry = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event": event,
            **(data or {}),
        }
        with open(self._log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # ------------------------------------------------------------------
    # Phase 1: DIALOG — interactive task formulation
    # ------------------------------------------------------------------

    def _dialog(self) -> None:
        _log("DIALOG", "analyzing codebase and generating epic...")

        # Single captured run: model explores the codebase, asks itself
        # the wizard questions, and produces the ```epic block.
        # Output is streamed to stderr so the user sees what's happening.
        result = opencode.run_captured(
            self._prompts["dialog"]
            + "\n\nExplore the codebase now and generate the ```epic block "
            "based on what you find. Make reasonable choices.",
            self.workdir,
            model=self.config.opencode_model,
            timeout=300,
        )

        epic_def = extract_epic(result.text)
        self._audit("dialog_parse", {"parsed": epic_def is not None})

        if epic_def is None or not epic_def.title:
            _log("DIALOG", "could not parse epic from model output, asking manually")
            epic_def = self._dialog_manual()

        self._create_epic_from_def(epic_def)

    def _create_epic_from_def(self, epic_def: EpicDef) -> None:
        """Create the epic in beads and merge settings into config."""
        self.epic_id = beads.create_epic(
            title=epic_def.title,
            description=epic_def.description,
        )
        if epic_def.acceptance:
            beads.update(self.epic_id, acceptance=epic_def.acceptance)

        if epic_def.checks:
            self.config.checks = epic_def.checks
        if epic_def.branch:
            self.config.branch_prefix = epic_def.branch
            if not self.config.branch_prefix.endswith("/"):
                self.config.branch_prefix += "/"
        if epic_def.worktree:
            self.config.use_worktree = True

        _log("DIALOG", f"created epic {self.epic_id}: {epic_def.title}")
        self._audit("epic_created", {"epic_id": self.epic_id, "title": epic_def.title})

    def _dialog_manual(self) -> EpicDef:
        print("\nEnter task details manually:")
        title = input("Title: ").strip()
        print("Description (end with empty line):")
        desc_lines = _read_multiline()
        print("Acceptance criteria (end with empty line):")
        acc_lines = _read_multiline()
        return EpicDef(
            title=title,
            description="\n".join(desc_lines),
            acceptance="\n".join(acc_lines),
        )

    # ------------------------------------------------------------------
    # Phase 2: PREPARE — git branch/worktree setup
    # ------------------------------------------------------------------

    def _prepare(self) -> None:
        if not self.epic_id:
            return

        safe_id = self.epic_id.replace("/", "-")

        if self.config.use_worktree:
            branch = f"{self.config.branch_prefix}{safe_id}"
            wt_path = self.workdir.parent / f"vtinker-{safe_id}"
            _git(self.workdir, "branch", branch)
            _git(self.workdir, "worktree", "add", str(wt_path), branch)
            self.workdir = wt_path
            beads.set_workdir(self.workdir)
            ensure_gitignore(self.workdir)
            self._init_log()
            _log("PREPARE", f"worktree at {wt_path}")
        elif self.config.branch_prefix:
            branch = f"{self.config.branch_prefix}{safe_id}"
            _git(self.workdir, "checkout", "-b", branch)
            _log("PREPARE", f"branch {branch}")

        self._record_branch_base()
        self._audit("prepare", {"workdir": str(self.workdir), "branch_base": self.branch_base})

    def _record_branch_base(self) -> None:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.workdir, capture_output=True, text=True,
        )
        if result.returncode == 0:
            self.branch_base = result.stdout.strip()

    # ------------------------------------------------------------------
    # Phase 3: PLAN — break epic into tasks
    # ------------------------------------------------------------------

    def _plan(self) -> None:
        _log("PLAN", "breaking epic into tasks")
        epic = beads.show(self.epic_id)

        prompt = self._prompts["plan"].format(
            epic_title=epic.get("title", ""),
            epic_description=epic.get("description", ""),
            acceptance=epic.get("acceptance_criteria", epic.get("acceptance", "")),
            workdir=str(self.workdir),
        )

        # Try up to 3 times — some models need a retry to produce the right format
        for attempt in range(3):
            if attempt > 0:
                _log("PLAN", f"retry {attempt}/2 — asking model to use ```task format")
                prompt = (
                    "Your previous response did not contain any ```task blocks. "
                    "Please try again. Output MUST use fenced ```task blocks.\n\n"
                    + prompt
                )

            result = self._opencode(prompt, phase="plan")
            tasks = extract_tasks(result.text)

            if tasks:
                self._create_tasks_from_defs(self.epic_id, tasks)
                _log("PLAN", f"created {len(tasks)} tasks")
                self._audit("plan_created", {"task_count": len(tasks)})
                return

            _log("PLAN", f"no tasks parsed (attempt {attempt + 1}/3)")
            self._audit("plan_retry", {"attempt": attempt + 1, "output_len": len(result.text)})

        _log("PLAN", f"FAILED after 3 attempts. Raw output:\n{result.text[:1000]}")
        self._audit("plan_failed", {"output_len": len(result.text)})
        raise VtinkerError(
            "PLAN phase failed: model did not produce any ```task blocks after 3 attempts. "
            "Try a different model or provide tasks manually."
        )

    def _create_tasks_from_defs(self, parent_id: str, tasks: list) -> dict[int, str]:
        """Create beads tasks from parsed TaskDefs. Returns id_map."""
        id_map: dict[int, str] = {}
        for i, task in enumerate(tasks, 1):
            deps = [id_map[d] for d in task.depends if d in id_map] or None
            # Store atomic flag in metadata via notes
            notes = "atomic: true" if task.atomic else None
            bead_id = beads.create_task(
                parent_id=parent_id,
                title=task.title,
                description=task.description,
                acceptance=task.acceptance,
                deps=deps,
            )
            if notes:
                beads.update(bead_id, notes=notes)
            id_map[i] = bead_id
            _log("PLAN", f"  {bead_id}: {task.title}{'  [atomic]' if task.atomic else ''}")
        return id_map

    # ------------------------------------------------------------------
    # Phase 4-7: EXECUTE LOOP
    # ------------------------------------------------------------------

    def _execute_loop(self) -> None:
        _log("LOOP", "starting execute loop")
        iteration = 0
        max_iterations = 100

        while iteration < max_iterations:
            iteration += 1
            ready_tasks = beads.ready(parent=self.epic_id)

            if not ready_tasks:
                all_children = beads.children(self.epic_id)
                open_tasks = [c for c in all_children
                              if c.get("status") not in ("closed", "done")]
                if not open_tasks:
                    _log("LOOP", "all tasks complete")
                    break
                _log("LOOP", f"blocked: {len(open_tasks)} tasks remain, none ready")
                for t in open_tasks:
                    _log("LOOP", f"  {t.get('id', '?')}: {t.get('title', '?')} [{t.get('status', '?')}]")
                break

            task = ready_tasks[0]
            self._process_task(task)

        if iteration >= max_iterations:
            _log("LOOP", "safety limit reached — stopping")

    def _process_task(self, task: dict) -> None:
        task_id = task.get("id", "?")
        _log("TASK", f"{task_id}: {task.get('title', '')}")
        self._audit("task_start", {"task_id": task_id, "title": task.get("title", "")})

        # Check for existing children (already refined)
        existing_children = beads.children(task_id)
        if not existing_children:
            # Skip REFINE if planner marked it atomic
            is_atomic = "atomic: true" in task.get("notes", "")
            if not is_atomic and self._refine(task):
                return

        # Record git state before execute
        pre_execute_rev = _git_rev(self.workdir)

        # EXECUTE
        self.doom.reset()
        self._execute(task)

        # Ensure changes are committed so review can see a clean diff
        self._ensure_committed(task)

        # REVIEW + FIX loop
        issues = ""
        for attempt in range(self.config.max_retries):
            check_results = checks.run_checks(self.config.checks, self.workdir)
            verdict, issues = self._review(task, check_results, pre_execute_rev)

            if verdict == "PASS":
                beads.close(task_id, reason="Completed and reviewed")
                _log("TASK", f"DONE: {task_id}")
                self._audit("task_done", {"task_id": task_id})
                return

            self.doom.record(task_id, issues)
            if self.doom.is_looping():
                _log("TASK", f"DOOM LOOP on {task_id} — needs manual intervention")
                beads.update(task_id, notes=f"Doom loop after {attempt + 1} attempts:\n{issues}")
                self._audit("doom_loop", {"task_id": task_id, "attempt": attempt + 1})
                return

            _log("TASK", f"fix attempt {attempt + 1}/{self.config.max_retries}")
            self._fix(task, issues, check_results)
            self._ensure_committed(task, fix_attempt=attempt + 1)

        _log("TASK", f"max retries reached for {task_id} — STOPPING")
        _log("TASK", f"last issues:\n{issues}")
        beads.update(task_id, status="blocked",
                     notes=f"Max retries ({self.config.max_retries}) reached. Last issues:\n{issues}")
        self._audit("task_max_retries", {"task_id": task_id})
        raise VtinkerError(
            f"Task {task_id} failed after {self.config.max_retries} attempts. "
            f"Fix manually then run: vtinker resume"
        )

    # ------------------------------------------------------------------
    # Sub-phases
    # ------------------------------------------------------------------

    def _refine(self, task: dict) -> bool:
        """Check if task needs splitting. Returns True if split occurred."""
        result = self._opencode(
            self._prompts["refine"].format(
                task_title=task.get("title", ""),
                task_description=task.get("description", ""),
            ),
            phase="refine",
        )

        verdict, _ = extract_verdict(result.text)
        if verdict == "ATOMIC":
            return False

        subtasks = extract_tasks(result.text)
        if not subtasks:
            return False

        self._create_tasks_from_defs(task["id"], subtasks)
        _log("REFINE", f"split into {len(subtasks)} subtasks")
        self._audit("task_refined", {"task_id": task["id"], "subtask_count": len(subtasks)})
        return True

    def _execute(self, task: dict) -> None:
        epic = beads.show(self.epic_id)
        all_children = beads.children(self.epic_id)
        completed = [c for c in all_children if c.get("status") in ("closed", "done")]
        completed_summary = "\n".join(
            f"- {c.get('title', c.get('id', '?'))}" for c in completed
        ) or "None yet"
        checks_desc = "\n".join(
            f"- {c.name}: {c.command}" for c in self.config.checks
        ) or "None configured"

        context_files = _extract_file_refs(task.get("description", ""), self.workdir)

        self._opencode(
            self._prompts["execute"].format(
                task_title=task.get("title", ""),
                task_description=task.get("description", ""),
                acceptance=_get_acceptance(task),
                epic_description=epic.get("description", ""),
                completed_summary=completed_summary,
                checks_description=checks_desc,
            ),
            files=context_files or None,
            phase="execute",
        )

    def _review(
        self,
        task: dict,
        check_results: list[checks.CheckResult],
        pre_execute_rev: str | None,
    ) -> tuple[str, str]:
        if pre_execute_rev:
            diff = _git_output(self.workdir, "diff", pre_execute_rev, "HEAD")
        else:
            diff = _git_output(self.workdir, "diff", "HEAD~1")

        unstaged = _git_output(self.workdir, "diff")
        if unstaged.strip():
            diff += "\n\n--- UNSTAGED CHANGES ---\n" + unstaged

        if not diff.strip():
            diff = "(no changes detected)"

        result = self._opencode(
            self._prompts["review"].format(
                task_title=task.get("title", ""),
                acceptance=_get_acceptance(task),
                git_diff=_truncate(diff, 8000),
                check_results=checks.format_results(check_results),
            ),
            phase="review",
        )

        verdict, issues = extract_verdict(result.text)
        self._audit("review", {"task_id": task.get("id"), "verdict": verdict, "has_issues": bool(issues)})
        return (verdict, issues)

    def _fix(self, task: dict, issues: str, check_results: list[checks.CheckResult]) -> None:
        diff = _git_output(self.workdir, "diff", "HEAD~1")
        unstaged = _git_output(self.workdir, "diff")
        if unstaged.strip():
            diff += "\n\n--- UNSTAGED ---\n" + unstaged

        checks_desc = "\n".join(f"- {c.name}: {c.command}" for c in self.config.checks)

        self._opencode(
            self._prompts["fix"].format(
                task_title=task.get("title", ""),
                review_feedback=issues,
                git_diff=_truncate(diff, 8000),
                checks_description=checks_desc,
            ),
            phase="fix",
        )

    def _ensure_committed(self, task: dict, fix_attempt: int | None = None) -> None:
        """Ensure any changes from execute/fix are committed."""
        status = _git_output(self.workdir, "status", "--porcelain")
        if not status.strip():
            return

        title = task.get("title", task.get("id", "task"))
        if fix_attempt:
            msg = f"vtinker: fix #{fix_attempt} for {title}"
        else:
            msg = f"vtinker: {title}"

        # Selective add: only tracked files + new files, skip vtinker artifacts
        # Add all changes except vtinker artifacts
        subprocess.run(
            ["git", "add", "-A", "--", ".", ":(exclude).vtinker", ":(exclude).vtinker-*"],
            cwd=self.workdir, capture_output=True, text=True,
        )
        proc = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=self.workdir, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            self._audit("auto_commit", {"message": msg})

    # ------------------------------------------------------------------
    # Phase 8: FINAL REVIEW
    # ------------------------------------------------------------------

    def _final_review(self, depth: int = 0) -> None:
        if depth >= 3:
            _log("FINAL", "max final review depth reached, stopping")
            return
        if not self.branch_base:
            _log("FINAL", "no branch base recorded, skipping final review")
            return

        _log("FINAL", "running final review")
        epic = beads.show(self.epic_id)
        all_children = beads.children(self.epic_id)
        full_diff = _git_output(self.workdir, "diff", self.branch_base, "HEAD")
        check_results = checks.run_checks(self.config.checks, self.workdir)
        task_summary = "\n".join(
            f"- [{c.get('status', '?')}] {c.get('title', c.get('id', '?'))}"
            for c in all_children
        )

        result = self._opencode(
            self._prompts["final_review"].format(
                epic_title=epic.get("title", ""),
                epic_description=epic.get("description", ""),
                acceptance=epic.get("acceptance_criteria", epic.get("acceptance", "")),
                full_diff=_truncate(full_diff, 15000),
                check_results=checks.format_results(check_results),
                task_summary=task_summary,
            ),
            phase="final",
        )

        verdict, missing = extract_verdict(result.text)
        self._audit("final_review", {"verdict": verdict})

        if verdict == "INCOMPLETE":
            _log("FINAL", f"final review found missing work, creating tasks...")
            new_tasks = extract_tasks(result.text)
            if new_tasks:
                self._create_tasks_from_defs(self.epic_id, new_tasks)
                _log("FINAL", f"created {len(new_tasks)} new tasks, re-entering loop")
                self._execute_loop()
                # Recursive final review (with depth limit via max_iterations)
                self._final_review(depth=depth + 1)
            else:
                _log("FINAL", f"could not parse new tasks from:\n{missing}")
        else:
            _log("FINAL", f"epic {self.epic_id} COMPLETE")

    # ------------------------------------------------------------------
    # OpenCode wrapper
    # ------------------------------------------------------------------

    def _model_for(self, phase: str) -> str | None:
        """Get the model for a specific phase, falling back to default."""
        overrides = {
            "plan": self.config.model_plan,
            "refine": self.config.model_plan,  # refine uses plan model
            "execute": self.config.model_execute,
            "review": self.config.model_review,
            "fix": self.config.model_execute,  # fix uses execute model
            "final": self.config.model_review,  # final review uses review model
        }
        return overrides.get(phase) or self.config.opencode_model

    def _opencode(
        self,
        prompt: str,
        files: list[Path] | None = None,
        timeout: int | None = None,
        phase: str | None = None,
    ) -> opencode.RunResult:
        """Run opencode with real-time progress streaming to stderr."""
        if timeout is None:
            timeout = self.config.opencode_timeout
        model = self._model_for(phase) if phase else self.config.opencode_model
        return opencode.run(
            prompt, self.workdir,
            model=model,
            files=files,
            timeout=timeout,
            on_event=opencode.default_progress,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _log(phase: str, msg: str) -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts} vtinker:{phase}] {msg}", file=sys.stderr)


def _git(workdir: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=workdir, check=True)


def _git_output(workdir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=workdir, capture_output=True, text=True,
    )
    return result.stdout


def _git_rev(workdir: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workdir, capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n... (truncated, {len(text)} total chars)"


def _read_multiline() -> list[str]:
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line:
            break
        lines.append(line)
    return lines


def _get_acceptance(bead: dict) -> str:
    """Get acceptance criteria from a bead dict, handling field name variants."""
    return bead.get("acceptance_criteria", bead.get("acceptance", bead.get("notes", "")))


def _extract_file_refs(description: str, workdir: Path) -> list[Path]:
    """Extract file paths mentioned in task description that actually exist."""
    files = []
    for match in re.finditer(r'(?:^|[\s`\'"])([./]?(?:[\w.-]+/)+[\w.-]+\.\w+)', description):
        path_str = match.group(1)
        for candidate in [Path(path_str), workdir / path_str]:
            if candidate.is_file() and candidate not in files:
                files.append(candidate)
                break
    return files
