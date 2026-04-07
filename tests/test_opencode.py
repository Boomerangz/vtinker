"""Tests for opencode wrapper — unit tests with mocked subprocess."""
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from vtinker.opencode import (
    RunResult,
    NetworkTimeoutError,
    default_progress,
    is_network_timeout,
    verbose_progress,
    run,
)


class TestDefaultProgress:
    """Test that callbacks don't crash on various event shapes."""

    def test_tool_use_running(self, capsys):
        event = {
            "type": "tool_use",
            "part": {
                "tool": "read",
                "state": {
                    "status": "running",
                    "input": {"filePath": "/tmp/test.py"},
                },
            },
        }
        default_progress(event)
        captured = capsys.readouterr()
        assert "read" in captured.err
        assert "/tmp/test.py" in captured.err

    def test_tool_use_completed_skipped(self, capsys):
        event = {
            "type": "tool_use",
            "part": {
                "tool": "read",
                "state": {
                    "status": "completed",
                    "input": {"filePath": "/tmp/test.py"},
                },
            },
        }
        default_progress(event)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_tool_use_empty_input_skipped(self, capsys):
        event = {"type": "tool_use", "part": {"tool": "read", "state": {}}}
        default_progress(event)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_step_finish_with_tokens(self, capsys):
        event = {
            "type": "step_finish",
            "part": {"tokens": {"total": 5000}},
        }
        default_progress(event)
        captured = capsys.readouterr()
        assert "5,000" in captured.err or "5000" in captured.err

    def test_unknown_event_no_crash(self):
        default_progress({"type": "unknown_type", "part": {}})
        default_progress({})
        default_progress({"type": "text"})  # no part


class TestVerboseProgress:
    def test_text_streaming(self, capsys):
        verbose_progress({
            "type": "text",
            "part": {"text": "Hello from model"},
        })
        captured = capsys.readouterr()
        assert "Hello from model" in captured.err

    def test_step_finish_newline(self, capsys):
        verbose_progress({"type": "step_finish", "part": {}})
        captured = capsys.readouterr()
        assert captured.err == "\n"


class TestIsNetworkTimeout:
    """Test network timeout detection logic."""

    def test_classic_network_timeout(self):
        """exit=-9, no text, no events => network timeout."""
        result = RunResult(exit_code=-9, text="", raw_events=[])
        assert is_network_timeout(result) is True

    def test_network_timeout_few_events(self):
        """exit=-9, no text, 1-2 events (e.g. session start) => still network timeout."""
        result = RunResult(exit_code=-9, text="", raw_events=[{"type": "session_start"}])
        assert is_network_timeout(result) is True

        result2 = RunResult(exit_code=-9, text="", raw_events=[
            {"type": "session_start"},
            {"type": "step_start"},
        ])
        assert is_network_timeout(result2) is True

    def test_model_timeout_with_text(self):
        """exit=-9, has text output => model was working, NOT network timeout."""
        result = RunResult(exit_code=-9, text="Some model output here", raw_events=[
            {"type": "text", "part": {"text": "Some model output here"}},
        ])
        assert is_network_timeout(result) is False

    def test_model_timeout_with_events(self):
        """exit=-9, no text, but many events => model was working, NOT network timeout."""
        events = [{"type": "tool_use"} for _ in range(5)]
        result = RunResult(exit_code=-9, text="", raw_events=events)
        assert is_network_timeout(result) is False

    def test_model_timeout_with_3_events(self):
        """exit=-9, no text, exactly 3 events => NOT network timeout (threshold is < 3)."""
        events = [{"type": "step_start"}, {"type": "tool_use"}, {"type": "step_finish"}]
        result = RunResult(exit_code=-9, text="", raw_events=events)
        assert is_network_timeout(result) is False

    def test_normal_exit_not_network_timeout(self):
        """exit=0 => never a network timeout, regardless of other fields."""
        result = RunResult(exit_code=0, text="", raw_events=[])
        assert is_network_timeout(result) is False

    def test_other_error_exit_not_network_timeout(self):
        """exit=1 (generic error) => not network timeout."""
        result = RunResult(exit_code=1, text="", raw_events=[])
        assert is_network_timeout(result) is False

    def test_whitespace_text_is_empty(self):
        """exit=-9, whitespace-only text => network timeout (text.strip() is empty)."""
        result = RunResult(exit_code=-9, text="  \n  ", raw_events=[])
        assert is_network_timeout(result) is True

    def test_exception_class_hierarchy(self):
        """NetworkTimeoutError is a subclass of OpenCodeError."""
        from vtinker.opencode import OpenCodeError
        assert issubclass(NetworkTimeoutError, OpenCodeError)
        err = NetworkTimeoutError("test")
        assert isinstance(err, OpenCodeError)
        assert isinstance(err, RuntimeError)
