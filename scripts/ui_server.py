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
import hmac
import http.server
import json
import os
import secrets
import sys
import urllib.parse
from typing import Any, Dict

SERVER_CSRF_TOKEN = secrets.token_urlsafe(32)

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
  <title>Context Graph &amp; Query Cache: Control Center</title>
  <meta name="description" content="Multi-LLM token cost ledger, 3D AST and schema relationship graph, anti-hallucination ground-truth pins, and query cache console." />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Geologica:wght,CRSV,SHRP@200..500,0,0..100&amp;display=swap" rel="stylesheet" />
  <style>
/* Hallmark · shape: app screen · genre: modern-minimal · theme: Vantage (deal 2/3, seed app-console-engineers-inspect-4348·aacbc226·2026-11-18·r0) · redesign: full
 * nav: top bar with inline tab strip · signature: feature cost ledger and 3D point-cloud schema graph · states: loading, empty, error, full · vantage: object/steel
 * axes: dark/grotesk-sans/chromatic-lime · posture: restrained · contrast: pass · finish-review: subagent · 8 findings · 8 resolved · gap: none · v2.0.0 */
/* Hallmark · pre-emit critique: P5 H5 E5 S4 R5 V5 · weakest: S, five KPI cards above tables looked like a stock SaaS template; replaced with a corner-ticked tabular measurement bar integrated with the feature cost ledger */
/* Hallmark · dropped tailwindcss.min.js · replaced CDN runtime with self-contained Vantage OKLCH token stylesheet */
/* Hallmark · reworded "Context Graph & Query Cache — Control Center" to "Context Graph & Query Cache: Control Center" · 19 names the dash */
/* Hallmark · reworded "Multi-LLM Token Analytics • File & Symbol Graph • Anti-Hallucination Ground-Truth Control Center" to "Multi-LLM token ledger, file and symbol graph, and ground-truth control center" · 63 names the middle dots */
/* Hallmark · reworded "Drag to Orbit 3D • Scroll to Zoom • Click Node to Inspect" to "Drag to orbit 3D, scroll to zoom, click a node to inspect" · 63 names the middle dots */
:root {
  color-scheme: dark;
  --space-3xs: 2px; --space-2xs: 4px; --space-xs: 8px; --space-sm: 12px; --space-md: 16px; --space-lg: 24px; --space-xl: 40px; --space-2xl: 64px; --space-3xl: 96px; --space-4xl: 144px;
  --text-xs: 0.75rem; --text-sm: 0.875rem; --text-md: 1rem; --text-lg: 1.2rem; --text-xl: 1.44rem; --text-2xl: 1.728rem; --text-3xl: 2.074rem;
  --text-display-s: 1.44rem; --text-display: 1.728rem; --text-section: 1.2rem; --text-title: 1rem; --text-lead: 1rem;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1); --ease-in: cubic-bezier(0.7, 0, 0.84, 0); --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
  --dur-micro: 120ms; --dur-short: 220ms; --dur-long: 420ms;
  --color-error: oklch(72% 0.15 27); --color-success: oklch(76% 0.13 150);
  --container: 1440px; --gutter: 64px; --gap-columns: 32px; --section-gap-s: 120px; --section-gap: 144px; --section-gap-l: 176px;
  --z-base: 1; --z-raised: 10; --z-dropdown: 100; --z-sticky: 200; --z-sticky-nav: 300; --z-modal: 400; --z-toast: 500; --z-tooltip: 600;
  --color-paper: oklch(13.5% 0.012 235); --color-paper-2: oklch(17% 0.014 235); --color-paper-3: oklch(21% 0.016 235);
  --color-ink: oklch(95% 0.006 230); --color-ink-2: oklch(82% 0.012 230); --color-muted: oklch(66% 0.016 230);
  --color-rule: oklch(27% 0.014 235); --color-rule-2: oklch(34% 0.016 235);
  --color-accent: oklch(89% 0.19 126); --color-accent-hi: oklch(93% 0.17 126); --color-accent-ink: oklch(19% 0.04 126); --color-focus: oklch(89% 0.19 126);
  --point-lo: oklch(42% 0.04 245); --point-mid: oklch(70% 0.04 232); --point-hi: oklch(96% 0.02 215);
  --point-edge: oklch(54% 0.03 235); --point-edge-hi: oklch(89% 0.19 126); --point-core: oklch(11.5% 0.012 235);
  --color-slot: oklch(21% 0.016 235);
  --font-display: "Geologica", ui-sans-serif, system-ui, sans-serif;
  --font-body: "Geologica", ui-sans-serif, system-ui, sans-serif;
  --radius-card: 4px; --radius-pill: 999px; --rule-hair: 1px; --tick: 10px;
  --shadow-card: none;
  --tracking-display: -0.035em; --display-weight: 300;
}
*, *::before, *::after { box-sizing: border-box; }
html, body { overflow-x: clip; }
html { scrollbar-color: var(--color-muted) var(--color-paper); scroll-padding-top: var(--space-3xl); }
body {
  margin: 0;
  background: var(--color-paper);
  color: var(--color-ink);
  font-family: var(--font-body);
  font-weight: 300;
  font-variation-settings: "SHRP" 0;
  font-size: var(--text-md);
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  caret-color: var(--color-accent);
}
::selection { background: color-mix(in oklab, var(--color-accent) 22%, transparent); color: var(--color-ink); }
:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; }
a { color: inherit; text-decoration-thickness: 1px; text-underline-offset: 0.16em; }
h1, h2, h3 {
  margin: 0;
  font-family: var(--font-display);
  font-weight: var(--display-weight);
  font-variation-settings: "SHRP" 100;
  font-synthesis: none;
  letter-spacing: var(--tracking-display);
  line-height: 1.05;
  overflow-wrap: break-word;
  min-width: 0;
  text-wrap: balance;
}
h1 { max-width: 24ch; font-size: var(--text-display); }
h2 { max-width: 34ch; font-size: var(--text-section); font-weight: 400; }
h3 { max-width: 42ch; font-size: var(--text-title); font-weight: 400; line-height: 1.2; }
p { margin: 0; text-wrap: pretty; color: var(--color-ink-2); }
p:not([class]) { max-width: 65ch; }
img, video, canvas, svg { max-width: 100%; display: block; }
[hidden], .hidden { display: none !important; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
button, input, select, textarea { font: inherit; }
.container { width: 100%; max-width: var(--container); margin-inline: auto; padding-inline: var(--gutter); padding-block: var(--space-lg); }
.num, .figure, td.num, th.num { font-variant-numeric: tabular-nums; }
.num { font-weight: 400; }
.num .u { color: var(--color-muted); font-size: var(--text-xs); }
.muted { color: var(--color-muted); font-size: var(--text-sm); }

/* Vantage four-corner symmetric ticks on measured surfaces */
.ticks {
  position: relative;
  background: var(--color-paper-2);
  border-radius: var(--radius-card);
  padding: var(--space-lg);
}
.ticks::before,
.ticks::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  border: var(--rule-hair) solid var(--color-rule-2);
}
.ticks::before {
  -webkit-mask: linear-gradient(90deg, var(--color-ink) var(--tick), transparent var(--tick), transparent calc(100% - var(--tick)), var(--color-ink) calc(100% - var(--tick)));
  mask: linear-gradient(90deg, var(--color-ink) var(--tick), transparent var(--tick), transparent calc(100% - var(--tick)), var(--color-ink) calc(100% - var(--tick)));
}
.ticks::after {
  -webkit-mask: linear-gradient(180deg, var(--color-ink) var(--tick), transparent var(--tick), transparent calc(100% - var(--tick)), var(--color-ink) calc(100% - var(--tick)));
  mask: linear-gradient(180deg, var(--color-ink) var(--tick), transparent var(--tick), transparent calc(100% - var(--tick)), var(--color-ink) calc(100% - var(--tick)));
}

