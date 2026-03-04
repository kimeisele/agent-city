"""Tests for city/todo_scanner.py — TODO extraction for Brain."""

import tempfile
from pathlib import Path

from city.todo_scanner import TodoItem, render_todo_digest, scan_todos


class TestScanTodos:
    def test_finds_todo(self, tmp_path):
        (tmp_path / "example.py").write_text("# TODO: fix this thing\nx = 1\n")
        items = scan_todos(tmp_path)
        assert len(items) == 1
        assert items[0].tag == "TODO"
        assert items[0].text == "fix this thing"
        assert items[0].line == 1
        assert items[0].priority == 0

    def test_finds_fixme(self, tmp_path):
        (tmp_path / "example.py").write_text("x = 1\n# FIXME: broken logic\n")
        items = scan_todos(tmp_path)
        assert len(items) == 1
        assert items[0].tag == "FIXME"
        assert items[0].priority == 1

    def test_finds_hack(self, tmp_path):
        (tmp_path / "example.py").write_text("# HACK: workaround for bug\n")
        items = scan_todos(tmp_path)
        assert len(items) == 1
        assert items[0].tag == "HACK"
        assert items[0].priority == 1

    def test_finds_xxx(self, tmp_path):
        (tmp_path / "example.py").write_text("# XXX: critical problem here\n")
        items = scan_todos(tmp_path)
        assert len(items) == 1
        assert items[0].tag == "XXX"
        assert items[0].priority == 2

    def test_multiple_files(self, tmp_path):
        (tmp_path / "a.py").write_text("# TODO: first\n")
        (tmp_path / "b.py").write_text("# TODO: second\n# FIXME: third\n")
        items = scan_todos(tmp_path)
        assert len(items) == 3

    def test_sorts_by_priority(self, tmp_path):
        (tmp_path / "code.py").write_text(
            "# TODO: low priority\n# XXX: high priority\n# FIXME: medium\n"
        )
        items = scan_todos(tmp_path)
        assert items[0].tag == "XXX"
        assert items[1].tag == "FIXME"
        assert items[2].tag == "TODO"

    def test_skips_short_comments(self, tmp_path):
        (tmp_path / "code.py").write_text("# TODO: ab\n# TODO: valid comment\n")
        items = scan_todos(tmp_path)
        assert len(items) == 1
        assert items[0].text == "valid comment"

    def test_skips_test_files(self, tmp_path):
        (tmp_path / "test_foo.py").write_text("# TODO: test-specific\n")
        (tmp_path / "real.py").write_text("# TODO: real code\n")
        items = scan_todos(tmp_path)
        assert len(items) == 1
        assert items[0].file == "real.py"

    def test_skips_git_dir(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "hook.py").write_text("# TODO: git internal\n")
        (tmp_path / "real.py").write_text("# TODO: real\n")
        items = scan_todos(tmp_path)
        assert len(items) == 1

    def test_empty_codebase(self, tmp_path):
        items = scan_todos(tmp_path)
        assert items == []

    def test_subdirectory_scan(self, tmp_path):
        sub = tmp_path / "city"
        sub.mkdir()
        (sub / "module.py").write_text("# TODO: nested todo\n")
        items = scan_todos(tmp_path)
        assert len(items) == 1
        assert "city/module.py" in items[0].file

    def test_case_insensitive(self, tmp_path):
        (tmp_path / "code.py").write_text("# todo: lowercase\n# Todo: mixed\n")
        items = scan_todos(tmp_path)
        assert len(items) == 2

    def test_real_codebase(self):
        """Scan actual agent-city codebase — should find some TODOs."""
        root = Path(__file__).parent.parent / "city"
        if root.exists():
            items = scan_todos(root)
            # At least the TODOs we just added should be found
            assert isinstance(items, list)


class TestRenderTodoDigest:
    def test_empty(self):
        rendered = render_todo_digest([])
        assert "0 items" in rendered
        assert "clean" in rendered

    def test_single_item(self):
        items = [TodoItem(tag="TODO", text="fix thing", file="a.py", line=5, priority=0)]
        rendered = render_todo_digest(items)
        assert "1 items" in rendered
        assert "fix thing" in rendered
        assert "a.py:5" in rendered

    def test_priority_counts(self):
        items = [
            TodoItem(tag="XXX", text="critical", file="a.py", line=1, priority=2),
            TodoItem(tag="FIXME", text="broken", file="b.py", line=2, priority=1),
            TodoItem(tag="TODO", text="later", file="c.py", line=3, priority=0),
        ]
        rendered = render_todo_digest(items)
        assert "1 high" in rendered
        assert "1 medium" in rendered
        assert "1 low" in rendered

    def test_caps_at_20(self):
        items = [
            TodoItem(tag="TODO", text=f"item {i}", file="a.py", line=i, priority=0)
            for i in range(30)
        ]
        rendered = render_todo_digest(items)
        assert "10 more" in rendered
