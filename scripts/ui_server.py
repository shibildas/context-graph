#!/usr/bin/env python3
"""
Interactive Web UI & Artifact Dashboard Generator for the Context Graph & Query Cache plugin.
Provides:
  1. Live local Web UI Control Center (`python3 scripts/ui_server.py --port 8765`) with REST endpoints
     for viewing Multi-LLM token usage, browsing file relationships, pinning ground-truth overrides,
     running hallucination verification, and refreshing workspace context.
  2. Static self-contained HTML artifact exporter (`python3 scripts/ui_server.py --export-html /path/to/out.html`)
     for rendering directly inside Antigravity's Generative UI side pane.
"""

import argparse
import http.server
import json
import os
import sys
import urllib.parse
from typing import Any, Dict

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "server"))

import db_engine


def collect_full_state(workspace_filter: str = "") -> Dict[str, Any]:
    token_report = db_engine.get_token_usage_report(
        workspace_path=workspace_filter if workspace_filter else None,
        limit=100,
    )
    conn = db_engine.get_connection()
    try:
        ws_rows = conn.execute(
            "SELECT DISTINCT workspace_path FROM files UNION SELECT DISTINCT workspace_path FROM ground_truth_overrides"
        ).fetchall()
        workspaces = sorted(
            list({r[0] for r in ws_rows if r[0] and r[0] != "global"})
        )
        if not workspaces and workspace_filter:
            workspaces = [db_engine.normalize_workspace(workspace_filter)]

        overviews: Dict[str, Any] = {}
        for ws in workspaces[:15]:
            overviews[ws] = db_engine.get_overview(ws, max_items=60)
        global_ov = db_engine.get_overview("global", max_items=30)
        if (
            global_ov["files"]
            or global_ov["ground_truth_overrides"]
            or global_ov["cached_queries"]
        ):
            overviews["global"] = global_ov
    finally:
        conn.close()

    return {
        "token_report": token_report,
        "workspaces": workspaces,
        "overviews": overviews,
    }


DASHBOARD_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Context Graph &amp; Query Cache — Control Center</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    body {
      background-color: var(--background);
      color: var(--foreground);
    }
    .cg-card {
      background-color: var(--card);
      border: 1px solid var(--border);
    }
    .cg-muted {
      color: var(--muted-foreground);
    }
    .cg-input {
      background-color: var(--background);
      border: 1px solid var(--border);
      color: var(--foreground);
    }
    .cg-btn-primary {
      background-color: #6366f1;
      color: #ffffff;
    }
    .cg-btn-primary:hover {
      background-color: #4f46e5;
    }
  </style>
