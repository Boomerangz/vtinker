"""Thin wrapper around the opencode CLI."""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_DEBUG = os.environ.get("VTINKER_DEBUG", "").lower() in ("1", "true", "yes")


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _dbg(msg: str) -> None:
    if _DEBUG:
        from vtinker.colors import DEBUG, RESET
        print(f"  {DEBUG}{_ts()} opencode: {msg}{RESET}", file=sys.stderr)


@dataclass
class TokenUsage:
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache_read: int = 0
    cost: float = 0.0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input=self.input + other.input,
            output=self.output + other.output,
            reasoning=self.reasoning + other.reasoning,
            cache_read=self.cache_read + other.cache_read,
            cost=self.cost + other.cost,
        )

    @property
    def total(self) -> int:
        return self.input + self.output


class OpenCodeError(RuntimeError):
    """Error from opencode that should stop execution (not retry)."""
    pass


class BudgetExhaustedError(OpenCodeError):
    """API credits/budget exhausted — no point retrying."""
    pass


@dataclass
class RunResult:
    exit_code: int
    text: str  # concatenated text output from the model
    session_id: str | None = None
    raw_events: list[dict] = field(default_factory=list)
    tokens: TokenUsage = field(default_factory=TokenUsage)


# ---------------------------------------------------------------------------
# Callbacks for streaming progress
# ---------------------------------------------------------------------------

def default_progress(event: dict) -> None:
    """Default progress callback: print tool use, text, thinking, and token counts to stderr."""
    from vtinker.colors import (
        RESET, TOOL_CALL, TOOL_RESULT, TOOL_PATH, THINKING,
        TEXT, STEP_LINE, TOKEN_INFO, DIM, BOLD, BR_BLACK,
    )

    etype = event.get("type", "")
    part = event.get("part", {})

    if etype == "tool_use":
        state = part.get("state", {})
        tool_input = state.get("input", {})
        status = state.get("status", "")
        tool = part.get("tool", "?")

        # Show result for completed tools
        if status == "completed":
            output = state.get("output", "")
            if output and tool in ("bash", "read", "grep", "glob"):
                lines = output.strip().split("\n")
                preview = "\n".join(lines[:5])
                if len(lines) > 5:
                    preview += f"\n{TOOL_RESULT}    ... ({len(lines)} lines total){RESET}"
                print(f"  {TOOL_RESULT}← {tool}: {preview}{RESET}", file=sys.stderr)
            return

        if not tool_input:
            return

        if tool == "write":
            path = tool_input.get("filePath", tool_input.get("file_path", ""))
            content = tool_input.get("content", "")
            nlines = content.count("\n") + 1
            print(f"  {TOOL_CALL}→ {BOLD}{tool}{RESET} {TOOL_PATH}{path}{RESET} {DIM}({nlines} lines){RESET}", file=sys.stderr)
            return
        elif tool == "edit":
            path = tool_input.get("filePath", tool_input.get("file_path", ""))
            old = tool_input.get("old_string", "")[:60].replace("\n", "↵")
            new = tool_input.get("new_string", "")[:60].replace("\n", "↵")
            print(f"  {TOOL_CALL}→ {BOLD}{tool}{RESET} {TOOL_PATH}{path}{RESET}", file=sys.stderr)
            print(f"    {DIM}«{old}» → «{new}»{RESET}", file=sys.stderr)
            return

        preview = ""
        for key in ("command", "filePath", "file_path", "pattern", "content"):
            if key in tool_input:
                val = str(tool_input[key])[:120].replace("\n", " ")
                preview = f" {DIM}{val}{RESET}"
                break
        print(f"  {TOOL_CALL}→ {BOLD}{tool}{RESET}{preview}", file=sys.stderr)

    elif etype == "text":
        text = part.get("text", "")
        if text:
            print(f"{TEXT}{text}{RESET}", end="", file=sys.stderr)

    elif etype in ("thinking", "reasoning"):
        text = part.get("text", part.get("thinking", ""))
        if text:
            lines = text.strip().split("\n")
            if len(lines) <= 3:
                for line in lines:
                    print(f"  {THINKING}💭 {line}{RESET}", file=sys.stderr)
            else:
                print(f"  {THINKING}💭 {lines[0]}{RESET}", file=sys.stderr)
                print(f"  {THINKING}   ... ({len(lines)} lines){RESET}", file=sys.stderr)
                print(f"  {THINKING}💭 {lines[-1]}{RESET}", file=sys.stderr)

    elif etype == "step_start":
        print(f"  {STEP_LINE}─────────────────────────────{RESET}", file=sys.stderr)

    elif etype == "step_finish":
        tokens = part.get("tokens", {})
        total = tokens.get("total", 0)
        reasoning = tokens.get("reasoning", 0)
        cost = part.get("cost", 0)
        parts = []
        if total:
            parts.append(f"{total:,} tok")
        if reasoning:
            parts.append(f"{reasoning:,} reason")
        if cost:
            parts.append(f"${cost:.4f}")
        if parts:
            print(f"\n  {TOKEN_INFO}── {' · '.join(parts)} ──{RESET}", file=sys.stderr)


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


