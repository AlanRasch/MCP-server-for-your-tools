"""Command-line options and environment variables.

Options (all optional):
  --root PATH        project folder (default: current folder, or PROJECT_ROOT)
  --allow-writes     let the assistant create or overwrite files (default: off)
  --allow-tests      let the assistant run the project's tests (default: off)
  --test-timeout N   seconds before a test run is stopped (default: 120)
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    root: Path
    allow_writes: bool = False
    allow_tests: bool = False
    test_timeout: int = 120


def parse_config(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(prog="project-context-mcp",
                                     description="MCP server that gives AI assistants safe access to a project folder.")
    parser.add_argument("--root", default=os.getenv("PROJECT_ROOT", os.getcwd()),
                        help="project folder (default: PROJECT_ROOT or the current folder)")
    parser.add_argument("--allow-writes", action="store_true",
                        default=_env_flag("PROJECT_ALLOW_WRITES"), help="allow creating/overwriting files")
    parser.add_argument("--allow-tests", action="store_true",
                        default=_env_flag("PROJECT_ALLOW_TESTS"), help="allow running the project's tests")
    parser.add_argument("--test-timeout", type=int, default=int(os.getenv("PROJECT_TEST_TIMEOUT", "120")),
                        help="seconds before a test run is stopped")
    args = parser.parse_args(argv)
    return Config(root=Path(args.root).expanduser().resolve(), allow_writes=args.allow_writes,
                  allow_tests=args.allow_tests, test_timeout=args.test_timeout)
