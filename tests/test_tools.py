"""Offline tests for the project tools. Run with:  python -m pytest -q"""

import shutil
import subprocess

import pytest

from project_context_mcp.tools import ProjectTools, ToolError


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "demo"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "node_modules" / "junk").mkdir(parents=True)
    (root / "src" / "app.py").write_text(
        "def add(a, b):\n    return a + b\n\n# TODO: handle floats\n", encoding="utf-8")
    (root / "tests" / "test_app.py").write_text(
        "from src.app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8")
    (root / "node_modules" / "junk" / "x.js").write_text("TODO ignored", encoding="utf-8")
    (root / "image.bin").write_bytes(b"\x00\x01\x02binary")
    return root


def test_read_only_by_default(project):
    tools = ProjectTools(project)
    with pytest.raises(ToolError, match="turned off"):
        tools.write_file("new.txt", "hi")
    with pytest.raises(ToolError, match="turned off"):
        tools.run_tests()


def test_paths_cannot_escape_the_project(project, tmp_path):
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")
    tools = ProjectTools(project)
    with pytest.raises(ToolError, match="outside the project"):
        tools.read_file("../secret.txt")
    with pytest.raises(ToolError, match="outside the project"):
        tools.read_file(str(tmp_path / "secret.txt"))


def test_project_tree_skips_ignored_folders(project):
    out = ProjectTools(project).project_tree()
    assert "src/" in out and "app.py" in out
    assert "node_modules" not in out


def test_read_file_numbers_lines_and_pages(project):
    out = ProjectTools(project).read_file("src/app.py", start_line=2, max_lines=2)
    assert "    2 |     return a + b" in out
    assert "showing lines 2-3 of 4" in out


def test_read_file_refuses_binary(project):
    with pytest.raises(ToolError, match="binary"):
        ProjectTools(project).read_file("image.bin")


def test_search_finds_code_and_skips_ignored(project):
    out = ProjectTools(project).search_code(r"def \w+")
    assert "src/app.py:1: def add(a, b):" in out
    assert "node_modules" not in out


def test_search_rejects_bad_regex(project):
    with pytest.raises(ToolError, match="Invalid regular expression"):
        ProjectTools(project).search_code("(unclosed")


def test_find_todos(project):
    out = ProjectTools(project).find_todos()
    assert "TODO: handle floats" in out
    assert "ignored" not in out


def test_find_files_by_glob(project):
    out = ProjectTools(project).find_files("test_*.py")
    assert out == "tests/test_app.py"


def test_file_stats_counts(project):
    out = ProjectTools(project).file_stats()
    assert ".py" in out and "TOTAL" in out


def test_write_file_when_enabled(project):
    tools = ProjectTools(project, allow_writes=True)
    tools.write_file("docs/notes.md", "# Notes\n")
    assert (project / "docs" / "notes.md").read_text(encoding="utf-8") == "# Notes\n"
    with pytest.raises(ToolError, match="already exists"):
        tools.write_file("docs/notes.md", "changed")
    tools.write_file("docs/notes.md", "changed", overwrite=True)
    assert (project / "docs" / "notes.md").read_text(encoding="utf-8") == "changed"


def test_write_file_cannot_touch_git_folder(project):
    (project / ".git").mkdir()
    with pytest.raises(ToolError, match=r"\.git"):
        ProjectTools(project, allow_writes=True).write_file(".git/config", "x", overwrite=True)


def test_run_tests_when_enabled(project):
    out = ProjectTools(project, allow_tests=True).run_tests()
    assert "exit code 0" in out


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_tools_on_a_real_repo(project):
    env_cmds = [
        ["git", "init", "-q"],
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", "add", "-A"],
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", "commit", "-q", "-m", "first commit"],
    ]
    for cmd in env_cmds:
        subprocess.run(cmd, cwd=project, check=True, capture_output=True)
    tools = ProjectTools(project)
    assert "first commit" in tools.git_log()
    (project / "src" / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    assert "app.py" in tools.git_status()
    assert "return a - b" in tools.git_diff("src/app.py")
