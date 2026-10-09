"""Checks which tools the MCP server offers, depending on the safety switches."""

import asyncio

from project_context_mcp.server import build_server
from project_context_mcp.tools import ProjectTools


def tool_names(allow_writes: bool, allow_tests: bool, root) -> set[str]:
    server = build_server(ProjectTools(root, allow_writes=allow_writes, allow_tests=allow_tests))
    return {t.name for t in asyncio.run(server.list_tools())}


def test_default_offers_only_read_only_tools(tmp_path):
    names = tool_names(False, False, tmp_path)
    assert {"project_tree", "read_file", "search_code", "git_status"} <= names
    assert "write_file" not in names
    assert "run_tests" not in names


def test_switches_add_the_optional_tools(tmp_path):
    names = tool_names(True, True, tmp_path)
    assert {"write_file", "run_tests"} <= names


def test_every_tool_has_a_description(tmp_path):
    server = build_server(ProjectTools(tmp_path, allow_writes=True, allow_tests=True))
    for tool in asyncio.run(server.list_tools()):
        assert tool.description, f"{tool.name} has no description"
