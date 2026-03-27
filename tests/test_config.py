"""Tests for config loading and state persistence."""
import json
import tempfile
from pathlib import Path

from vtinker.config import Check, Config, State, load_config, load_state, save_state


class TestLoadConfig:
    def test_defaults_when_no_file(self):
        config = load_config(Path("/nonexistent/vtinker.json"))
        assert config.branch_prefix == "vtinker/"
        assert config.use_worktree is False
        assert config.max_retries == 10
        assert config.checks == []
        assert config.opencode_model is None
        assert config.prompts_dir is None

    def test_load_full_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({
                "workdir": "/tmp/project",
                "branch_prefix": "auto/",
                "use_worktree": True,
                "max_retries": 5,
                "checks": [
                    {"name": "build", "command": "make build"},
                    {"name": "test", "command": "make test"},
                ],
                "opencode": {
                    "model": "anthropic/claude-sonnet",
                    "agent": "build",
                },
                "prompts_dir": "my-prompts",
            }, f)
            path = Path(f.name)

        try:
            config = load_config(path)
            assert config.branch_prefix == "auto/"
            assert config.use_worktree is True
            assert config.max_retries == 5
            assert len(config.checks) == 2
            assert config.checks[0].name == "build"
            assert config.checks[1].command == "make test"
            assert config.opencode_model == "anthropic/claude-sonnet"
            assert config.opencode_agent == "build"
            assert config.prompts_dir == Path("my-prompts")
        finally:
            path.unlink()

    def test_partial_config(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"max_retries": 10}, f)
            path = Path(f.name)

        try:
            config = load_config(path)
            assert config.max_retries == 10
            assert config.branch_prefix == "vtinker/"  # default
            assert config.checks == []  # default
        finally:
            path.unlink()


class TestState:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            state = State(
                epic_id="bd-abc123",
                workdir="/tmp/workdir",
                branch_base="deadbeef",
                checks=[
                    {"name": "build", "command": "go build"},
                    {"name": "test", "command": "go test"},
                ],
            )
            save_state(state, workdir)

            loaded = load_state(workdir)
            assert loaded is not None
            assert loaded.epic_id == "bd-abc123"
            assert loaded.workdir == "/tmp/workdir"
            assert loaded.branch_base == "deadbeef"
            assert len(loaded.checks) == 2
            assert loaded.checks[0]["name"] == "build"

    def test_load_missing_state(self):
        with tempfile.TemporaryDirectory() as d:
            assert load_state(Path(d)) is None

    def test_save_without_optional_fields(self):
        with tempfile.TemporaryDirectory() as d:
            workdir = Path(d)
            state = State(epic_id="bd-xyz", workdir="/tmp")
            save_state(state, workdir)

            loaded = load_state(workdir)
            assert loaded.epic_id == "bd-xyz"
            assert loaded.branch_base is None
            assert loaded.checks is None
