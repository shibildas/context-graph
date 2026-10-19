#!/usr/bin/env sh
# Universal Installer for the Context Graph & Query Cache plugin.
# Installs into Google Antigravity, and optionally registers MCP for Claude Code, Cursor, and Gemini CLI.
#
# Usage:
#   sh ./install.sh            # Installs into Antigravity + auto-detects Claude/Cursor/Gemini CLI
#   sh ./install.sh --all      # Installs into all supported LLM clients

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
AGY_TARGET="${HOME}/.gemini/config/plugins/context-graph"

chmod +x "${REPO_DIR}/server/db_engine.py" \
         "${REPO_DIR}/server/mcp_server.py" \
         "${REPO_DIR}/scripts/session_start.py" \
         "${REPO_DIR}/scripts/post_tool_tracker.py" \
         "${REPO_DIR}/scripts/token_report.py" \
         "${REPO_DIR}/scripts/context_ctl.py" \
         "${REPO_DIR}/scripts/ui_server.py"

# 1. Install into Google Antigravity
mkdir -p "${HOME}/.gemini/config/plugins"
if [ "${REPO_DIR}" = "${AGY_TARGET}" ]; then
  echo "[Antigravity] Plugin already at ${AGY_TARGET}."
else
  rm -rf "${AGY_TARGET}"
  cp -R "${REPO_DIR}" "${AGY_TARGET}"
  echo "[Antigravity] Installed plugin to ${AGY_TARGET}."
fi

SERVER_SCRIPT="${AGY_TARGET}/server/mcp_server.py"

# 2. Register MCP server in Cursor (~/.cursor/mcp.json) if ~/.cursor exists or --all passed
if [ -d "${HOME}/.cursor" ] || [ "$1" = "--all" ]; then
  mkdir -p "${HOME}/.cursor"
  python3 - "${HOME}/.cursor/mcp.json" "${SERVER_SCRIPT}" <<'PYEOF'
import json, os, sys
cfg_path, srv = sys.argv[1], sys.argv[2]
data = {}
if os.path.isfile(cfg_path):
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
data.setdefault("mcpServers", {})["context-graph-mcp"] = {
    "command": "python3",
    "args": [srv],
    "env": {"PYTHONUNBUFFERED": "1"},
}
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
print(f"[Cursor] Registered context-graph-mcp in {cfg_path}.")
PYEOF
fi

# 3. Register plugin & MCP in Claude Code (~/.claude/plugins/context-graph) if ~/.claude exists or --all passed
if [ -d "${HOME}/.claude" ] || [ "$1" = "--all" ]; then
  CLAUDE_TARGET="${HOME}/.claude/plugins/context-graph"
  mkdir -p "${HOME}/.claude/plugins"
  if [ "${REPO_DIR}" != "${CLAUDE_TARGET}" ]; then
    rm -rf "${CLAUDE_TARGET}"
    cp -R "${REPO_DIR}" "${CLAUDE_TARGET}"
  fi
  echo "[Claude Code] Installed plugin to ${CLAUDE_TARGET}."
fi

echo ""
echo "Installation complete!"
echo "- Launch Interactive Web UI: python3 ${AGY_TARGET}/scripts/ui_server.py --port 8765"
echo "- View token usage CLI:      python3 ${AGY_TARGET}/scripts/token_report.py"
echo "- Override/Refresh CLI:      python3 ${AGY_TARGET}/scripts/context_ctl.py --help"
echo "- Restart your LLM client (Antigravity / Claude Code / Cursor) to load context-graph-mcp."
