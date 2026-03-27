"""Tests for opencode wrapper — unit tests with mocked subprocess."""
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from vtinker.opencode import (
    RunResult,
    default_progress,
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
        assert "5000" in captured.err

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
