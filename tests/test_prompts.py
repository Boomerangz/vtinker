"""Tests for prompt template loading."""
import tempfile
from pathlib import Path

from vtinker.prompts import load_prompts, DIALOG, PLAN, EXECUTE, REVIEW, FIX, FINAL_REVIEW, REFINE


class TestLoadPrompts:
    def test_defaults(self):
        prompts = load_prompts()
        assert len(prompts) == 9
        assert prompts["dialog"] == DIALOG
        assert prompts["plan"] == PLAN
        assert prompts["execute"] == EXECUTE
        assert prompts["review"] == REVIEW
        assert prompts["fix"] == FIX
        assert prompts["final_review"] == FINAL_REVIEW
        assert prompts["refine"] == REFINE

    def test_override_single_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            override = Path(d) / "execute.md"
            override.write_text("Custom execute prompt: {task_title}")

            prompts = load_prompts(Path(d))
            assert prompts["execute"] == "Custom execute prompt: {task_title}"
            # Others unchanged
            assert prompts["plan"] == PLAN
            assert prompts["review"] == REVIEW

    def test_override_multiple_prompts(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "plan.md").write_text("Custom plan")
            (Path(d) / "review.md").write_text("Custom review")

            prompts = load_prompts(Path(d))
            assert prompts["plan"] == "Custom plan"
            assert prompts["review"] == "Custom review"
            assert prompts["execute"] == EXECUTE  # unchanged

    def test_nonexistent_dir(self):
        prompts = load_prompts(Path("/nonexistent/dir"))
        assert prompts["dialog"] == DIALOG  # falls back to defaults

    def test_prompts_have_required_slots(self):
        """Verify default prompts contain expected format slots."""
        assert "{epic_title}" in PLAN
        assert "{task_title}" in EXECUTE
        assert "{acceptance}" in REVIEW
        assert "{git_diff}" in REVIEW
        assert "{check_results}" in REVIEW
        assert "{review_feedback}" in FIX
        assert "{full_diff}" in FINAL_REVIEW
