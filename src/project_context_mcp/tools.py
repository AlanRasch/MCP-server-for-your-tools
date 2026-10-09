"""Developer tools that operate on one project folder.

These are plain Python methods so they can be tested without starting a server.
The MCP layer in server.py exposes them to AI assistants.

Safety rules:
  * every path must stay inside the project root (symlinks are followed and checked)
  * read-only tools are always available
  * writing files and running tests are OFF unless explicitly enabled
  * git is only used for read-only commands (status, log, diff)
  * no shell is used: commands are passed as argument lists
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea", ".vscode",
}
MAX_READ_BYTES = 300_000         # largest file read in one go
MAX_SEARCH_FILE_BYTES = 1_000_000
MAX_OUTPUT_CHARS = 20_000        # longer outputs are cut so they fit in an AI context
MAX_WRITE_BYTES = 500_000
TODO_PATTERN = r"\b(TODO|FIXME|HACK|XXX)\b"


class ToolError(Exception):
    """A problem the caller should see as a plain message."""


def _clip(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... (output cut at {limit} characters)"


class ProjectTools:
    def __init__(self, root: str | Path, allow_writes: bool = False, allow_tests: bool = False,
                 test_timeout: int = 120):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"Project folder does not exist: {self.root}")
        self.allow_writes = allow_writes
        self.allow_tests = allow_tests
        self.test_timeout = test_timeout

    # ------------------------------------------------------------ helpers
    def _resolve(self, path: str = ".") -> Path:
        target = (self.root / (path or ".")).resolve()
        if target != self.root and self.root not in target.parents:
            raise ToolError(f"'{path}' is outside the project folder.")
        return target

    def _rel(self, target: Path) -> str:
        return target.relative_to(self.root).as_posix() or "."

    def _walk_files(self, start: Path):
        """Yield every file under `start`, skipping ignored folders and links that leave the project."""
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and not d.endswith(".egg-info"))
            for name in sorted(filenames):
                p = Path(dirpath) / name
                try:
                    p.resolve().relative_to(self.root)
                except ValueError:
                    continue  # symlink pointing outside the project
                yield p

    @staticmethod
    def _is_text(p: Path) -> bool:
        try:
            with p.open("rb") as f:
                return b"\0" not in f.read(2048)
        except OSError:
            return False

    def _git(self, args: list[str], timeout: int = 20) -> str:
        git = shutil.which("git")
        if not git:
            raise ToolError("git is not installed or not on the PATH.")
        proc = subprocess.run([git, *args], cwd=self.root, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise ToolError((proc.stderr or proc.stdout).strip() or "git command failed.")
        return _clip(proc.stdout.strip()) or "(no output)"

    # ------------------------------------------------------------ read-only tools
    def project_tree(self, path: str = ".", max_depth: int = 3) -> str:
        start = self._resolve(path)
        if not start.is_dir():
            raise ToolError(f"'{path}' is not a folder.")
        max_depth = max(1, min(int(max_depth), 8))
        lines: list[str] = [f"{self._rel(start)}/"]

        def add(folder: Path, depth: int) -> None:
            if depth > max_depth or len(lines) > 400:
                return
            entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            for entry in entries:
                if entry.name in IGNORED_DIRS or entry.is_symlink():
                    continue
                indent = "  " * depth
                if entry.is_dir():
                    lines.append(f"{indent}{entry.name}/")
                    add(entry, depth + 1)
                else:
                    lines.append(f"{indent}{entry.name}")

        add(start, 1)
        if len(lines) > 400:
            lines.append("... (tree cut; use a smaller path or max_depth)")
        return "\n".join(lines)

    def file_stats(self) -> str:
        files: Counter[str] = Counter()
        lines_by_ext: Counter[str] = Counter()
        total_files = 0
        for p in self._walk_files(self.root):
            total_files += 1
            ext = p.suffix.lower() or "(no extension)"
            files[ext] += 1
            if p.stat().st_size <= MAX_SEARCH_FILE_BYTES and self._is_text(p):
                with p.open("rb") as f:
                    lines_by_ext[ext] += sum(1 for _ in f)
        if not total_files:
            return "No files found."
        rows = [f"{'type':<16}{'files':>8}{'lines':>10}"]
        for ext, n in files.most_common(15):
            rows.append(f"{ext:<16}{n:>8}{lines_by_ext[ext]:>10}")
        rows.append(f"{'TOTAL':<16}{total_files:>8}{sum(lines_by_ext.values()):>10}")
        return "\n".join(rows)

    def read_file(self, path: str, start_line: int = 1, max_lines: int = 300) -> str:
        target = self._resolve(path)
        if not target.is_file():
            raise ToolError(f"'{path}' is not a file.")
        if target.stat().st_size > MAX_READ_BYTES * 3:
            raise ToolError("File is too large to read in one go.")
        if not self._is_text(target):
            raise ToolError("File looks like binary data and cannot be shown as text.")
        start_line = max(1, int(start_line))
        max_lines = max(1, min(int(max_lines), 1000))
        text = target.read_bytes()[:MAX_READ_BYTES].decode("utf-8", errors="replace").splitlines()
        chunk = text[start_line - 1:start_line - 1 + max_lines]
        numbered = "\n".join(f"{start_line + i:>5} | {line}" for i, line in enumerate(chunk))
        footer = f"\n(showing lines {start_line}-{start_line + len(chunk) - 1} of {len(text)})" if chunk else \
                 "\n(no lines at that position)"
        return _clip(numbered + footer)

    def find_files(self, name_pattern: str, path: str = ".", max_results: int = 100) -> str:
        """Find files whose name matches a glob such as '*.py' or 'test_*'."""
        start = self._resolve(path)
        hits = []
        for p in self._walk_files(start):
            if fnmatch.fnmatch(p.name, name_pattern):
                hits.append(self._rel(p))
                if len(hits) >= max_results:
                    break
        return "\n".join(hits) or f"No files matching '{name_pattern}'."

    def search_code(self, pattern: str, path: str = ".", max_results: int = 50,
                    ignore_case: bool = False) -> str:
        """Search text files with a regular expression. Returns file:line: text."""
        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as err:
            raise ToolError(f"Invalid regular expression: {err}") from None
        start = self._resolve(path)
        max_results = max(1, min(int(max_results), 500))
        hits: list[str] = []
        for p in self._walk_files(start):
            if p.stat().st_size > MAX_SEARCH_FILE_BYTES or not self._is_text(p):
                continue
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, 1):
                if regex.search(line):
                    hits.append(f"{self._rel(p)}:{number}: {line.strip()[:200]}")
                    if len(hits) >= max_results:
                        return _clip("\n".join(hits) + "\n(stopped at max_results)")
        return _clip("\n".join(hits)) or "No matches."

    def find_todos(self, max_results: int = 100) -> str:
        return self.search_code(TODO_PATTERN, max_results=max_results)

    def git_status(self) -> str:
        return self._git(["status", "--short", "--branch"])

    def git_log(self, limit: int = 10) -> str:
        limit = max(1, min(int(limit), 50))
        return self._git(["log", "--oneline", "--decorate", f"-n{limit}"])

    def git_diff(self, path: str | None = None, staged: bool = False) -> str:
        args = ["diff"]
        if staged:
            args.append("--staged")
        if path:
            args += ["--", self._rel(self._resolve(path))]
        return self._git(args)

    # ------------------------------------------------------------ optional tools
    def run_tests(self, path: str = ".") -> str:
        if not self.allow_tests:
            raise ToolError("Running tests is turned off. Start the server with --allow-tests to enable it.")
        target = self._resolve(path)
        rel = self._rel(target)
        has_python_tests = any(
            p.name.startswith("test_") or p.name.endswith("_test.py") for p in self._walk_files(self.root)
        ) or (self.root / "pyproject.toml").exists() or (self.root / "pytest.ini").exists()
        if has_python_tests:
            cmd = [sys.executable, "-m", "pytest", "-q", rel]
        elif (self.root / "package.json").exists() and shutil.which("npm"):
            cmd = ["npm", "test", "--silent"]
        else:
            raise ToolError("No test setup found (looked for Python tests or a package.json with npm test).")
        try:
            proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=self.test_timeout)
        except subprocess.TimeoutExpired:
            raise ToolError(f"Tests took longer than {self.test_timeout} seconds and were stopped.") from None
        output = (proc.stdout + proc.stderr)
        tail = output[-8000:]
        return f"exit code {proc.returncode}\n{tail}"

    def write_file(self, path: str, content: str, overwrite: bool = False) -> str:
        if not self.allow_writes:
            raise ToolError("Writing files is turned off. Start the server with --allow-writes to enable it.")
        target = self._resolve(path)
        if target == self.root:
            raise ToolError("Choose a file path, not the project folder.")
        if ".git" in target.relative_to(self.root).parts:
            raise ToolError("Writing inside .git is not allowed.")
        if target.is_dir():
            raise ToolError(f"'{path}' is a folder.")
        if target.exists() and not overwrite:
            raise ToolError(f"'{path}' already exists. Pass overwrite=true to replace it.")
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ToolError("Content is too large (limit 500 KB).")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {self._rel(target)}."
