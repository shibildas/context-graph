---
name: context-graph
description: >-
  Manage and query the Context Graph & Query Cache to index codebases with zero LLM tokens,
  map file and implementation relationships, persist queried/generated data, and view token
  usage per conversation and related Git repository.
---

# Context Graph & Query Cache Skill

Use this skill when the user asks to:
- View **LLM token usage** per conversation or aggregated by project / related Git repository
- Index a codebase into the persistent context graph
- Inspect or visualize file/implementation relationships
- Store or retrieve queried/generated data
- Audit stale vs. fresh files in the cache

## Available MCP Tools (`context-graph-mcp`)

| Tool | Purpose |
| :--- | :--- |
| `cache_get_token_usage` | Returns LLM token usage (`input_tokens`, `cache_read_tokens`, `output_tokens`, `total_tokens`, and `cache_hit_rate_pct`) per conversation and grouped by project / Git repository (`repo_name`, `git_remote`, `git_branch`). |
| `cache_auto_index_workspace` | Statically scans the workspace (zero LLM tokens), extracting classes, functions, line numbers, exports, and `imports` relationships into SQLite (`~/.gemini/context-graph/cache.db`). |
| `cache_get_overview` | Returns workspace cache statistics, Git repository metadata, fresh vs. stale files, mapped relationships, and stored queries/datasets. |
| `cache_get_file_context` | Returns a single file's SHA-256 staleness status (`is_stale`), summary, symbol line numbers, incoming/outgoing relationships, and 2-hop neighbor summaries. |
| `cache_upsert_file` | Saves or updates an LLM-enriched summary, symbol map, and outgoing dependencies for a file, recording its current disk SHA-256 and `mtime`. |
| `cache_add_relationship` | Records semantic implementation relationships (`calls`, `implements`, `extends`, `reads_data_from`, `writes_data_to`, `tests`, `configures`). |
| `cache_store_query` | Saves queried data (DB results, API payloads, complex grep findings) or LLM-generated datasets/insights under a reusable `query_key`. |
| `cache_search` | Searches across all cached files, symbols, relationships, and stored queries. |

## Standard Workflows

### 1. Viewing Token Usage per Conversation & Project/Git Repo
1. Call `cache_get_token_usage()` (or pass `workspace_path` to filter to a specific project/repo), or run:
   ```bash
   python3 ~/.gemini/config/plugins/context-graph/scripts/token_report.py
   ```
2. Present two Markdown tables to the user:
   - **By Project / Related Git Repository**: Repo name, root path, branch, remote URL, conversation count, input tokens, cache read tokens, output tokens, total tokens, and cache hit rate %.
   - **By Conversation**: Conversation link (`[<short-id>](conversation://<conversation_id>)`), prompt title, related repo, turn count, token breakdown, and cache efficiency %.

### 2. Zero-Token Codebase Onboarding
1. Run `cache_auto_index_workspace(workspace_path="<workspace>")` to populate the initial file and import graph.
2. Run `cache_get_overview(workspace_path="<workspace>")` to inspect the discovered hub files.
3. Read only core entrypoints or hub files if deeper semantic understanding is needed, and enrich them with `cache_upsert_file` and `cache_add_relationship`.

### 3. Storing & Reusing Queried or Generated Data
1. Before running a multi-step investigation or data generation task, call `cache_search(workspace_path="<workspace>", query="<topic>", category="queries")`.
2. After executing a query or generating structured data, persist it immediately via `cache_store_query`.
