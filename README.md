# Project Context MCP Server

A Model Context Protocol (MCP) server that gives AI assistants safe access to a software project. Connect it to an MCP-compatible assistant, point it at a project folder, and the assistant can explore the code, search it, read files, check git history and changes, and, if you allow it, run tests or create files.

It is built for developers who want an assistant that understands their codebase without handing it unrestricted access to their machine.

---

## What it provides

| Tool | What it does | Enabled by default |
|---|---|---|
| `project_tree` | Shows the folder structure, skipping `.git`, `node_modules`, virtual environments and build output | Yes |
| `file_stats` | Counts files and lines by file type | Yes |
| `read_file` | Reads a text file with line numbers, with paging (`start_line`, `max_lines`) | Yes |
| `find_files` | Finds files by name pattern, such as `*.py` or `test_*` | Yes |
| `search_code` | Searches all text files with a regular expression | Yes |
| `find_todos` | Lists TODO, FIXME, HACK and XXX comments | Yes |
| `git_status` | Shows changed, staged and untracked files | Yes |
| `git_log` | Shows recent commits | Yes |
| `git_diff` | Shows uncommitted changes, optionally for one file or only staged changes | Yes |
| `run_tests` | Runs `pytest`, or `npm test` when there is a `package.json` | No, needs `--allow-tests` |
| `write_file` | Creates a new file, or replaces one when `overwrite` is true | No, needs `--allow-writes` |

Tools that are switched off are not offered to the assistant at all.

---

## Safety

- **Project folder only.** Every path is checked against the project root. Attempts such as `../../etc/passwd` or links that point outside the project are refused.
- **Read-only by default.** Writing files and running tests each need an explicit flag.
- **Git is read-only.** The server runs `status`, `log` and `diff` only. It never commits, pushes or changes branches.
- **No shell.** Commands are passed as argument lists, so there is no shell injection.
- **Size limits.** Large files, very long output and oversized writes are cut off, so the assistant's context stays manageable.
- **Nothing inside `.git` can be written.**

Running tests executes the project's own code. Enable `--allow-tests` only for projects you trust.

---

## Requirements

- Python 3.10 or newer
- Git (optional, needed only for the git tools)
- An MCP-compatible AI client, such as Claude Desktop

---

## Installation

### macOS

```bash
cd project-context-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Windows (PowerShell)

```powershell
cd project-context-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

---

## Running the server

The server is started by your AI client, but you can start it yourself to check it:

```bash
python -m project_context_mcp --root /path/to/your/project
```

Options:

| Option | Environment variable | Default | Meaning |
|---|---|---|---|
| `--root PATH` | `PROJECT_ROOT` | current folder | The project the assistant may use |
| `--allow-writes` | `PROJECT_ALLOW_WRITES=true` | off | Let the assistant create or replace files |
| `--allow-tests` | `PROJECT_ALLOW_TESTS=true` | off | Let the assistant run the project's tests |
| `--test-timeout N` | `PROJECT_TEST_TIMEOUT` | 120 | Seconds before a test run is stopped |

The server prints a status line to stderr when it starts. It writes nothing else to the terminal, because the MCP protocol uses the standard output.

---

## Connecting to an AI client

### Claude Desktop

1. Open the Claude Desktop configuration file:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
2. Add an entry under `mcpServers`, using the full path to the Python in your virtual environment. See `examples/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "project-context": {
      "command": "/full/path/to/project-context-mcp/.venv/bin/python",
      "args": ["-m", "project_context_mcp", "--root", "/full/path/to/your-project"]
    }
  }
}
```

On Windows, the Python path is `C:\full\path\to\project-context-mcp\.venv\Scripts\python.exe`, and the paths need doubled backslashes inside JSON, for example `"C:\\Users\\you\\project"`.

3. Restart Claude Desktop. The project tools should appear in the tools menu.

To enable writing or tests, add the flags to `args`, for example `"--allow-tests"`.

### Any other MCP client

Any client that supports MCP over stdio can start the server with the same command and arguments.

### Testing without an AI client

The official MCP Inspector lets you try each tool in a browser:

```bash
npx @modelcontextprotocol/inspector python -m project_context_mcp --root /path/to/your-project
```

---

## Example requests to an assistant

- "Give me an overview of this project's structure and the main modules."
- "Where is the database connection set up? Show me the code."
- "What changed since the last commit? Explain the diff."
- "List the TODO comments and group them by file."
- "Run the tests and tell me what is failing."
- "Create `docs/architecture.md` with a short summary of the modules." (requires `--allow-writes`)

---

## Project structure

```
project-context-mcp/
├── src/project_context_mcp/
│   ├── __init__.py
│   ├── __main__.py      # python -m project_context_mcp
│   ├── config.py        # command-line options and environment variables
│   ├── server.py        # MCP tool definitions and startup
│   └── tools.py         # the project tools and their safety checks
├── tests/
│   ├── test_server.py   # checks which tools are offered
│   └── test_tools.py    # tests for each tool and safety rule
├── examples/
│   └── claude_desktop_config.json
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Running the tests

```bash
pip install -e ".[dev]"
python -m pytest -q
```

The tests create temporary projects, so they do not touch your own files. The git test creates a temporary repository.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: project_context_mcp` | Run `pip install -e .` in the project folder, using the same Python that the client uses |
| Tool missing from the client | Check that you enabled `--allow-writes` or `--allow-tests` if you expected those tools |
| `is outside the project folder` | Use a path relative to `--root`, or make sure the file really is inside it |
| `git is not installed` | Install Git, or ignore the git tools |
| `No test setup found` | Add a `tests/` folder with `test_*.py` files, or a `package.json` with a `test` script |
| Tests stop after 120 seconds | Raise `--test-timeout` |
| Client shows the server as failed | Start it manually with the same command to read the error message |

---

## Extending the server

To add a tool:

1. Add a method to `ProjectTools` in `tools.py`. Use `self._resolve()` for any path, and raise `ToolError` for problems the user should see.
2. Register it in `build_server()` in `server.py` with a clear description and the right annotation (`READ_ONLY` for anything that does not change files).
3. Add a test in `tests/test_tools.py`.

---

**Author:** Dr. Firend Alan Rasch, American University of Phnom Penh
**License:** MIT (or your preferred license)
