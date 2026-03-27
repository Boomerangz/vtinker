"""Tests for the parse module — the most critical part of vtinker."""
from vtinker.parse import (
    EpicDef,
    TaskDef,
    extract_epic,
    extract_tasks,
    extract_verdict,
    _extract_all_fenced_blocks,
    _parse_sections,
)


# -----------------------------------------------------------------------
# extract_epic
# -----------------------------------------------------------------------

class TestExtractEpic:
    def test_basic(self):
        text = """
```epic
title: Port auth service
branch: feat/auth
worktree: false

description:
Port the auth service from PHP to Go.

acceptance:
- All endpoints work
- Tests pass

checks:
- build: go build ./...
- test: go test ./...
```
"""
        epic = extract_epic(text)
        assert epic is not None
        assert epic.title == "Port auth service"
        assert epic.branch == "feat/auth"
        assert epic.worktree is False
        assert "Port the auth service" in epic.description
        assert "All endpoints work" in epic.acceptance
        assert len(epic.checks) == 2
        assert epic.checks[0].name == "build"
        assert epic.checks[0].command == "go build ./..."
        assert epic.checks[1].name == "test"

    def test_worktree_true(self):
        text = """
```epic
title: Refactor
branch: none
worktree: true

description:
Refactor things.

acceptance:
- It compiles

checks:
- build: make
```
"""
        epic = extract_epic(text)
        assert epic.worktree is True
        assert epic.branch == ""  # "none" is excluded

    def test_multiline_description(self):
        text = """
```epic
title: Complex task
branch: none
worktree: false

description:
Line one of the description.
Line two with more details.
Line three with even more context.

acceptance:
- Criterion A
- Criterion B
- Criterion C

checks:
- lint: ruff check .
```
"""
        epic = extract_epic(text)
        assert epic.description.count("\n") >= 2
        assert "Line three" in epic.description
        assert epic.acceptance.count("\n") >= 2

    def test_no_epic_block(self):
        assert extract_epic("just some text without epic block") is None

    def test_nested_code_in_description(self):
        text = """
```epic
title: Fix handler
branch: none
worktree: false

description:
The current handler looks like this:
```go
func Handle(w http.ResponseWriter) {
    w.Write([]byte("ok"))
}
```
We need to add error handling.

acceptance:
- Errors return 500
- No panics

checks:
- build: go build ./...
```
"""
        epic = extract_epic(text)
        assert epic is not None
        assert "func Handle" in epic.description
        assert "Errors return 500" in epic.acceptance

    def test_empty_checks(self):
        text = """
```epic
title: Quick fix
branch: none
worktree: false

description:
Fix a typo.

acceptance:
- Typo is fixed

checks:
```
"""
        epic = extract_epic(text)
        assert epic is not None
        assert epic.checks == []

    def test_surrounding_text_ignored(self):
        text = """
Here's what I came up with after analyzing the codebase:

```epic
title: The real epic
branch: none
worktree: false

description:
The task.

acceptance:
- Done
```

Let me know if you want changes!
"""
        epic = extract_epic(text)
        assert epic.title == "The real epic"


# -----------------------------------------------------------------------
# extract_tasks
# -----------------------------------------------------------------------

class TestExtractTasks:
    def test_single_task(self):
        text = """
```task
title: Add login endpoint
depends: none

description:
Create POST /login handler in handlers/auth.go

acceptance:
- Returns JWT on success
- Returns 401 on failure
```
"""
        tasks = extract_tasks(text)
        assert len(tasks) == 1
        assert tasks[0].title == "Add login endpoint"
        assert tasks[0].depends == []
        assert "POST /login" in tasks[0].description
        assert "JWT" in tasks[0].acceptance

    def test_multiple_tasks_with_deps(self):
        text = """
```task
title: Task A
depends: none

description:
First task.

acceptance:
- A works
```

```task
title: Task B
depends: 1

description:
Second task, depends on A.

acceptance:
- B works
```

```task
title: Task C
depends: 1, 2

description:
Third task.

acceptance:
- C works
```
"""
        tasks = extract_tasks(text)
        assert len(tasks) == 3
        assert tasks[0].depends == []
        assert tasks[1].depends == [1]
        assert tasks[2].depends == [1, 2]

    def test_atomic_flag(self):
        text = """
```task
title: Fix typo
depends: none
atomic: true

description:
Fix typo in README.md line 42.

acceptance:
- Typo fixed
```

```task
title: Implement auth
depends: none
atomic: false

description:
Full auth service.

acceptance:
- Works
```
"""
        tasks = extract_tasks(text)
        assert tasks[0].atomic is True
        assert tasks[1].atomic is False

    def test_no_tasks(self):
        assert extract_tasks("no task blocks here") == []

    def test_empty_title_skipped(self):
        text = """
```task
title:
depends: none

description:
No title provided.

acceptance:
- Something
```
"""
        assert extract_tasks(text) == []

    def test_nested_code_blocks(self):
        text = """
```task
title: Refactor handler
depends: none

description:
Change this code:
```python
def old():
    pass
```
To use the new pattern.

acceptance:
- New pattern used
- Tests pass
```
"""
        tasks = extract_tasks(text)
        assert len(tasks) == 1
        assert "def old" in tasks[0].description
        assert "New pattern used" in tasks[0].acceptance

    def test_unknown_fields_in_description(self):
        """Lines that look like 'field: value' but aren't known fields
        should be treated as content, not section headers."""
        text = """
```task
title: Handle URLs
depends: none

description:
The endpoint should support:
http: //example.com/api
ftp: //files.example.com
custom-header: X-Request-ID

acceptance:
- URLs parsed correctly
```
"""
        tasks = extract_tasks(text)
        assert len(tasks) == 1
        assert "http: //example.com" in tasks[0].description
        assert "custom-header:" in tasks[0].description


