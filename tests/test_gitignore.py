"""Tests for gitignore management."""
import tempfile
from pathlib import Path

from vtinker.gitignore import VTINKER_ENTRIES, ensure_gitignore


class TestEnsureGitignore:
    def test_creates_gitignore_if_missing(self):
        with tempfile.TemporaryDirectory() as d:
            ensure_gitignore(Path(d))
            content = (Path(d) / ".gitignore").read_text()
            for entry in VTINKER_ENTRIES:
                assert entry in content

    def test_appends_to_existing(self):
        with tempfile.TemporaryDirectory() as d:
            gi = Path(d) / ".gitignore"
            gi.write_text("node_modules/\n.env\n")
            ensure_gitignore(Path(d))
            content = gi.read_text()
            assert "node_modules/" in content
            assert ".env" in content
            for entry in VTINKER_ENTRIES:
                assert entry in content

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            ensure_gitignore(Path(d))
            content1 = (Path(d) / ".gitignore").read_text()
            ensure_gitignore(Path(d))
            content2 = (Path(d) / ".gitignore").read_text()
            assert content1 == content2

    def test_no_double_newline_when_existing_ends_with_newline(self):
        with tempfile.TemporaryDirectory() as d:
            gi = Path(d) / ".gitignore"
            gi.write_text("*.pyc\n")
            ensure_gitignore(Path(d))
            content = gi.read_text()
            assert "\n\n\n" not in content

    def test_adds_newline_when_existing_doesnt_end_with_one(self):
        with tempfile.TemporaryDirectory() as d:
            gi = Path(d) / ".gitignore"
            gi.write_text("*.pyc")  # no trailing newline
            ensure_gitignore(Path(d))
            content = gi.read_text()
            assert "*.pyc\n" in content
