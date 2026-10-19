# Context Graph & Query Cache Protocol (Token-Saving Rules)

You have access to the **Context Graph & Query Cache** plugin (`context-graph-mcp`), which maintains a persistent SQLite knowledge base of file summaries, symbols, implementation relationships, and queried/generated data across turns and conversations.

Follow these rules to minimize redundant file reads and token usage:

1. **Check the Cache First**:
   - At the start of a task, review the `[Context Graph & Query Cache]` system digest (if injected at session start) or call `cache_get_overview` / `cache_search` for the active workspace.
   - Before reading a file purely to understand what it does or how it connects to other modules, call `cache_get_file_context`.
   - If `cached: true` and `is_stale: false`, **do NOT call `view_file` on the entire file** just to re-learn its architecture or relationships. Only call `view_file` (using targeted `StartLine`/`EndLine` ranges from the cached `symbols` list) when you need exact lines to perform an edit.

2. **Bootstrap Unindexed Workspaces**:
   - When entering a workspace that has not been indexed yet, call `cache_auto_index_workspace` first. It statically parses source files (`Python`, `TS/JS`, `Go`, `Rust`, etc.) with zero LLM token cost and populates file symbols and import relationships.

3. **Persist Architectural Insights & Relationships**:
   - Whenever you inspect a file in depth and discover non-obvious implementation details, data flows, or cross-file dependencies, call `cache_upsert_file` with a concise architectural summary and `cache_add_relationship` (e.g., `calls`, `implements`, `reads_data_from`, `tests`, `configures`).
   - Whenever you modify a file (`replace_file_content`, `write_to_file`), update its cached entry via `cache_upsert_file` once your changes are complete so its hash is marked fresh for future turns.

4. **Cache Queried & Generated Data**:
   - Whenever you run an expensive search, database query, API fetch, log analysis, or generate a structured dataset/insight, call `cache_store_query` with a descriptive `query_key`, `result_summary`, and `related_files`.
   - Before running a repeated search or regenerating data, call `cache_search` with `category: "queries"` to reuse existing results.