</head>
<body class="antialiased p-6 min-h-screen">
  <div class="max-w-7xl mx-auto space-y-6">
    <!-- Header -->
    <div class="cg-card rounded-xl p-5 flex flex-wrap items-center justify-between gap-4 shadow-sm">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-indigo-500/20 border border-indigo-400/40 flex items-center justify-center text-indigo-400 font-bold text-lg">
          CG
        </div>
        <div>
          <h1 class="text-xl font-bold tracking-tight">Context Graph &amp; Query Cache</h1>
          <p class="text-xs cg-muted">Multi-LLM Token Analytics • File &amp; Symbol Graph • Anti-Hallucination Ground-Truth Control Center</p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span id="mode-badge" class="text-xs px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-medium">
          SQLite Cache Active
        </span>
        <button onclick="reloadState()" id="btn-sync" class="text-xs px-3 py-1.5 rounded-lg cg-btn-primary font-medium transition">
          Sync &amp; Refresh Data
        </button>
      </div>
    </div>

    <!-- KPI Cards -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4" id="kpi-grid"></div>

    <!-- Navigation Tabs -->
    <div class="flex flex-wrap gap-2 border-b border-[var(--border,#334155)] pb-2">
      <button onclick="switchTab('tokens')" id="tab-tokens" class="px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600 text-white">
        1. Token Usage &amp; Git Repos
      </button>
      <button onclick="switchTab('graph')" id="tab-graph" class="px-4 py-2 rounded-lg text-sm font-medium cg-card cg-muted">
        2. Context Graph &amp; Files
      </button>
      <button onclick="switchTab('overrides')" id="tab-overrides" class="px-4 py-2 rounded-lg text-sm font-medium cg-card cg-muted">
        3. Anti-Hallucination &amp; Overrides
      </button>
      <button onclick="switchTab('queries')" id="tab-queries" class="px-4 py-2 rounded-lg text-sm font-medium cg-card cg-muted">
        4. Cached Queries &amp; Data
      </button>
    </div>

    <!-- Tab 1: Token Usage -->
    <div id="view-tokens" class="space-y-6">
      <div class="cg-card rounded-xl p-5 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-base font-semibold">Token Usage by LLM Client</h2>
          <span class="text-xs cg-muted">Automatically scanned from Antigravity, Claude Code &amp; Codex CLI transcripts</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse text-sm">
            <thead>
              <tr class="border-b border-[var(--border,#334155)] text-xs cg-muted">
                <th class="py-2 px-3">LLM Client</th>
                <th class="py-2 px-3 text-right">Conversations</th>
                <th class="py-2 px-3 text-right">Turns</th>
                <th class="py-2 px-3 text-right">Input Tokens</th>
                <th class="py-2 px-3 text-right">Cache Read Tokens</th>
                <th class="py-2 px-3 text-right">Output Tokens</th>
                <th class="py-2 px-3 text-right">Total Tokens</th>
                <th class="py-2 px-3 text-right">Cache Hit %</th>
              </tr>
            </thead>
            <tbody id="table-clients"></tbody>
          </table>
        </div>
      </div>

      <div class="cg-card rounded-xl p-5 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-base font-semibold">Token Usage by Project / Related Git Repository</h2>
          <input id="repo-search" oninput="renderTokens()" type="text" placeholder="Filter repo or branch..." class="cg-input rounded-lg px-3 py-1.5 text-xs w-64" />
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse text-sm">
            <thead>
              <tr class="border-b border-[var(--border,#334155)] text-xs cg-muted">
                <th class="py-2 px-3">Project / Git Repo</th>
                <th class="py-2 px-3">Branch</th>
                <th class="py-2 px-3 text-right">Convs</th>
                <th class="py-2 px-3 text-right">Turns</th>
                <th class="py-2 px-3 text-right">Input Tokens</th>
                <th class="py-2 px-3 text-right">Cache Read</th>
                <th class="py-2 px-3 text-right">Output</th>
                <th class="py-2 px-3 text-right">Total Tokens</th>
                <th class="py-2 px-3 text-right">Cache Hit %</th>
              </tr>
            </thead>
            <tbody id="table-repos"></tbody>
          </table>
        </div>
      </div>

      <div class="cg-card rounded-xl p-5 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-base font-semibold">Token Usage per Conversation</h2>
          <input id="conv-search" oninput="renderTokens()" type="text" placeholder="Search prompt, repo, or ID..." class="cg-input rounded-lg px-3 py-1.5 text-xs w-72" />
        </div>
        <div class="overflow-x-auto max-h-96 overflow-y-auto">
          <table class="w-full text-left border-collapse text-sm">
            <thead>
              <tr class="border-b border-[var(--border,#334155)] text-xs cg-muted">
                <th class="py-2 px-3">Client</th>
                <th class="py-2 px-3">Conv ID</th>
                <th class="py-2 px-3">Prompt / Title</th>
                <th class="py-2 px-3">Project / Repo</th>
                <th class="py-2 px-3 text-right">Turns</th>
                <th class="py-2 px-3 text-right">Input</th>
                <th class="py-2 px-3 text-right">Cache Read</th>
                <th class="py-2 px-3 text-right">Output</th>
                <th class="py-2 px-3 text-right">Total Tokens</th>
                <th class="py-2 px-3 text-right">Hit %</th>
              </tr>
            </thead>
            <tbody id="table-convs"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Tab 2: Context Graph & Files -->
    <div id="view-graph" class="space-y-6 hidden">
      <div class="cg-card rounded-xl p-5 flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <label class="text-xs font-medium cg-muted">Workspace:</label>
          <select id="ws-select" onchange="renderGraph()" class="cg-input rounded-lg px-3 py-1.5 text-xs"></select>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button onclick="apiAction('verify')" class="text-xs px-3 py-1.5 rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40 font-medium">
            Verify &amp; Fix Hallucinated Symbols
          </button>
          <button onclick="apiAction('refresh_stale')" class="text-xs px-3 py-1.5 rounded-lg bg-sky-500/20 text-sky-300 border border-sky-500/40 font-medium">
            Refresh Stale Files
          </button>
          <button onclick="apiAction('refresh_all')" class="text-xs px-3 py-1.5 rounded-lg cg-btn-primary font-medium">
            Force Rebuild All
          </button>
        </div>
      </div>

      <div id="action-toast" class="hidden cg-card rounded-xl p-4 border-l-4 border-indigo-500 text-xs font-mono whitespace-pre-wrap"></div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2 cg-card rounded-xl p-5 space-y-3">
          <h3 class="text-base font-semibold">Tracked Files &amp; AST Symbols</h3>
          <div id="files-list" class="space-y-2.5 max-h-[500px] overflow-y-auto pr-1"></div>
        </div>
        <div class="cg-card rounded-xl p-5 space-y-3">
          <h3 class="text-base font-semibold">File &amp; Implementation Relationships</h3>
          <div id="rels-list" class="space-y-2 max-h-[500px] overflow-y-auto pr-1"></div>
        </div>
      </div>
    </div>

    <!-- Tab 3: Anti-Hallucination & Overrides -->
    <div id="view-overrides" class="space-y-6 hidden">
      <div class="cg-card rounded-xl p-5 space-y-4">
        <h3 class="text-base font-semibold">Pin a Verified Ground-Truth Override (Anti-Hallucination Pin)</h3>
        <p class="text-xs cg-muted">
          Ground-truth pins are injected at the top of SessionStart and file context lookups so the LLM never repeats a corrected mistake.
        </p>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input id="ov-ws" type="text" placeholder="Workspace path (or 'global')" class="cg-input rounded-lg px-3 py-2 text-xs" />
          <input id="ov-key" type="text" placeholder="Override slug (e.g. hdfc-live-env)" class="cg-input rounded-lg px-3 py-2 text-xs" />
          <select id="ov-priority" class="cg-input rounded-lg px-3 py-2 text-xs">
            <option value="critical">Priority: CRITICAL</option>
            <option value="high" selected>Priority: HIGH</option>
            <option value="normal">Priority: NORMAL</option>
          </select>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <input id="ov-mistake" type="text" placeholder="Hallucination / false assumption to prevent..." class="cg-input rounded-lg px-3 py-2 text-xs" />
          <input id="ov-truth" type="text" placeholder="Verified ground-truth rule that MUST be followed..." class="cg-input rounded-lg px-3 py-2 text-xs" />
        </div>
        <div class="flex items-center justify-between gap-3">
          <span id="ov-cli-preview" class="text-xs font-mono cg-muted truncate"></span>
          <button onclick="submitOverride()" class="px-4 py-2 rounded-lg cg-btn-primary text-xs font-semibold">
            Save Ground-Truth Pin
          </button>
        </div>
      </div>

      <div class="cg-card rounded-xl p-5 space-y-3">
        <h3 class="text-base font-semibold">Active Ground-Truth Overrides</h3>
        <div id="overrides-list" class="space-y-2.5"></div>
      </div>
    </div>

    <!-- Tab 4: Cached Queries -->
    <div id="view-queries" class="space-y-6 hidden">
      <div class="cg-card rounded-xl p-5 space-y-3">
        <h3 class="text-base font-semibold">Stored Queries &amp; Generated Data</h3>
        <div id="queries-list" class="space-y-3"></div>
      </div>
    </div>
  </div>

  <script>
    let STATE = __INITIAL_STATE_JSON__;
    const IS_LIVE_SERVER = window.location.protocol.startsWith('http');

    function fmtNum(n) {
      return Number(n || 0).toLocaleString();
    }

    function switchTab(tab) {
      ['tokens', 'graph', 'overrides', 'queries'].forEach(t => {
        document.getElementById('view-' + t).classList.toggle('hidden', t !== tab);
        const btn = document.getElementById('tab-' + t);
        if (t === tab) {
          btn.className = 'px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600 text-white';
        } else {
          btn.className = 'px-4 py-2 rounded-lg text-sm font-medium cg-card cg-muted';
        }
      });
    }

    function renderKPIs() {
      const gt = STATE.token_report.grand_totals;
      let totalFiles = 0, totalRels = 0, totalOverrides = 0;
      Object.values(STATE.overviews || {}).forEach(ov => {
        totalFiles += (ov.stats?.total_cached_files || 0);
        totalRels += (ov.stats?.total_relationships || 0);
        totalOverrides += (ov.stats?.active_ground_truth_overrides || 0);
      });

      const cards = [
        { label: 'Total Tokens Tracked', val: fmtNum(gt.total_tokens), sub: `${gt.total_conversations} conversations` },
        { label: 'Cache Hit Efficiency', val: `${gt.cache_hit_rate_pct}%`, sub: `${fmtNum(gt.cache_read_tokens)} cached tokens` },
        { label: 'Input / Output Tokens', val: fmtNum(gt.input_tokens), sub: `${fmtNum(gt.output_tokens)} output tokens` },
        { label: 'Indexed Files & Edges', val: `${totalFiles} files`, sub: `${totalRels} implementation edges` },
        { label: 'Ground-Truth Pins', val: `${totalOverrides}`, sub: `Anti-hallucination overrides` },
      ];

      document.getElementById('kpi-grid').innerHTML = cards.map(c => `
        <div class="cg-card rounded-xl p-4">
          <div class="text-xs cg-muted">${c.label}</div>
          <div class="text-xl font-bold mt-1">${c.val}</div>
          <div class="text-xs cg-muted mt-1">${c.sub}</div>
        </div>
      `).join('');
    }

    function renderTokens() {
      const tr = STATE.token_report;
      document.getElementById('table-clients').innerHTML = (tr.by_client || []).map(c => `
        <tr class="border-b border-[var(--border,#334155)]/50">
          <td class="py-2.5 px-3 font-semibold text-indigo-400">${c.client_source}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(c.conversation_count)}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(c.total_turns)}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(c.input_tokens)}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(c.cache_read_tokens)}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(c.output_tokens)}</td>
          <td class="py-2.5 px-3 text-right font-bold">${fmtNum(c.total_tokens)}</td>
          <td class="py-2.5 px-3 text-right text-emerald-400 font-medium">${c.cache_hit_rate_pct}%</td>
        </tr>
      `).join('');

      const rFilter = (document.getElementById('repo-search')?.value || '').toLowerCase();
      const repos = (tr.by_project_repo || []).filter(r =>
        !rFilter ||
        (r.repo_name || '').toLowerCase().includes(rFilter) ||
        (r.project_root || '').toLowerCase().includes(rFilter) ||
        (r.git_branch || '').toLowerCase().includes(rFilter)
      );
      document.getElementById('table-repos').innerHTML = repos.map(r => `
        <tr class="border-b border-[var(--border,#334155)]/50">
          <td class="py-2.5 px-3">
            <div class="font-semibold">${r.repo_name}</div>
            <div class="text-xs cg-muted truncate max-w-xs">${r.project_root}</div>
          </td>
          <td class="py-2.5 px-3 font-mono text-xs text-sky-400">${r.git_branch || '-'}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(r.conversation_count)}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(r.total_turns)}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(r.input_tokens)}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(r.cache_read_tokens)}</td>
          <td class="py-2.5 px-3 text-right">${fmtNum(r.output_tokens)}</td>
          <td class="py-2.5 px-3 text-right font-bold">${fmtNum(r.total_tokens)}</td>
          <td class="py-2.5 px-3 text-right text-emerald-400 font-medium">${r.cache_hit_rate_pct}%</td>
        </tr>
      `).join('');

      const cFilter = (document.getElementById('conv-search')?.value || '').toLowerCase();
      const convs = (tr.by_conversation || []).filter(c =>
        !cFilter ||
        (c.title || '').toLowerCase().includes(cFilter) ||
        (c.repo_name || '').toLowerCase().includes(cFilter) ||
        (c.conversation_id || '').toLowerCase().includes(cFilter)
      );
      document.getElementById('table-convs').innerHTML = convs.map(c => `
        <tr class="border-b border-[var(--border,#334155)]/50">
          <td class="py-2 px-3 text-xs font-mono text-indigo-400">${c.client_source}</td>
          <td class="py-2 px-3 text-xs font-mono cg-muted">${c.conversation_id.slice(0, 8)}...</td>
          <td class="py-2 px-3 max-w-xs truncate" title="${(c.title || '').replace(/"/g, '&quot;')}">${c.title}</td>
          <td class="py-2 px-3 font-medium">${c.repo_name}</td>
          <td class="py-2 px-3 text-right">${fmtNum(c.turn_count)}</td>
          <td class="py-2 px-3 text-right">${fmtNum(c.input_tokens)}</td>
          <td class="py-2 px-3 text-right">${fmtNum(c.cache_read_tokens)}</td>
          <td class="py-2 px-3 text-right">${fmtNum(c.output_tokens)}</td>
          <td class="py-2 px-3 text-right font-bold">${fmtNum(c.total_tokens)}</td>
          <td class="py-2 px-3 text-right text-emerald-400">${c.cache_hit_rate_pct}%</td>
        </tr>
      `).join('');
    }

    function initWorkspaces() {
      const sel = document.getElementById('ws-select');
      const keys = Object.keys(STATE.overviews || {});
      sel.innerHTML = keys.map(k => `<option value="${k}">${k}</option>`).join('');
      if (keys.length > 0 && !document.getElementById('ov-ws').value) {
        document.getElementById('ov-ws').value = keys[0];
      }
      renderGraph();
      renderOverridesAndQueries();
    }

    function renderGraph() {
      const ws = document.getElementById('ws-select')?.value;
      const ov = (STATE.overviews || {})[ws] || { files: [], relationships: [] };

      const filesHtml = (ov.files || []).map(f => {
        const badge = f.is_stale
          ? '<span class="px-2 py-0.5 text-xs rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">STALE</span>'
          : '<span class="px-2 py-0.5 text-xs rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">FRESH</span>';
        const syms = (f.key_symbols || []).map(s => `<code class="px-1.5 py-0.5 rounded bg-slate-800 text-sky-300 text-xs">${s}</code>`).join(' ');
        return `
          <div class="p-3 rounded-lg border border-[var(--border,#334155)] space-y-1.5">
            <div class="flex items-center justify-between gap-2">
              <span class="font-mono text-xs font-semibold">${f.rel_path}</span>
              ${badge}
            </div>
            <p class="text-xs cg-muted">${f.summary}</p>
            ${syms ? `<div class="flex flex-wrap gap-1 pt-1">${syms}</div>` : ''}
          </div>
        `;
      }).join('');
      document.getElementById('files-list').innerHTML = filesHtml || '<p class="text-xs cg-muted">No cached files for this workspace yet.</p>';

      const relsHtml = (ov.relationships || []).map(r => `
        <div class="p-2.5 rounded-lg border border-[var(--border,#334155)] text-xs space-y-1">
          <div class="font-mono"><span class="text-sky-400">${r.source}</span> <span class="px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">[${r.type}]</span> &rarr; <span class="text-emerald-400">${r.target}</span></div>
          ${r.description ? `<div class="cg-muted">${r.description}</div>` : ''}
        </div>
      `).join('');
      document.getElementById('rels-list').innerHTML = relsHtml || '<p class="text-xs cg-muted">No relationships recorded for this workspace yet.</p>';
    }

    function renderOverridesAndQueries() {
      let allOverrides = [];
      let allQueries = [];
      Object.entries(STATE.overviews || {}).forEach(([ws, ov]) => {
        (ov.ground_truth_overrides || []).forEach(o => allOverrides.push({ ...o, ws }));
        (ov.cached_queries || []).forEach(q => allQueries.push({ ...q, ws }));
      });

      document.getElementById('overrides-list').innerHTML = allOverrides.map(o => `
        <div class="p-3.5 rounded-lg border border-amber-500/40 bg-amber-500/5 space-y-1">
          <div class="flex items-center justify-between">
            <span class="font-mono text-xs font-bold text-amber-300">[${(o.priority || 'high').toUpperCase()}] ${o.override_key}</span>
            <span class="text-xs cg-muted font-mono">${o.ws}</span>
          </div>
          <div class="text-sm font-medium">${o.verified_truth}</div>
          ${o.hallucination_or_mistake ? `<div class="text-xs text-rose-400">Prevents hallucination: ${o.hallucination_or_mistake}</div>` : ''}
        </div>
      `).join('') || '<p class="text-xs cg-muted">No ground-truth overrides pinned yet. Use the form above or `context_ctl.py correct` to add one.</p>';

      document.getElementById('queries-list').innerHTML = allQueries.map(q => `
        <div class="p-3.5 rounded-lg border border-[var(--border,#334155)] space-y-1">
          <div class="flex items-center justify-between">
            <span class="font-mono text-xs font-bold text-indigo-400">${q.query_key} (${q.category})</span>
            <span class="text-xs cg-muted font-mono">${q.ws}</span>
          </div>
          ${q.query_text ? `<div class="text-xs cg-muted">Query: ${q.query_text}</div>` : ''}
          <div class="text-sm">${q.result_summary}</div>
        </div>
      `).join('') || '<p class="text-xs cg-muted">No cached queries stored yet.</p>';
    }

    async function apiAction(action) {
      const ws = document.getElementById('ws-select')?.value || 'global';
      const toast = document.getElementById('action-toast');
      toast.classList.remove('hidden');
      if (!IS_LIVE_SERVER) {
        const cmdMap = {
          verify: `python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py verify --workspace "${ws}"`,
          refresh_stale: `python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py refresh --workspace "${ws}" --mode stale_only`,
          refresh_all: `python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py refresh --workspace "${ws}" --mode force_all`,
        };
        toast.textContent = `[Artifact Preview Mode] Run in terminal or start live UI server (python3 scripts/ui_server.py):\\n$ ${cmdMap[action]}`;
        return;
      }
      toast.textContent = `Running ${action} on ${ws}...`;
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, workspace_path: ws })
      });
      const data = await res.json();
      toast.textContent = JSON.stringify(data, null, 2);
      await reloadState();
    }

    async function submitOverride() {
      const ws = document.getElementById('ov-ws').value || 'global';
      const key = document.getElementById('ov-key').value.trim();
      const priority = document.getElementById('ov-priority').value;
      const mistake = document.getElementById('ov-mistake').value.trim();
      const truth = document.getElementById('ov-truth').value.trim();
      if (!key || !truth) {
        alert('Please enter both Override Slug and Verified Ground-Truth Rule.');
        return;
      }
      if (!IS_LIVE_SERVER) {
        document.getElementById('ov-cli-preview').textContent =
          `Run: python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py correct -w "${ws}" -k "${key}" --mistake "${mistake}" --truth "${truth}" --priority ${priority}`;
        return;
      }
      await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'correct',
          workspace_path: ws,
          override_key: key,
          hallucination_or_mistake: mistake,
          verified_truth: truth,
          priority
        })
      });
      document.getElementById('ov-key').value = '';
      document.getElementById('ov-mistake').value = '';
      document.getElementById('ov-truth').value = '';
      await reloadState();
    }

    async function reloadState() {
      if (IS_LIVE_SERVER) {
        const res = await fetch('/api/state');
        STATE = await res.json();
      }
      renderKPIs();
      renderTokens();
      initWorkspaces();
    }

    if (!getComputedStyle(document.documentElement).getPropertyValue('--background').trim()) {
      const rootStyle = document.documentElement.style;
      rootStyle.setProperty('--background', '#0f172a');
      rootStyle.setProperty('--foreground', '#f8fafc');
      rootStyle.setProperty('--card', '#1e293b');
      rootStyle.setProperty('--muted-foreground', '#94a3b8');
      rootStyle.setProperty('--border', '#334155');
    }

    reloadState();
  </script>
