---
name: context-graph
description: >-
  Manage and query the Context Graph & Query Cache to index codebases with zero LLM tokens,
  override or refresh stale context, fix and prevent hallucinations with ground-truth pins,
  map file relationships, persist queried/generated data, and view multi-LLM token usage.
---

# Context Graph, Query Cache & Anti-Hallucination Skill

Use this skill when the user asks to:
- **Override, refresh, or reset cached context** (`cache_refresh_context`, `cache_override_entry`)
- **Fix or prevent LLM hallucinations** by auditing symbols against disk AST (`cache_verify_and_fix_hallucinations`) or pinning a verified correction (`cache_record_correction`)
- View **LLM token usage** per conversation, per LLM client, or aggregated by project / Git repository (`cache_get_token_usage`)
- Index a codebase or visualize file/implementation relationships (`cache_auto_index_workspace`, `cache_get_overview`)
- Store or retrieve queried/generated data (`cache_store_query`, `cache_search`)

## Available MCP Tools (`context-graph-mcp`)

| Tool | Purpose |
| :--- | :--- |
| `cache_record_correction` | Pins a verified user correction / ground-truth rule (`override_key`, `hallucination_or_mistake`, `verified_truth`, `scope_files`) and flags affected files for refresh so the LLM never repeats a hallucination. |
| `cache_verify_and_fix_hallucinations` | Audits cached symbols, files, and relationships against actual disk AST/files. Automatically removes ghost files, deletes broken edges, and repairs phantom/drifted symbol names. |
| `cache_refresh_context` | Refreshes or resets context with modes: `'stale_only'`, `'force_all'`, `'file'`, `'purge_queries'`, or `'hard_reset'`. |
| `cache_override_entry` | Directly overrides or deletes a specific cached `'file'`, `'query'`, `'relationship'`, or `'override'` entry. |
| `cache_get_token_usage` | Returns LLM token usage (`input_tokens`, `cache_read_tokens`, `output_tokens`, `total_tokens`, `cache_hit_rate_pct`) per conversation, per LLM client, and grouped by project / Git repository. |
| `cache_auto_index_workspace` | Statically scans the workspace (zero LLM tokens), extracting classes, functions, line numbers, exports, and `imports` relationships into SQLite (`~/.gemini/context-graph/cache.db`). |
| `cache_get_overview` | Returns workspace cache statistics, active ground-truth overrides, Git repo metadata, fresh vs. stale files, relationships, and stored queries. |
| `cache_get_file_context` | Returns a file's ground-truth overrides, SHA-256 staleness status (`is_stale`), summary, symbol line numbers, and 1- or 2-hop relationships. |
| `cache_upsert_file` | Saves or updates an LLM-enriched summary, symbol map, and outgoing dependencies for a file. |
| `cache_add_relationship` | Records semantic implementation relationships (`calls`, `implements`, `extends`, `reads_data_from`, `writes_data_to`, `tests`, `configures`). |
| `cache_store_query` | Saves queried data or LLM-generated datasets/insights under a reusable `query_key`. |
| `cache_search` | Searches across all ground-truth overrides, cached files, symbols, relationships, and stored queries. |

## Standard Workflows

### 1. Fixing a Hallucination or Recording a Ground-Truth Override
1. Call `cache_record_correction` with:
   - `workspace_path`: Active workspace path
   - `override_key`: Short descriptive slug (e.g., `"api-timeout-config"`)
   - `hallucination_or_mistake`: What was wrongly assumed or hallucinated
   - `verified_truth`: The exact verified behavior or rule
   - `scope_files`: List of affected files
2. Run `cache_verify_and_fix_hallucinations(workspace_path="<workspace>", auto_fix=True)` to purge any phantom symbols, deleted files, or broken edges from the SQLite graph.

### 2. Refreshing or Resetting Context
- **Refresh only modified files**: `cache_refresh_context(workspace_path="<workspace>", mode="stale_only")`
- **Force rebuild all files & edges from disk**: `cache_refresh_context(workspace_path="<workspace>", mode="force_all")`
- **Refresh a single file**: `cache_refresh_context(workspace_path="<workspace>", mode="file", target="src/app.py")`
- **Hard reset workspace cache** (keeps ground-truth overrides & token history): `cache_refresh_context(workspace_path="<workspace>", mode="hard_reset")`