/* App Shell & Navigation */
.app-stack { display: flex; flex-direction: column; gap: var(--space-lg); }
.shell-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding-bottom: var(--space-md);
  border-bottom: var(--rule-hair) solid var(--color-rule);
}
.shell-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
}
.brand-block { display: flex; flex-direction: column; gap: var(--space-2xs); }
.brand-sub { font-size: var(--text-sm); color: var(--color-muted); }
.shell-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-sm); }
.status-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  min-height: 36px;
  padding: 0 var(--space-sm);
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: var(--radius-pill);
  font-size: var(--text-sm);
  color: var(--color-ink-2);
  white-space: nowrap;
}
.status-chip::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--color-accent);
}
.status-chip[data-offline="true"]::before { background: var(--color-muted); }

/* Controls (8 states, 38px app height with 44px hit target) */
.btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-xs);
  min-height: 38px;
  padding: 0 var(--space-md);
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: var(--radius-pill);
  background: transparent;
  color: var(--color-ink);
  font-size: var(--text-sm);
  font-weight: 400;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color var(--dur-short) var(--ease-out), transform var(--dur-micro) var(--ease-out);
}
.btn::after { content: ""; position: absolute; inset: -4px 0; }
@media (hover: hover) {
  .btn:hover { background: var(--color-paper-3); }
}
.btn:active { transform: translateY(1px); }
.btn:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; }
.btn:disabled, .btn[aria-disabled="true"] { opacity: 0.55; cursor: not-allowed; transform: none; }
.btn[aria-busy="true"] { cursor: progress; opacity: 0.75; }
.btn--primary {
  background: var(--color-accent);
  color: var(--color-accent-ink);
  border-color: var(--color-accent);
}
@media (hover: hover) {
  .btn--primary:hover { background: var(--color-accent-hi); }
}
.btn[aria-pressed="true"], .btn.is-active {
  background: var(--color-paper-3);
  border-color: var(--color-accent);
  color: var(--color-ink);
}
.cat-swatch {
  width: 6px;
  height: 6px;
  border-radius: var(--radius-pill);
  background: var(--point-mid);
  flex-shrink: 0;
}
.cat-swatch--model { background: var(--color-accent); }
.cat-swatch--engine { background: var(--point-hi); }
.cat-swatch--repo { background: var(--point-mid); }
.cat-swatch--api { background: var(--point-lo); }

/* Tab strip */
.tab-bar {
  display: flex;
  flex-wrap: nowrap;
  gap: var(--space-xs);
  overflow-x: auto;
  padding-bottom: var(--space-3xs);
}
.tab-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  padding: 0 var(--space-md);
  border: var(--rule-hair) solid transparent;
  border-radius: var(--radius-card);
  background: transparent;
  color: var(--color-muted);
  font-size: var(--text-sm);
  font-weight: 400;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color var(--dur-short) var(--ease-out);
}
@media (hover: hover) {
  .tab-btn:hover { color: var(--color-ink); background: var(--color-paper-2); }
}
.tab-btn:active { transform: translateY(1px); }
.tab-btn:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; }
.tab-btn:disabled, .tab-btn[aria-disabled="true"] { opacity: 0.55; cursor: not-allowed; }
.tab-btn.is-active {
  background: var(--color-paper-2);
  border-color: var(--color-rule-2);
  color: var(--color-ink);
}
.tab-btn.is-active::before {
  content: "";
  width: 6px;
  height: 6px;
  margin-right: var(--space-xs);
  border-radius: var(--radius-pill);
  background: var(--color-accent);
}

/* Inputs & Selects (8 states, constant border width) */
.input {
  min-height: 38px;
  max-width: 100%;
  min-width: 0;
  padding: 0 var(--space-sm);
  border: var(--rule-hair) solid var(--color-muted);
  border-radius: var(--radius-card);
  background: var(--color-paper);
  color: var(--color-ink);
  font-size: var(--text-sm);
  text-overflow: ellipsis;
  outline: 2px solid transparent;
  outline-offset: -2px;
  transition: background-color var(--dur-short) var(--ease-out);
}
.input::placeholder { color: var(--color-muted); }
@media (hover: hover) {
  .input:hover { background: var(--color-paper-2); }
}
.input:focus-visible { outline-color: var(--color-focus); border-color: var(--color-ink-2); }
.input:disabled, .input[aria-disabled="true"] { opacity: 0.55; cursor: not-allowed; }
.input[aria-invalid="true"] { border-color: var(--color-error); }
.input--search { width: 18rem; max-width: 100%; }

/* Measured Telemetry Strip (#kpi-grid) */
.telemetry-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  padding: var(--space-md) var(--space-lg);
  background: var(--color-paper-2);
}
.telemetry-cell {
  display: flex;
  flex-direction: column;
  gap: var(--space-2xs);
  padding-inline: var(--space-md);
  border-left: var(--rule-hair) solid var(--color-rule);
  min-width: 0;
}
.telemetry-cell:first-child { padding-left: 0; border-left: 0; }
.telemetry-cell:last-child { padding-right: 0; }
.telemetry-label { font-size: var(--text-sm); color: var(--color-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.telemetry-val { font-family: var(--font-display); font-size: var(--text-xl); font-weight: 300; font-variant-numeric: tabular-nums; color: var(--color-ink); line-height: 1.1; }
.telemetry-val--signal { color: var(--color-accent); }
.telemetry-sub { font-size: var(--text-xs); color: var(--color-ink-2); font-variant-numeric: tabular-nums; }

/* Panels, Grids & Tables (surface ladder: paper with top hairlines for ledgers, ticks on measured objects) */
.view-stack { display: flex; flex-direction: column; gap: var(--space-lg); }
.split-grid { display: grid; grid-template-columns: 7fr 5fr; gap: var(--gap-columns); align-items: start; }
.panel { display: flex; flex-direction: column; gap: var(--space-md); min-width: 0; }
.ledger-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding-top: var(--space-lg);
  border-top: var(--rule-hair) solid var(--color-rule);
  min-width: 0;
}
.panel-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}
.panel-title-group { display: flex; flex-direction: column; gap: var(--space-3xs); }
.table-scroll { width: 100%; overflow-x: auto; max-height: 26rem; overflow-y: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); text-align: left; }
.data-table th {
  position: sticky;
  top: 0;
  z-index: var(--z-raised);
  background: var(--color-paper);
  padding: var(--space-xs) var(--space-sm);
  border-bottom: var(--rule-hair) solid var(--color-rule-2);
  color: var(--color-muted);
  font-weight: 400;
  font-size: var(--text-sm);
  white-space: nowrap;
}
.data-table td {
  padding: var(--space-sm);
  border-bottom: var(--rule-hair) solid var(--color-rule);
  color: var(--color-ink-2);
  vertical-align: top;
}
.data-table tr:last-child td { border-bottom: 0; }
.data-table td.primary-col { color: var(--color-ink); font-weight: 400; max-width: 18rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.data-table th.num, .data-table td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.signal-text { color: var(--color-accent); font-weight: 400; }
.tag {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2xs);
  padding: var(--space-3xs) var(--space-xs);
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: var(--radius-card);
  font-size: var(--text-xs);
  color: var(--color-ink-2);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.tag--live { border-color: var(--color-accent); color: var(--color-accent); }

/* 3D Point-Cloud & Schema Viewport */
.toolbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  padding-bottom: var(--space-md);
  border-bottom: var(--rule-hair) solid var(--color-rule);
}
.toolbar-group { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-xs); min-width: 0; max-width: 100%; }
.graph-layout { display: grid; grid-template-columns: 8fr 4fr; gap: var(--gap-columns); align-items: stretch; }
.canvas-stage {
  position: relative;
  height: 28rem;
  background: var(--point-core);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-card);
  overflow: hidden;
}
.canvas-stage canvas { width: 100%; height: 100%; cursor: grab; }
.canvas-stage canvas:active { cursor: grabbing; }
.canvas-overlay-top {
  position: absolute;
  top: var(--space-sm);
  left: var(--space-sm);
  right: var(--space-sm);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2xs);
  pointer-events: none;
}
.canvas-overlay-top .btn { pointer-events: auto; min-height: 32px; padding: 0 var(--space-sm); font-size: var(--text-xs); background: color-mix(in oklab, var(--color-paper) 84%, transparent); }
.canvas-overlay-bottom {
  position: absolute;
  bottom: var(--space-sm);
  left: var(--space-sm);
  right: var(--space-sm);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-xs);
  pointer-events: none;
}
.hud-caption {
  padding: var(--space-2xs) var(--space-sm);
  background: color-mix(in oklab, var(--color-paper) 86%, transparent);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-card);
  font-size: var(--text-xs);
  color: var(--color-ink-2);
}
.canvas-zoom { display: flex; gap: var(--space-2xs); pointer-events: auto; }
.canvas-zoom .btn { min-height: 32px; padding: 0 var(--space-sm); background: color-mix(in oklab, var(--color-paper) 88%, transparent); }
.inspector-pane {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 28rem;
}
.inspector-scroll { display: flex; flex-direction: column; gap: var(--space-md); overflow-y: auto; padding-right: var(--space-2xs); }
.inspector-foot {
  padding-top: var(--space-sm);
  border-top: var(--rule-hair) solid var(--color-rule);
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--color-muted);
}
.record-list { display: flex; flex-direction: column; gap: var(--space-xs); max-height: 28rem; overflow-y: auto; }
.record-row {
  padding: var(--space-sm);
  border-bottom: var(--rule-hair) solid var(--color-rule);
  display: flex;
  flex-direction: column;
  gap: var(--space-2xs);
}
.record-row:last-child { border-bottom: 0; }
.record-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-xs); }
.code-chip-row { display: flex; flex-wrap: wrap; gap: var(--space-2xs); padding-top: var(--space-3xs); }
.code-chip {
  padding: var(--space-3xs) var(--space-xs);
  background: var(--color-paper-2);
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-card);
  font-size: var(--text-xs);
  color: var(--color-ink-2);
}

