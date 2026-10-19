# Context Graph & Query Cache (`context-graph`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

An **Antigravity Plugin** that persists **file summaries**, **symbol line maps**, **code & implementation relationships**, **LLM-queried / generated data**, and **token usage analytics per conversation and Git repository** in a local SQLite knowledge graph (`~/.gemini/context-graph/cache.db`).

By tracking file `SHA-256` hashes and modification times (`mtime`), Antigravity knows which files are **fresh** (unchanged on disk) versus **stale** (modified), allowing it to understand file relationships and reuse prior query results without burning tokens re-reading unchanged files.

---

## Installation (via `git clone`)

Requires **Python 3** (uses only the Python standard library—`sqlite3`, `ast`, `hashlib`, `json`, `re`, `configparser`—with **zero external `pip` dependencies**).

### Option 1: Global Install (All Workspaces)
Clone directly into your global Antigravity plugins directory:

```bash
mkdir -p ~/.gemini/config/plugins
git clone <YOUR_GIT_REPO_URL> ~/.gemini/config/plugins/context-graph
```

### Option 2: Workspace-Scoped Install (Per-Project / Team Shared)
Clone into your project's `.agents/plugins/` directory:

```bash
mkdir -p .agents/plugins
git clone <YOUR_GIT_REPO_URL> .agents/plugins/context-graph
```

### Option 3: Clone Anywhere + Run Installer
```bash
git clone <YOUR_GIT_REPO_URL> context-graph
cd context-graph
sh ./install.sh
```

> **Note**: Restart Antigravity after installing so the plugin's MCP server (`context-graph-mcp`), lifecycle hooks, skill, and rules are loaded.

---

## Features

1. **Token Usage Analytics per Conversation & Related Git Repo (`cache_get_token_usage` & `scripts/token_report.py`)**:
   - Automatically parses Antigravity conversation transcripts (`transcript.jsonl`) and tracks `input_tokens`, `cache_read_tokens`, `output_tokens`, `total_tokens`, and **Cache Hit Rate %**.
   - Automatically links each conversation to its **Project / Git Repository** (detecting `.git` root, repository name, `origin` remote URL, and active branch).
   - Run anytime in chat (*"Show token usage per conversation and grouped by project/repo"*) or directly from the terminal:
     ```bash
     python3 ~/.gemini/config/plugins/context-graph/scripts/token_report.py
     ```
2. **Zero-Token Static Indexing (`cache_auto_index_workspace`)**:
   - Statically parses source files (`Python` via `ast`, plus `TypeScript`, `JavaScript`, `Go`, `Rust`, `Java`, `C/C++`, `SQL`, etc.) to extract classes, functions, line numbers, exported symbols, and `imports` relationships with zero LLM token cost.
3. **SHA-256 Staleness Detection (`cache_get_file_context`)**:
   - Every cached file records its `mtime` and `SHA-256` digest. On subsequent turns or sessions, if `is_stale` is `false`, Antigravity uses the cached architectural summary, symbol line numbers, and incoming/outgoing edges instead of calling `view_file` on the entire file.
4. **Persistent Query & Generated Data Cache (`cache_store_query` / `cache_search`)**:
   - Stores expensive search findings, database query outputs, API responses, and LLM-generated datasets under a `query_key` linked to `related_files`.
5. **Automatic Lifecycle Hooks (`hooks.json`)**:
   - **`SessionStart` (`scripts/session_start.py`)**: Automatically indexes unindexed workspaces (up to 60 files) and injects a compact `[Context Graph & Query Cache]` digest at the start of a conversation.
   - **`PostToolUse` (`scripts/post_tool_tracker.py`)**: Passively tracks `view_file`, `replace_file_content`, `multi_replace_file_content`, `write_to_file`, `grep_search`, and `find_by_name`—automatically indexing newly viewed files, marking edited files as `needs_refresh`, and syncing live conversation token usage.

---

## Bundled Components

```text
context-graph/
├── plugin.json                        # Antigravity plugin manifest
├── mcp_config.json                    # Portable stdio MCP server configuration
├── hooks.json                         # SessionStart & PostToolUse lifecycle hooks
├── install.sh                         # Optional helper installer script
├── LICENSE                            # MIT License
├── README.md                          # Documentation
├── assets/
│   └── logo.svg                       # Plugin icon
├── server/
│   ├── db_engine.py                   # SQLite graph + token tracker + Git repo detector + AST indexer
│   └── mcp_server.py                  # Zero-dependency JSON-RPC 2.0 Stdio MCP server
├── scripts/
│   ├── session_start.py               # Injects workspace context digest on SessionStart
│   ├── post_tool_tracker.py           # Tracks file reads, edits & token usage on PostToolUse
│   └── token_report.py                # CLI & Markdown reporter for token usage per conversation/repo
├── rules/
│   └── AGENTS.md                      # Always-on token-saving protocol for the LLM
├── skills/
│   └── context-graph/
│       └── SKILL.md                   # On-demand workflows for token reports, indexing & Mermaid graphs
└── agents/
    └── context-indexer.md             # Background subagent for indexing large codebases
```

---

## Available MCP Tools (`context-graph-mcp`)

| Tool | Description |
| :--- | :--- |
| `cache_get_token_usage` | View token usage (`input_tokens`, `cache_read_tokens`, `output_tokens`, `total_tokens`, `cache_hit_rate_pct`) per conversation and grouped by project / Git repository. |
| `cache_auto_index_workspace` | Zero-token static indexer that scans workspace files and populates symbols and `imports` edges. |
| `cache_get_overview` | Returns workspace cache stats, Git repo info, fresh/stale file counts, relationships, and stored queries. |
| `cache_get_file_context` | Checks if a file is fresh (`is_stale: false`) and returns its summary, symbols, and 1- or 2-hop relationships. |
| `cache_upsert_file` | Saves an LLM-enriched summary, symbol map, and outgoing dependencies with current disk `SHA-256`. |
| `cache_add_relationship` | Adds a directed relationship (`imports`, `calls`, `implements`, `extends`, `reads_data_from`, `tests`, `configures`). |
| `cache_store_query` | Saves queried data or LLM-generated datasets under a reusable `query_key`. |
| `cache_search` | Searches across all cached file summaries, symbols, relationships, and stored queries. |

---

## License

Released under the [MIT License](./LICENSE).
