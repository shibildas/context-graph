# Context Graph & Query Cache (`context-graph`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Stdlib%20Only)-success.svg)](#installation)

A **Universal Multi-LLM Plugin, MCP Knowledge Graph, 3D Data Model Visualizer & Token Analytics Control Center** for **Google Antigravity**, **Claude Code**, **Cursor**, **Windsurf**, **OpenAI Codex CLI**, and **Google Gemini CLI**.

`context-graph` eliminates redundant file reads, prevents repeated LLM hallucinations, and tracks token consumption across all your AI coding tools using a shared local SQLite database (`~/.gemini/context-graph/cache.db`) with **zero external `pip` dependencies**.

---

## What It Solves

1. **Zero-Token Codebase Indexing & Context Reuse**:
   Statically indexes Python, TypeScript/JavaScript, Go, Rust, SQL, and Markdown files (extracting classes, functions, line numbers, exports, and `imports` edges) with SHA-256 staleness detection (`is_stale`) so your LLM only reads files when their content actually changes.
2. **Anti-Hallucination & Ground-Truth Overrides**:
   - **Ground-Truth Pins (`ground_truth_overrides`)**: Pin verified domain rules or user corrections that are automatically injected at `SessionStart` and on every file lookup so the LLM never repeats a corrected mistake.
   - **Automated Hallucination Detector & Healer**: Audits cached symbols, line numbers, and dependency edges against the live filesystem and purges phantom symbols, deleted ghost files, and broken relationships.
3. **Interactive 3D Data Model & Context Graph UI**:
   Includes a rotatable, zoomable **3D Force-Directed WebGL/Canvas Graph** (`scripts/ui_server.py` and `context-graph-dashboard.html`) that visualizes the 6 core SQLite data model tables (`files`, `relationships`, `query_cache`, `ground_truth_overrides`, `conversation_usage`, `access_log`), live workspace files, extracted symbols, and cross-file dependency edges.
4. **Multi-LLM Token Usage Analytics (with Automatic Secret Redaction)**:
   Scans and aggregates token usage (`input_tokens`, `cache_read_tokens`, `output_tokens`, `total_tokens`, `cache_hit_rate_pct`) across **Google Antigravity**, **Claude Code**, and **OpenAI Codex CLI**, grouped by **LLM client**, **Git repository / branch**, and **individual conversation**, while automatically redacting any credentials or connection strings from conversation titles and Git remotes.

---

## Interactive Web UI & 3D Data Model Visualizer

### 1. Launch the Live Local Web UI Control Center (`scripts/ui_server.py`)
```bash
python3 ~/.gemini/config/plugins/context-graph/scripts/ui_server.py --port 8765
# Open http://127.0.0.1:8765 in your browser
```
The Web UI provides 4 interactive tabs backed by live REST endpoints (`/api/state`, `/api/verify`, `/api/refresh`, `/api/override/add`, `/api/override/delete`):
- **Tab 1 — Multi-LLM Token Usage**: Breakdown by LLM client (`antigravity`, `claude-code`, `codex-cli`), project / Git repository, and searchable conversation history.
- **Tab 2 — Context Graph & 3D Data Model**: Interactive 3D rotatable force-directed graph (`Core Data Models + Workspace Files`, `Core SQLite Schema Only`, or `Workspace Files & Symbols Only`) with a live node inspector for PK/FK columns, SHA-256 hashes, and symbol line numbers.
- **Tab 3 — Anti-Hallucination & Overrides**: Create, filter, and delete verified ground-truth overrides (`CRITICAL`, `HIGH`, `NORMAL`) and run 1-click Hallucination Audits or Context Refreshes.
- **Tab 4 — Stored Queries**: Search and purge reusable LLM-queried datasets and architectural insights.

### 2. Export a Self-Contained HTML Dashboard
```bash
python3 ~/.gemini/config/plugins/context-graph/scripts/ui_server.py --export-html ./context-graph-dashboard.html
```

### 3. Native Antigravity Plugin Management Page
Open `customization://context-graph` inside Google Antigravity.

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

## Installation

Requires **Python 3.9+** (uses only the Python standard library—`sqlite3`, `ast`, `hashlib`, `json`, `re`, `configparser`, `http.server`—with **zero external `pip` dependencies**).

### 1. Universal Installer (Antigravity + Claude Code + Cursor)
```bash
git clone https://github.com/shibildas/context-graph.git
cd context-graph
sh ./install.sh --all
```

### 2. Direct Clone for Google Antigravity
- **Global (All Workspaces)**:
  ```bash
  mkdir -p ~/.gemini/config/plugins
  git clone https://github.com/shibildas/context-graph.git ~/.gemini/config/plugins/context-graph
  ```
- **Per-Project Workspace**:
  ```bash
  mkdir -p .agents/plugins
  git clone https://github.com/shibildas/context-graph.git .agents/plugins/context-graph
  ```

---

## MCP Tools Reference (`context-graph-mcp`)

The Stdio MCP server (`server/mcp_server.py`) exposes **12 tools**:

| Tool Name | Description |
| :--- | :--- |
| `cache_get_overview` | Returns workspace cache stats, active ground-truth overrides, Git metadata, fresh vs. stale files, relationships, and stored queries. |
| `cache_get_file_context` | Returns a file's ground-truth overrides, SHA-256 staleness (`is_stale`), summary, symbol line numbers, and 1- or 2-hop relationships. |
| `cache_auto_index_workspace` | Statically scans the workspace (zero LLM tokens), extracting classes, functions, line numbers, exports, and `imports` relationships into SQLite. |
| `cache_upsert_file` | Saves or updates an LLM-enriched file summary, symbol list, and outgoing dependency edges. |
| `cache_add_relationship` | Records semantic implementation relationships (`imports`, `calls`, `implements`, `extends`, `reads_data_from`, `writes_data_to`, `tests`, `configures`). |
| `cache_store_query` | Persists expensive search results, DB schema queries, or generated datasets under a reusable `query_key`. |
| `cache_search` | Searches across all ground-truth overrides, cached files, symbols, relationships, and stored queries. |
| `cache_record_correction` | Records a verified ground-truth override (`override_key`, `hallucination_or_mistake`, `verified_truth`, `scope_files`, `priority`) so the LLM never repeats a mistake. |
| `cache_verify_and_fix_hallucinations` | Audits cached symbols, line numbers, and edges against live files on disk and auto-purges hallucinated symbols, deleted files, and broken edges. |
| `cache_refresh_context` | Refreshes or resets context with 5 modes: `stale_only`, `force_all`, `file`, `purge_queries`, or `hard_reset`. |
| `cache_override_entry` | Directly overrides or deletes a specific cached `'file'`, `'query'`, `'relationship'`, or `'override'` entry. |
| `cache_get_token_usage` | Aggregates multi-LLM token usage per conversation, per LLM client, and grouped by project / Git repository. |

---

## CLI Utilities

### 1. Context Override, Refresh & Anti-Hallucination CLI (`scripts/context_ctl.py`)
```bash
# 1. Audit & auto-fix hallucinated symbols, ghost files, and broken relationships:
python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py verify --workspace /path/to/repo

# 2. Refresh context (stale_only | force_all | file | purge_queries | hard_reset):
python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py refresh --workspace /path/to/repo --mode force_all

# 3. Pin a verified ground-truth override to prevent an LLM hallucination:
python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py correct \
  --workspace /path/to/repo \
  --key "api-timeout-ms" \
  --mistake "Assuming DEFAULT_TIMEOUT_MS is 30000 in production" \
  --truth "DEFAULT_TIMEOUT_MS must be set to 5000 in production" \
  --priority critical

# 4. List active ground-truth overrides:
python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py overrides --workspace /path/to/repo
```

### 2. Multi-LLM Token Usage CLI (`scripts/token_report.py`)
```bash
# View full Markdown report across all workspaces & LLM clients:
python3 ~/.gemini/config/plugins/context-graph/scripts/token_report.py

# Filter by workspace or LLM client (antigravity | claude-code | codex-cli):
python3 ~/.gemini/config/plugins/context-graph/scripts/token_report.py --workspace /path/to/repo --client antigravity
```

---

## SQLite Data Model (`~/.gemini/context-graph/cache.db`)

| Table | Primary Key | Purpose |
| :--- | :--- | :--- |
| `files` | `(workspace_path, rel_path)` | Stores `content_hash` (SHA-256), `mtime`, `language`, `summary`, `symbols_json`, and `exports_json`. |
| `relationships` | `(workspace_path, source_path, target_path, rel_type)` | Directed graph edges (`imports`, `calls`, `implements`, `extends`, `reads_data_from`, `writes_data_to`, `tests`, `configures`). |
| `query_cache` | `(workspace_path, query_key)` | Stores reusable queried/generated data (`query_text`, `result_json`, `tags_json`, `related_files_json`). |
| `ground_truth_overrides` | `(workspace_path, override_key)` | Stores verified anti-hallucination pins (`hallucination_or_mistake`, `verified_truth`, `scope_files_json`, `priority`, `active`). |
| `conversation_usage` | `conversation_id` | Multi-LLM token analytics (`client_source`, `workspace_path`, `repo_name`, `git_remote`, `git_branch`, `model_name`, `turn_count`, `input_tokens`, `cache_read_tokens`, `output_tokens`, `total_tokens`). |
| `access_log` | `id` (Auto-Increment) | Audit trail of tool reads/edits (`SessionStart`, `PostToolUse`, `verify_and_fix`). |

---

## Repository Structure

```text
context-graph/
├── plugin.json                  # Google Antigravity plugin manifest
├── mcp_config.json              # Antigravity MCP server config
├── .claude-plugin/plugin.json   # Claude Code plugin manifest
├── .mcp.json                    # Claude Code / Cursor / Windsurf MCP config
├── gemini-extension.json        # Google Gemini CLI extension manifest
├── hooks.json                   # Automatic SessionStart & PostToolUse hooks
├── pyproject.toml               # Python package & Pyrefly / Pyright search-path config
├── install.sh                   # Universal multi-client installer
├── context-graph-dashboard.html # Standalone Web UI & 3D Data Model Graph
├── rules/
│   └── AGENTS.md                # Always-on Context Graph & Anti-Hallucination protocol
├── skills/
│   └── context-graph/SKILL.md   # Slash command (/context-graph) & workflow guide
├── agents/
│   └── context-indexer.md       # Background subagent for zero-cost workspace indexing
├── server/
│   ├── __init__.py
│   ├── db_engine.py             # SQLite WAL engine, AST/regex indexer, secret redactor & token scanner
│   └── mcp_server.py            # Stdio JSON-RPC 2.0 MCP server (12 tools)
└── scripts/
    ├── ui_server.py             # Live Web UI server (http://127.0.0.1:8765) & HTML exporter
    ├── context_ctl.py           # CLI for overrides, context refresh & hallucination repair
    ├── token_report.py          # CLI for multi-LLM token usage analytics
    ├── session_start.py         # SessionStart hook (injects ground-truth pins & graph digest)
    └── post_tool_tracker.py     # PostToolUse hook (tracks file reads/edits & syncs token usage)
```

---

## License

Released under the [MIT License](./LICENSE).
