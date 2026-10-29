// @ts-nocheck
/**
 * Context Graph & Query Cache — Native VS Code / Cursor / Windsurf / Antigravity Extension
 * Zero external npm dependencies. Powered by the Python 3 standard-library SQLite engine.
 */

const vscode = require('vscode');
const cp = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

/**
 * Resolves the root directory containing `server/db_engine.py` and `scripts/context_ctl.py`.
 * Checks:
 *   1. Bundled `backend/` inside the extension folder
 *   2. Parent repository folder (`../`) when running from `vscode-extension/`
 *   3. Global plugin installation (`~/.gemini/config/plugins/context-graph`)
 */
function resolveBackendRoot(extensionPath) {
  const candidates = [
    path.join(extensionPath, 'backend'),
    path.dirname(extensionPath),
    path.join(os.homedir(), '.gemini', 'config', 'plugins', 'context-graph'),
  ];
  for (const cand of candidates) {
    if (
      fs.existsSync(path.join(cand, 'server', 'db_engine.py')) &&
      fs.existsSync(path.join(cand, 'scripts', 'context_ctl.py'))
    ) {
      return cand;
    }
  }
  return path.dirname(extensionPath);
}

function getPythonBin() {
  const cfg = vscode.workspace.getConfiguration('contextGraph');
  return cfg.get('pythonPath') || 'python3';
}

function getActiveWorkspacePath() {
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    return folders[0].uri.fsPath;
  }
  return 'global';
}

function execPythonScript(scriptPath, args = []) {
  const py = getPythonBin();
  return new Promise((resolve, reject) => {
    cp.execFile(
      py,
      [scriptPath, ...args],
      { maxBuffer: 16 * 1024 * 1024, timeout: 30000 },
      (err, stdout, stderr) => {
        if (err) {
          reject(new Error(stderr || err.message));
          return;
        }
        resolve(stdout);
      }
    );
  });
}

class SimpleTreeProvider {
  constructor(getItemsFn) {
    this._getItemsFn = getItemsFn;
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
  }

  refresh() {
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element) {
    return element;
  }

