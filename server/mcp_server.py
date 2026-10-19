#!/usr/bin/env python3
"""
MCP Server (Stdio JSON-RPC 2.0) for the Universal Context Graph & Query Cache plugin.
Compatible with Google Antigravity, Claude Code, Claude Desktop, Cursor, Windsurf,
Cline, Roo Code, OpenAI Codex CLI, and Gemini CLI.
"""

import json
import os
import sys
import traceback
from typing import Any, Dict

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

from server import db_engine


TOOLS = [
    {
        "name": "cache_get_overview",
        "description": (
            "Retrieve a token-efficient overview of the workspace's cached files, "
            "verified ground-truth overrides (anti-hallucination pins), staleness status, "
            "module/implementation relationships, and stored query/generated data. Call this FIRST."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "max_items": {
                    "type": "integer",
                    "description": "Maximum number of entries to return per category (default: 50).",
                },
            },
            "required": ["workspace_path"],
        },
    },
    {
        "name": "cache_get_file_context",
        "description": (
            "Check if a file is already in the context graph and whether it is fresh (unchanged on disk). "
            "Returns any ground-truth anti-hallucination overrides, cached implementation summary, symbols, "
            "incoming/outgoing file relationships, and related cached queries."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative path to the file.",
                },
                "depth": {
                    "type": "integer",
                    "description": "Relationship traversal depth (1 = direct edges, 2 = include neighbor summaries).",
                },
            },
            "required": ["workspace_path", "file_path"],
        },
    },
    {
        "name": "cache_upsert_file",
        "description": (
            "Store or update a file's architectural summary, key symbols, exported APIs, and outgoing "
            "relationships in the persistent knowledge graph. Automatically records the file's SHA-256 "
            "and mtime so future turns know whether the file is still fresh."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Absolute or workspace-relative path to the file.",
                },
                "summary": {
                    "type": "string",
                    "description": "Concise architectural and implementation summary of the file.",
                },
                "symbols": {
                    "type": "array",
                    "description": "List of key symbols (e.g., [{'name': 'MyClass', 'kind': 'class', 'line': 10}]).",
                    "items": {"type": "object"},
                },
                "exports": {
                    "type": "array",
                    "description": "List of exported symbol names or endpoints.",
                    "items": {"type": "string"},
                },
                "tags": {
                    "type": "array",
                    "description": "Optional domain tags (e.g., ['auth', 'db', 'api']).",
                    "items": {"type": "string"},
                },
                "dependencies": {
                    "type": "array",
                    "description": "Optional list of outgoing file relationships: [{'target_file': '...', 'relation_type': 'imports|calls|implements|tests', 'description': '...'}].",
                    "items": {"type": "object"},
                },
            },
            "required": ["workspace_path", "file_path", "summary"],
        },
    },
    {
        "name": "cache_add_relationship",
        "description": (
            "Record a directed implementation or data relationship between two files "
            "(e.g., 'imports', 'calls', 'implements', 'reads_data_from', 'writes_data_to', 'tests', 'configures')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "source_file": {
                    "type": "string",
                    "description": "Source file path.",
                },
                "target_file": {
                    "type": "string",
                    "description": "Target file path.",
                },
                "relation_type": {
                    "type": "string",
                    "description": "Type of relationship (imports, calls, implements, extends, reads_data_from, tests, configures).",
                },
                "description": {
                    "type": "string",
                    "description": "Explanation of how source_file uses or relates to target_file.",
                },
            },
            "required": ["workspace_path", "source_file", "target_file", "relation_type"],
        },
    },
    {
        "name": "cache_store_query",
        "description": (
            "Persist queried data, search results, database/API responses, or LLM-generated analysis/datasets "
            "so future turns and conversations can retrieve the result immediately without re-running queries or burning tokens."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "query_key": {
                    "type": "string",
                    "description": "Unique slug identifier (e.g., 'auth-token-flow', 'db-user-schema', 'api-routes-list').",
                },
                "category": {
                    "type": "string",
                    "description": "One of: 'queried_data', 'generated_data', 'architecture_note', 'bug_investigation'.",
                },
                "query_text": {
                    "type": "string",
                    "description": "The original query, command, or prompt that produced this data.",
                },
                "result_summary": {
                    "type": "string",
                    "description": "Detailed, self-contained summary of the findings or generated data.",
                },
                "data": {
                    "type": "object",
                    "description": "Optional structured JSON object holding the queried or generated dataset.",
                },
                "artifact_path": {
                    "type": "string",
                    "description": "Optional file path if full raw output was saved to a file.",
                },
                "related_files": {
                    "type": "array",
                    "description": "List of file paths associated with this query/data.",
                    "items": {"type": "string"},
                },
                "tags": {
                    "type": "array",
                    "description": "Tags for fast lookup.",
                    "items": {"type": "string"},
                },
            },
            "required": ["workspace_path", "query_key", "result_summary"],
        },
    },
    {
        "name": "cache_search",
        "description": (
            "Search across all ground-truth overrides, cached file summaries, symbols, code relationships, and stored query/generated data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "query": {
                    "type": "string",
                    "description": "Keyword, symbol name, file name, or topic to search for.",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category: 'all' (default), 'overrides', 'files', 'relationships', 'queries'.",
                },
            },
            "required": ["workspace_path", "query"],
        },
    },
    {
        "name": "cache_auto_index_workspace",
        "description": (
            "Zero-token static indexer: scans the workspace directory, extracts classes/functions/line-numbers "
            "and import relationships across Python, TypeScript, JavaScript, Go, Rust, etc., and populates the SQLite context graph."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "max_files": {
                    "type": "integer",
                    "description": "Maximum number of source files to index (default: 200).",
                },
                "force": {
                    "type": "boolean",
                    "description": "If true, re-indexes files even if their SHA-256/mtime is unchanged.",
                },
            },
            "required": ["workspace_path"],
        },
    },
    {
        "name": "cache_record_correction",
        "description": (
            "Fix an LLM hallucination or record a verified user correction as a high-priority ground-truth override pin. "
            "Automatically injected at the top of future sessions and file context lookups so the LLM never repeats the mistake."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory (or 'global').",
                },
                "override_key": {
                    "type": "string",
                    "description": "Unique slug identifier for this correction (e.g., 'api-timeout-ms', 'strict-null-checks').",
                },
                "hallucination_or_mistake": {
                    "type": "string",
                    "description": "Description of the false assumption or hallucination that occurred.",
                },
                "verified_truth": {
                    "type": "string",
                    "description": "The authoritative ground truth that MUST be followed instead.",
                },
                "scope_files": {
                    "type": "array",
                    "description": "Optional list of files where this ground-truth rule applies.",
                    "items": {"type": "string"},
                },
                "priority": {
                    "type": "string",
                    "description": "Priority level: 'critical', 'high' (default), or 'normal'.",
                },
            },
            "required": ["workspace_path", "override_key", "verified_truth"],
        },
    },
    {
        "name": "cache_verify_and_fix_hallucinations",
        "description": (
            "Audit the cached context graph against actual disk files to detect and automatically fix hallucinations: "
            "purges deleted ghost files, removes broken relationships, and re-syncs drifted/phantom AST symbol names and line numbers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional specific file path to audit (audits entire workspace if omitted).",
                },
                "auto_fix": {
                    "type": "boolean",
                    "description": "If true (default), automatically repairs drifted symbols and deletes ghost files/edges.",
                },
            },
            "required": ["workspace_path"],
        },
    },
    {
        "name": "cache_refresh_context",
        "description": (
            "Refresh or reset cached context for a workspace or file. "
            "Modes: 'stale_only' (default), 'force_all' (rebuild all files/edges), 'file' (refresh single target file), "
            "'purge_queries' (clear cached query results), 'hard_reset' (wipe files/edges/queries while keeping ground-truth overrides)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "mode": {
                    "type": "string",
                    "description": "One of: 'stale_only', 'force_all', 'file', 'purge_queries', 'hard_reset'.",
                },
                "target": {
                    "type": "string",
                    "description": "Optional file path (when mode='file') or query_key/tag (when mode='purge_queries').",
                },
            },
            "required": ["workspace_path"],
        },
    },
    {
        "name": "cache_override_entry",
        "description": (
            "Directly override or delete any specific cached entry (file summary, query, relationship, or ground-truth override)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Absolute path to the workspace root directory.",
                },
                "target_type": {
                    "type": "string",
                    "description": "One of: 'file', 'query', 'relationship', 'override'.",
                },
                "target_key": {
                    "type": "string",
                    "description": "File path (for 'file'/'relationship'), query_key (for 'query'), or override_key (for 'override').",
                },
                "new_value": {
                    "type": "string",
                    "description": "New summary or ground-truth text (when delete=false).",
                },
                "delete": {
                    "type": "boolean",
                    "description": "If true, deletes the entry from the cache.",
                },
                "target_file_secondary": {
                    "type": "string",
                    "description": "Optional target file path when overriding/deleting a specific 'relationship'.",
                },
            },
            "required": ["workspace_path", "target_type", "target_key"],
        },
    },
    {
        "name": "cache_get_token_usage",
        "description": (
            "View LLM token usage (input_tokens, cache_read_tokens, output_tokens, total_tokens, and cache hit rate %) "
            "broken down per conversation, per LLM client (antigravity, claude-code, codex-cli), and aggregated by project / Git repository."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Optional workspace or Git repository path to filter by. Omit or pass 'all' to view all projects/repos.",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "Optional specific conversation ID to inspect.",
                },
                "client_source": {
                    "type": "string",
                    "description": "Optional LLM client filter: 'antigravity', 'claude-code', 'codex-cli', or 'all'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of conversations to return (default: 50).",
                },
            },
        },
    },
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    ws = args.get("workspace_path") or args.get("workspace") or "global"
    if name == "cache_get_overview":
        return db_engine.get_overview(
            workspace_path=ws,
            max_items=int(args.get("max_items", 50)),
        )
    elif name == "cache_get_file_context":
        return db_engine.get_file_context(
            workspace_path=ws,
            file_path=args["file_path"],
            depth=int(args.get("depth", 1)),
        )
    elif name == "cache_upsert_file":
        return db_engine.upsert_file(
            workspace_path=ws,
            file_path=args["file_path"],
            summary=args.get("summary", ""),
            symbols=args.get("symbols"),
            exports=args.get("exports"),
            tags=args.get("tags"),
            dependencies=args.get("dependencies"),
        )
    elif name == "cache_add_relationship":
        return db_engine.add_relationship(
            workspace_path=ws,
            source_file=args["source_file"],
            target_file=args["target_file"],
            relation_type=args["relation_type"],
            description=args.get("description", ""),
        )
    elif name == "cache_store_query":
        return db_engine.store_query(
            workspace_path=ws,
            query_key=args["query_key"],
            result_summary=args["result_summary"],
            query_text=args.get("query_text", ""),
            category=args.get("category", "queried_data"),
            data=args.get("data"),
            artifact_path=args.get("artifact_path", ""),
            related_files=args.get("related_files"),
            tags=args.get("tags"),
        )
    elif name == "cache_search":
        return db_engine.search_cache(
            workspace_path=ws,
            query=args["query"],
            category=args.get("category", "all"),
        )
    elif name == "cache_auto_index_workspace":
        return db_engine.auto_index_workspace(
            workspace_path=ws,
            max_files=int(args.get("max_files", 200)),
            force=bool(args.get("force", False)),
        )
    elif name == "cache_record_correction":
        return db_engine.record_correction(
            workspace_path=ws,
            override_key=args["override_key"],
            verified_truth=args["verified_truth"],
            hallucination_or_mistake=args.get("hallucination_or_mistake", ""),
            scope_files=args.get("scope_files"),
            priority=args.get("priority", "high"),
        )
    elif name == "cache_verify_and_fix_hallucinations":
        return db_engine.verify_and_fix_hallucinations(
            workspace_path=ws,
            file_path=args.get("file_path"),
            auto_fix=bool(args.get("auto_fix", True)),
        )
    elif name == "cache_refresh_context":
        return db_engine.refresh_context(
            workspace_path=ws,
            mode=args.get("mode", "stale_only"),
            target=args.get("target"),
        )
    elif name == "cache_override_entry":
        return db_engine.override_or_delete_entry(
            workspace_path=ws,
            target_type=args["target_type"],
            target_key=args["target_key"],
            new_value=args.get("new_value", ""),
            delete=bool(args.get("delete", False)),
            target_file_secondary=args.get("target_file_secondary", ""),
        )
    elif name == "cache_get_token_usage":
        return db_engine.get_token_usage_report(
            workspace_path=args.get("workspace_path") or args.get("workspace"),
            conversation_id=args.get("conversation_id"),
            client_source=args.get("client_source"),
            limit=int(args.get("limit", 50)),
        )
    else:
        raise ValueError(f"Unknown tool: {name}")


def send_response(msg: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params") or {}

        if req_id is None:
            continue

        try:
            if method == "initialize":
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": params.get(
                                "protocolVersion", "2024-11-05"
                            ),
                            "capabilities": {"tools": {}},
                            "serverInfo": {
                                "name": "context-graph-mcp",
                                "version": "1.3.0",
                            },
                        },
                    }
                )
            elif method == "ping":
                send_response({"jsonrpc": "2.0", "id": req_id, "result": {}})
            elif method == "tools/list":
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"tools": TOOLS},
                    }
                )
            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments") or {}
                output = handle_tool_call(tool_name, tool_args)
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(output, indent=2),
                                }
                            ],
                            "isError": False,
                        },
                    }
                )
            else:
                send_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}",
                        },
                    }
                )
        except Exception as exc:
            send_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "status": "error",
                                        "error": str(exc),
                                        "traceback": traceback.format_exc(),
                                    },
                                    indent=2,
                                ),
                            }
                        ],
                        "isError": True,
                    },
                }
            )


if __name__ == "__main__":
    main()
