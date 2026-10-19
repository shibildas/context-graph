#!/usr/bin/env sh
# One-step installer for the Antigravity Context Graph & Query Cache plugin.
# Can be run after cloning the repository anywhere on your machine.

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="${HOME}/.gemini/config/plugins/context-graph"

mkdir -p "${HOME}/.gemini/config/plugins"

if [ "${REPO_DIR}" = "${TARGET_DIR}" ]; then
  echo "Plugin is already cloned directly at ${TARGET_DIR}."
else
  rm -rf "${TARGET_DIR}"
  cp -R "${REPO_DIR}" "${TARGET_DIR}"
  echo "Installed context-graph plugin to ${TARGET_DIR}."
fi

chmod +x "${TARGET_DIR}/server/db_engine.py" \
         "${TARGET_DIR}/server/mcp_server.py" \
         "${TARGET_DIR}/scripts/session_start.py" \
         "${TARGET_DIR}/scripts/post_tool_tracker.py"

echo "Done! Restart Antigravity to activate the Context Graph & Query Cache plugin."
