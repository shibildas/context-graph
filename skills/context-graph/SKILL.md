---
name: context-graph
description: >-
  Manage and query the Context Graph & Query Cache to index codebases with zero LLM tokens,
  map file and implementation relationships, persist queried/generated data, and visualize
  module architecture without re-reading unchanged files.
---

# Context Graph & Query Cache Skill

Use this skill when the user asks to index a codebase, inspect or visualize file/implementation relationships, store or retrieve queried/generated data, or audit stale vs. fresh files in the cache.

## Available MCP Tools (`context-graph-mcp`)

| Tool | Purpose |
| :--- | :--- |
| `cache_auto_index_workspace` | Statically scans the workspace (zero LLM tokens), extracting classes, functions, line numbers, exports, and `imports` relationships into SQLite (`~/.gemini/context-graph/cache.db`). |
| `cache_get_overview` | Returns workspace cache statistics, fresh vs. stale files, mapped relationships, and stored queries/datasets. |
| `cache_get_file_context` | Returns a single file's SHA-256 staleness status (`is_stale`), summary, symbol line numbers, incoming/outgoing relationships, and 2-hop neighbor summaries. |
| `cache_upsert_file` | Saves or updates an LLM-enriched summary, symbol map, and outgoing dependencies for a file, recording its current disk SHA-256 and `mtime`. |
| `cache_add_relationship` | Records semantic implementation relationships (`calls`, `implements`, `extends`, `reads_data_from`, `writes_data_to`, `tests`, `configures`). |
| `cache_store_query` | Saves queried data (DB results, API payloads, complex grep findings) or LLM-generated datasets/insights under a reusable `query_key`. |
| `cache_search` | Searches across all cached files, symbols, relationships, and stored queries. |

## Standard Workflows

### 1. Zero-Token Codebase Onboarding
1. Run `cache_auto_index_workspace(workspace_path="<workspace>")` to populate the initial file and import graph.
2. Run `cache_get_overview(workspace_path="<workspace>")` to inspect the discovered hub files (files with the most incoming/outgoing relationships).
3. Read only the core entrypoints or hub files if deeper semantic understanding is needed, and enrich them with `cache_upsert_file` and `cache_add_relationship`.

### 2. Storing & Reusing Queried or Generated Data
1. Before running a multi-step investigation or data generation task, call `cache_search(workspace_path="<workspace>", query="<topic>", category="queries")`.
2. After executing a query or generating structured data, persist it immediately:
   ```json
   {
     "workspace_path": "/path/to/workspace",
     "query_key": "billing-webhook-flow",
     "category": "architecture_note",
     "query_text": "How Stripe webhook events flow into subscription state updates",
     "result_summary": "POST /api/webhooks/stripe (webhook_handler.py:L24) verifies signature, dispatches to SubscriptionService.sync_status (billing.py:L88), and writes to subscriptions table.",
     "related_files": ["src/api/webhook_handler.py", "src/services/billing.py"],
     "tags": ["billing", "stripe", "webhook"]
   }
   ```

### 3. Visualizing the Architecture Graph
When the user asks to see how files and implementations relate:
1. Call `cache_get_overview(workspace_path="<workspace>", max_items=100)`.
2. Render a Mermaid `flowchart LR` diagram grouping files by directory/domain and labeling directed edges with their `relation_type`.
