"""Tests for checks module."""
import tempfile
from pathlib import Path

from vtinker.checks import CheckResult, format_results, run_checks
from vtinker.config import Check


class TestRunChecks:
    def test_passing_check(self):
        results = run_checks(
            [Check("echo", "echo hello")],
            Path("/tmp"),
        )
        assert len(results) == 1
        assert results[0].passed
        assert results[0].exit_code == 0
        assert "hello" in results[0].stdout

    def test_failing_check(self):
        results = run_checks(
            [Check("fail", "exit 1")],
            Path("/tmp"),
        )
        assert len(results) == 1
        assert not results[0].passed
        assert results[0].exit_code == 1

    def test_multiple_checks_no_short_circuit(self):
        """All checks run even if first one fails."""
        results = run_checks(
            [
                Check("fail", "exit 1"),
                Check("pass", "echo ok"),
            ],
            Path("/tmp"),
        )
        assert len(results) == 2
        assert not results[0].passed
        assert results[1].passed

    def test_empty_checks(self):
        assert run_checks([], Path("/tmp")) == []

    def test_check_in_specific_directory(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "marker.txt").write_text("found")
            results = run_checks(
                [Check("marker", "cat marker.txt")],
                Path(d),
            )
            assert results[0].passed
            assert "found" in results[0].stdout


class TestFormatResults:
    def test_empty(self):
        assert format_results([]) == "No checks configured."

    def test_passing(self):
        result = format_results([
            CheckResult("build", "make", 0, "ok", ""),
        ])
        assert "[PASS]" in result
        assert "build" in result

    def test_failing_shows_output(self):
        result = format_results([
            CheckResult("test", "pytest", 1, "2 failed", "error trace"),
        ])
        assert "[FAIL]" in result
        assert "error trace" in result
        assert "2 failed" in result

    def test_mixed(self):
        result = format_results([
            CheckResult("build", "make", 0, "", ""),
            CheckResult("test", "pytest", 1, "fail", "err"),
        ])
        assert result.count("[PASS]") == 1
        assert result.count("[FAIL]") == 1
