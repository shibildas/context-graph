# Context Graph, Query Cache & Anti-Hallucination Protocol

You have access to the **Context Graph & Query Cache** plugin (`context-graph-mcp`), which maintains a persistent SQLite knowledge base of file summaries, symbols, implementation relationships, queried/generated data, and **verified ground-truth overrides** across turns and conversations.

Follow these rules to minimize redundant file reads, save tokens, and prevent hallucinations:

1. **Obey Verified Ground-Truth Overrides First**:
   - Always check `ground_truth_overrides` in the `[Context Graph & Query Cache]` session digest, `cache_get_overview`, or `cache_get_file_context`.
   - Ground-truth overrides represent explicit user corrections and verified facts. They **strictly override** any prior model assumptions or older cached summaries.

2. **Check the Cache Before Reading Files**:
   - Before reading a file purely to understand what it does or how it connects to other modules, call `cache_get_file_context`.
   - If `cached: true` and `is_stale: false`, **do NOT read the entire file** just to re-learn its architecture or relationships. Only read targeted line ranges (using the cached `symbols` list) when you need exact lines to perform an edit.

3. **Fix Hallucinations & Record User Corrections Immediately**:
   - Whenever the user corrects a false assumption, points out a hallucination, or clarifies a non-obvious domain rule, immediately call `cache_record_correction` with `override_key`, `hallucination_or_mistake`, `verified_truth`, and `scope_files` so the mistake is never repeated in future turns or sessions.
   - If you suspect cached symbols, line numbers, or relationships have drifted from disk, call `cache_verify_and_fix_hallucinations` or `cache_refresh_context`.

4. **Persist Architectural Insights, Relationships & Queried Data**:
   - When entering an unindexed workspace, call `cache_auto_index_workspace` first (zero LLM token cost).
   - Whenever you inspect a file in depth or modify a file, update its cached entry via `cache_upsert_file` and `cache_add_relationship`.
   - Whenever you run an expensive search, database query, API fetch, or generate a structured dataset, call `cache_store_query` so future turns can reuse it via `cache_search`.
