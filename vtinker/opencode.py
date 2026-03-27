"""Thin wrapper around the opencode CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class RunResult:
    exit_code: int
    text: str  # concatenated text output from the model
    session_id: str | None = None
    raw_events: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Callbacks for streaming progress
# ---------------------------------------------------------------------------

def default_progress(event: dict) -> None:
    """Default progress callback: print tool use, text, and token counts to stderr."""
    etype = event.get("type", "")
    part = event.get("part", {})

    if etype == "tool_use":
        state = part.get("state", {})
        tool_input = state.get("input", {})
        if not tool_input or state.get("status") == "completed":
            return
        tool = part.get("tool", "?")
        preview = ""
        for key in ("command", "filePath", "file_path", "pattern", "content"):
            if key in tool_input:
                val = str(tool_input[key])[:80].replace("\n", " ")
                preview = f" {val}"
                break
        print(f"  -> {tool}{preview}", file=sys.stderr)

    elif etype == "text":
        text = part.get("text", "")
        if text:
            print(text, end="", file=sys.stderr)

    elif etype == "step_finish":
        tokens = part.get("tokens", {})
        total = tokens.get("total", 0)
        if total:
            print(f"\n  ({total} tokens)", file=sys.stderr)


def verbose_progress(event: dict) -> None:
    """Verbose progress: stream full text output and tool calls to stderr."""
    etype = event.get("type", "")
    part = event.get("part", {})

    if etype == "tool_use":
        state = part.get("state", {})
        tool_input = state.get("input", {})
        if not tool_input or state.get("status") == "completed":
            return
        tool = part.get("tool", "?")
        preview = ""
        for key in ("command", "filePath", "file_path", "pattern"):
            if key in tool_input:
                val = str(tool_input[key])[:80]
                preview = f" {key}={val}"
                break
        print(f"  -> {tool}{preview}", file=sys.stderr)

    elif etype == "text":
        text = part.get("text", "")
        if text:
            print(text, end="", file=sys.stderr)

    elif etype == "step_finish":
        print(file=sys.stderr)  # newline after streamed text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(
    prompt: str,
    workdir: Path,
    model: str | None = None,
    agent: str | None = None,
    files: list[Path] | None = None,
    timeout: int = 600,
    session: str | None = None,
    on_event: Callable[[dict], None] | None = default_progress,
) -> RunResult:
    """Run opencode with a prompt. Streams JSONL events, returns parsed result.

    If on_event is provided, each parsed event is passed to it in real-time
    (from a reader thread). This gives the user visibility into what the
    agent is doing.
    """
    prompt_file: str | None = None
    if len(prompt) > 4000:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, prefix="vtinker-prompt-",
        ) as f:
            f.write(prompt)
            prompt_file = f.name

    try:
        cmd = ["opencode", "run"]
        if prompt_file:
            cmd += ["Execute the task described in the attached file.", "-f", prompt_file]
        else:
            cmd.append(prompt)
        cmd += ["--dir", str(workdir), "--format", "json"]
        if model:
            cmd += ["--model", model]
        if agent:
            cmd += ["--agent", agent]
        if session:
            cmd += ["--session", session]
        if files:
            for fpath in files:
                cmd += ["-f", str(fpath)]

        # Stream stdout line-by-line for real-time progress
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        events: list[dict] = []
        text_parts: list[str] = []
        session_id: str | None = None

        def _read_stderr():
            # Drain stderr to prevent blocking
            for _ in proc.stderr:
                pass

        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stderr_thread.start()

        # Read stdout line by line
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            events.append(event)

            if not session_id and event.get("sessionID"):
                session_id = event["sessionID"]

            if event.get("type") == "text":
                part = event.get("part", {})
                text = part.get("text", "")
                if text:
                    text_parts.append(text)

            # Call progress callback
            if on_event:
                try:
                    on_event(event)
                except Exception:
                    pass  # never crash on progress callback

        proc.wait(timeout=timeout)
        stderr_thread.join(timeout=5)

    except subprocess.TimeoutExpired:
        proc.kill()
        return RunResult(exit_code=-1, text="[vtinker] opencode timed out")
    finally:
        if prompt_file:
            Path(prompt_file).unlink(missing_ok=True)

    return RunResult(
        exit_code=proc.returncode or 0,
        text="".join(text_parts),
        session_id=session_id,
        raw_events=events,
    )


def run_interactive(
    prompt: str,
    workdir: Path,
    model: str | None = None,
) -> RunResult:
    """Run opencode interactively (user sees and controls the session).

    Uses --format json to capture the session ID while still showing
    output to the user via the verbose_progress callback piped to stderr.

    The user won't be able to interact (type messages), but they'll see
    the full agent output. For the DIALOG phase, this means the wizard
    prompt must be self-contained enough to produce the ```epic block
    in one shot. If interactive dialog is needed, we fall back to
    running without --format json and skip session continuation.
    """
    prompt_file: str | None = None
    if len(prompt) > 4000:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, prefix="vtinker-dialog-",
        ) as f:
            f.write(prompt)
            prompt_file = f.name

    try:
        cmd = ["opencode", "run"]
        if prompt_file:
            cmd += ["Execute the task described in the attached file.", "-f", prompt_file]
        else:
            cmd.append(prompt)
        cmd += ["--dir", str(workdir)]
        if model:
            cmd += ["--model", model]

        # Interactive: inherited stdio, user can type
        proc = subprocess.run(cmd)
    finally:
        if prompt_file:
            Path(prompt_file).unlink(missing_ok=True)

    # We can't get the session ID from interactive mode.
    # The caller must handle this (e.g., re-run non-interactively).
    return RunResult(exit_code=proc.returncode, text="")


def run_captured(
    prompt: str,
    workdir: Path,
    model: str | None = None,
    files: list[Path] | None = None,
    timeout: int = 600,
) -> RunResult:
    """Run opencode non-interactively with streaming output to stderr.

    Combines capturing (for parsing) with visibility (for the user).
    Used by DIALOG when we need both the epic block AND user visibility.
    """
    return run(
        prompt, workdir, model=model, files=files,
        timeout=timeout, on_event=verbose_progress,
    )
