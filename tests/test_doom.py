"""Tests for doom-loop detector."""
from vtinker.doom import DoomDetector


class TestDoomDetector:
    def test_not_looping_initially(self):
        d = DoomDetector(threshold=3)
        assert not d.is_looping()

    def test_not_looping_below_threshold(self):
        d = DoomDetector(threshold=3)
        d.record("task-1", "error A")
        d.record("task-1", "error A")
        assert not d.is_looping()

    def test_looping_at_threshold(self):
        d = DoomDetector(threshold=3)
        d.record("task-1", "error A")
        d.record("task-1", "error A")
        d.record("task-1", "error A")
        assert d.is_looping()

    def test_not_looping_different_errors(self):
        d = DoomDetector(threshold=3)
        d.record("task-1", "error A")
        d.record("task-1", "error B")
        d.record("task-1", "error A")
        assert not d.is_looping()

    def test_not_looping_different_tasks(self):
        d = DoomDetector(threshold=3)
        d.record("task-1", "error A")
        d.record("task-2", "error A")
        d.record("task-1", "error A")
        assert not d.is_looping()

    def test_reset(self):
        d = DoomDetector(threshold=3)
        d.record("t", "e")
        d.record("t", "e")
        d.record("t", "e")
        assert d.is_looping()
        d.reset()
        assert not d.is_looping()

    def test_looping_after_non_looping(self):
        """Doom detected when the LAST N entries repeat."""
        d = DoomDetector(threshold=2)
        d.record("t1", "ok")
        d.record("t2", "fail")
        d.record("t2", "fail")
        assert d.is_looping()

    def test_threshold_1(self):
        d = DoomDetector(threshold=1)
        d.record("t", "e")
        assert d.is_looping()

    def test_high_threshold(self):
        d = DoomDetector(threshold=5)
        for _ in range(4):
            d.record("t", "e")
        assert not d.is_looping()
        d.record("t", "e")
        assert d.is_looping()
