"""Prompt templates for every orchestrator phase.

Each template uses {slot} placeholders filled by str.format().
Structured output uses ``` fenced blocks with field: value pairs.

Templates can be overridden by placing files in a prompts/ directory
alongside vtinker.json. File names: dialog.md, plan.md, refine.md,
execute.md, review.md, fix.md, final_review.md.
"""
from __future__ import annotations

from pathlib import Path

DIALOG = """\
You are a task formulation assistant. Analyze the codebase and define a coding task.

Steps:
1. Read the project structure (list files, read key configs like package.json, Cargo.toml, pubspec.yaml, go.mod, etc.)
2. Understand what the project does, what languages/frameworks it uses
3. Identify what build/test/lint commands are available
4. Based on your analysis, formulate a clear epic definition

Consider these aspects:
- What type of work makes sense: new feature / port / bug fix / refactor
- Which files and directories are relevant
- What does "done" look like — specific, testable criteria
- What commands verify success (build, test, lint)

Output a summary in this EXACT format (the ``` markers are important):

```epic
title: <one-line title>
branch: <branch name or "none">
worktree: <true or false>

description:
<detailed multi-line description with all relevant context>

acceptance:
<multi-line acceptance criteria, one per line, each starting with "- ">

checks:
- <check_name>: <shell command>
- <check_name>: <shell command>
```
"""

PLAN = """\
You are a project planner. Break down an epic into sequential tasks.

EPIC: {epic_title}

DESCRIPTION:
{epic_description}

ACCEPTANCE CRITERIA:
{acceptance}

WORKING DIRECTORY: {workdir}

Rules:
- Each task must be completable in a SINGLE coding session
- Tasks are ordered: later tasks may depend on earlier ones
- Each task has clear, testable acceptance criteria
- Do NOT write code. Only plan.
- Read relevant source files to understand what exists before planning
- If a task is clearly simple (single file, trivial change), add "atomic: true" to its fields

Output each task inside a fenced block (the ``` markers are required):

```task
title: <short title>
depends: <comma-separated task numbers, or "none">
atomic: <true or false — true if this is clearly a small, single-file change>

description:
<multi-line description — mention files, functions, patterns>

acceptance:
<multi-line acceptance criteria>
```

Output as many ```task blocks as needed, one after another.
"""

REFINE = """\
Evaluate whether this task can be completed atomically in one coding session.

TASK: {task_title}

DESCRIPTION:
{task_description}

A task is atomic if:
- It touches at most 3-5 files
- It involves one logical change
- A coding assistant can complete it without losing context

If atomic, respond with EXACTLY:
VERDICT: ATOMIC

If it needs splitting, respond with:
VERDICT: SPLIT

Then output subtasks as ```task blocks:

```task
title: <subtask title>
depends: <subtask numbers or "none">

description:
<what to do>

acceptance:
<how to verify>
```
"""

EXECUTE = """\
You have ONE task to complete. Do it fully, then stop.

TASK: {task_title}

DESCRIPTION:
{task_description}

ACCEPTANCE CRITERIA:
{acceptance}

EPIC CONTEXT:
{epic_description}

COMPLETED SO FAR:
{completed_summary}

CHECKS THAT MUST PASS AFTER YOUR WORK:
{checks_description}

Rules:
- Complete this task and ONLY this task
- Do not leave TODO comments, placeholders, or partial implementations
- Make sure all acceptance criteria are met
- Run the check commands listed above before finishing
- If a check fails, fix the issue before stopping
- Do not touch files unrelated to this task
"""

REVIEW = """\
You are a code reviewer. Review the changes made for a specific task.

TASK: {task_title}

ACCEPTANCE CRITERIA:
{acceptance}

GIT DIFF:
{git_diff}

CHECK RESULTS:
{check_results}

Focus on what matters: does the code work and meet the acceptance criteria?

Answer each question:
1. Are ALL acceptance criteria met? (This is the most important question)
2. Do all checks pass?
3. Are there TODO comments, debug code, or incomplete implementations?
4. Are there bugs or correctness issues?

NOTE: If the diff contains changes beyond the task scope (extra files, additional
features), that is OK as long as the acceptance criteria are met and checks pass.
Do NOT fail the review just because extra work was done. Only fail if acceptance
criteria are NOT met, checks fail, or there are bugs.

Ignore vtinker artifacts (.vtinker/, .vtinker-*) in the diff.

Then output your verdict as EXACTLY one of:

VERDICT: PASS

or:

VERDICT: FAIL
ISSUES:
- <issue 1>
- <issue 2>
"""

FIX = """\
A code review found issues with your previous work. Fix them.

TASK: {task_title}

REVIEW FEEDBACK:
{review_feedback}

GIT DIFF OF CURRENT CHANGES:
{git_diff}

Rules:
- Fix ONLY the issues listed above
- Do not make unrelated changes
- Run checks after fixing:
{checks_description}
"""

FINAL_REVIEW = """\
Final review of ALL work done for this epic.

EPIC: {epic_title}

DESCRIPTION:
{epic_description}

ACCEPTANCE CRITERIA:
{acceptance}

FULL GIT DIFF:
{full_diff}

CHECK RESULTS:
{check_results}

TASKS COMPLETED:
{task_summary}

Review:
1. Are ALL epic acceptance criteria met?
2. Is there any leftover or incomplete work?
3. Are there new issues introduced?
4. Is the code consistent across all changes?

If everything is complete, respond with:
VERDICT: COMPLETE

If work remains, respond with:
VERDICT: INCOMPLETE

Then output missing items as ```task blocks:

```task
title: <what's missing>
depends: none

description:
<what needs to be done>

acceptance:
<how to verify>
```
"""

# ---------------------------------------------------------------------------
# Template loader
# ---------------------------------------------------------------------------

_TEMPLATES = {
    "dialog": "DIALOG",
    "plan": "PLAN",
    "refine": "REFINE",
    "execute": "EXECUTE",
    "review": "REVIEW",
    "fix": "FIX",
    "final_review": "FINAL_REVIEW",
}


def load_prompts(prompts_dir: Path | None = None) -> dict[str, str]:
    """Load prompt templates, with optional overrides from a directory.

    Returns a dict mapping template name to template string.
    User overrides are plain .md files in prompts_dir (e.g., prompts/execute.md).
    They must contain the same {slot} placeholders as the defaults.
    """
    result = {}
    module = globals()
    for file_stem, var_name in _TEMPLATES.items():
        # Start with default
        result[file_stem] = module[var_name]
        # Check for override
        if prompts_dir:
            override = prompts_dir / f"{file_stem}.md"
            if override.is_file():
                result[file_stem] = override.read_text()
    return result
