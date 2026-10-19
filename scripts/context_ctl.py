#!/usr/bin/env python3
"""
CLI Control Utility for Context Graph Override, Refresh & Anti-Hallucination management.

Examples:
  # 1. Audit & auto-fix hallucinated symbols, ghost files, and broken relationships:
  python3 scripts/context_ctl.py verify --workspace /path/to/repo

  # 2. Refresh context (stale_only, force_all, file, purge_queries, hard_reset):
  python3 scripts/context_ctl.py refresh --workspace /path/to/repo --mode force_all

  # 3. Record a verified ground-truth override to prevent an LLM hallucination:
  python3 scripts/context_ctl.py correct --workspace /path/to/repo \
    --key "hdfc-live-env" \
    --mistake "Assuming HDFC_ENV is LIVE in production" \
    --truth "HDFC_ENV must be set to PRODUCTION in live environment"

  # 4. Override or delete a specific cached entry:
  python3 scripts/context_ctl.py override --workspace /path/to/repo \
    --type query --key "old-query-key" --delete
"""

import argparse
import json
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "server"))

import db_engine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage Context Graph overrides, context refreshes, and hallucination fixes."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # verify subcommand
    p_verify = sub.add_parser(
        "verify",
        help="Audit cache against disk AST to detect and fix hallucinated symbols, ghost files, and broken edges.",
    )
    p_verify.add_argument("--workspace", "-w", required=True, help="Workspace path.")
    p_verify.add_argument("--file", "-f", default=None, help="Optional single file path.")
    p_verify.add_argument(
        "--dry-run",
        action="store_true",
        help="Report issues without modifying the SQLite cache.",
    )

    # refresh subcommand
    p_refresh = sub.add_parser(
        "refresh",
        help="Refresh or reset workspace context (stale_only, force_all, file, purge_queries, hard_reset).",
    )
    p_refresh.add_argument("--workspace", "-w", required=True, help="Workspace path.")
    p_refresh.add_argument(
        "--mode",
        "-m",
        default="stale_only",
        choices=["stale_only", "force_all", "file", "purge_queries", "hard_reset"],
        help="Refresh mode (default: stale_only).",
    )
    p_refresh.add_argument(
        "--target",
        "-t",
        default=None,
        help="Target file path (for --mode file) or query_key/tag (for --mode purge_queries).",
    )

    # correct subcommand
    p_correct = sub.add_parser(
        "correct",
        help="Pin a verified ground-truth correction to fix and prevent an LLM hallucination.",
    )
    p_correct.add_argument(
        "--workspace", "-w", default="global", help="Workspace path (or 'global')."
    )
    p_correct.add_argument("--key", "-k", required=True, help="Unique override key slug.")
    p_correct.add_argument(
        "--truth",
        required=True,
        help="Authoritative verified ground-truth statement.",
    )
    p_correct.add_argument(
        "--mistake",
        default="",
        help="What the LLM previously hallucinated or got wrong.",
    )
    p_correct.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Optional related file paths.",
    )
    p_correct.add_argument(
        "--priority",
        default="high",
        choices=["critical", "high", "normal"],
        help="Priority level (default: high).",
    )

    # override subcommand
    p_override = sub.add_parser(
        "override",
        help="Directly override or delete a cached file, query, relationship, or ground-truth entry.",
    )
    p_override.add_argument("--workspace", "-w", required=True, help="Workspace path.")
    p_override.add_argument(
        "--type",
        required=True,
        choices=["file", "query", "relationship", "override"],
        help="Entry type.",
    )
    p_override.add_argument("--key", "-k", required=True, help="Target file path or key.")
    p_override.add_argument("--value", "-v", default="", help="New summary/value text.")
    p_override.add_argument(
        "--delete", action="store_true", help="Delete the entry instead of updating."
    )

    args = parser.parse_args()

    if args.cmd == "verify":
        res = db_engine.verify_and_fix_hallucinations(
            workspace_path=args.workspace,
            file_path=args.file,
            auto_fix=not args.dry_run,
        )
    elif args.cmd == "refresh":
        res = db_engine.refresh_context(
            workspace_path=args.workspace,
            mode=args.mode,
            target=args.target,
        )
    elif args.cmd == "correct":
        res = db_engine.record_correction(
            workspace_path=args.workspace,
            override_key=args.key,
            verified_truth=args.truth,
            hallucination_or_mistake=args.mistake,
            scope_files=args.files,
            priority=args.priority,
        )
    elif args.cmd == "override":
        res = db_engine.override_or_delete_entry(
            workspace_path=args.workspace,
            target_type=args.type,
            target_key=args.key,
            new_value=args.value,
            delete=args.delete,
        )
    else:
        res = {"status": "error", "message": "Unknown command"}

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
