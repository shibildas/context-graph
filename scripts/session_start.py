#!/usr/bin/env python3
"""
Universal SessionStart Hook for the context-graph plugin.
Compatible with:
  - Google Antigravity (`workspacePaths` -> `injectSteps.systemMessage`)
  - Claude Code / Gemini CLI (`cwd` / `hook_event_name` -> `hookSpecificOutput.additionalContext`)
"""

import json
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "server"))

import db_engine


def build_digest(workspace_path: str) -> str:
    overview = db_engine.get_overview(workspace_path, max_items=35)
    stats = overview["stats"]

    if (
        stats["total_cached_files"] == 0
        and workspace_path != "global"
        and os.path.isdir(workspace_path)
    ):
        db_engine.auto_index_workspace(workspace_path, max_files=60, force=False)
        overview = db_engine.get_overview(workspace_path, max_items=35)
        stats = overview["stats"]

    if (
        stats["total_cached_files"] == 0
        and stats["total_relationships"] == 0
        and stats["total_cached_queries"] == 0
    ):
        return ""

    lines = [
        f"## [Context Graph & Query Cache] Active Workspace Memory (`{workspace_path}`)",
        (
            f"**Stats**: {stats['fresh_files']} fresh files, {stats['stale_files']} stale files, "
            f"{stats['total_relationships']} mapped relationships, {stats['total_cached_queries']} cached queries/datasets."
        ),
        "> **Token-Saving Directive**: Files marked `[FRESH]` have NOT changed on disk since they were analyzed. Rely on the summaries, symbols, and relationships below (or call `cache_get_file_context` / `cache_search`) instead of re-reading full files.",
        "",
    ]

    if overview["cached_queries"]:
        lines.append("### Cached Queries & Generated Data")
        for q in overview["cached_queries"][:15]:
            lines.append(
                f"- **`{q['query_key']}`** ({q['category']}): {q['result_summary']}"
            )
        lines.append("")

    if overview["relationships"]:
        lines.append("### Key File & Implementation Relationships")
        for r in overview["relationships"][:25]:
            desc = f" — {r['description']}" if r.get("description") else ""
            lines.append(f"- `{r['source']}` **[{r['type']}]** -> `{r['target']}`{desc}")
        lines.append("")

    if overview["files"]:
        lines.append("### Tracked Files Summary")
        for f in overview["files"][:25]:
            badge = "STALE" if f["is_stale"] else "FRESH"
            syms = (
                f" | Symbols: `{', '.join(f['key_symbols'])}`"
                if f.get("key_symbols")
                else ""
            )
            lines.append(f"- `[{badge}]` `{f['rel_path']}`: {f['summary']}{syms}")

    return "\n".join(lines)


def main() -> None:
    try:
        raw = sys.stdin.read().strip()
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    # Detect workspace across Antigravity (`workspacePaths`) and Claude Code / Gemini CLI (`cwd`)
    workspace_paths = payload.get("workspacePaths") or []
    workspace = (
        workspace_paths[0]
        if workspace_paths
        else (payload.get("cwd") or "global")
    )

    is_claude_or_gemini_cli = (
        "hook_event_name" in payload or ("cwd" in payload and "workspacePaths" not in payload)
    )

    try:
        digest = build_digest(workspace)
        if not digest:
            out = {}
        elif is_claude_or_gemini_cli:
            out = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": digest,
                }
            }
        else:
            out = {
                "injectSteps": [
                    {
                        "systemMessage": {
                            "systemMessage": digest,
                        }
                    }
                ]
            }
    except Exception:
        out = {}

    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
