# Context Graph & Query Cache (`context-graph`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

A **Universal Multi-LLM Plugin & MCP Knowledge Graph** for **Google Antigravity**, **Claude Code**, **Cursor**, **Windsurf**, **OpenAI Codex CLI**, and **Google Gemini CLI**.

It persists **file summaries**, **symbol line maps**, **code & implementation relationships**, **LLM-queried / generated data**, and **token usage analytics per conversation, per LLM client, and per Git repository** in a shared local SQLite database (`~/.gemini/context-graph/cache.db`).

By tracking file `SHA-256` hashes and modification times (`mtime`), your AI coding assistants know which files are **fresh** (unchanged on disk) versus **stale** (modified)—allowing every LLM tool on your machine to share the same architectural memory without burning tokens re-reading unchanged files.

---

## Supported LLM Clients

| Client | Manifest / Integration Included | Shared SQLite Cache | Lifecycle Hooks | Token Usage Tracking |
| :--- | :--- | :---: | :---: | :---: |
| **Google Antigravity** | `plugin.json` + `mcp_config.json` + `hooks.json` | Yes | Yes (`SessionStart`, `PostToolUse`) | Yes (`~/.gemini/antigravity/brain/`) |
| **Claude Code** | `.claude-plugin/plugin.json` + `.mcp.json` + `hooks.json` | Yes | Yes (`SessionStart`, `PostToolUse`) | Yes (`~/.claude/projects/`) |
| **Google Gemini CLI** | `gemini-extension.json` + `rules/AGENTS.md` | Yes | Yes | Yes |
| **OpenAI Codex CLI** | MCP Server + `rules/AGENTS.md` + `skills/` | Yes | — | Yes (`~/.codex/sessions/`) |
| **Cursor / Windsurf / Cline** | `.mcp.json` (`context-graph-mcp` Stdio) | Yes | — | — |

---

## Installation (via `git clone`)

Requires **Python 3** (uses only the Python standard library—`sqlite3`, `ast`, `hashlib`, `json`, `re`, `configparser`—with **zero external `pip` dependencies**).

### 1. Universal Installer (Antigravity + Claude Code + Cursor)
```bash
git clone <YOUR_GIT_REPO_URL> context-graph
cd context-graph
sh ./install.sh --all
```

### 2. Direct Clone for Google Antigravity
- **Global (All Workspaces)**:
  ```bash
  mkdir -p ~/.gemini/config/plugins
  git clone <YOUR_GIT_REPO_URL> ~/.gemini/config/plugins/context-graph
  ```
- **Per-Project Workspace**:
  ```bash
  mkdir -p .agents/plugins
  git clone <YOUR_GIT_REPO_URL> .agents/plugins/context-graph
  ```

### 3. Direct Setup for Claude Code / Gemini CLI / Codex CLI
- **Claude Code**:
  ```bash
  claude mcp add context-graph -- python3 ~/.gemini/config/plugins/context-graph/server/mcp_server.py
  # Or load as a full plugin with hooks & skills:
  claude --plugin-dir ~/.gemini/config/plugins/context-graph
  ```
- **Gemini CLI**:
  ```bash
  gemini extensions install <YOUR_GIT_REPO_URL>
  ```
- **Cursor / Windsurf / Claude Desktop**:
  Add `context-graph-mcp` to your `mcp.json`:
  ```json
  {
    "mcpServers": {
      "context-graph-mcp": {
        "command": "python3",
        "args": ["/path/to/context-graph/server/mcp_server.py"]
      }
    }
  }
  ```

---

## Key Features

### 1. Multi-LLM Token Usage Analytics (`cache_get_token_usage` & `scripts/token_report.py`)
- Scans transcript logs across **Antigravity** (`~/.gemini/antigravity/brain/`), **Claude Code** (`~/.claude/projects/`), and **Codex CLI** (`~/.codex/sessions/`).
- Reports `input_tokens`, `cache_read_tokens`, `output_tokens`, `total_tokens`, and **Cache Hit Rate %** broken down by:
  1. **LLM Client** (`antigravity`, `claude-code`, `codex-cli`)
  2. **Project / Related Git Repository** (automatically detecting `.git` root, repository name, `origin` remote URL, and active branch)
  3. **Individual Conversation** (with prompt title and turn count)
- Run from the terminal anytime:
  ```bash
  python3 ~/.gemini/config/plugins/context-graph/scripts/token_report.py
  # Filter by repo or client:
  python3 ~/.gemini/config/plugins/context-graph/scripts/token_report.py --workspace /path/to/repo --client antigravity
  ```

### 2. Zero-Token Static Codebase Indexing (`cache_auto_index_workspace`)
- Statically parses source files (`Python` via `ast`, plus `TypeScript`, `JavaScript`, `Go`, `Rust`, `Java`, `C/C++`, `SQL`, etc.) to extract classes, functions, line numbers, exported symbols, and `imports` relationships with zero LLM token cost.

### 3. SHA-256 Staleness Detection (`cache_get_file_context`)
- Every cached file records its `mtime` and `SHA-256` digest. On subsequent turns or sessions, if `is_stale` is `false`, the LLM uses the cached architectural summary, symbol line numbers, and incoming/outgoing edges instead of reading the entire file.

### 4. Persistent Query & Generated Data Cache (`cache_store_query` / `cache_search`)
- Stores expensive search findings, database query outputs, API responses, and LLM-generated datasets under a `query_key` linked to `related_files`.

---

## Repository Structure

```text
context-graph/
├── plugin.json                        # Google Antigravity plugin manifest
├── .claude-plugin/
│   └── plugin.json                    # Claude Code plugin manifest
├── gemini-extension.json              # Google Gemini CLI extension manifest
├── mcp_config.json                    # Antigravity MCP server config
├── .mcp.json                          # Claude Code / Cursor MCP server config
├── hooks.json                         # Universal SessionStart & PostToolUse hooks
├── install.sh                         # Universal installer script
├── LICENSE                            # MIT License
├── README.md                          # Documentation
├── assets/
│   └── logo.svg                       # Plugin icon
├── server/
│   ├── db_engine.py                   # SQLite graph + multi-LLM token tracker + AST indexer
│   └── mcp_server.py                  # Zero-dependency JSON-RPC 2.0 Stdio MCP server
├── scripts/
│   ├── session_start.py               # Injects workspace context digest on SessionStart
│   ├── post_tool_tracker.py           # Tracks file reads, edits & token usage on PostToolUse
│   └── token_report.py                # CLI & Markdown reporter for multi-LLM token usage
├── rules/
│   └── AGENTS.md                      # Always-on token-saving protocol for all LLMs
├── skills/
│   └── context-graph/
│       └── SKILL.md                   # On-demand workflows for token reports & indexing
└── agents/
    └── context-indexer.md             # Background subagent for indexing large codebases
```

---

## License

Released under the [MIT License](./LICENSE).
