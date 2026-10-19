#!/usr/bin/env python3
"""
CLI & Helper Reporter for viewing LLM token usage per conversation and per project/Git repo.
Usage:
  python3 scripts/token_report.py [--workspace /path/to/repo] [--json]
"""

import argparse
import json
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "server"))

import db_engine


def fmt_num(n: int) -> str:
    return f"{n:,}"


def print_markdown_report(report: dict) -> None:
    gt = report["grand_totals"]
    print("# Antigravity Token Usage Report\n")
    print(
        f"**Total Conversations**: {gt['total_conversations']} | "
        f"**Total Tokens**: `{fmt_num(gt['total_tokens'])}` "
        f"(Input: `{fmt_num(gt['input_tokens'])}`, "
        f"Cache Read: `{fmt_num(gt['cache_read_tokens'])}` [{gt['cache_hit_rate_pct']}%], "
        f"Output: `{fmt_num(gt['output_tokens'])}`)\n"
    )

    print("## 1. Token Usage by Project / Related Git Repo\n")
    print(
        "| Project / Git Repo | Branch | Remote URL | Convs | Turns | Input Tokens | Cache Read Tokens | Output Tokens | Total Tokens | Cache Hit % |"
    )
    print("| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for p in report["by_project_repo"]:
        remote = p["git_remote"] or "-"
        branch = p["git_branch"] or "-"
        print(
            f"| **{p['repo_name']}** (`{p['project_root']}`) | `{branch}` | `{remote}` | "
            f"{p['conversation_count']} | {p['total_turns']} | "
            f"{fmt_num(p['input_tokens'])} | {fmt_num(p['cache_read_tokens'])} | "
            f"{fmt_num(p['output_tokens'])} | **{fmt_num(p['total_tokens'])}** | {p['cache_hit_rate_pct']}% |"
        )
    print("")

    print("## 2. Token Usage per Conversation\n")
    print(
        "| Conversation ID | Prompt / Title | Project / Repo | Turns | Input | Cache Read | Output | Total Tokens | Cache Hit % |"
    )
    print("| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for c in report["by_conversation"]:
        short_id = c["conversation_id"][:8]
        title = (c["title"] or "").replace("|", "\\|")[:55]
        print(
            f"| `{short_id}...` | {title} | **{c['repo_name']}** | {c['turn_count']} | "
            f"{fmt_num(c['input_tokens'])} | {fmt_num(c['cache_read_tokens'])} | "
            f"{fmt_num(c['output_tokens'])} | **{fmt_num(c['total_tokens'])}** | {c['cache_hit_rate_pct']}% |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View Antigravity LLM token usage per conversation and per project/Git repo."
    )
    parser.add_argument(
        "--workspace",
        "-w",
        default=None,
        help="Optional workspace or Git repository path to filter by.",
    )
    parser.add_argument(
        "--conversation",
        "-c",
        default=None,
        help="Optional conversation ID to filter by.",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=50,
        help="Maximum number of conversations to list (default: 50).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of Markdown tables.",
    )
    args = parser.parse_args()

    report = db_engine.get_token_usage_report(
        workspace_path=args.workspace,
        conversation_id=args.conversation,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_markdown_report(report)


if __name__ == "__main__":
    main()