  getChildren(element) {
    if (element && element.children) {
      return Promise.resolve(element.children);
    }
    return Promise.resolve(this._getItemsFn());
  }
}

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  const backendRoot = resolveBackendRoot(context.extensionPath);
  const ctlScript = path.join(backendRoot, 'scripts', 'context_ctl.py');
  const uiScript = path.join(backendRoot, 'scripts', 'ui_server.py');
  const mcpScript = path.join(backendRoot, 'server', 'mcp_server.py');

  let cachedState = null;
  let currentWebviewPanel = null;

  // Status Bar Item
  const statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100
  );
  statusBarItem.command = 'contextGraph.openDashboard';
  statusBarItem.tooltip = 'Click to open Context Graph 3D Control Center & Cost-per-Feature Analytics';
  context.subscriptions.push(statusBarItem);

  // Tree Providers
  const featuresProvider = new SimpleTreeProvider(() => {
    if (!cachedState || !cachedState.token_report) {
      return [new vscode.TreeItem('Loading token & feature metrics...')];
    }
    const tr = cachedState.token_report;
    const gt = tr.grand_totals || {};
    const summaryItem = new vscode.TreeItem(
      `Total: $${Number(gt.estimated_cost_usd || 0).toFixed(2)} | Saved: $${Number(gt.estimated_cache_savings_usd || 0).toFixed(2)}`,
      vscode.TreeItemCollapsibleState.None
    );
    summaryItem.description = `${gt.total_conversations || 0} convs • ${gt.plugin_calls || 0} plugin calls`;
    summaryItem.iconPath = new vscode.ThemeIcon('graph');
    summaryItem.command = {
      command: 'contextGraph.openDashboard',
      title: 'Open Dashboard',
    };

    const featureItems = (tr.by_feature || []).slice(0, 40).map((f) => {
      const ticketPrefix = f.ticket_id ? `${f.ticket_id} ` : '';
      const item = new vscode.TreeItem(
        `${ticketPrefix}${f.feature_name}`,
        vscode.TreeItemCollapsibleState.None
      );
      const savedStr =
        f.plugin_calls > 0
          ? ` (Saved $${Number(f.estimated_cache_savings_usd || 0).toFixed(2)})`
          : '';
      item.description = `$${Number(f.estimated_cost_usd || 0).toFixed(2)}${savedStr} • ${f.repo_name}`;
      item.tooltip = `Feature: ${f.feature_name}\nRepo: ${f.repo_name}\nBranch: ${f.git_branch}\nTokens: ${Number(f.total_tokens || 0).toLocaleString()}\nPlugin Used: ${f.plugin_calls > 0 ? `Yes (${f.plugin_calls} calls)` : 'No ($0.00 saved)'}`;
      item.iconPath = new vscode.ThemeIcon(
        f.plugin_calls > 0 ? 'sparkle' : 'git-branch'
      );
      return item;
    });

    return [summaryItem, ...featureItems];
  });

  const overridesProvider = new SimpleTreeProvider(() => {
    if (!cachedState || !cachedState.overviews) {
      return [new vscode.TreeItem('No ground-truth overrides loaded')];
    }
    const ws = getActiveWorkspacePath();
    const ov =
      cachedState.overviews[ws] ||
      Object.values(cachedState.overviews)[0] ||
      {};
    const list = ov.ground_truth_overrides || [];
    if (list.length === 0) {
      const empty = new vscode.TreeItem(
        'No active overrides — click (+) to pin a rule'
      );
      empty.iconPath = new vscode.ThemeIcon('info');
      empty.command = {
        command: 'contextGraph.addOverride',
        title: 'Add Ground-Truth Override',
      };
      return [empty];
    }
    return list.map((o) => {
      const item = new vscode.TreeItem(
        `[${(o.priority || 'high').toUpperCase()}] ${o.override_key}`,
        vscode.TreeItemCollapsibleState.None
      );
      item.description = o.verified_truth;
      item.tooltip = `Rule: ${o.verified_truth}\nPrevents: ${o.hallucination_or_mistake || 'N/A'}`;
      item.iconPath = new vscode.ThemeIcon('pinned');
      return item;
    });
  });

  const filesProvider = new SimpleTreeProvider(() => {
    if (!cachedState || !cachedState.overviews) {
      return [new vscode.TreeItem('Workspace not indexed yet')];
    }
    const ws = getActiveWorkspacePath();
    const ov =
      cachedState.overviews[ws] ||
      Object.values(cachedState.overviews)[0] ||
      {};
    const files = ov.files || [];
    if (files.length === 0) {
      const empty = new vscode.TreeItem(
        'Click sync icon to auto-index workspace (0 tokens)'
      );
      empty.iconPath = new vscode.ThemeIcon('sync');
      empty.command = {
        command: 'contextGraph.indexWorkspace',
        title: 'Auto-Index Workspace',
      };
      return [empty];
    }
    return files.map((f) => {
      const item = new vscode.TreeItem(
        f.rel_path,
        vscode.TreeItemCollapsibleState.None
      );
      item.description = `${f.is_stale ? 'STALE' : 'FRESH'} • ${f.symbol_count || 0} symbols`;
      item.tooltip = `${f.rel_path}\n${f.summary || ''}\nSymbols: ${(f.key_symbols || []).join(', ')}`;
      item.iconPath = new vscode.ThemeIcon(
        f.is_stale ? 'warning' : 'pass-filled'
      );
      if (f.file_path && fs.existsSync(f.file_path)) {
        item.command = {
          command: 'vscode.open',
          title: 'Open File',
          arguments: [vscode.Uri.file(f.file_path)],
        };
      }
      return item;
    });
  });

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider(
      'contextGraphFeatures',
      featuresProvider
    ),
    vscode.window.registerTreeDataProvider(
      'contextGraphOverrides',
      overridesProvider
    ),
    vscode.window.registerTreeDataProvider('contextGraphFiles', filesProvider)
  );

  async function refreshAllState(toastMessage = '') {
    const ws = getActiveWorkspacePath();
    try {
      const raw = await execPythonScript(uiScript, [
        '--dump-state',
        '--workspace',
        ws === 'global' ? '' : ws,
      ]);
      cachedState = JSON.parse(raw);

      featuresProvider.refresh();
      overridesProvider.refresh();
      filesProvider.refresh();

      const cfg = vscode.workspace.getConfiguration('contextGraph');
      if (cfg.get('showStatusBarCost', true)) {
        const gt = (cachedState.token_report || {}).grand_totals || {};
        const cost = Number(gt.estimated_cost_usd || 0).toFixed(2);
        const saved = Number(gt.estimated_cache_savings_usd || 0).toFixed(2);
        statusBarItem.text = `$(graph) CG: $${cost} (Saved $${saved})`;
        statusBarItem.show();
      } else {
        statusBarItem.hide();
      }

      if (currentWebviewPanel) {
        currentWebviewPanel.webview.postMessage({
          type: 'stateUpdate',
          state: cachedState,
          toastMessage,
        });
      }
    } catch (err) {
      statusBarItem.text = '$(graph) Context Graph';
      statusBarItem.show();
    }
  }

  // Commands
  context.subscriptions.push(
    vscode.commands.registerCommand('contextGraph.refreshTrees', async () => {
      await refreshAllState();
    }),

    vscode.commands.registerCommand('contextGraph.openDashboard', async () => {
      const ws = getActiveWorkspacePath();
      if (currentWebviewPanel) {
        currentWebviewPanel.reveal(vscode.ViewColumn.One);
        await refreshAllState();
        return;
      }

      currentWebviewPanel = vscode.window.createWebviewPanel(
        'contextGraphDashboard',
        'Context Graph — Control Center',
        vscode.ViewColumn.One,
        {
          enableScripts: true,
          retainContextWhenHidden: true,
        }
      );

      currentWebviewPanel.onDidDispose(() => {
        currentWebviewPanel = null;
      });

      currentWebviewPanel.webview.onDidReceiveMessage(async (msg) => {
        if (!msg || typeof msg !== 'object') return;
        const targetWs =
          msg.workspace_path && msg.workspace_path !== '__sqlite_schema__'
            ? msg.workspace_path
            : ws;

        if (msg.type === 'reloadState') {
          await refreshAllState();
        } else if (msg.type === 'apiAction') {
          let out = '';
          if (msg.action === 'verify') {
            out = await execPythonScript(ctlScript, [
              'verify',
              '--workspace',
              targetWs,
            ]);
          } else if (msg.action === 'refresh_stale') {
            out = await execPythonScript(ctlScript, [
              'refresh',
              '--workspace',
              targetWs,
              '--mode',
              'stale_only',
            ]);
          } else if (msg.action === 'refresh_all') {
            out = await execPythonScript(ctlScript, [
              'refresh',
              '--workspace',
              targetWs,
              '--mode',
              'force_all',
            ]);
          }
          await refreshAllState(out.trim());
        } else if (msg.type === 'submitOverride') {
          const out = await execPythonScript(ctlScript, [
            'correct',
            '--workspace',
            targetWs,
            '--key',
            msg.override_key,
            '--truth',
            msg.verified_truth,
            '--mistake',
            msg.hallucination_or_mistake || '',
            '--priority',
            msg.priority || 'high',
          ]);
          await refreshAllState(out.trim());
          vscode.window.showInformationMessage(
            `Pinned Ground-Truth Override: ${msg.override_key}`
          );
        }
      });

      const tmpHtml = path.join(
        os.tmpdir(),
        `context-graph-vscode-${process.pid}.html`
      );
      try {
        await execPythonScript(uiScript, [
          '--export-html',
          tmpHtml,
          '--workspace',
          ws === 'global' ? '' : ws,
        ]);
        currentWebviewPanel.webview.html = fs.readFileSync(tmpHtml, 'utf8');
      } catch (err) {
        currentWebviewPanel.webview.html = `<html><body style="padding:24px;font-family:sans-serif;color:#f87171"><h3>Failed to load Context Graph Dashboard</h3><pre>${err.message}</pre></body></html>`;
      }
    }),

    vscode.commands.registerCommand('contextGraph.indexWorkspace', async () => {
      const ws = getActiveWorkspacePath();
      if (ws === 'global') {
        vscode.window.showWarningMessage(
          'Open a workspace folder first to index its files.'
        );
        return;
      }
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'Context Graph: Indexing workspace (zero LLM tokens)...',
        },
        async () => {
          const out = await execPythonScript(ctlScript, [
            'refresh',
            '--workspace',
            ws,
            '--mode',
            'force_all',
          ]);
          await refreshAllState(out);
          vscode.window.showInformationMessage(
            `Context Graph indexed workspace: ${path.basename(ws)}`
          );
        }
      );
    }),

    vscode.commands.registerCommand(
      'contextGraph.verifyHallucinations',
      async () => {
        const ws = getActiveWorkspacePath();
        const out = await execPythonScript(ctlScript, [
          'verify',
          '--workspace',
          ws,
        ]);
        const res = JSON.parse(out);
        await refreshAllState(out);
        vscode.window.showInformationMessage(
          `Hallucination Audit Complete: ${res.issues_found || 0} issue(s) found, ${res.auto_fixed || 0} auto-fixed.`
        );
      }
    ),

    vscode.commands.registerCommand('contextGraph.addOverride', async () => {
      const ws = getActiveWorkspacePath();
      const key = await vscode.window.showInputBox({
        prompt: 'Override Identifier Slug (e.g. auth-flow-v2)',
        placeHolder: 'auth-flow-v2',
      });
      if (!key) return;

      const truth = await vscode.window.showInputBox({
        prompt: 'Verified Ground-Truth Rule (authoritative fact)',
        placeHolder: 'AdmissionV3 uses AdmissionV3Engine, never legacy V1',
      });
      if (!truth) return;

      const mistake = await vscode.window.showInputBox({
        prompt: 'Hallucination or Mistake to Prevent (optional)',
        placeHolder: 'Assuming v1 controller handles v3 routes',
      });

      const priority = await vscode.window.showQuickPick(
        ['critical', 'high', 'normal'],
        { placeHolder: 'Select override priority' }
      );

      await execPythonScript(ctlScript, [
        'correct',
        '--workspace',
        ws,
        '--key',
        key,
        '--truth',
        truth,
        '--mistake',
        mistake || '',
        '--priority',
        priority || 'high',
      ]);
      await refreshAllState();
      vscode.window.showInformationMessage(
        `Pinned Ground-Truth Override [${key}]`
      );
    }),

    vscode.commands.registerCommand(
      'contextGraph.exportOverrides',
      async () => {
        const ws = getActiveWorkspacePath();
        if (ws === 'global') return;
        const out = await execPythonScript(ctlScript, [
          'export-overrides',
          '--workspace',
          ws,
        ]);
        const res = JSON.parse(out);
        vscode.window.showInformationMessage(
          `Exported ${res.exported_count} override(s) to ${res.file_path}`
        );
      }
    ),

    vscode.commands.registerCommand(
      'contextGraph.importOverrides',
      async () => {
        const ws = getActiveWorkspacePath();
        if (ws === 'global') return;
        const out = await execPythonScript(ctlScript, [
          'import-overrides',
          '--workspace',
          ws,
        ]);
        const res = JSON.parse(out);
        await refreshAllState();
        vscode.window.showInformationMessage(
          `Imported ${res.imported_count} override(s) from ${res.file_path}`
        );
      }
    ),

    vscode.commands.registerCommand('contextGraph.refreshStale', async () => {
      const ws = getActiveWorkspacePath();
      await execPythonScript(ctlScript, [
        'refresh',
        '--workspace',
        ws,
        '--mode',
        'stale_only',
      ]);
      await refreshAllState();
      vscode.window.showInformationMessage('Refreshed stale files in Context Graph.');
    }),

    vscode.commands.registerCommand(
      'contextGraph.installMcpConfig',
      async () => {
        const ws = getActiveWorkspacePath();
        if (ws === 'global') {
          vscode.window.showWarningMessage('Open a workspace folder first.');
          return;
        }
        const mcpPayload = {
          mcpServers: {
            'context-graph-mcp': {
              command: getPythonBin(),
              args: [mcpScript],
              env: {
                PYTHONUNBUFFERED: '1',
              },
            },
          },
        };
        const mcpFile = path.join(ws, '.mcp.json');
        fs.writeFileSync(mcpFile, JSON.stringify(mcpPayload, null, 2) + '\n');
        vscode.window.showInformationMessage(
          `Configured Context Graph MCP server in ${mcpFile}`
        );
      }
    )
  );

  // Auto-index on file save
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (doc) => {
      const cfg = vscode.workspace.getConfiguration('contextGraph');
      if (!cfg.get('autoIndexOnSave', true)) return;
      const ws = getActiveWorkspacePath();
      if (ws === 'global' || !doc.uri.fsPath.startsWith(ws)) return;
      try {
        await execPythonScript(ctlScript, [
          'refresh',
          '--workspace',
          ws,
          '--mode',
          'file',
          '--target',
          doc.uri.fsPath,
        ]);
        await refreshAllState();
      } catch (_) {}
    })
  );

  // Startup initialization: auto-import `.context-graph/overrides.json` if present, then load state
  (async () => {
    const ws = getActiveWorkspacePath();
    const cfg = vscode.workspace.getConfiguration('contextGraph');
    if (
      ws !== 'global' &&
      cfg.get('autoImportOverridesOnStartup', true) &&
      fs.existsSync(path.join(ws, '.context-graph', 'overrides.json'))
    ) {
      try {
        await execPythonScript(ctlScript, [
          'import-overrides',
          '--workspace',
          ws,
        ]);
      } catch (_) {}
    }
    await refreshAllState();
  })();
}

function deactivate() {}

module.exports = {
  activate,
  deactivate,
};
