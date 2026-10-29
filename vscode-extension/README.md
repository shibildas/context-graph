# Context Graph & Query Cache — VS Code Extension

Native **VS Code / Cursor / Windsurf / Antigravity IDE** extension for **Context Graph & Query Cache**.

## Features

1. **Activity Bar & 3 Sidebar Tree Views**:
   - **Cost per Feature & Token Spend**: Live breakdown of LLM spend and `context-graph` plugin savings grouped by Git feature branch, ticket (`#1643`, `#584`), and task.
   - **Ground-Truth Overrides (Anti-Hallucination)**: View, pin, export, and import authoritative domain rules (`.context-graph/overrides.json`).
   - **Tracked Files & Symbol Graph**: Inspect `[FRESH]` vs. `[STALE]` cached files, AST symbol counts, and click any file to jump directly to it in the editor.
2. **Interactive 3D Control Center Webview (`Context Graph: Open 3D Control Center & Token Analytics`)**:
   - Native VS Code Webview panel featuring the interactive 3D force-directed data model & file graph, Cost-per-Feature tables, and one-click hallucination verification.
3. **Live Status Bar Spend & Savings Badge**:
   - Displays `$(graph) CG: $X.XX (Saved $Y.YY)` in the status bar and opens the 3D Control Center when clicked.
4. **Automatic File Save Indexing & Team Overrides Sync**:
   - Automatically updates file AST symbols and SHA-256 signatures in SQLite on file save (`contextGraph.autoIndexOnSave`).
   - Automatically imports `.context-graph/overrides.json` when opening a workspace (`contextGraph.autoImportOverridesOnStartup`).

## One-Command Installation (VS Code / Cursor / Windsurf / Antigravity)

From the repository root, run:

```bash
python3 vscode-extension/install_vscode_ext.py
```

Then run **`Developer: Reload Window`** in your IDE (`Cmd+Shift+P` / `Ctrl+Shift+P`).

## Packaging as a `.vsix` File (Optional)

```bash
python3 vscode-extension/install_vscode_ext.py
cd vscode-extension
npx @vscode/vsce package
```