</body>
</html>
"""


def build_html(workspace_filter: str = "") -> str:
    state = collect_full_state(workspace_filter)
    return DASHBOARD_HTML_TEMPLATE.replace(
        "__INITIAL_STATE_JSON__", json.dumps(state)
    )


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            self._send_json(collect_full_state())
        else:
            html_bytes = build_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)

    def do_POST(self) -> None:
        if self.path != "/api/action":
            self._send_json({"error": "Not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        action = body.get("action")
        ws = body.get("workspace_path", "global")

        if action == "verify":
            res = db_engine.verify_and_fix_hallucinations(ws, auto_fix=True)
        elif action == "refresh_stale":
            res = db_engine.refresh_context(ws, mode="stale_only")
        elif action == "refresh_all":
            res = db_engine.refresh_context(ws, mode="force_all")
        elif action == "correct":
            res = db_engine.record_correction(
                workspace_path=ws,
                override_key=body["override_key"],
                verified_truth=body["verified_truth"],
                hallucination_or_mistake=body.get("hallucination_or_mistake", ""),
                priority=body.get("priority", "high"),
            )
        else:
            res = {"error": f"Unknown action: {action}"}
        self._send_json(res)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch the Context Graph Web UI Control Center or export a standalone HTML artifact."
    )
    parser.add_argument(
        "--port", "-p", type=int, default=8765, help="Port for local web server (default: 8765)."
    )
    parser.add_argument(
        "--export-html",
        default=None,
        help="Export a self-contained HTML dashboard to this file path and exit.",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        default="",
        help="Optional workspace filter when exporting HTML.",
    )
    args = parser.parse_args()

    if args.export_html:
        out_path = os.path.abspath(os.path.expanduser(args.export_html))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        html_content = build_html(args.workspace)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Exported Context Graph HTML dashboard to {out_path}")
        return

    server = http.server.HTTPServer(("127.0.0.1", args.port), DashboardHandler)
    print(f"Context Graph UI Control Center running at http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
