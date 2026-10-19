# Context Graph & Query Cache (`context-graph`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

A **Universal Multi-LLM Plugin & MCP Knowledge Graph** for **Google Antigravity**, **Claude Code**, **Cursor**, **Windsurf**, **OpenAI Codex CLI**, and **Google Gemini CLI**.

It persists **file summaries**, **symbol line maps**, **code & implementation relationships**, **LLM-queried / generated data**, **ground-truth anti-hallucination overrides**, and **token usage analytics per conversation, per LLM client, and per Git repository** in a shared local SQLite database (`~/.gemini/context-graph/cache.db`).

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

---

## Key Features

### 1. Override, Refresh Context & Fix Hallucinations (`scripts/context_ctl.py` + MCP Tools)
- **Pin Verified Ground-Truth Corrections (`cache_record_correction`)**:
  When an LLM hallucinates or makes a wrong assumption, record a high-priority ground-truth pin. It is automatically injected at the very top of `SessionStart` and `cache_get_file_context` so the LLM never repeats the mistake:
  ```bash
  python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py correct \
    --workspace /path/to/repo \
    --key "hdfc-live-env" \
    --mistake "Assuming HDFC_ENV is LIVE in production" \
    --truth "HDFC_ENV must be set to PRODUCTION in live environment"
  ```
- **Automated Hallucination Detector & Healer (`cache_verify_and_fix_hallucinations`)**:
  Audits the SQLite cache against actual files and AST symbols on disk—automatically purging deleted ghost files, removing broken relationships, and repairing phantom/drifted symbol names:
  ```bash
  python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py verify --workspace /path/to/repo
  ```
- **Granular or Full Context Refresh (`cache_refresh_context` & `cache_override_entry`)**:
  Refresh stale files (`stale_only`), force-rebuild the entire workspace graph (`force_all`), refresh a single file (`file`), purge cached queries (`purge_queries`), or hard-reset the workspace cache (`hard_reset`) while keeping your ground-truth overrides:
  ```bash
  python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py refresh --workspace /path/to/repo --mode force_all
  ```

### 2. Multi-LLM Token Usage Analytics (`cache_get_token_usage` & `scripts/token_report.py`)
- Scans transcript logs across **Antigravity**, **Claude Code**, and **Codex CLI**.
- Reports `input_tokens`, `cache_read_tokens`, `output_tokens`, `total_tokens`, and **Cache Hit Rate %** broken down by **LLM Client**, **Project / Related Git Repository**, and **Individual Conversation**:
  ```bash
  python3 ~/.gemini/config/plugins/context-graph/scripts/token_report.py
  ```

### 3. Zero-Token Static Codebase Indexing (`cache_auto_index_workspace`)
- Statically parses source files (`Python` via `ast`, plus `TypeScript`, `JavaScript`, `Go`, `Rust`, `Java`, `C/C++`, `SQL`, etc.) to extract classes, functions, line numbers, exported symbols, and `imports` relationships with zero LLM token cost.

---

## Available MCP Tools (`context-graph-mcp`)

| Tool | Description |
| :--- | :--- |
| `cache_record_correction` | Pin a verified user correction / ground-truth rule to fix and prevent repeating an LLM hallucination. |
| `cache_verify_and_fix_hallucinations` | Audit cached files, symbols, and edges against disk AST and auto-fix phantom symbols or ghost files. |
| `cache_refresh_context` | Refresh or reset context (`stale_only`, `force_all`, `file`, `purge_queries`, `hard_reset`). |
| `cache_override_entry` | Directly override or delete a specific cached `file`, `query`, `relationship`, or `override`. |
| `cache_get_token_usage` | View token usage per conversation, per LLM client, and grouped by project / Git repository. |
| `cache_auto_index_workspace` | Zero-token static indexer that scans workspace files and populates symbols and `imports` edges. |
| `cache_get_overview` | Returns workspace cache stats, ground-truth overrides, Git repo info, fresh/stale files, and relationships. |
| `cache_get_file_context` | Checks if a file is fresh (`is_stale: false`) and returns its overrides, summary, symbols, and relationships. |
| `cache_upsert_file` | Saves an LLM-enriched summary, symbol map, and outgoing dependencies with current disk `SHA-256`. |
| `cache_add_relationship` | Adds a directed relationship (`imports`, `calls`, `implements`, `extends`, `reads_data_from`, `tests`, `configures`). |
| `cache_store_query` | Saves queried data or LLM-generated datasets under a reusable `query_key`. |
| `cache_search` | Searches across all ground-truth overrides, cached file summaries, symbols, relationships, and stored queries. |

---

## License

Released under the [MIT License](./LICENSE).
