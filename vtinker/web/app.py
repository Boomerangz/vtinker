"""FastAPI web application for vtinker monitoring dashboard."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from vtinker.web.monitor import (
    RunInfo, discover_runs, parse_run, tail_log, read_output_log,
)

app = FastAPI(title="vtinker", docs_url=None, redoc_url=None)

# Paths
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["basename"] = lambda p: Path(p).name if p else ""

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# State: tracked run directories
_tracked_dirs: list[Path] = []
_running_processes: dict[str, subprocess.Popen] = {}


def set_search_dirs(dirs: list[Path]) -> None:
    """Set directories to search for vtinker runs."""
    global _tracked_dirs
    _tracked_dirs = dirs


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    runs = discover_runs(_tracked_dirs)
    # Also check for running processes we launched
    for workdir, proc in list(_running_processes.items()):
        if proc.poll() is not None:
            del _running_processes[workdir]
    return templates.TemplateResponse(request, "dashboard.html", {
        "runs": runs,
        "running_pids": {k: v.pid for k, v in _running_processes.items()},
    })


@app.get("/run/{workdir:path}", response_class=HTMLResponse)
async def run_detail(request: Request, workdir: str):
    path = Path(workdir)
    if not path.exists():
        return RedirectResponse("/")
    run = parse_run(path)
    output_lines = read_output_log(path, last_n=200)
    is_running = workdir in _running_processes and _running_processes[workdir].poll() is None
    return templates.TemplateResponse(request, "run_detail.html", {
        "run": run,
        "output_lines": output_lines,
        "is_running": is_running,
    })


@app.get("/new", response_class=HTMLResponse)
async def new_run_page(request: Request):
    return templates.TemplateResponse(request, "new_run.html")


@app.post("/api/start")
async def start_run(
    workdir: str = Form(...),
    epic_text: str = Form(""),
    epic_file: str = Form(""),
    plan_model: str = Form("openrouter/deepseek-v3.2"),
    execute_model: str = Form(""),
    review_model: str = Form(""),
):
    """Start a new vtinker run."""
    path = Path(workdir).resolve()
    path.mkdir(parents=True, exist_ok=True)

    execute_model = execute_model or plan_model
    review_model = review_model or plan_model

    # Create .vtinker/config.json
    vtinker_dir = path / ".vtinker"
    vtinker_dir.mkdir(exist_ok=True)

    config = {
        "max_retries": 10,
        "opencode_timeout": 900,
        "checks": [],
        "opencode": {"model": plan_model},
        "models": {
            "plan": plan_model,
            "execute": execute_model,
            "review": review_model,
        },
    }
    with open(vtinker_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    # Write epic if provided as text
    epic_path = None
    if epic_text.strip():
        epic_path = path / "epic.md"
        epic_path.write_text(epic_text)
    elif epic_file.strip():
        epic_path = Path(epic_file)

    # Init git if needed
    if not (path / ".git").exists():
        subprocess.run(["git", "init"], cwd=path, capture_output=True)

    # Build vtinker command
    cmd = [sys.executable, "-c",
           "import sys; sys.path.insert(0, '.'); "
           "from vtinker.cli import main; "
           f"sys.argv = ['vtinker', 'start', '--dir', '{path}'"
           + (f", '--from', '{epic_path}'" if epic_path else "")
           + "]; main()"]

    # Launch vtinker as subprocess
    log_file = open(path / "output.log", "w")
    proc = subprocess.Popen(
        cmd,
        cwd=str(Path(__file__).parent.parent.parent),  # vtinker repo root
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    _running_processes[str(path)] = proc

    # Add to tracked dirs if parent not already tracked
    parent = path.parent
    if parent not in _tracked_dirs:
        _tracked_dirs.append(parent)

    return RedirectResponse(f"/run/{path}", status_code=303)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/runs")
async def api_list_runs():
    runs = discover_runs(_tracked_dirs)
    return [_run_to_dict(r) for r in runs]


@app.get("/api/run/{workdir:path}")
async def api_run_detail(workdir: str):
    path = Path(workdir)
    if not path.exists():
        return {"error": "not found"}
    run = parse_run(path)
    return _run_to_dict(run)


@app.get("/api/run/{workdir:path}/output")
async def api_run_output(workdir: str, lines: int = 100):
    path = Path(workdir)
    output = read_output_log(path, last_n=lines)
    return {"lines": output}


# ---------------------------------------------------------------------------
# WebSocket for real-time updates
# ---------------------------------------------------------------------------

@app.websocket("/ws/run/{workdir:path}")
async def ws_run(websocket: WebSocket, workdir: str):
    await websocket.accept()
    path = Path(workdir)
    log_file = path / ".vtinker" / "log.jsonl"
    last_line = 0
    last_output_size = 0

    try:
        while True:
            # Check for new log entries
            if log_file.exists():
                new_events = tail_log(log_file, from_line=last_line)
                if new_events:
                    last_line += len(new_events)
                    run = parse_run(path)
                    await websocket.send_json({
                        "type": "state",
                        "run": _run_to_dict(run),
                    })

            # Check for new output lines
            output_file = path / "output.log"
            if output_file.exists():
                try:
                    size = output_file.stat().st_size
                    if size != last_output_size:
                        last_output_size = size
                        lines = read_output_log(path, last_n=50)
                        await websocket.send_json({
                            "type": "output",
                            "lines": lines[-20:],
                        })
                except OSError:
                    pass

            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_to_dict(run: RunInfo) -> dict:
    return {
        "workdir": run.workdir,
        "epic_id": run.epic_id,
        "epic_title": run.epic_title or Path(run.workdir).name,
        "status": run.status,
        "total_tasks": run.total_tasks,
        "done_tasks": run.done_tasks,
        "fix_count": run.fix_count,
        "replan_count": run.replan_count,
        "tokens_total": run.tokens_total,
        "cost": run.cost,
        "start_time": run.start_time,
        "current_task": run.current_task,
        "models": run.models,
        "tasks": {
            tid: {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "fix_attempts": t.fix_attempts,
            }
            for tid, t in run.tasks.items()
        },
    }
