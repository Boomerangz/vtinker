<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.kz.md">Қазақша</a> ·
  <a href="README.ar.md">العربية</a>
</p>

<p align="center"><img src=".github/assets/logo.png" width="200" /></p>

<h1 align="center">vtinker</h1>

<p align="center">
  <strong>The virtual tinkerer that turns a vague idea into shipped code.</strong>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" alt="Python 3.11+" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
  <a href="#"><img src="https://img.shields.io/badge/dependencies-zero-brightgreen" alt="Zero Dependencies" /></a>
  <a href="#"><img src="https://img.shields.io/badge/tests-passing-brightgreen" alt="Tests Passing" /></a>
</p>

<br />

Autonomous coding agent orchestrator that runs on top of [OpenCode](https://github.com/opencode-ai/opencode) and [Beads](https://github.com/steveyegge/beads). Give it a goal, walk away, come back to a finished branch with passing tests.

<br />

## Why vtinker?

- **Recursive task decomposition** -- plan, refine, execute, review, fix, repeat
- **Model-agnostic** -- works with any model supported by OpenCode (GLM, Qwen, MiniMax, Kimi, ...)
- **State lives in Beads**, not in memory -- every task, verdict, and fix attempt is tracked as an issue
- **Doom-loop detection** -- recognizes when the agent is stuck repeating the same failed fix and stops burning tokens
- **Resume from any point** -- interrupted at 2 AM? `vtinker resume` picks up exactly where it left off
- **Real-time streaming** -- watch tool calls and model output scroll by as each phase runs
- **Per-phase model routing** -- use a strong model for planning, a fast one for execution, a careful one for review

<br />

## Quick Start

```bash
# 1. Install prerequisites
#    - OpenCode CLI: https://github.com/opencode-ai/opencode
#    - Beads CLI:    https://github.com/steveyegge/beads
#    - Python 3.11+

# 2. Install vtinker
pip install -e .

# 3. Navigate to your project
cd /path/to/your/project

# 4. Create a config (optional -- vtinker will auto-detect most things)
mkdir -p .vtinker
cat > .vtinker/config.json << 'EOF'
{
  "checks": [
    {"name": "build", "command": "go build ./..."},
    {"name": "test",  "command": "go test ./..."}
  ]
}
EOF

# 5. Run
vtinker start
```

Or skip the interactive dialog entirely:

```bash
vtinker start --title "Add rate limiting to API" --desc "Implement token bucket rate limiter for all /api/* endpoints"
```

Or feed a spec file:

```bash
vtinker start --from epic.md
```

<br />

## How It Works

```
 DIALOG ── PREPARE ── PLAN ──┐
                              │
                    ┌─────────┘
                    │
                    ├── REFINE ── EXECUTE ── REVIEW ── FIX ──┐
                    │                                         │
                    └─────────────────────────────────────────┘
                              │
                        FINAL REVIEW
```

| Phase | What happens |
|-------|-------------|
| **DIALOG** | Model explores the codebase, formulates an epic with acceptance criteria and check commands |
| **PREPARE** | Creates a git branch (or worktree) for isolated work |
| **PLAN** | Breaks the epic into ordered, dependency-aware tasks with acceptance criteria |
| **REFINE** | Evaluates each task -- atomic tasks execute directly, complex ones get split into subtasks |
| **EXECUTE** | Model implements one task, guided by description + acceptance criteria + context of completed work |
| **REVIEW** | Model reviews the git diff against acceptance criteria; checks (build/test/lint) run automatically |
| **FIX** | If review fails, model gets the feedback + diff and fixes the issues |
| **FINAL REVIEW** | Full diff reviewed against the original epic; any gaps spawn new tasks and the loop continues |

Every phase streams output to stderr so you can watch progress in real time.

<br />

## Configuration

Place a config file at `.vtinker/config.json` (or `vtinker.json` at the project root):

```jsonc
{
  // Working directory (default: current directory)
  "workdir": ".",

  // Git branch prefix for the work branch
  "branch_prefix": "vtinker/",

  // Use a git worktree instead of switching branches
  "use_worktree": false,

  // Max fix attempts per task before giving up
  "max_retries": 10,

  // Timeout per OpenCode call in seconds
  "opencode_timeout": 900,

  // Directory containing custom prompt templates
  "prompts_dir": null,

  // Commands that must pass after each task
  "checks": [
    {"name": "build", "command": "go build ./..."},
    {"name": "test",  "command": "go test ./..."},
    {"name": "lint",  "command": "golangci-lint run"}
  ],

  // Default model for all phases
  "opencode": {
    "model": "glm-5",
    "agent": null
  },

  // Per-phase model overrides (optional)
  // Unset phases fall back to opencode.model
  "models": {
    "plan":    "glm-5",        // used for PLAN + REFINE
    "execute": "glm-4.7",     // used for EXECUTE + FIX
    "review":  "glm-5"        // used for REVIEW + FINAL REVIEW
  }
}
```

<br />

## Benchmark Results

Models tested on real-world coding tasks with vtinker orchestration:

| Model | Time | Tasks Completed | Tests Written | Fix Attempts | Quality |
|:------|-----:|:---------------:|:-------------:|:------------:|:-------:|
| GLM-5 | 30m | 8/8 | 51 | 0 | **A+** |
| GLM-4.7 | 25m | 7/7 | 74 | 1 | **A** |
| MiniMax-m2.7 | 41m | 8/8 | 22 | 1 | **B-** |
| MiniMax-m2.5 | 45m | 5/5 | 19 | 3 | **C** |
| Kimi K2.5 | DNF | - | - | - | **F** |
| Qwen3-coder | 9m | 1/1 | 3 | 1 | **D** |

> GLM-5 completed all tasks on the first try with zero fix attempts. Kimi K2.5 did not finish (doom-looped).

<br />

## Architecture

```
vtinker/
  cli.py          CLI entry point — start, resume, status commands
  orchestrator.py Main loop: phases, state machine, git integration
  config.py       Config loading (.vtinker/config.json) + state persistence
  beads.py        Thin wrapper around the bd (Beads) CLI
  opencode.py     OpenCode process management with JSONL streaming
  prompts.py      Prompt templates for every phase (overridable)
  parse.py        Structured output parser — fenced blocks, verdicts, sections
  checks.py       Run configured check commands, format results
  doom.py         Doom-loop detector (hash-based repeated failure detection)
  gitignore.py    Auto-manage .gitignore for vtinker artifacts
```

<br />

## Custom Prompts

Override any phase's prompt by placing a Markdown file in your prompts directory:

```bash
mkdir -p .vtinker/prompts
```

```
.vtinker/prompts/
  dialog.md        # Task formulation wizard
  plan.md          # Epic-to-tasks decomposition
  refine.md        # Atomic vs. split decision
  execute.md       # Implementation instructions
  review.md        # Code review criteria
  fix.md           # Fix instructions from review feedback
  final_review.md  # Full epic review
```

Each file must contain the same `{placeholder}` slots as the default templates. See [`vtinker/prompts.py`](vtinker/prompts.py) for the full list of slots per phase.

Point your config at the directory:

```json
{
  "prompts_dir": ".vtinker/prompts"
}
```

<br />

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| **Python 3.11+** | Runtime | [python.org](https://www.python.org/) |
| **OpenCode CLI** | LLM interface | [github.com/opencode-ai/opencode](https://github.com/opencode-ai/opencode) |
| **Beads CLI** (`bd`) | Issue/task tracker | [github.com/beads-project/beads](https://github.com/steveyegge/beads) |

<br />

## CLI Reference

```
vtinker start [--config PATH] [--dir PATH] [--title TEXT] [--desc TEXT] [--from FILE]
vtinker resume [EPIC_ID] [--config PATH] [--dir PATH]
vtinker status [EPIC_ID]
```

| Command | Description |
|---------|-------------|
| `start` | Begin a new vtinker session (interactive or headless) |
| `resume` | Resume an interrupted session from saved state |
| `status` | Show epic progress and task completion |

<br />

## License

[MIT](LICENSE)
