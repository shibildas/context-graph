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
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

from server import db_engine


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
        1. Cost per Feature &amp; Token Usage
      </button>
      <button onclick="switchTab('graph')" id="tab-graph" class="px-4 py-2 rounded-lg text-sm font-medium cg-card cg-muted">
        2. 3D Data Models &amp; Context Graph
      </button>
      <button onclick="switchTab('overrides')" id="tab-overrides" class="px-4 py-2 rounded-lg text-sm font-medium cg-card cg-muted">
        3. Anti-Hallucination &amp; Overrides
      </button>
      <button onclick="switchTab('queries')" id="tab-queries" class="px-4 py-2 rounded-lg text-sm font-medium cg-card cg-muted">
        4. Cached Queries &amp; Data
      </button>
    </div>

    <!-- Tab 1: Cost per Feature & Token Usage -->
    <div id="view-tokens" class="space-y-6">
      <div class="cg-card rounded-xl p-5 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 class="text-base font-semibold">Cost &amp; Token Usage per Feature (Git Branches &amp; Tasks)</h2>
            <p class="text-xs cg-muted">Plugin savings are strictly $0.00 for features/tasks where the context-graph plugin was not invoked</p>
          </div>
          <input id="feature-search" oninput="renderTokens()" type="text" placeholder="Filter feature, ticket (#1643), or repo..." class="cg-input rounded-lg px-3 py-1.5 text-xs w-72" />
        </div>
        <div class="overflow-x-auto max-h-96 overflow-y-auto">
          <table class="w-full text-left border-collapse text-sm">
            <thead>
              <tr class="border-b border-[var(--border,#334155)] text-xs cg-muted">
                <th class="py-2 px-3">Feature / Task</th>
                <th class="py-2 px-3">Ticket(s)</th>
                <th class="py-2 px-3">Repo(s) &amp; Branch</th>
                <th class="py-2 px-3 text-right">Convs</th>
                <th class="py-2 px-3 text-right">Turns</th>
                <th class="py-2 px-3 text-right">Total Tokens</th>
                <th class="py-2 px-3 text-center">Plugin Used</th>
                <th class="py-2 px-3 text-right">Plugin Tokens Saved</th>
                <th class="py-2 px-3 text-right">Actual Cost ($)</th>
                <th class="py-2 px-3 text-right">Saved by Plugin ($)</th>
              </tr>
            </thead>
            <tbody id="table-features"></tbody>
          </table>
        </div>
      </div>

      <div class="cg-card rounded-xl p-5 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-base font-semibold">Token Usage &amp; Cost by LLM Client</h2>
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
                <th class="py-2 px-3 text-right">API Prefix Cache</th>
                <th class="py-2 px-3 text-right">Output Tokens</th>
                <th class="py-2 px-3 text-right">Total Tokens</th>
                <th class="py-2 px-3 text-right">Plugin Calls</th>
                <th class="py-2 px-3 text-right">Actual Cost ($)</th>
                <th class="py-2 px-3 text-right">Saved by Plugin ($)</th>
              </tr>
            </thead>
            <tbody id="table-clients"></tbody>
          </table>
        </div>
      </div>

      <div class="cg-card rounded-xl p-5 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-base font-semibold">Token Usage &amp; Cost by Project / Related Git Repository</h2>
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
                <th class="py-2 px-3 text-right">Total Tokens</th>
                <th class="py-2 px-3 text-center">Plugin Used</th>
                <th class="py-2 px-3 text-right">Plugin Tokens Saved</th>
                <th class="py-2 px-3 text-right">Actual Cost ($)</th>
                <th class="py-2 px-3 text-right">Saved by Plugin ($)</th>
              </tr>
            </thead>
            <tbody id="table-repos"></tbody>
          </table>
        </div>
      </div>

      <div class="cg-card rounded-xl p-5 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-base font-semibold">Token Usage &amp; Cost per Conversation</h2>
          <input id="conv-search" oninput="renderTokens()" type="text" placeholder="Search feature, prompt, repo, or ID..." class="cg-input rounded-lg px-3 py-1.5 text-xs w-72" />
        </div>
        <div class="overflow-x-auto max-h-96 overflow-y-auto">
          <table class="w-full text-left border-collapse text-sm">
            <thead>
              <tr class="border-b border-[var(--border,#334155)] text-xs cg-muted">
                <th class="py-2 px-3">Client</th>
                <th class="py-2 px-3">Conv ID</th>
                <th class="py-2 px-3">Feature / Prompt</th>
                <th class="py-2 px-3">Project / Repo</th>
                <th class="py-2 px-3 text-right">Turns</th>
                <th class="py-2 px-3 text-right">Total Tokens</th>
                <th class="py-2 px-3 text-center">Plugin Used</th>
                <th class="py-2 px-3 text-right">Plugin Tokens Saved</th>
                <th class="py-2 px-3 text-right">Actual Cost ($)</th>
                <th class="py-2 px-3 text-right">Saved by Plugin ($)</th>
              </tr>
            </thead>
            <tbody id="table-convs"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Tab 2: 3D Data Models & Context Graph -->
    <div id="view-graph" class="space-y-6 hidden">
      <div class="cg-card rounded-xl p-5 flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap items-center gap-3">
          <label class="text-xs font-medium cg-muted">Workspace / Schema:</label>
          <select id="ws-select" onchange="renderGraph()" class="cg-input rounded-lg px-3 py-1.5 text-xs"></select>
          <button onclick="toggle3DRotate()" id="btn-3d-rotate" class="text-xs px-3 py-1.5 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 font-medium">
            3D Orbit: ON
          </button>
          <button onclick="toggle3DLayers()" id="btn-3d-layers" class="text-xs px-3 py-1.5 rounded-lg cg-input font-medium">
            Layout: 3D Force Sphere
          </button>
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

      <!-- Interactive 3D Data Model & AST Graph Viewport -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2 cg-card rounded-xl p-3 relative overflow-hidden" style="height: 440px; background: #090d16;">
          <canvas id="graph3d-canvas" class="w-full h-full cursor-grab active:cursor-grabbing block"></canvas>
          <div class="absolute top-4 left-4 flex flex-wrap gap-1.5">
            <button onclick="set3DFilter('all')" class="text-xs px-2.5 py-1 rounded bg-white/15 text-white border border-white/25">All Nodes</button>
            <button onclick="set3DFilter('model')" class="text-xs px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">Data Models / Tables</button>
            <button onclick="set3DFilter('engine')" class="text-xs px-2.5 py-1 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">Engines / UseCases</button>
            <button onclick="set3DFilter('repo')" class="text-xs px-2.5 py-1 rounded bg-sky-500/20 text-sky-300 border border-sky-500/40">Repos / Queries</button>
            <button onclick="set3DFilter('api')" class="text-xs px-2.5 py-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">APIs / Overrides</button>
          </div>
          <div class="absolute bottom-4 left-4 right-4 flex items-center justify-between pointer-events-none">
            <span id="graph3d-hud" class="text-xs font-mono px-2.5 py-1 rounded bg-slate-900/80 text-slate-300 border border-slate-700">Drag to Orbit 3D • Scroll to Zoom • Click Node to Inspect</span>
            <div class="flex gap-1.5 pointer-events-auto">
              <button onclick="zoom3D(1.18)" class="text-xs px-2.5 py-1 rounded bg-slate-900/85 text-white border border-slate-700 font-bold">+</button>
              <button onclick="zoom3D(0.85)" class="text-xs px-2.5 py-1 rounded bg-slate-900/85 text-white border border-slate-700 font-bold">&minus;</button>
            </div>
          </div>
        </div>
        <div class="cg-card rounded-xl p-5 flex flex-col justify-between" style="height: 440px;">
          <div id="graph3d-inspector" class="space-y-3 overflow-y-auto pr-1"></div>
          <div class="pt-3 border-t border-[var(--border)] text-xs cg-muted flex items-center justify-between">
            <span>3D Perspective Projection</span>
            <span class="text-emerald-400">PK / FK &amp; AST Graph</span>
          </div>
        </div>
      </div>

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
          <input id="ov-key" type="text" placeholder="Override slug (e.g. api-timeout-ms)" class="cg-input rounded-lg px-3 py-2 text-xs" />
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
    const API_BASE = window.location.protocol.startsWith('http') ? '' : 'http://127.0.0.1:8765';
    let STATE = {
      token_report: {
        grand_totals: {
          total_conversations: 0,
          total_features: 0,
          input_tokens: 0,
          cache_read_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          cache_hit_rate_pct: 0,
          estimated_cost_usd: 0,
          uncached_cost_usd: 0,
          estimated_cache_savings_usd: 0
        },
        by_feature: [],
        by_client: [],
        by_project_repo: [],
        by_conversation: []
      },
      workspaces: [],
      overviews: {}
    };

    function fmtNum(n) {
      return Number(n || 0).toLocaleString();
    }

    function fmtUsd(n) {
      return '$' + Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

    function pluginBadge(calls) {
      const n = Number(calls || 0);
      if (n > 0) {
        return `<span class="px-2 py-0.5 text-xs rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono">Yes (${n})</span>`;
      }
      return `<span class="px-2 py-0.5 text-xs rounded bg-slate-800 cg-muted font-mono">No</span>`;
    }

    function renderKPIs() {
      const gt = STATE.token_report.grand_totals || {};
      const featCount = gt.total_features || (STATE.token_report.by_feature || []).length;
      let totalFiles = 0, totalRels = 0, totalOverrides = 0;
      Object.values(STATE.overviews || {}).forEach(ov => {
        totalFiles += (ov.stats?.total_cached_files || 0);
        totalRels += (ov.stats?.total_relationships || 0);
        totalOverrides += (ov.stats?.active_ground_truth_overrides || 0);
      });

      const cards = [
        { label: 'Est. Total LLM Spend', val: fmtUsd(gt.estimated_cost_usd), sub: `${fmtNum(gt.total_conversations)} conversations (${featCount} features)` },
        { label: 'Saved by Context-Graph', val: fmtUsd(gt.estimated_cache_savings_usd), sub: `${fmtNum(gt.plugin_tokens_saved)} tokens (${fmtNum(gt.plugin_calls)} plugin calls)` },
        { label: 'Total Tokens Tracked', val: fmtNum(gt.total_tokens), sub: `${fmtNum(gt.input_tokens)} in / ${fmtNum(gt.output_tokens)} out` },
        { label: 'Indexed Graph & Edges', val: `${totalFiles} files`, sub: `${totalRels} implementation edges` },
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
      const tr = STATE.token_report || {};

      const fFilter = (document.getElementById('feature-search')?.value || '').toLowerCase();
      const features = (tr.by_feature || []).filter(f =>
        !fFilter ||
        (f.feature_name || '').toLowerCase().includes(fFilter) ||
        (f.ticket_id || '').toLowerCase().includes(fFilter) ||
        (f.repo_name || '').toLowerCase().includes(fFilter) ||
        (f.git_branch || '').toLowerCase().includes(fFilter)
      );
      const featEl = document.getElementById('table-features');
      if (featEl) {
        featEl.innerHTML = features.map(f => {
          const used = Number(f.plugin_calls || 0) > 0;
          return `
            <tr class="border-b border-[var(--border,#334155)]/50">
              <td class="py-2.5 px-3 font-semibold max-w-xs truncate" title="${(f.feature_name || '').replace(/"/g, '&quot;')}">${f.feature_name}</td>
              <td class="py-2.5 px-3 font-mono text-xs text-amber-300">${f.ticket_id || '-'}</td>
              <td class="py-2.5 px-3">
                <div class="text-xs font-medium">${f.repo_name}</div>
                <div class="text-xs font-mono text-sky-400 truncate max-w-xs">${f.git_branch || '-'}</div>
              </td>
              <td class="py-2.5 px-3 text-right">${fmtNum(f.conversation_count)}</td>
              <td class="py-2.5 px-3 text-right">${fmtNum(f.total_turns)}</td>
              <td class="py-2.5 px-3 text-right font-bold">${fmtNum(f.total_tokens)}</td>
              <td class="py-2.5 px-3 text-center">${pluginBadge(f.plugin_calls)}</td>
              <td class="py-2.5 px-3 text-right ${used ? 'text-emerald-400 font-medium' : 'cg-muted'}">${used ? fmtNum(f.plugin_tokens_saved) : '0'}</td>
              <td class="py-2.5 px-3 text-right font-bold text-amber-300">${fmtUsd(f.estimated_cost_usd)}</td>
              <td class="py-2.5 px-3 text-right ${used ? 'font-bold text-emerald-400' : 'cg-muted'}">${used ? fmtUsd(f.estimated_cache_savings_usd) : '$0.00'}</td>
            </tr>
          `;
        }).join('');
      }

      document.getElementById('table-clients').innerHTML = (tr.by_client || []).map(c => {
        const used = Number(c.plugin_calls || 0) > 0;
        return `
          <tr class="border-b border-[var(--border,#334155)]/50">
            <td class="py-2.5 px-3 font-semibold text-indigo-400">${c.client_source}</td>
            <td class="py-2.5 px-3 text-right">${fmtNum(c.conversation_count)}</td>
            <td class="py-2.5 px-3 text-right">${fmtNum(c.total_turns)}</td>
            <td class="py-2.5 px-3 text-right">${fmtNum(c.input_tokens)}</td>
            <td class="py-2.5 px-3 text-right">${fmtNum(c.cache_read_tokens)}</td>
            <td class="py-2.5 px-3 text-right">${fmtNum(c.output_tokens)}</td>
            <td class="py-2.5 px-3 text-right font-bold">${fmtNum(c.total_tokens)}</td>
            <td class="py-2.5 px-3 text-right">${fmtNum(c.plugin_calls)}</td>
            <td class="py-2.5 px-3 text-right font-bold text-amber-300">${fmtUsd(c.estimated_cost_usd)}</td>
            <td class="py-2.5 px-3 text-right ${used ? 'font-bold text-emerald-400' : 'cg-muted'}">${used ? fmtUsd(c.estimated_cache_savings_usd) : '$0.00'}</td>
          </tr>
        `;
      }).join('');

      const rFilter = (document.getElementById('repo-search')?.value || '').toLowerCase();
      const repos = (tr.by_project_repo || []).filter(r =>
        !rFilter ||
        (r.repo_name || '').toLowerCase().includes(rFilter) ||
        (r.project_root || '').toLowerCase().includes(rFilter) ||
        (r.git_branch || '').toLowerCase().includes(rFilter)
      );
      document.getElementById('table-repos').innerHTML = repos.map(r => {
        const used = Number(r.plugin_calls || 0) > 0;
        return `
          <tr class="border-b border-[var(--border,#334155)]/50">
            <td class="py-2.5 px-3">
              <div class="font-semibold">${r.repo_name}</div>
              <div class="text-xs cg-muted truncate max-w-xs">${r.project_root}</div>
            </td>
            <td class="py-2.5 px-3 font-mono text-xs text-sky-400">${r.git_branch || '-'}</td>
            <td class="py-2.5 px-3 text-right">${fmtNum(r.conversation_count)}</td>
            <td class="py-2.5 px-3 text-right">${fmtNum(r.total_turns)}</td>
            <td class="py-2.5 px-3 text-right font-bold">${fmtNum(r.total_tokens)}</td>
            <td class="py-2.5 px-3 text-center">${pluginBadge(r.plugin_calls)}</td>
            <td class="py-2.5 px-3 text-right ${used ? 'text-emerald-400 font-medium' : 'cg-muted'}">${used ? fmtNum(r.plugin_tokens_saved) : '0'}</td>
            <td class="py-2.5 px-3 text-right font-bold text-amber-300">${fmtUsd(r.estimated_cost_usd)}</td>
            <td class="py-2.5 px-3 text-right ${used ? 'font-bold text-emerald-400' : 'cg-muted'}">${used ? fmtUsd(r.estimated_cache_savings_usd) : '$0.00'}</td>
          </tr>
        `;
      }).join('');

      const cFilter = (document.getElementById('conv-search')?.value || '').toLowerCase();
      const convs = (tr.by_conversation || []).filter(c =>
        !cFilter ||
        (c.title || '').toLowerCase().includes(cFilter) ||
        (c.feature_name || '').toLowerCase().includes(cFilter) ||
        (c.repo_name || '').toLowerCase().includes(cFilter) ||
        (c.conversation_id || '').toLowerCase().includes(cFilter)
      );
      document.getElementById('table-convs').innerHTML = convs.map(c => {
        const used = Number(c.plugin_calls || 0) > 0;
        return `
          <tr class="border-b border-[var(--border,#334155)]/50">
            <td class="py-2 px-3 text-xs font-mono text-indigo-400">${c.client_source}</td>
            <td class="py-2 px-3 text-xs font-mono cg-muted">${c.conversation_id.slice(0, 8)}...</td>
            <td class="py-2 px-3 max-w-xs truncate" title="${(c.title || '').replace(/"/g, '&quot;')}">
              <div class="font-medium truncate">${c.feature_name || c.title}</div>
              <div class="text-xs cg-muted truncate">${c.title}</div>
            </td>
            <td class="py-2 px-3 font-medium">${c.repo_name}</td>
            <td class="py-2 px-3 text-right">${fmtNum(c.turn_count)}</td>
            <td class="py-2.5 px-3 text-right font-bold">${fmtNum(c.total_tokens)}</td>
            <td class="py-2 px-3 text-center">${pluginBadge(c.plugin_calls)}</td>
            <td class="py-2 px-3 text-right ${used ? 'text-emerald-400 font-medium' : 'cg-muted'}">${used ? fmtNum(c.plugin_tokens_saved) : '0'}</td>
            <td class="py-2 px-3 text-right font-bold text-amber-300">${fmtUsd(c.estimated_cost_usd)}</td>
            <td class="py-2 px-3 text-right ${used ? 'font-bold text-emerald-400' : 'cg-muted'}">${used ? fmtUsd(c.estimated_cache_savings_usd) : '$0.00'}</td>
          </tr>
        `;
      }).join('');
    }

    const G3D_COLORS = {
      model:  { fill: '#10b981', glow: 'rgba(16,185,129,0.45)', badge: 'Data Model / Table', text: '#6ee7b7' },
      engine: { fill: '#6366f1', glow: 'rgba(99,102,241,0.45)', badge: 'Engine / UseCase', text: '#a5b4fc' },
      repo:   { fill: '#0ea5e9', glow: 'rgba(14,165,233,0.45)', badge: 'Repository / Cache', text: '#7dd3fc' },
      api:    { fill: '#f59e0b', glow: 'rgba(245,158,11,0.45)', badge: 'API / Ground-Truth', text: '#fcd34d' },
      ui:     { fill: '#ec4899', glow: 'rgba(236,72,153,0.45)', badge: 'UI / Hook', text: '#f9a8d4' }
    };

    const SQLITE_CORE_MODELS = {
      nodes: [
        { id: 'files', label: 'files (Table)', category: 'model', tier: -1, size: 22, summary: 'Primary file & AST symbol index table storing SHA-256 signatures and extracted symbol line maps.', fields: ['PK (workspace_path, file_path)', 'rel_path : TEXT', 'content_hash : SHA-256', 'symbols_json : JSON [{name, kind, line}]', 'exports_json : JSON', 'tags_json : JSON'] },
        { id: 'relationships', label: 'relationships (Table)', category: 'model', tier: -1, size: 19, summary: 'Directed implementation graph edges connecting source and target files.', fields: ['PK (workspace_path, source_file, target_file, relation_type)', 'FK source_file -> files.file_path', 'FK target_file -> files.file_path', 'relation_type : imports | calls | reads_data_from | writes_data_to'] },
        { id: 'ground_truth_overrides', label: 'ground_truth_overrides', category: 'api', tier: -1, size: 20, summary: 'Verified anti-hallucination rules and user corrections injected at SessionStart.', fields: ['PK (workspace_path, override_key)', 'hallucination_or_mistake : TEXT', 'verified_truth : TEXT', 'scope_files_json : JSON -> files', 'priority : critical | high | normal'] },
        { id: 'cached_queries', label: 'cached_queries (Table)', category: 'repo', tier: -1, size: 18, summary: 'Reusable cache of expensive database queries, API responses, and generated datasets.', fields: ['PK (workspace_path, query_key)', 'category : queried_data | generated_data', 'result_summary : TEXT', 'data_json : JSON', 'related_files_json : JSON -> files'] },
        { id: 'conversation_usage', label: 'conversation_usage', category: 'model', tier: -1, size: 21, summary: 'Multi-LLM token analytics per conversation and related Git repository.', fields: ['PK conversation_id : TEXT', 'client_source : antigravity | claude-code | codex-cli', 'repo_name & git_branch : TEXT', 'input_tokens, cache_read_tokens, output_tokens, total_tokens : INT'] },
        { id: 'tool_activity', label: 'tool_activity (Table)', category: 'repo', tier: 0, size: 15, summary: 'Audit log of PostToolUse file reads, edits, and tool calls.', fields: ['PK id : INTEGER', 'FK session_id -> conversation_usage', 'FK target_path -> files.file_path', 'tool_name : TEXT'] },
        { id: 'db_engine', label: 'server/db_engine.py', category: 'engine', tier: 0, size: 24, summary: 'Core SQLite Graph Engine, AST Static Indexer, Hallucination Verifier & Transcript Scanner.', fields: ['auto_index_workspace()', 'verify_and_fix_hallucinations()', 'record_correction()', 'refresh_context()', 'get_token_usage_report()'] },
        { id: 'mcp_server', label: 'server/mcp_server.py', category: 'api', tier: 1, size: 18, summary: 'Stdio JSON-RPC 2.0 MCP Server exposing 12 tools to all LLM clients.', fields: ['cache_get_overview', 'cache_get_file_context', 'cache_record_correction', 'cache_verify_and_fix_hallucinations', 'cache_get_token_usage'] },
        { id: 'ui_server', label: 'scripts/ui_server.py', category: 'ui', tier: 1, size: 17, summary: 'Interactive Web UI Control Center & 3D Data Model Explorer.', fields: ['GET /api/state', 'POST /api/action', '3D Data Model Graph Canvas'] }
      ],
      edges: [
        { source: 'relationships', target: 'files', type: 'FK source/target' },
        { source: 'ground_truth_overrides', target: 'files', type: 'FK scope_files' },
        { source: 'cached_queries', target: 'files', type: 'FK related_files' },
        { source: 'tool_activity', target: 'files', type: 'FK target_path' },
        { source: 'tool_activity', target: 'conversation_usage', type: 'FK session_id' },
        { source: 'db_engine', target: 'files', type: 'indexes AST' },
        { source: 'db_engine', target: 'relationships', type: 'maps edges' },
        { source: 'db_engine', target: 'ground_truth_overrides', type: 'pins truth' },
        { source: 'db_engine', target: 'cached_queries', type: 'caches queries' },
        { source: 'db_engine', target: 'conversation_usage', type: 'scans tokens' },
        { source: 'mcp_server', target: 'db_engine', type: 'calls 12 tools' },
        { source: 'ui_server', target: 'db_engine', type: 'queries state' }
      ]
    };

    let g3dNodes = [], g3dEdges = [], g3dParticles = [], g3dSelected = null;
    let g3dFilter = 'all', g3dRotate = true, g3dLayers = false;
    let g3dRotY = 0.45, g3dRotX = 0.26, g3dZoom = 1.0;
    let g3dDrag = false, g3dMoved = false, g3dSX = 0, g3dSY = 0, g3dStarted = false;

    function classify3DCategory(relPath, summary) {
      const p = (relPath + ' ' + (summary || '')).toLowerCase();
      if (p.includes('model') || p.includes('schema') || p.includes('entity') || p.includes('types') || p.includes('db_engine')) return 'model';
      if (p.includes('repo') || p.includes('dao') || p.includes('store') || p.includes('query')) return 'repo';
      if (p.includes('controller') || p.includes('mcp_server') || p.includes('route') || p.includes('api')) return 'api';
      if (p.includes('page') || p.includes('component') || p.includes('slice') || p.includes('ui_') || p.includes('.tsx')) return 'ui';
      return 'engine';
    }

    function load3DGraph(graphData) {
      const nCount = graphData.nodes.length || 1;
      g3dNodes = graphData.nodes.map((n, i) => {
        const phi = Math.acos(1 - 2 * (i + 0.5) / nCount);
        const theta = Math.PI * (1 + Math.sqrt(5)) * i;
        const rad = 135;
        return {
          ...n,
          x: rad * Math.sin(phi) * Math.cos(theta),
          y: (n.tier || 0) * 80 + (Math.random() - 0.5) * 30,
          z: rad * Math.cos(phi),
          vx: 0, vy: 0, vz: 0, projX: 0, projY: 0, projScale: 1, depthZ: 0
        };
      });
      const map = Object.fromEntries(g3dNodes.map(n => [n.id, n]));
      g3dEdges = (graphData.edges || [])
        .filter(e => map[e.source] && map[e.target])
        .map(e => ({ ...e, sourceNode: map[e.source], targetNode: map[e.target] }));
      g3dParticles = g3dEdges.map((e, idx) => ({ edge: e, t: (idx * 0.21) % 1, speed: 0.006 + (idx % 3) * 0.002 }));
      g3dSelected = g3dNodes[0] || null;
      render3DInspector();
    }

    function render3DInspector() {
      const box = document.getElementById('graph3d-inspector');
      if (!box || !g3dSelected) return;
      const col = G3D_COLORS[g3dSelected.category] || G3D_COLORS.engine;
      const inc = g3dEdges.filter(e => e.targetNode.id === g3dSelected.id);
      const out = g3dEdges.filter(e => e.sourceNode.id === g3dSelected.id);
      const fieldsHtml = (g3dSelected.fields || []).map(f =>
        `<div class="px-2.5 py-1 rounded bg-[var(--background)] border border-[var(--border)] font-mono text-xs truncate" title="${f}">${f}</div>`
      ).join('');
      const relsHtml = [
        ...out.map(e => `<div class="text-xs font-mono"><span class="text-indigo-400">&rarr; ${e.type}</span> ${e.targetNode.label}</div>`),
        ...inc.map(e => `<div class="text-xs font-mono"><span class="text-emerald-400">&larr; ${e.type}</span> ${e.sourceNode.label}</div>`)
      ].join('');
      box.innerHTML = `
        <div class="space-y-1">
          <span class="text-xs px-2 py-0.5 rounded font-semibold" style="background:${col.glow};color:${col.text}">${col.badge}</span>
          <h4 class="text-sm font-bold font-mono pt-1">${g3dSelected.fullPath || g3dSelected.label}</h4>
          <p class="text-xs cg-muted">${g3dSelected.summary || ''}</p>
        </div>
        <div class="space-y-1">
          <div class="text-xs font-semibold uppercase tracking-wider cg-muted">Columns / AST Symbols (${(g3dSelected.fields || []).length})</div>
          <div class="space-y-1 max-h-44 overflow-y-auto pr-1">${fieldsHtml}</div>
        </div>
        <div class="space-y-1">
          <div class="text-xs font-semibold uppercase tracking-wider cg-muted">3D Edges (${inc.length + out.length})</div>
          <div class="space-y-1">${relsHtml || '<span class="text-xs cg-muted">No direct edges</span>'}</div>
        </div>
      `;
    }

    function init3DCanvasEvents() {
      if (g3dStarted) return;
      const cvs = document.getElementById('graph3d-canvas');
      if (!cvs) return;
      g3dStarted = true;
      cvs.addEventListener('pointerdown', e => {
        g3dDrag = true; g3dMoved = false; g3dSX = e.clientX; g3dSY = e.clientY;
        cvs.setPointerCapture(e.pointerId);
      });
      cvs.addEventListener('pointermove', e => {
        if (!g3dDrag) return;
        const dx = e.clientX - g3dSX, dy = e.clientY - g3dSY;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) g3dMoved = true;
        g3dRotY += dx * 0.0075;
        g3dRotX = Math.max(-1.25, Math.min(1.25, g3dRotX + dy * 0.0075));
        g3dSX = e.clientX; g3dSY = e.clientY;
      });
      cvs.addEventListener('pointerup', e => {
        g3dDrag = false;
        if (!g3dMoved) {
          const rect = cvs.getBoundingClientRect();
          const mx = e.clientX - rect.left, my = e.clientY - rect.top;
          const vis = g3dNodes.filter(n => g3dFilter === 'all' || n.category === g3dFilter).sort((a, b) => a.depthZ - b.depthZ);
          for (const n of vis) {
            if (Math.hypot(mx - n.projX, my - n.projY) <= Math.max(12, n.size * n.projScale)) {
              g3dSelected = n;
              render3DInspector();
              break;
            }
          }
        }
      });
      cvs.addEventListener('wheel', e => {
        e.preventDefault();
        zoom3D(e.deltaY < 0 ? 1.08 : 0.92);
      }, { passive: false });

      function stepAndDraw() {
        const rect = cvs.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          const dpr = window.devicePixelRatio || 1;
          if (cvs.width !== Math.floor(rect.width * dpr) || cvs.height !== Math.floor(rect.height * dpr)) {
            cvs.width = Math.floor(rect.width * dpr);
            cvs.height = Math.floor(rect.height * dpr);
          }
          const ctx = cvs.getContext('2d');
          ctx.save();
          ctx.scale(dpr, dpr);
          const w = rect.width, h = rect.height;
          ctx.fillStyle = '#090d16';
          ctx.fillRect(0, 0, w, h);

          if (g3dRotate && !g3dDrag) g3dRotY += 0.0045;
          const vis = g3dNodes.filter(n => g3dFilter === 'all' || n.category === g3dFilter);
          const visSet = new Set(vis.map(n => n.id));

          // 3D Force physics
          for (let i = 0; i < vis.length; i++) {
            for (let j = i + 1; j < vis.length; j++) {
              const a = vis[i], b = vis[j];
              const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
              const dSq = dx * dx + dy * dy + dz * dz + 45;
              const f = 1900 / dSq, d = Math.sqrt(dSq);
              a.vx += (dx / d) * f; a.vy += (dy / d) * f; a.vz += (dz / d) * f;
              b.vx -= (dx / d) * f; b.vy -= (dy / d) * f; b.vz -= (dz / d) * f;
            }
          }
          g3dEdges.forEach(e => {
            const a = e.sourceNode, b = e.targetNode;
            const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
            const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
            const s = (d - 110) * 0.012;
            a.vx += (dx / d) * s; a.vy += (dy / d) * s; a.vz += (dz / d) * s;
            b.vx -= (dx / d) * s; b.vy -= (dy / d) * s; b.vz -= (dz / d) * s;
          });
          vis.forEach(n => {
            n.vx -= n.x * 0.008; n.vz -= n.z * 0.008;
            n.vy += g3dLayers ? (((n.tier || 0) * 95) - n.y) * 0.06 : -n.y * 0.008;
            n.vx *= 0.82; n.vy *= 0.82; n.vz *= 0.82;
            n.x += n.vx; n.y += n.vy; n.z += n.vz;

            const cosY = Math.cos(g3dRotY), sinY = Math.sin(g3dRotY);
            const x1 = n.x * cosY - n.z * sinY, z1 = n.z * cosY + n.x * sinY;
            const cosX = Math.cos(g3dRotX), sinX = Math.sin(g3dRotX);
            const y2 = n.y * cosX - z1 * sinX, z2 = z1 * cosX + n.y * sinX;
            const sc = (430 * g3dZoom) / Math.max(80, 400 + z2);
            n.projX = w / 2 + x1 * sc; n.projY = h / 2 + y2 * sc; n.projScale = sc; n.depthZ = z2;
          });

          g3dEdges.forEach(e => {
            if (!visSet.has(e.sourceNode.id) || !visSet.has(e.targetNode.id)) return;
            const a = e.sourceNode, b = e.targetNode;
            const hi = g3dSelected && (g3dSelected.id === a.id || g3dSelected.id === b.id);
            ctx.strokeStyle = hi ? 'rgba(129,140,248,0.9)' : 'rgba(148,163,184,0.3)';
            ctx.lineWidth = hi ? 2 : 1.1;
            ctx.beginPath(); ctx.moveTo(a.projX, a.projY); ctx.lineTo(b.projX, b.projY); ctx.stroke();
          });

          g3dParticles.forEach(pt => {
            const a = pt.edge.sourceNode, b = pt.edge.targetNode;
            if (!visSet.has(a.id) || !visSet.has(b.id)) return;
            pt.t = (pt.t + pt.speed) % 1;
            const px = a.projX + (b.projX - a.projX) * pt.t, py = a.projY + (b.projY - a.projY) * pt.t;
            ctx.fillStyle = (G3D_COLORS[a.category] || G3D_COLORS.engine).fill;
            ctx.beginPath(); ctx.arc(px, py, 2.3, 0, Math.PI * 2); ctx.fill();
          });

          [...vis].sort((a, b) => b.depthZ - a.depthZ).forEach(n => {
            const col = G3D_COLORS[n.category] || G3D_COLORS.engine;
            const r = Math.max(7, n.size * n.projScale * 0.78);
            const sel = g3dSelected && g3dSelected.id === n.id;
            const grad = ctx.createRadialGradient(n.projX - r * 0.3, n.projY - r * 0.3, r * 0.1, n.projX, n.projY, r);
            grad.addColorStop(0, '#ffffff'); grad.addColorStop(0.3, col.fill); grad.addColorStop(1, '#0f172a');
            ctx.beginPath(); ctx.arc(n.projX, n.projY, r, 0, Math.PI * 2);
            ctx.fillStyle = grad; ctx.fill();
            if (sel) { ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2; ctx.stroke(); }
            ctx.font = `${sel ? '700' : '600'} 11px Inter, system-ui, sans-serif`;
            ctx.fillStyle = sel ? '#ffffff' : '#e2e8f0';
            ctx.textAlign = 'center';
            ctx.fillText(n.label, n.projX, n.projY + r + 13);
          });
          ctx.restore();
        }
        requestAnimationFrame(stepAndDraw);
      }
      requestAnimationFrame(stepAndDraw);
    }

    function set3DFilter(cat) { g3dFilter = cat; }
    function toggle3DRotate() {
      g3dRotate = !g3dRotate;
      document.getElementById('btn-3d-rotate').textContent = `3D Orbit: ${g3dRotate ? 'ON' : 'OFF'}`;
    }
    function toggle3DLayers() {
      g3dLayers = !g3dLayers;
      document.getElementById('btn-3d-layers').textContent = g3dLayers ? 'Layout: 3D Stratified Tiers' : 'Layout: 3D Force Sphere';
    }
    function zoom3D(f) { g3dZoom = Math.max(0.55, Math.min(2.2, g3dZoom * f)); }

    function initWorkspaces() {
      const sel = document.getElementById('ws-select');
      const keys = Object.keys(STATE.overviews || {});
      const opts = ['<option value="__sqlite_schema__">SQLite Core Data Models (6 Schema Tables)</option>']
        .concat(keys.map(k => `<option value="${k}">${k}</option>`));
      sel.innerHTML = opts.join('');
      if (keys.length > 0 && !document.getElementById('ov-ws').value) {
        document.getElementById('ov-ws').value = keys[0];
      }
      init3DCanvasEvents();
      renderGraph();
      renderOverridesAndQueries();
    }

    function renderGraph() {
      const ws = document.getElementById('ws-select')?.value || '__sqlite_schema__';
      if (ws === '__sqlite_schema__' || !(STATE.overviews || {})[ws]) {
        load3DGraph(SQLITE_CORE_MODELS);
      } else {
        const ov = STATE.overviews[ws];
        const tierMap = { model: -1, repo: -0.5, engine: 0, api: 0.6, ui: 1.1 };
        const dynNodes = (ov.files || []).slice(0, 30).map(f => {
          const cat = classify3DCategory(f.rel_path, f.summary);
          return {
            id: f.rel_path,
            label: f.rel_path.split('/').pop(),
            fullPath: f.rel_path,
            category: cat,
            tier: tierMap[cat] || 0,
            size: Math.min(24, Math.max(14, 13 + (f.symbol_count || 0))),
            summary: f.summary,
            fields: (f.key_symbols && f.key_symbols.length) ? f.key_symbols : [f.rel_path]
          };
        });
        const idSet = new Set(dynNodes.map(n => n.id));
        const dynEdges = (ov.relationships || [])
          .filter(r => idSet.has(r.source) && idSet.has(r.target))
          .map(r => ({ source: r.source, target: r.target, type: r.type }));
        load3DGraph(dynNodes.length ? { nodes: dynNodes, edges: dynEdges } : SQLITE_CORE_MODELS);
      }
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
      document.getElementById('files-list').innerHTML = filesHtml || '<p class="text-xs cg-muted">Select an indexed workspace above to browse tracked files.</p>';

      const relsHtml = (ov.relationships || []).map(r => `
        <div class="p-2.5 rounded-lg border border-[var(--border,#334155)] text-xs space-y-1">
          <div class="font-mono"><span class="text-sky-400">${r.source}</span> <span class="px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">[${r.type}]</span> &rarr; <span class="text-emerald-400">${r.target}</span></div>
          ${r.description ? `<div class="cg-muted">${r.description}</div>` : ''}
        </div>
      `).join('');
      document.getElementById('rels-list').innerHTML = relsHtml || '<p class="text-xs cg-muted">Select an indexed workspace above to browse file relationships.</p>';
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
      toast.textContent = `Running ${action} on ${ws}...`;
      try {
        const res = await fetch(`${API_BASE}/api/action`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, workspace_path: ws })
        });
        const data = await res.json();
        toast.textContent = JSON.stringify(data, null, 2);
        await reloadState();
      } catch (err) {
        const cmdMap = {
          verify: `python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py verify --workspace "${ws}"`,
          refresh_stale: `python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py refresh --workspace "${ws}" --mode stale_only`,
          refresh_all: `python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py refresh --workspace "${ws}" --mode force_all`,
        };
        toast.textContent = `Start local server (python3 scripts/ui_server.py --port 8765) or run via CLI:\\n$ ${cmdMap[action]}`;
      }
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
      try {
        await fetch(`${API_BASE}/api/action`, {
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
      } catch (err) {
        document.getElementById('ov-cli-preview').textContent =
          `Run: python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py correct -w "${ws}" -k "${key}" --mistake "${mistake}" --truth "${truth}" --priority ${priority}`;
      }
    }

    async function reloadState() {
      const badge = document.getElementById('mode-badge');
      try {
        const res = await fetch(`${API_BASE}/api/state`);
        if (res.ok) {
          STATE = await res.json();
          if (badge) {
            badge.textContent = 'Live SQLite API Connected';
            badge.className = 'text-xs px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-medium';
          }
        }
      } catch (err) {
        if (badge) {
          badge.textContent = 'Offline — Run: python3 scripts/ui_server.py';
          badge.className = 'text-xs px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30 font-medium';
        }
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
    return DASHBOARD_HTML_TEMPLATE


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
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
            self._send_cors_headers()
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
