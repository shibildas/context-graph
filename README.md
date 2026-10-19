# Context Graph & Query Cache (`context-graph`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

A **Universal Multi-LLM Plugin, MCP Knowledge Graph & Web UI Control Center** for **Google Antigravity**, **Claude Code**, **Cursor**, **Windsurf**, **OpenAI Codex CLI**, and **Google Gemini CLI**.

It persists **file summaries**, **symbol line maps**, **code & implementation relationships**, **LLM-queried / generated data**, **ground-truth anti-hallucination overrides**, and **token usage analytics per conversation, per LLM client, and per Git repository** in a shared local SQLite database (`~/.gemini/context-graph/cache.db`).

---

## Interactive UI Options

1. **Live Local Web UI Control Center (`scripts/ui_server.py`)**:
   Launch a local interactive web dashboard with live SQLite actions (verify & fix hallucinations, refresh context, pin ground-truth overrides, filter token usage by repo/conversation):
   ```bash
   python3 ~/.gemini/config/plugins/context-graph/scripts/ui_server.py --port 8765
   # Open http://localhost:8765 in your browser
   ```
2. **Self-Contained HTML Artifact Export (for Antigravity Generative UI)**:
   ```bash
   python3 ~/.gemini/config/plugins/context-graph/scripts/ui_server.py --export-html ./dashboard.html
   ```
3. **Native Antigravity Plugin Management Page**:
   Open `customization://context-graph` inside Antigravity.

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

Requires **Python 3** (uses only the Python standard library—`sqlite3`, `ast`, `hashlib`, `json`, `re`, `configparser`, `http.server`—with **zero external `pip` dependencies**).

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
  ```bash
  python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py correct \
    --workspace /path/to/repo \
    --key "hdfc-live-env" \
    --mistake "Assuming HDFC_ENV is LIVE in production" \
    --truth "HDFC_ENV must be set to PRODUCTION in live environment"
  ```
- **Automated Hallucination Detector & Healer (`cache_verify_and_fix_hallucinations`)**:
  ```bash
  python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py verify --workspace /path/to/repo
  ```
- **Granular or Full Context Refresh (`cache_refresh_context` & `cache_override_entry`)**:
  ```bash
  python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py refresh --workspace /path/to/repo --mode force_all
  ```

### 2. Multi-LLM Token Usage Analytics (`cache_get_token_usage` & `scripts/token_report.py`)
```bash
python3 ~/.gemini/config/plugins/context-graph/scripts/token_report.py
```

---

## License

Released under the [MIT License](./LICENSE).
