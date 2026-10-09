"""MCP server: exposes the project tools to AI assistants over stdio.

IMPORTANT: over the stdio transport, stdout carries the protocol messages.
Never print to stdout in this package; use stderr for logs.
"""

from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .config import Config, parse_config
from .tools import ProjectTools

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
RUNS_CODE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

INSTRUCTIONS = (
    "Tools for working with one software project. Start with project_tree or file_stats to learn the "
    "layout, then use search_code, find_files and read_file. Use git_status, git_log and git_diff to see "
    "recent changes. Paths are relative to the project folder. Write and test tools may be unavailable "
    "unless the owner enabled them."
)


def build_server(tools: ProjectTools) -> FastMCP:
    mcp = FastMCP("project-context", instructions=INSTRUCTIONS)

    @mcp.tool(description="Show the folder structure of the project (or a sub-folder).", annotations=READ_ONLY)
    def project_tree(path: str = ".", max_depth: int = 3) -> str:
        return tools.project_tree(path, max_depth)

    @mcp.tool(description="Count files and lines by file type across the project.", annotations=READ_ONLY)
    def file_stats() -> str:
        return tools.file_stats()

    @mcp.tool(description="Read a text file with line numbers. Use start_line and max_lines to page through it.",
              annotations=READ_ONLY)
    def read_file(path: str, start_line: int = 1, max_lines: int = 300) -> str:
        return tools.read_file(path, start_line, max_lines)

    @mcp.tool(description="Find files by name using a glob pattern such as '*.py' or 'test_*'.",
              annotations=READ_ONLY)
    def find_files(name_pattern: str, path: str = ".", max_results: int = 100) -> str:
        return tools.find_files(name_pattern, path, max_results)

    @mcp.tool(description="Search all text files for a regular expression. Returns file:line: text.",
              annotations=READ_ONLY)
    def search_code(pattern: str, path: str = ".", max_results: int = 50, ignore_case: bool = False) -> str:
        return tools.search_code(pattern, path, max_results, ignore_case)

    @mcp.tool(description="List TODO, FIXME, HACK and XXX comments in the project.", annotations=READ_ONLY)
    def find_todos(max_results: int = 100) -> str:
        return tools.find_todos(max_results)

    @mcp.tool(description="Show git status: changed, staged and untracked files.", annotations=READ_ONLY)
    def git_status() -> str:
        return tools.git_status()

    @mcp.tool(description="Show the most recent git commits (one line each).", annotations=READ_ONLY)
    def git_log(limit: int = 10) -> str:
        return tools.git_log(limit)

    @mcp.tool(description="Show uncommitted changes, optionally for one file and/or only staged changes.",
              annotations=READ_ONLY)
    def git_diff(path: str | None = None, staged: bool = False) -> str:
        return tools.git_diff(path, staged)

    if tools.allow_tests:
        @mcp.tool(description="Run the project's tests (pytest or npm test) and return the results.",
                  annotations=RUNS_CODE)
        def run_tests(path: str = ".") -> str:
            return tools.run_tests(path)

    if tools.allow_writes:
        @mcp.tool(description="Create a new text file, or replace an existing one when overwrite is true.",
                  annotations=WRITE)
        def write_file(path: str, content: str, overwrite: bool = False) -> str:
            return tools.write_file(path, content, overwrite)

    return mcp


def main(argv: list[str] | None = None) -> None:
    config: Config = parse_config(argv)
    tools = ProjectTools(config.root, config.allow_writes, config.allow_tests, config.test_timeout)
    print(f"project-context MCP server: root={config.root} writes={config.allow_writes} "
          f"tests={config.allow_tests}", file=sys.stderr)
    build_server(tools).run("stdio")
