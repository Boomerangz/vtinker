"""Run configured check commands and format results."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from vtinker.config import Check


@dataclass
class CheckResult:
    name: str
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def run_checks(checks: list[Check], workdir: Path) -> list[CheckResult]:
    """Run all configured checks. Does not short-circuit."""
    results = []
    for check in checks:
        try:
            proc = subprocess.run(
                check.command,
                shell=True,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            results.append(CheckResult(
                name=check.name,
                command=check.command,
                exit_code=proc.returncode,
                stdout=proc.stdout[-2000:],
                stderr=proc.stderr[-2000:],
            ))
        except subprocess.TimeoutExpired:
            results.append(CheckResult(
                name=check.name,
                command=check.command,
                exit_code=-1,
                stdout="",
                stderr="TIMEOUT after 300s",
            ))
    return results


def format_results(results: list[CheckResult]) -> str:
    """Format check results for inclusion in prompts."""
    if not results:
        return "No checks configured."
    lines = []
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"[{status}] {r.name}: {r.command} (exit {r.exit_code})")
        if not r.passed:
            if r.stderr:
                lines.append(f"  stderr: {r.stderr[:500]}")
            if r.stdout:
                lines.append(f"  stdout: {r.stdout[:500]}")
    return "\n".join(lines)
