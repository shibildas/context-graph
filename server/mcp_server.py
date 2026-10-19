#!/usr/bin/env python3
"""
MCP Server (Stdio JSON-RPC 2.0) for the Antigravity context-graph plugin.
Exposes tools to query and persist file summaries, code implementation relationships,
queried/generated LLM data, and token usage per conversation and Git repository.
"""

import json
import os
import sys
import traceback
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_engine


TOOLS = [
    {
        "name": "cache_get_overview",
        "description": (
            "Retrieve a token-efficient overview of the workspace's cached files, "
            "staleness status (fresh vs modified on disk), module/implementation relationships, "
            "and stored query/generated data. Call this FIRST before exploring a codebase."
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
            "Returns its cached implementation summary, symbols (functions/classes with line numbers), "
            "incoming/outgoing file relationships, and related cached queries. "
            "If is_stale is false, you do NOT need to spend tokens calling view_file to understand it."
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
            "Search across all cached file summaries, symbols, code relationships, and stored query/generated data."
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
                    "description": "Filter by category: 'all' (default), 'files', 'relationships', 'queries'.",
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
        "name": "cache_get_token_usage",
        "description": (
            "View LLM token usage (input_tokens, cache_read_tokens, output_tokens, total_tokens, and cache hit rate %) "
            "broken down per conversation and aggregated by project / related Git repository (repo name, remote URL, branch)."
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
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of conversations to return (default: 50).",
                },
            },
        },
    },
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "cache_get_overview":
        return db_engine.get_overview(
            workspace_path=args.get("workspace_path", "global"),
            max_items=int(args.get("max_items", 50)),
        )
    elif name == "cache_get_file_context":
        return db_engine.get_file_context(
            workspace_path=args.get("workspace_path", "global"),
            file_path=args["file_path"],
            depth=int(args.get("depth", 1)),
        )
    elif name == "cache_upsert_file":
        return db_engine.upsert_file(
            workspace_path=args.get("workspace_path", "global"),
            file_path=args["file_path"],
            summary=args.get("summary", ""),
            symbols=args.get("symbols"),
            exports=args.get("exports"),
            tags=args.get("tags"),
            dependencies=args.get("dependencies"),
        )
    elif name == "cache_add_relationship":
        return db_engine.add_relationship(
            workspace_path=args.get("workspace_path", "global"),
            source_file=args["source_file"],
            target_file=args["target_file"],
            relation_type=args["relation_type"],
            description=args.get("description", ""),
        )
    elif name == "cache_store_query":
        return db_engine.store_query(
            workspace_path=args.get("workspace_path", "global"),
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
            workspace_path=args.get("workspace_path", "global"),
            query=args["query"],
            category=args.get("category", "all"),
        )
    elif name == "cache_auto_index_workspace":
        return db_engine.auto_index_workspace(
            workspace_path=args.get("workspace_path", "global"),
            max_files=int(args.get("max_files", 200)),
            force=bool(args.get("force", False)),
        )
    elif name == "cache_get_token_usage":
        return db_engine.get_token_usage_report(
            workspace_path=args.get("workspace_path"),
            conversation_id=args.get("conversation_id"),
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
                                "version": "1.1.0",
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