/* Override Form & Status */
.form-grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-sm); }
.form-grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-sm); }
.field-group { display: flex; flex-direction: column; gap: var(--space-2xs); min-width: 0; }
.field-label { font-size: var(--text-sm); color: var(--color-ink-2); font-weight: 400; }
.form-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}
.helper-line {
  min-height: 1lh;
  font-size: var(--text-xs);
  color: var(--color-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 48rem;
}
.helper-line[data-error="true"] { color: var(--color-error); }
.toast-banner {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-paper-2);
  border-left: 2px solid var(--color-accent);
  font-size: var(--text-sm);
  color: var(--color-ink);
  white-space: pre-wrap;
}
.empty-state {
  padding: var(--space-lg) var(--space-md);
  color: var(--color-muted);
  font-size: var(--text-sm);
}
.error-state {
  padding: var(--space-lg) var(--space-md);
  color: var(--color-error);
  font-size: var(--text-sm);
}
.skeleton-bar {
  display: block;
  height: 14px;
  width: 72%;
  background: var(--color-paper-3);
  border-radius: var(--radius-card);
}

@media (max-width: 60rem) {
  :root { --gutter: 24px; }
  .telemetry-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: var(--space-md); }
  .telemetry-cell:nth-child(odd) { padding-left: 0; border-left: 0; }
  .split-grid, .graph-layout, .form-grid-3, .form-grid-2 { grid-template-columns: minmax(0, 1fr); }
  .inspector-pane { height: auto; max-height: 24rem; }
}
@media (max-width: 40rem) {
  :root { --gutter: 16px; --gap-columns: 16px; }
  .telemetry-strip { grid-template-columns: minmax(0, 1fr); }
  .telemetry-cell { padding-inline: 0; border-left: 0; border-top: var(--rule-hair) solid var(--color-rule); padding-top: var(--space-xs); }
  .telemetry-cell:first-child { border-top: 0; padding-top: 0; }
  .hud-caption { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  *:not(.keep-motion), *:not(.keep-motion)::before, *:not(.keep-motion)::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
  </style>
</head>
<body>
  <div class="container app-stack">
    <!-- App Shell Header -->
    <header class="shell-header">
      <div class="shell-top">
        <div class="brand-block">
          <h1>Context Graph &amp; Query Cache</h1>
          <p class="brand-sub">Multi-LLM token ledger, file and symbol graph, and ground-truth control center</p>
        </div>
        <div class="shell-actions">
          <span id="mode-badge" class="status-chip" role="status">SQLite cache active</span>
          <button type="button" onclick="reloadState()" id="btn-sync" class="btn btn--primary">Sync data</button>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <nav class="tab-bar" role="tablist" aria-label="Console views">
        <button type="button" role="tab" aria-selected="true" onclick="switchTab('tokens')" id="tab-tokens" class="tab-btn is-active">
          1. Cost &amp; token ledger
        </button>
        <button type="button" role="tab" aria-selected="false" onclick="switchTab('graph')" id="tab-graph" class="tab-btn">
          2. 3D schema &amp; AST graph
        </button>
        <button type="button" role="tab" aria-selected="false" onclick="switchTab('overrides')" id="tab-overrides" class="tab-btn">
          3. Ground-truth overrides
        </button>
        <button type="button" role="tab" aria-selected="false" onclick="switchTab('queries')" id="tab-queries" class="tab-btn">
          4. Cached queries
        </button>
      </nav>
    </header>

    <!-- Measured Telemetry Strip -->
    <section class="ticks telemetry-strip" id="kpi-grid" aria-label="Workspace telemetry summary"></section>

    <!-- Tab 1: Cost per Feature & Token Usage -->
    <main id="view-tokens" class="view-stack">
      <section class="ledger-section">
        <div class="panel-head">
          <div class="panel-title-group">
            <h2>Cost &amp; token usage per feature</h2>
            <p class="muted">Plugin savings report $0.00 on branches where Context Graph was not invoked.</p>
          </div>
          <label class="visually-hidden" for="feature-search">Filter features, tickets, or repositories</label>
          <input id="feature-search" name="feature_search" oninput="renderTokens()" type="search" placeholder="e.g. #101 or main" class="input input--search" />
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>Feature or task</th>
                <th>Ticket</th>
                <th>Repo &amp; branch</th>
                <th class="num">Convs</th>
                <th class="num">Turns</th>
                <th class="num">Total tokens</th>
                <th>Plugin used</th>
                <th class="num">Tokens saved</th>
                <th class="num">Actual cost</th>
                <th class="num">Saved cost</th>
              </tr>
            </thead>
            <tbody id="table-features"></tbody>
          </table>
        </div>
      </section>

      <section class="ledger-section">
        <div class="panel-head">
          <div class="panel-title-group">
            <h2>Usage by LLM client</h2>
            <p class="muted">Scanned from Antigravity, Claude Code, and Codex CLI transcripts.</p>
          </div>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>Client</th>
                <th class="num">Convs</th>
                <th class="num">Turns</th>
                <th class="num">Input</th>
                <th class="num">Prefix cache</th>
                <th class="num">Output</th>
                <th class="num">Total</th>
                <th class="num">Calls</th>
                <th class="num">Cost</th>
                <th class="num">Saved</th>
              </tr>
            </thead>
            <tbody id="table-clients"></tbody>
          </table>
        </div>
      </section>

      <section class="ledger-section">
        <div class="panel-head">
          <div class="panel-title-group">
            <h2>Cost by project &amp; repository</h2>
            <p class="muted">Grouped by Git root and active branch.</p>
          </div>
          <label class="visually-hidden" for="repo-search">Filter repository or branch</label>
          <input id="repo-search" name="repo_search" oninput="renderTokens()" type="search" placeholder="e.g. context-graph" class="input input--search" />
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>Project or repo</th>
                <th>Branch</th>
                <th class="num">Convs</th>
                <th class="num">Turns</th>
                <th class="num">Total tokens</th>
                <th>Plugin</th>
                <th class="num">Tokens saved</th>
                <th class="num">Actual cost</th>
                <th class="num">Saved</th>
              </tr>
            </thead>
            <tbody id="table-repos"></tbody>
          </table>
        </div>
      </section>

      <section class="ledger-section">
        <div class="panel-head">
          <div class="panel-title-group">
            <h2>Token usage per conversation</h2>
            <p class="muted">Individual session transcripts ordered by recent activity.</p>
          </div>
          <label class="visually-hidden" for="conv-search">Filter conversations by prompt, repo, or ID</label>
          <input id="conv-search" name="conv_search" oninput="renderTokens()" type="search" placeholder="e.g. 1cabc4bf or audit" class="input input--search" />
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>Client</th>
                <th>Conv ID</th>
                <th>Feature or prompt</th>
                <th>Repository</th>
                <th class="num">Turns</th>
                <th class="num">Total tokens</th>
                <th>Plugin used</th>
                <th class="num">Tokens saved</th>
                <th class="num">Actual cost</th>
                <th class="num">Saved cost</th>
              </tr>
            </thead>
            <tbody id="table-convs"></tbody>
          </table>
        </div>
      </section>
    </main>

    <!-- Tab 2: 3D Data Models & Context Graph -->
    <section id="view-graph" class="view-stack hidden" aria-label="3D Data Models and Context Graph">
      <div class="toolbar-row">
        <div class="toolbar-group">
          <label class="field-label" for="ws-select">Workspace</label>
          <select id="ws-select" name="workspace" onchange="renderGraph()" class="input"></select>
          <button type="button" onclick="toggle3DRotate()" id="btn-3d-rotate" class="btn is-active">3D orbit: on</button>
          <button type="button" onclick="toggle3DLayers()" id="btn-3d-layers" class="btn">Layout: force sphere</button>
        </div>
        <div class="toolbar-group">
          <button type="button" onclick="apiAction('verify')" class="btn">Verify symbols</button>
          <button type="button" onclick="apiAction('refresh_stale')" class="btn">Refresh stale</button>
          <button type="button" onclick="apiAction('refresh_all')" class="btn">Rebuild index</button>
        </div>
      </div>

      <div id="action-toast" role="status" aria-live="polite" class="hidden toast-banner"></div>

      <!-- Interactive 3D Point-Cloud & AST Graph Viewport -->
      <div class="graph-layout">
        <div class="canvas-stage" id="graph3d-stage">
          <canvas id="graph3d-canvas" role="img" aria-label="Interactive 3D point-cloud data model and AST relationship graph"></canvas>
          <div class="canvas-overlay-top" role="toolbar" aria-label="Node category filter">
            <button type="button" data-filter="all" aria-pressed="true" onclick="set3DFilter('all')" class="btn is-active">All clusters</button>
            <button type="button" data-filter="model" aria-pressed="false" onclick="set3DFilter('model')" class="btn"><span class="cat-swatch cat-swatch--model" aria-hidden="true"></span>Data models</button>
            <button type="button" data-filter="engine" aria-pressed="false" onclick="set3DFilter('engine')" class="btn"><span class="cat-swatch cat-swatch--engine" aria-hidden="true"></span>Engines</button>
            <button type="button" data-filter="repo" aria-pressed="false" onclick="set3DFilter('repo')" class="btn"><span class="cat-swatch cat-swatch--repo" aria-hidden="true"></span>Repositories</button>
            <button type="button" data-filter="api" aria-pressed="false" onclick="set3DFilter('api')" class="btn"><span class="cat-swatch cat-swatch--api" aria-hidden="true"></span>APIs &amp; pins</button>
          </div>
          <div class="canvas-overlay-bottom">
            <span id="graph3d-hud" class="hud-caption">Drag to orbit 3D, scroll to zoom, click a point cluster to inspect</span>
            <div class="canvas-zoom">
              <button type="button" onclick="zoom3D(1.18)" class="btn" aria-label="Zoom in">+</button>
              <button type="button" onclick="zoom3D(0.85)" class="btn" aria-label="Zoom out">&minus;</button>
            </div>
          </div>
        </div>
        <aside class="ticks inspector-pane" aria-label="Selected node inspector">
          <div id="graph3d-inspector" class="inspector-scroll"></div>
          <div class="inspector-foot">
            <span>3D lidar point cloud</span>
            <span class="signal-text">PK, FK &amp; AST scan</span>
          </div>
        </aside>
      </div>

      <div class="split-grid">
        <section class="ledger-section">
          <h2>Tracked files &amp; AST symbols</h2>
          <div id="files-list" class="record-list"></div>
        </section>
        <section class="ledger-section">
          <h2>Implementation relationships</h2>
          <div id="rels-list" class="record-list"></div>
        </section>
      </div>
    </section>

    <!-- Tab 3: Anti-Hallucination & Overrides -->
    <section id="view-overrides" class="view-stack hidden" aria-label="Anti-Hallucination Ground-Truth Overrides">
      <div class="ticks panel">
        <div class="panel-title-group">
          <h2>Pin a verified ground-truth override</h2>
          <p class="muted">Ground-truth pins are injected at SessionStart and file context lookups so corrected mistakes never recur.</p>
        </div>
        <div class="form-grid-3">
          <div class="field-group">
            <label class="field-label" for="ov-ws">Workspace path (required)</label>
            <input id="ov-ws" name="workspace_path" type="text" placeholder="global" class="input" aria-required="true" />
          </div>
          <div class="field-group">
            <label class="field-label" for="ov-key">Override slug (required)</label>
            <input id="ov-key" name="override_key" type="text" placeholder="api-timeout-ms" class="input" aria-required="true" />
          </div>
          <div class="field-group">
            <label class="field-label" for="ov-priority">Priority</label>
            <select id="ov-priority" name="priority" class="input">
              <option value="critical">Priority: critical</option>
              <option value="high" selected>Priority: high</option>
              <option value="normal">Priority: normal</option>
            </select>
          </div>
        </div>
        <div class="form-grid-2">
          <div class="field-group">
            <label class="field-label" for="ov-mistake">Hallucination or false assumption</label>
            <input id="ov-mistake" name="mistake" type="text" placeholder="Legacy v1 controller handles v3 routes" class="input" />
          </div>
          <div class="field-group">
            <label class="field-label" for="ov-truth">Verified ground-truth rule (required)</label>
            <input id="ov-truth" name="verified_truth" type="text" placeholder="AdmissionV3 uses AdmissionV3Engine" class="input" aria-required="true" />
          </div>
        </div>
        <div class="form-footer">
          <span id="ov-cli-preview" class="helper-line" aria-live="polite">Ready to pin ground-truth rule to SQLite store.</span>
          <button type="button" onclick="submitOverride()" class="btn btn--primary">Save ground-truth pin</button>
        </div>
      </div>

      <div class="ledger-section">
        <h2>Active ground-truth overrides</h2>
        <div id="overrides-list" class="record-list"></div>
      </div>
    </section>

    <!-- Tab 4: Cached Queries -->
    <section id="view-queries" class="view-stack hidden" aria-label="Cached Queries and Generated Data">
      <div class="ledger-section">
        <h2>Stored queries &amp; generated datasets</h2>
        <div id="queries-list" class="record-list"></div>
      </div>
    </section>
  </div>

  <script>
    const vscodeApi = (typeof acquireVsCodeApi === 'function') ? acquireVsCodeApi() : null;
    const API_BASE = window.location.protocol.startsWith('http') ? '' : 'http://127.0.0.1:8765';
    const REDUCED_MOTION = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let DATA_STATE = window.__INITIAL_CG_STATE__ ? 'full' : 'loading';
    let STATE = window.__INITIAL_CG_STATE__ || {
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

    function readToken(name) {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    window.addEventListener('message', event => {
      const msg = event.data;
      if (!msg || typeof msg !== 'object') return;
      if (msg.type === 'stateUpdate' && msg.state) {
        STATE = msg.state;
        DATA_STATE = 'full';
        const badge = document.getElementById('mode-badge');
        if (badge) {
          badge.textContent = 'VS Code extension connected';
          badge.removeAttribute('data-offline');
        }
        if (msg.toastMessage) {
          const toast = document.getElementById('action-toast');
          if (toast) {
            toast.classList.remove('hidden');
            toast.textContent = msg.toastMessage;
          }
        }
        renderKPIs();
        renderTokens();
        initWorkspaces();
      }
    });

    function fmtNum(n) {
      return Number(n || 0).toLocaleString();
    }

    function fmtUsd(n) {
      return '$' + Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function switchTab(tab) {
      ['tokens', 'graph', 'overrides', 'queries'].forEach(t => {
        const view = document.getElementById('view-' + t);
        if (view) view.classList.toggle('hidden', t !== tab);
        const btn = document.getElementById('tab-' + t);
        if (btn) {
          btn.classList.toggle('is-active', t === tab);
          btn.setAttribute('aria-selected', t === tab ? 'true' : 'false');
        }
      });
      if (typeof history !== 'undefined' && history.replaceState) {
        try {
          const url = new URL(window.location.href);
          url.searchParams.set('tab', tab);
          history.replaceState(null, '', url.toString());
        } catch (_) {}
      }
    }

    function pluginBadge(calls) {
      const n = Number(calls || 0);
      if (n > 0) {
        return `<span class="tag tag--live">Yes (${n})</span>`;
      }
      return `<span class="tag">No</span>`;
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
        { label: 'Est. total LLM spend', val: fmtUsd(gt.estimated_cost_usd), sub: `${fmtNum(gt.total_conversations)} convs across ${featCount} features`, signal: false },
        { label: 'Saved by Context Graph', val: fmtUsd(gt.estimated_cache_savings_usd), sub: `${fmtNum(gt.plugin_tokens_saved)} tokens (${fmtNum(gt.plugin_calls)} calls)`, signal: true },
        { label: 'Total tokens tracked', val: fmtNum(gt.total_tokens), sub: `${fmtNum(gt.input_tokens)} in / ${fmtNum(gt.output_tokens)} out`, signal: false },
        { label: 'Indexed AST graph', val: `${fmtNum(totalFiles)} files`, sub: `${fmtNum(totalRels)} implementation edges`, signal: false },
        { label: 'Ground-truth pins', val: `${fmtNum(totalOverrides)}`, sub: 'Active anti-hallucination rules', signal: false },
      ];

      document.getElementById('kpi-grid').innerHTML = cards.map(c => `
        <div class="telemetry-cell">
          <div class="telemetry-label">${c.label}</div>
          <div class="telemetry-val ${c.signal ? 'telemetry-val--signal' : ''}">${DATA_STATE === 'loading' ? '<span class="skeleton-bar" aria-hidden="true"></span>' : c.val}</div>
          <div class="telemetry-sub">${c.sub}</div>
        </div>
      `).join('');
    }

    function stateTableRow(colspan, what, why) {
      if (DATA_STATE === 'loading') {
        return `<tr><td colspan="${colspan}"><span class="skeleton-bar" aria-hidden="true"></span></td></tr>`;
      }
      if (DATA_STATE === 'error') {
        return `<tr><td colspan="${colspan}" class="error-state">Local SQLite API at 127.0.0.1:8765 did not respond. Start python3 scripts/ui_server.py --port 8765 and click Sync data.</td></tr>`;
      }
      return `<tr><td colspan="${colspan}" class="empty-state">${what}. ${why}</td></tr>`;
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
        featEl.innerHTML = features.length ? features.map(f => {
          const used = Number(f.plugin_calls || 0) > 0;
          return `
            <tr>
              <td class="primary-col" title="${(f.feature_name || '').replace(/"/g, '&quot;')}">${f.feature_name}</td>
              <td class="num">${f.ticket_id || 'None'}</td>
              <td>
                <div>${f.repo_name}</div>
                <div class="muted">${f.git_branch || 'default'}</div>
              </td>
              <td class="num">${fmtNum(f.conversation_count)}</td>
              <td class="num">${fmtNum(f.total_turns)}</td>
              <td class="num">${fmtNum(f.total_tokens)}</td>
              <td>${pluginBadge(f.plugin_calls)}</td>
              <td class="num ${used ? 'signal-text' : ''}">${used ? fmtNum(f.plugin_tokens_saved) : '0'}</td>
              <td class="num">${fmtUsd(f.estimated_cost_usd)}</td>
              <td class="num ${used ? 'signal-text' : ''}">${used ? fmtUsd(f.estimated_cache_savings_usd) : '$0.00'}</td>
            </tr>
          `;
        }).join('') : stateTableRow(10, 'No matching feature branches recorded', 'Run Sync data or clear the search filter to view all tracked tasks.');
      }

      const clients = tr.by_client || [];
      document.getElementById('table-clients').innerHTML = clients.length ? clients.map(c => {
        const used = Number(c.plugin_calls || 0) > 0;
        return `
          <tr>
            <td class="primary-col">${c.client_source}</td>
            <td class="num">${fmtNum(c.conversation_count)}</td>
            <td class="num">${fmtNum(c.total_turns)}</td>
            <td class="num">${fmtNum(c.input_tokens)}</td>
            <td class="num">${fmtNum(c.cache_read_tokens)}</td>
            <td class="num">${fmtNum(c.output_tokens)}</td>
            <td class="num">${fmtNum(c.total_tokens)}</td>
            <td class="num">${fmtNum(c.plugin_calls)}</td>
            <td class="num">${fmtUsd(c.estimated_cost_usd)}</td>
            <td class="num ${used ? 'signal-text' : ''}">${used ? fmtUsd(c.estimated_cache_savings_usd) : '$0.00'}</td>
          </tr>
        `;
      }).join('') : stateTableRow(10, 'No client transcript metrics available', 'Start a session in Antigravity, Claude Code, or Codex CLI and click Sync data.');

      const rFilter = (document.getElementById('repo-search')?.value || '').toLowerCase();
      const repos = (tr.by_project_repo || []).filter(r =>
        !rFilter ||
        (r.repo_name || '').toLowerCase().includes(rFilter) ||
        (r.project_root || '').toLowerCase().includes(rFilter) ||
        (r.git_branch || '').toLowerCase().includes(rFilter)
      );
      document.getElementById('table-repos').innerHTML = repos.length ? repos.map(r => {
        const used = Number(r.plugin_calls || 0) > 0;
        return `
          <tr>
            <td class="primary-col">
              <div>${r.repo_name}</div>
              <div class="muted">${r.project_root}</div>
            </td>
            <td>${r.git_branch || 'default'}</td>
            <td class="num">${fmtNum(r.conversation_count)}</td>
            <td class="num">${fmtNum(r.total_turns)}</td>
            <td class="num">${fmtNum(r.total_tokens)}</td>
            <td>${pluginBadge(r.plugin_calls)}</td>
            <td class="num ${used ? 'signal-text' : ''}">${used ? fmtNum(r.plugin_tokens_saved) : '0'}</td>
            <td class="num">${fmtUsd(r.estimated_cost_usd)}</td>
            <td class="num ${used ? 'signal-text' : ''}">${used ? fmtUsd(r.estimated_cache_savings_usd) : '$0.00'}</td>
          </tr>
        `;
      }).join('') : stateTableRow(9, 'No matching repositories found', 'Clear the repository filter or index a workspace to populate repository costs.');

      const cFilter = (document.getElementById('conv-search')?.value || '').toLowerCase();
      const convs = (tr.by_conversation || []).filter(c =>
        !cFilter ||
        (c.title || '').toLowerCase().includes(cFilter) ||
        (c.feature_name || '').toLowerCase().includes(cFilter) ||
        (c.repo_name || '').toLowerCase().includes(cFilter) ||
        (c.conversation_id || '').toLowerCase().includes(cFilter)
      );
      document.getElementById('table-convs').innerHTML = convs.length ? convs.map(c => {
        const used = Number(c.plugin_calls || 0) > 0;
        return `
          <tr>
            <td>${c.client_source}</td>
            <td class="num">${c.conversation_id.slice(0, 8)}&hellip;</td>
            <td class="primary-col" title="${(c.title || '').replace(/"/g, '&quot;')}">
              <div>${c.feature_name || c.title}</div>
              <div class="muted">${c.title}</div>
            </td>
            <td>${c.repo_name}</td>
            <td class="num">${fmtNum(c.turn_count)}</td>
            <td class="num">${fmtNum(c.total_tokens)}</td>
            <td>${pluginBadge(c.plugin_calls)}</td>
            <td class="num ${used ? 'signal-text' : ''}">${used ? fmtNum(c.plugin_tokens_saved) : '0'}</td>
            <td class="num">${fmtUsd(c.estimated_cost_usd)}</td>
            <td class="num ${used ? 'signal-text' : ''}">${used ? fmtUsd(c.estimated_cache_savings_usd) : '$0.00'}</td>
          </tr>
        `;
      }).join('') : stateTableRow(10, 'No matching conversations recorded', 'Clear the conversation search field or sync local transcripts.');
    }

    const G3D_CATEGORIES = {
      model:  { token: '--color-accent', badge: 'Data model or table' },
      engine: { token: '--point-hi', badge: 'Engine or use case' },
      repo:   { token: '--point-mid', badge: 'Repository or cache' },
      api:    { token: '--point-lo', badge: 'API or ground-truth pin' },
      ui:     { token: '--point-mid', badge: 'UI or hook' }
    };

    const SQLITE_CORE_MODELS = {
      nodes: [
        { id: 'files', label: 'files (table)', category: 'model', tier: -1, size: 22, summary: 'Primary file and AST symbol index table storing SHA-256 signatures and extracted symbol line maps.', fields: ['PK (workspace_path, file_path)', 'rel_path : TEXT', 'content_hash : SHA-256', 'symbols_json : JSON [{name, kind, line}]', 'exports_json : JSON', 'tags_json : JSON'] },
        { id: 'relationships', label: 'relationships (table)', category: 'model', tier: -1, size: 19, summary: 'Directed implementation graph edges connecting source and target files.', fields: ['PK (workspace_path, source_file, target_file, relation_type)', 'FK source_file -> files.file_path', 'FK target_file -> files.file_path', 'relation_type : imports | calls | reads_data_from | writes_data_to'] },
        { id: 'ground_truth_overrides', label: 'ground_truth_overrides', category: 'api', tier: -1, size: 20, summary: 'Verified anti-hallucination rules and user corrections injected at SessionStart.', fields: ['PK (workspace_path, override_key)', 'hallucination_or_mistake : TEXT', 'verified_truth : TEXT', 'scope_files_json : JSON -> files', 'priority : critical | high | normal'] },
        { id: 'cached_queries', label: 'cached_queries (table)', category: 'repo', tier: -1, size: 18, summary: 'Reusable cache of expensive database queries, API responses, and generated datasets.', fields: ['PK (workspace_path, query_key)', 'category : queried_data | generated_data', 'result_summary : TEXT', 'data_json : JSON', 'related_files_json : JSON -> files'] },
        { id: 'conversation_usage', label: 'conversation_usage', category: 'model', tier: -1, size: 21, summary: 'Multi-LLM token analytics per conversation and related Git repository.', fields: ['PK conversation_id : TEXT', 'client_source : antigravity | claude-code | codex-cli', 'repo_name & git_branch : TEXT', 'input_tokens, cache_read_tokens, output_tokens, total_tokens : INT'] },
        { id: 'tool_activity', label: 'tool_activity (table)', category: 'repo', tier: 0, size: 15, summary: 'Audit log of PostToolUse file reads, edits, and tool calls.', fields: ['PK id : INTEGER', 'FK session_id -> conversation_usage', 'FK target_path -> files.file_path', 'tool_name : TEXT'] },
        { id: 'db_engine', label: 'server/db_engine.py', category: 'engine', tier: 0, size: 24, summary: 'Core SQLite Graph Engine, AST Static Indexer, Hallucination Verifier, and Transcript Scanner.', fields: ['auto_index_workspace()', 'verify_and_fix_hallucinations()', 'record_correction()', 'refresh_context()', 'get_token_usage_report()'] },
        { id: 'mcp_server', label: 'server/mcp_server.py', category: 'api', tier: 1, size: 18, summary: 'Stdio JSON-RPC 2.0 MCP Server exposing 12 tools to all LLM clients.', fields: ['cache_get_overview', 'cache_get_file_context', 'cache_record_correction', 'cache_verify_and_fix_hallucinations', 'cache_get_token_usage'] },
        { id: 'ui_server', label: 'scripts/ui_server.py', category: 'ui', tier: 1, size: 17, summary: 'Interactive Web UI Control Center and 3D Data Model Explorer.', fields: ['GET /api/state', 'POST /api/action', '3D Data Model Graph Canvas'] }
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

    let g3dNodes = [], g3dEdges = [], g3dSelected = null;
    let g3dFilter = 'all', g3dRotate = !REDUCED_MOTION, g3dLayers = false, g3dHoverPause = false;
    let g3dRotY = 0.45, g3dRotX = 0.26, g3dZoom = 1.0, g3dSweepPhase = 0.35;
    let g3dDrag = false, g3dMoved = false, g3dSX = 0, g3dSY = 0, g3dStarted = false;

    function classify3DCategory(relPath, summary) {
      const p = (relPath + ' ' + (summary || '')).toLowerCase();
      if (p.includes('model') || p.includes('schema') || p.includes('entity') || p.includes('types') || p.includes('db_engine')) return 'model';
      if (p.includes('repo') || p.includes('dao') || p.includes('store') || p.includes('query')) return 'repo';
      if (p.includes('controller') || p.includes('mcp_server') || p.includes('route') || p.includes('api')) return 'api';
      if (p.includes('page') || p.includes('component') || p.includes('slice') || p.includes('ui_') || p.includes('.tsx')) return 'ui';
      return 'engine';
    }

    function buildClusterSamples(size) {
      const count = Math.max(28, size * 2);
      const samples = [];
      for (let k = 0; k < count; k++) {
        const phi = Math.acos(1 - 2 * (k + 0.5) / count);
        const theta = Math.PI * (1 + Math.sqrt(5)) * k;
        const r = (size * 1.15) * (0.55 + 0.45 * ((k * 7) % 11) / 10);
        samples.push({
          ox: r * Math.sin(phi) * Math.cos(theta),
          oy: r * Math.cos(phi) * 0.72,
          oz: r * Math.sin(phi) * Math.sin(theta),
          elev: (Math.cos(phi) + 1) * 0.5
        });
      }
      return samples;
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
          y: (n.tier || 0) * 80 + ((i % 3) - 1) * 14,
          z: rad * Math.cos(phi),
          vx: 0, vy: 0, vz: 0, projX: 0, projY: 0, projScale: 1, depthZ: 0,
          samples: buildClusterSamples(n.size || 18)
        };
      });
      const map = Object.fromEntries(g3dNodes.map(n => [n.id, n]));
      g3dEdges = (graphData.edges || [])
        .filter(e => map[e.source] && map[e.target])
        .map(e => ({ ...e, sourceNode: map[e.source], targetNode: map[e.target] }));
      g3dSelected = g3dNodes[0] || null;
      render3DInspector();
    }

    function render3DInspector() {
      const box = document.getElementById('graph3d-inspector');
      if (!box || !g3dSelected) return;
      const meta = G3D_CATEGORIES[g3dSelected.category] || G3D_CATEGORIES.engine;
      const inc = g3dEdges.filter(e => e.targetNode.id === g3dSelected.id);
      const out = g3dEdges.filter(e => e.sourceNode.id === g3dSelected.id);
      const fieldsHtml = (g3dSelected.fields || []).map(f =>
        `<div class="code-chip" title="${f}">${f}</div>`
      ).join('');
      const relsHtml = [
        ...out.map(e => `<div class="muted"><span class="signal-text">${e.type}</span> to ${e.targetNode.label}</div>`),
        ...inc.map(e => `<div class="muted"><span class="signal-text">${e.type}</span> from ${e.sourceNode.label}</div>`)
      ].join('');
      box.innerHTML = `
        <div class="field-group">
          <div><span class="tag tag--live">${meta.badge}</span></div>
          <h3>${g3dSelected.fullPath || g3dSelected.label}</h3>
          <p class="muted">${g3dSelected.summary || ''}</p>
        </div>
        <div class="field-group">
          <h3>Columns and AST symbols (${(g3dSelected.fields || []).length})</h3>
          <div class="code-chip-row">${fieldsHtml}</div>
        </div>
        <div class="field-group">
          <h3>Connected 3D edges (${inc.length + out.length})</h3>
          <div class="record-list">${relsHtml || '<span class="muted">No direct edges on this node.</span>'}</div>
        </div>
      `;
    }

    function init3DCanvasEvents() {
      if (g3dStarted) return;
      const cvs = document.getElementById('graph3d-canvas');
      const stage = document.getElementById('graph3d-stage');
      if (!cvs) return;
      g3dStarted = true;
      const rotBtn = document.getElementById('btn-3d-rotate');
      if (rotBtn) {
        rotBtn.textContent = `3D orbit: ${g3dRotate ? 'on' : 'off'}`;
        rotBtn.classList.toggle('is-active', g3dRotate);
      }
      if (stage) {
        stage.addEventListener('pointerenter', () => { g3dHoverPause = true; });
        stage.addEventListener('pointerleave', () => { g3dHoverPause = false; });
        stage.addEventListener('focusin', () => { g3dHoverPause = true; });
        stage.addEventListener('focusout', () => { g3dHoverPause = false; });
      }
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
            if (Math.hypot(mx - n.projX, my - n.projY) <= Math.max(18, n.size * n.projScale * 1.25)) {
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
          const bgCol = readToken('--point-core');
          const inkCol = readToken('--color-ink');
          const ink2Col = readToken('--color-ink-2');
          const mutedCol = readToken('--color-muted');
          const ruleCol = readToken('--color-rule-2');
          const ptLo = readToken('--point-lo');
          const ptMid = readToken('--point-mid');
          const ptHi = readToken('--point-hi');
          const limeCol = readToken('--color-accent');
          const bodyFont = readToken('--font-body');

          ctx.save();
          ctx.scale(dpr, dpr);
          const w = rect.width, h = rect.height;
          ctx.fillStyle = bgCol;
          ctx.fillRect(0, 0, w, h);

          if (g3dRotate && !g3dDrag && !g3dHoverPause && !REDUCED_MOTION) {
            g3dRotY += 0.0022;
            g3dSweepPhase = (g3dSweepPhase + 0.0024) % 1;
          }
          const sweepX = (Math.sin(g3dSweepPhase * Math.PI * 2) * 0.5 + 0.5) * w;
          const vis = g3dNodes.filter(n => g3dFilter === 'all' || n.category === g3dFilter);
          const linkedIds = new Set();
          if (g3dSelected) {
            g3dEdges.forEach(e => {
              if (e.sourceNode.id === g3dSelected.id) linkedIds.add(e.targetNode.id);
              if (e.targetNode.id === g3dSelected.id) linkedIds.add(e.sourceNode.id);
            });
          }

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
            const s = (d - 115) * 0.012;
            a.vx += (dx / d) * s; a.vy += (dy / d) * s; a.vz += (dz / d) * s;
            b.vx -= (dx / d) * s; b.vy -= (dy / d) * s; b.vz -= (dz / d) * s;
          });

          const cosY = Math.cos(g3dRotY), sinY = Math.sin(g3dRotY);
          const cosX = Math.cos(g3dRotX), sinX = Math.sin(g3dRotX);
          const allPoints = [];

          vis.forEach(n => {
            n.vx -= n.x * 0.008; n.vz -= n.z * 0.008;
            n.vy += g3dLayers ? (((n.tier || 0) * 95) - n.y) * 0.06 : -n.y * 0.008;
            n.vx *= 0.82; n.vy *= 0.82; n.vz *= 0.82;
            n.x += n.vx; n.y += n.vy; n.z += n.vz;

            const x1 = n.x * cosY - n.z * sinY, z1 = n.z * cosY + n.x * sinY;
            const y2 = n.y * cosX - z1 * sinX, z2 = z1 * cosX + n.y * sinX;
            const sc = (430 * g3dZoom) / Math.max(80, 400 + z2);
            n.projX = w / 2 + x1 * sc; n.projY = h / 2 + y2 * sc; n.projScale = sc; n.depthZ = z2;

            const isFound = (g3dSelected && g3dSelected.id === n.id) || linkedIds.has(n.id);
            (n.samples || []).forEach(sp => {
              const sx = n.x + sp.ox, sy = n.y + sp.oy, sz = n.z + sp.oz;
              const rx1 = sx * cosY - sz * sinY, rz1 = sz * cosY + sx * sinY;
              const ry2 = sy * cosX - rz1 * sinX, rz2 = rz1 * cosX + sy * sinX;
              const psc = (430 * g3dZoom) / Math.max(80, 400 + rz2);
              const px = w / 2 + rx1 * psc, py = h / 2 + ry2 * psc;
              const swept = Math.abs(px - sweepX) < 28;
              allPoints.push({
                px, py, rz2, psc,
                col: isFound ? limeCol : (swept ? ptHi : (sp.elev > 0.66 ? ptHi : (sp.elev > 0.33 ? ptMid : ptLo))),
                rad: Math.max(1.1, (isFound ? 2.1 : 1.65) * psc)
              });
            });
          });

          allPoints.sort((a, b) => b.rz2 - a.rz2).forEach(pt => {
            ctx.fillStyle = pt.col;
            ctx.beginPath();
            ctx.arc(pt.px, pt.py, pt.rad, 0, Math.PI * 2);
            ctx.fill();
          });

          ctx.font = `400 12px ${bodyFont}`;
          [...vis].sort((a, b) => b.depthZ - a.depthZ).forEach(n => {
            const sel = g3dSelected && g3dSelected.id === n.id;
            const linked = linkedIds.has(n.id);
            ctx.fillStyle = sel ? limeCol : (linked ? inkCol : ink2Col);
            ctx.textAlign = 'center';
            ctx.fillText(n.label, n.projX, n.projY + Math.max(16, n.size * n.projScale) + 12);
          });

          // Vantage hairline leader callouts (at most two on screen)
          const calloutTargets = [];
          if (g3dSelected && vis.includes(g3dSelected)) calloutTargets.push(g3dSelected);
          const firstLinked = vis.find(n => linkedIds.has(n.id));
          if (firstLinked) calloutTargets.push(firstLinked);
          calloutTargets.slice(0, 2).forEach((cn, idx) => {
            const dir = idx === 0 ? 1 : -1;
            const lx = Math.max(56, Math.min(w - 140, cn.projX + dir * 42));
            const ly = Math.max(48, Math.min(h - 56, cn.projY - 26));
            ctx.fillStyle = limeCol;
            ctx.beginPath();
            ctx.arc(cn.projX, cn.projY, 3, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = ruleCol;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(cn.projX, cn.projY);
            ctx.lineTo(lx, ly);
            ctx.lineTo(lx + dir * 54, ly);
            ctx.stroke();
            ctx.fillStyle = inkCol;
            ctx.textAlign = dir > 0 ? 'left' : 'right';
            ctx.fillText(`${(cn.fields || []).length} symbols`, lx + dir * 4, ly - 5);
            ctx.fillStyle = mutedCol;
            ctx.fillText(cn.category, lx + dir * 4, ly + 13);
          });

          ctx.restore();
        }
        requestAnimationFrame(stepAndDraw);
      }
      requestAnimationFrame(stepAndDraw);
    }

    function set3DFilter(cat) {
      g3dFilter = cat;
      document.querySelectorAll('[data-filter]').forEach(btn => {
        const active = btn.getAttribute('data-filter') === cat;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
      });
    }
    function toggle3DRotate() {
      g3dRotate = !g3dRotate;
      const btn = document.getElementById('btn-3d-rotate');
      if (btn) {
        btn.textContent = `3D orbit: ${g3dRotate ? 'on' : 'off'}`;
        btn.classList.toggle('is-active', g3dRotate);
      }
    }
    function toggle3DLayers() {
      g3dLayers = !g3dLayers;
      const btn = document.getElementById('btn-3d-layers');
      if (btn) {
        btn.textContent = g3dLayers ? 'Layout: stratified tiers' : 'Layout: force sphere';
        btn.classList.toggle('is-active', g3dLayers);
      }
    }
    function zoom3D(f) { g3dZoom = Math.max(0.55, Math.min(2.2, g3dZoom * f)); }

    function initWorkspaces() {
      const sel = document.getElementById('ws-select');
      const keys = Object.keys(STATE.overviews || {});
      const opts = ['<option value="__sqlite_schema__">SQLite core data models (6 schema tables)</option>']
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
          ? '<span class="tag">Stale</span>'
          : '<span class="tag tag--live">Fresh</span>';
        const syms = (f.key_symbols || []).map(s => `<code class="code-chip">${s}</code>`).join(' ');
        return `
          <div class="record-row">
            <div class="record-head">
              <strong>${f.rel_path}</strong>
              ${badge}
            </div>
            <p class="muted">${f.summary}</p>
            ${syms ? `<div class="code-chip-row">${syms}</div>` : ''}
          </div>
        `;
      }).join('');
      document.getElementById('files-list').innerHTML = filesHtml || '<p class="empty-state">No tracked files loaded for this view. Select an indexed workspace above or click Rebuild index.</p>';

      const relsHtml = (ov.relationships || []).map(r => `
        <div class="record-row">
          <div><span class="signal-text">${r.source}</span> <span class="tag">${r.type}</span> to <strong>${r.target}</strong></div>
          ${r.description ? `<div class="muted">${r.description}</div>` : ''}
        </div>
      `).join('');
      document.getElementById('rels-list').innerHTML = relsHtml || '<p class="empty-state">No cross-file implementation edges recorded for this selection. Select an indexed workspace above to inspect AST relationships.</p>';
    }

    function renderOverridesAndQueries() {
      let allOverrides = [];
      let allQueries = [];
      Object.entries(STATE.overviews || {}).forEach(([ws, ov]) => {
        (ov.ground_truth_overrides || []).forEach(o => allOverrides.push({ ...o, ws }));
        (ov.cached_queries || []).forEach(q => allQueries.push({ ...q, ws }));
      });

      document.getElementById('overrides-list').innerHTML = allOverrides.map(o => `
        <div class="record-row">
          <div class="record-head">
            <span class="signal-text">[${(o.priority || 'high')}] ${o.override_key}</span>
            <span class="muted">${o.ws}</span>
          </div>
          <div>${o.verified_truth}</div>
          ${o.hallucination_or_mistake ? `<div class="muted">Prevents mistake: ${o.hallucination_or_mistake}</div>` : ''}
        </div>
      `).join('') || '<p class="empty-state">No ground-truth overrides pinned yet. Complete the form above to record a verified domain rule.</p>';

      document.getElementById('queries-list').innerHTML = allQueries.map(q => `
        <div class="record-row">
          <div class="record-head">
            <span class="signal-text">${q.query_key} (${q.category})</span>
            <span class="muted">${q.ws}</span>
          </div>
          ${q.query_text ? `<div class="muted">Query: ${q.query_text}</div>` : ''}
          <div>${q.result_summary}</div>
        </div>
      `).join('') || '<p class="empty-state">No cached queries stored yet. Expensive database queries and generated datasets saved via cache_store_query appear here.</p>';
    }

    async function apiAction(action) {
      const ws = document.getElementById('ws-select')?.value || 'global';
      const toast = document.getElementById('action-toast');
      toast.classList.remove('hidden');
      toast.textContent = `Running ${action} on ${ws}\u2026`;
      if (vscodeApi) {
        vscodeApi.postMessage({ type: 'apiAction', action, workspace_path: ws });
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/action`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CG-Token': window.__CG_CSRF_TOKEN__ || ''
          },
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
      const wsEl = document.getElementById('ov-ws');
      const keyEl = document.getElementById('ov-key');
      const truthEl = document.getElementById('ov-truth');
      const helpEl = document.getElementById('ov-cli-preview');
      const ws = wsEl.value || 'global';
      const key = keyEl.value.trim();
      const priority = document.getElementById('ov-priority').value;
      const mistake = document.getElementById('ov-mistake').value.trim();
      const truth = truthEl.value.trim();

      keyEl.toggleAttribute('aria-invalid', !key);
      truthEl.toggleAttribute('aria-invalid', !truth);
      if (!key || !truth) {
        helpEl.setAttribute('data-error', 'true');
        helpEl.textContent = 'Enter both an override slug and a verified ground-truth rule before saving.';
        (!key ? keyEl : truthEl).focus();
        return;
      }
      helpEl.removeAttribute('data-error');
      if (vscodeApi) {
        vscodeApi.postMessage({
          type: 'submitOverride',
          workspace_path: ws,
          override_key: key,
          hallucination_or_mistake: mistake,
          verified_truth: truth,
          priority
        });
        keyEl.value = '';
        document.getElementById('ov-mistake').value = '';
        truthEl.value = '';
        helpEl.textContent = `Pinned ground-truth override ${key}.`;
        return;
      }
      try {
        await fetch(`${API_BASE}/api/action`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CG-Token': window.__CG_CSRF_TOKEN__ || ''
          },
          body: JSON.stringify({
            action: 'correct',
            workspace_path: ws,
            override_key: key,
            hallucination_or_mistake: mistake,
            verified_truth: truth,
            priority
          })
        });
        keyEl.value = '';
        document.getElementById('ov-mistake').value = '';
        truthEl.value = '';
        helpEl.textContent = `Pinned ground-truth override ${key}.`;
        await reloadState();
      } catch (err) {
        helpEl.textContent =
          `Offline: run python3 ~/.gemini/config/plugins/context-graph/scripts/context_ctl.py correct -w "${ws}" -k "${key}" --mistake "${mistake}" --truth "${truth}" --priority ${priority}`;
      }
    }

    async function reloadState() {
      const badge = document.getElementById('mode-badge');
      const syncBtn = document.getElementById('btn-sync');
      if (syncBtn) syncBtn.setAttribute('aria-busy', 'true');
      if (!window.__INITIAL_CG_STATE__ && DATA_STATE !== 'full') {
        DATA_STATE = 'loading';
        renderKPIs();
        renderTokens();
      }
      if (vscodeApi) {
        vscodeApi.postMessage({ type: 'reloadState' });
        if (badge) {
          badge.textContent = 'VS Code extension connected';
          badge.removeAttribute('data-offline');
        }
        if (syncBtn) syncBtn.removeAttribute('aria-busy');
        renderKPIs();
        renderTokens();
        initWorkspaces();
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/state`);
        if (res.ok) {
          STATE = await res.json();
          DATA_STATE = 'full';
          if (badge) {
            badge.textContent = 'Live SQLite API connected';
            badge.removeAttribute('data-offline');
          }
        }
      } catch (err) {
        DATA_STATE = window.__INITIAL_CG_STATE__ ? 'full' : 'error';
        if (badge) {
          badge.textContent = window.__INITIAL_CG_STATE__ ? 'Embedded snapshot active' : 'Offline: run python3 scripts/ui_server.py';
          badge.setAttribute('data-offline', 'true');
        }
      }
      if (syncBtn) syncBtn.removeAttribute('aria-busy');
      renderKPIs();
      renderTokens();
      initWorkspaces();
    }

    (function restoreUrlState() {
      try {
        const params = new URLSearchParams(window.location.search);
        const t = params.get('tab');
        if (t && ['tokens', 'graph', 'overrides', 'queries'].includes(t)) {
          switchTab(t);
        }
      } catch (_) {}
    })();

    reloadState();
  </script>
