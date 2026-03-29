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

RESEARCH = """\
You are a research assistant preparing reference materials for a coding project.

EPIC: {epic_title}

DESCRIPTION:
{epic_description}

Your job: find specific documentation URLs that a developer will need to implement this project.

Steps:
1. Identify the key technical concepts, protocols, APIs, and libraries involved
2. Use web search to find the OFFICIAL documentation for each
3. Find the SPECIFIC pages/sections — not homepages, but the exact reference needed
4. Prefer: official docs > specs > tutorials with code > blog posts

Output a ```refs block listing each URL with a short label:

```refs
- <label>: <url>
- <label>: <url>
```

Focus on URLs that contain:
- API references with function signatures and examples
- Protocol specs with message formats and data structures
- Library docs with usage patterns
- Configuration references

Do NOT include:
- Generic homepages or marketing pages
- Outdated documentation
- URLs that require authentication
"""

PLAN = """\
You are a project planner. Break down an epic into sequential tasks.

EPIC: {epic_title}

DESCRIPTION:
{epic_description}

ACCEPTANCE CRITERIA:
{acceptance}

REFERENCE DOCUMENTATION:
{research_refs}

WORKING DIRECTORY: {workdir}

Rules:
- Each task must be completable in a SINGLE coding session
- Tasks are ordered: later tasks may depend on earlier ones
- Each task has clear, testable acceptance criteria
- Do NOT write code. Only plan.
- Only read source files if you need to understand existing code. If the project is empty or new, skip file reading.
- If a task is clearly simple (single file, trivial change), add "atomic: true" to its fields
- CRITICAL: dependencies must be correct. If task B imports or uses files/modules created by task A, then B MUST list A in its depends field. Double-check every depends value before outputting.
- Test tasks must depend on the implementation tasks they test
- If reference docs are available, attach relevant URLs to each task in the "refs:" field. The executor will use webfetch to read them. Only attach refs that are directly relevant to that specific task.
- PARALLELISM: If multiple tasks have the same dependencies and touch DIFFERENT files/modules with no overlap, assign them the same "parallel_group" label (e.g., "A", "B"). Tasks in the same group can run concurrently. Only group tasks that are truly independent — same deps, different files, no shared state. When in doubt, don't group.

Output each task inside a fenced block (the ``` markers are required):

```task
title: <short title>
depends: <comma-separated task numbers, or "none">
atomic: <true or false — true if this is clearly a small, single-file change>
parallel_group: <group label like "A", "B", or empty if sequential>

description:
<multi-line description — mention files, functions, patterns>

acceptance:
<multi-line acceptance criteria>

refs:
- <url relevant to this task>
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

REFERENCE DOCS:
{task_refs}

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
- If reference docs are listed above, use webfetch to read them BEFORE writing code. They contain the exact specs and API details you need.
"""

REVIEW = """\
You are a code reviewer. Review the changes made for a specific task.

TASK: {task_title}

ACCEPTANCE CRITERIA:
{acceptance}

PROJECT FILES:
{file_listing}

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
Final review of ALL work done for this epic. You MUST verify thoroughly before approving.

EPIC: {epic_title}

DESCRIPTION:
{epic_description}

ACCEPTANCE CRITERIA:
{acceptance}

TASKS COMPLETED:
{task_summary}

PREVIOUS CHECK RESULTS:
{check_results}

IMPORTANT: Do NOT trust the diff or check results above blindly. You must verify yourself:

Step 1: Run the check commands yourself:
{checks_description}

Step 2: Read the key source files to verify they are complete (no stubs, no TODOs, no placeholders)

Step 3: Check each acceptance criterion one by one — is it actually implemented?

Step 4: Only after verifying, give your verdict.

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

PLAN_REVIEW = """\
Review and improve this project plan. Look for issues and fix them.

EPIC: {epic_title}

DESCRIPTION:
{epic_description}

CURRENT PLAN:
{current_plan}

Check for these common problems:
1. DEPENDENCY ERRORS: If task B uses/imports files created by task A, does B depend on A? If not, fix it.
2. GRANULARITY: Are any tasks too large (touching 5+ files, multiple logical changes)? Split them.
3. ORDERING: Would a different order be more natural or reduce risk?
4. MISSING TASKS: Are there acceptance criteria not covered by any task?
5. TEST COVERAGE: Do test tasks depend on the implementation tasks they test?

If the plan is good and you have no improvements, respond with:
VERDICT: GOOD

If you found issues, respond with:
VERDICT: IMPROVED

Then output the COMPLETE improved plan (all tasks, not just changed ones) as ```task blocks:

```task
title: <short title>
depends: <comma-separated task numbers, or "none">
atomic: <true or false>

description:
<multi-line description>

acceptance:
<specific, testable criteria>
```
"""

REPLAN = """\
A task has failed after multiple attempts. Review the project state and rebuild the plan.

EPIC: {epic_title}

DESCRIPTION:
{epic_description}

ACCEPTANCE CRITERIA:
{acceptance}

FAILED TASK: {failed_task_title}
FAILURE REASON:
{failure_reason}

TASKS COMPLETED SO FAR:
{completed_summary}

REMAINING OPEN TASKS:
{open_summary}

EXISTING FILES IN PROJECT:
{file_listing}

CHECK RESULTS:
{check_results}

Analyze the situation:
1. Why did the failed task fail? (missing dependency? wrong approach? task too large?)
2. What has already been built and is working?
3. What is still needed to meet the epic acceptance criteria?

Now create a NEW set of tasks to replace ALL remaining open tasks (including the failed one).
The new plan should:
- Build on what already exists (do NOT redo completed work)
- Fix the ordering/dependency issues that caused the failure
- Ensure each task's dependencies are correct (if task B uses files from task A, B must depend on A)
- Keep tasks small and atomic where possible

Output each task inside a fenced block:

```task
title: <short title>
depends: <comma-separated task numbers within this new plan, or "none">
atomic: <true or false>

description:
<multi-line description — mention specific files to create/modify>

acceptance:
<specific, testable criteria>
```

Output as many ```task blocks as needed, one after another.
"""

# ---------------------------------------------------------------------------
# Template loader
# ---------------------------------------------------------------------------

_TEMPLATES = {
    "dialog": "DIALOG",
    "research": "RESEARCH",
    "plan": "PLAN",
    "refine": "REFINE",
    "execute": "EXECUTE",
    "review": "REVIEW",
    "fix": "FIX",
    "final_review": "FINAL_REVIEW",
    "plan_review": "PLAN_REVIEW",
    "replan": "REPLAN",
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