_BUDGET_PATTERNS = [
    "insufficient", "budget", "credit", "quota", "exceeded",
    "payment", "billing", "402", "limit reached",
    "no remaining balance", "out of credits",
]


def _check_budget_error(msg: str) -> None:
    """Raise BudgetExhaustedError if the message indicates no credits/budget."""
    msg_lower = msg.lower()
    for pattern in _BUDGET_PATTERNS:
        if pattern in msg_lower:
            raise BudgetExhaustedError(f"API budget exhausted: {msg}")


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
        cmd += ["--dir", str(workdir), "--format", "json", "--thinking", "--title", "vtinker"]
        if model:
            cmd += ["--model", model]
        if agent:
            cmd += ["--agent", agent]
        if session:
            cmd += ["--session", session]
        if files:
            for fpath in files:
                cmd += ["-f", str(fpath)]

        _dbg(f"CMD: {' '.join(cmd)}")
        _dbg(f"CWD: (inherited)  PROXY: HTTPS_PROXY={os.environ.get('HTTPS_PROXY', '<unset>')} "
             f"HTTP_PROXY={os.environ.get('HTTP_PROXY', '<unset>')}")

        # Stream stdout line-by-line for real-time progress
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        events: list[dict] = []
        text_parts: list[str] = []
        session_id: str | None = None
        usage = TokenUsage()

        def _read_stderr():
            # Drain stderr to prevent blocking
            for line in proc.stderr:
                _dbg(f"STDERR: {line.rstrip()}")

        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stderr_thread.start()

        _dbg(f"PID: {proc.pid} — waiting for stdout events...")
        lines_read = 0
        last_event_time = time.monotonic()
        watchdog_stop = threading.Event()

        def _watchdog():
            """Print heartbeat every 30s of silence so user knows it's alive."""
            while not watchdog_stop.wait(30):
                silence = time.monotonic() - last_event_time
                if silence >= 29:
                    _dbg(f"no events for {int(silence)}s (events so far: {lines_read}, pid: {proc.pid})")

        if _DEBUG:
            wd_thread = threading.Thread(target=_watchdog, daemon=True)
            wd_thread.start()

        # Read stdout line by line
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            lines_read += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                _dbg(f"JSON-PARSE-FAIL: {line[:200]}")
                continue

            events.append(event)
            last_event_time = time.monotonic()
            etype = event.get("type", "?")
            _dbg(f"EVENT #{lines_read}: type={etype}")

            # Check for error events (budget exhausted, model not found, etc.)
            if event.get("type") == "error":
                err = event.get("error", {})
                err_msg = err.get("data", {}).get("message", "") or err.get("name", "unknown error")
                _dbg(f"ERROR EVENT: {err_msg}")
                _check_budget_error(err_msg)

            if not session_id and event.get("sessionID"):
                session_id = event["sessionID"]

            if event.get("type") == "text":
                part = event.get("part", {})
                text = part.get("text", "")
                if text:
                    text_parts.append(text)

            if event.get("type") == "step_finish":
                part = event.get("part", {})
                tokens = part.get("tokens", {})
                cache = tokens.get("cache", {})
                usage += TokenUsage(
                    input=tokens.get("input", 0),
                    output=tokens.get("output", 0),
                    reasoning=tokens.get("reasoning", 0),
                    cache_read=cache.get("read", 0),
                    cost=part.get("cost", 0),
                )

            # Call progress callback
            if on_event:
                try:
                    on_event(event)
                except Exception:
                    pass  # never crash on progress callback

        watchdog_stop.set()
        _dbg(f"stdout EOF — {lines_read} events read, waiting for process...")
        proc.wait(timeout=timeout)
        _dbg(f"process exited: code={proc.returncode}")
        stderr_thread.join(timeout=5)

    except subprocess.TimeoutExpired:
        proc.kill()
        return RunResult(exit_code=-1, text="[vtinker] opencode timed out")
    finally:
        if prompt_file:
            Path(prompt_file).unlink(missing_ok=True)

    # Check for errors in non-zero exit with no text output
    if proc.returncode and not text_parts:
        # Look for error events we might have missed
        for evt in events:
            if evt.get("type") == "error":
                err = evt.get("error", {})
                err_msg = err.get("data", {}).get("message", "") or err.get("name", "")
                _check_budget_error(err_msg)

    return RunResult(
        exit_code=proc.returncode or 0,
        text="".join(text_parts),
        session_id=session_id,
        raw_events=events,
        tokens=usage,
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