# -----------------------------------------------------------------------
# extract_verdict
# -----------------------------------------------------------------------

class TestExtractVerdict:
    def test_pass(self):
        v, d = extract_verdict("some analysis\nVERDICT: PASS\n")
        assert v == "PASS"
        assert d == ""

    def test_fail_with_issues(self):
        v, d = extract_verdict(
            "analysis\nVERDICT: FAIL\nISSUES:\n- missing error handling\n- no tests"
        )
        assert v == "FAIL"
        assert "missing error handling" in d
        assert "no tests" in d

    def test_atomic(self):
        v, _ = extract_verdict("VERDICT: ATOMIC")
        assert v == "ATOMIC"

    def test_split(self):
        v, _ = extract_verdict("VERDICT: SPLIT")
        assert v == "SPLIT"

    def test_complete(self):
        v, _ = extract_verdict("VERDICT: COMPLETE")
        assert v == "COMPLETE"

    def test_incomplete_with_missing(self):
        v, d = extract_verdict(
            "VERDICT: INCOMPLETE\nMISSING:\n- middleware\n- logging"
        )
        assert v == "INCOMPLETE"
        assert "middleware" in d

    def test_unknown_when_no_verdict(self):
        v, d = extract_verdict("no verdict in this text at all")
        assert v == "UNKNOWN"
        assert len(d) > 0  # last 500 chars as fallback

    def test_last_verdict_wins(self):
        """If model outputs multiple VERDICT lines, take the last one."""
        v, _ = extract_verdict(
            "VERDICT: FAIL\nactually wait\nVERDICT: PASS"
        )
        assert v == "PASS"

    def test_case_insensitive(self):
        v, _ = extract_verdict("Verdict: pass")
        assert v == "PASS"


# -----------------------------------------------------------------------
# _extract_all_fenced_blocks (internal, but critical)
# -----------------------------------------------------------------------

class TestFencedBlocks:
    def test_no_blocks(self):
        assert _extract_all_fenced_blocks("hello world", "task") == []

    def test_single_block(self):
        text = "before\n```task\ncontent here\n```\nafter"
        blocks = _extract_all_fenced_blocks(text, "task")
        assert len(blocks) == 1
        assert "content here" in blocks[0]

    def test_multiple_blocks(self):
        text = "```task\nA\n```\ntext\n```task\nB\n```\n"
        blocks = _extract_all_fenced_blocks(text, "task")
        assert len(blocks) == 2
        assert "A" in blocks[0]
        assert "B" in blocks[1]

    def test_nested_fences(self):
        text = """
```task
outer content
```python
inner code
```
more outer content
```
"""
        blocks = _extract_all_fenced_blocks(text, "task")
        assert len(blocks) == 1
        assert "inner code" in blocks[0]
        assert "more outer content" in blocks[0]

    def test_deeply_nested(self):
        text = """
```task
level 1
```go
func main() {
    fmt.Println("hello")
}
```
back to level 1
```bash
echo "test"
```
still level 1
```
"""
        blocks = _extract_all_fenced_blocks(text, "task")
        assert len(blocks) == 1
        assert "func main" in blocks[0]
        assert 'echo "test"' in blocks[0]
        assert "still level 1" in blocks[0]

    def test_different_block_types_ignored(self):
        text = "```epic\nepic content\n```\n```task\ntask content\n```\n"
        blocks = _extract_all_fenced_blocks(text, "task")
        assert len(blocks) == 1
        assert "task content" in blocks[0]

    def test_unterminated_block(self):
        text = "```task\ncontent without closing fence"
        blocks = _extract_all_fenced_blocks(text, "task")
        assert len(blocks) == 1
        assert "content without closing fence" in blocks[0]


# -----------------------------------------------------------------------
# _parse_sections (internal, but critical)
# -----------------------------------------------------------------------

class TestParseSections:
    def test_single_line_fields(self):
        s = _parse_sections("title: Hello\ndepends: none\n")
        assert s["title"] == "Hello"
        assert s["depends"] == "none"

    def test_multiline_field(self):
        s = _parse_sections("description:\nline 1\nline 2\nline 3\n")
        assert "line 1" in s["description"]
        assert "line 3" in s["description"]

    def test_mixed_fields(self):
        s = _parse_sections(
            "title: My Task\ndescription:\nDo something.\nMore details.\n\nacceptance:\n- A\n- B\n"
        )
        assert s["title"] == "My Task"
        assert "More details" in s["description"]
        assert "- B" in s["acceptance"]

    def test_unknown_field_names_ignored(self):
        s = _parse_sections("title: X\nfoo: bar\nbaz: qux\n")
        assert s["title"].startswith("X")
        assert "foo" not in s
        # "foo: bar" is part of title's continuation
        assert "foo: bar" in s["title"]