</body>
</html>
"""


def build_html(workspace_filter: str = "", csrf_token: str = "") -> str:
    state_json = json.dumps(collect_full_state(workspace_filter)).replace("</", "<\\/")
    token_json = json.dumps(csrf_token)
    inject = (
        f"  <script>window.__INITIAL_CG_STATE__ = {state_json};"
        f" window.__CG_CSRF_TOKEN__ = {token_json};</script>\n  <script>\n    const vscodeApi"
    )
    return DASHBOARD_HTML_TEMPLATE.replace("  <script>\n    const vscodeApi", inject, 1)


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _allowed_origins(self) -> set:
        port = self.server.server_address[1]
        return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    def _is_origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return origin in self._allowed_origins()

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and origin in self._allowed_origins():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CG-Token")

    def do_OPTIONS(self) -> None:
        if not self._is_origin_allowed():
            self.send_response(403)
            self.end_headers()
            return
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
        if not self._is_origin_allowed():
            self._send_json({"error": "Forbidden origin"}, 403)
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/state":
            self._send_json(collect_full_state())
        else:
            html_bytes = build_html(csrf_token=SERVER_CSRF_TOKEN).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)

    def do_POST(self) -> None:
        if not self._is_origin_allowed():
            self._send_json({"error": "Forbidden origin"}, 403)
            return
        token = self.headers.get("X-CG-Token", "")
        if not token or not hmac.compare_digest(token, SERVER_CSRF_TOKEN):
            self._send_json({"error": "Invalid or missing CSRF token"}, 403)
            return
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
        "--dump-state",
        action="store_true",
        help="Print full JSON state to stdout and exit (used by VS Code extension).",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        default="",
        help="Optional workspace filter when exporting HTML or dumping state.",
    )
    args = parser.parse_args()

    if args.dump_state:
        print(json.dumps(collect_full_state(args.workspace)))
        return

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
