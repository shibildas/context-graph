#!/usr/bin/env python3
"""
CLI & Helper Reporter for viewing LLM token usage across Antigravity, Claude Code, and Codex CLI,
broken down per LLM client, per project/Git repo, and per conversation.
Usage:
  python3 scripts/token_report.py [--workspace /path/to/repo] [--client antigravity|claude-code|codex-cli] [--json]
"""

import argparse
import json
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

from server import db_engine


def fmt_num(n: int) -> str:
    return f"{n:,}"


def fmt_usd(val: float) -> str:
    return f"${float(val or 0.0):,.2f}"


def print_markdown_report(report: dict) -> None:
    gt = report["grand_totals"]
    print("# Multi-LLM Token Usage & Cost Report\n")
    print(
        f"**Total Conversations**: {gt['total_conversations']} | "
        f"**Features Tracked**: {gt.get('total_features', len(report.get('by_feature', [])))} | "
        f"**Total Tokens**: `{fmt_num(gt['total_tokens'])}` "
        f"(Input: `{fmt_num(gt['input_tokens'])}`, "
        f"API Prefix Cache: `{fmt_num(gt['cache_read_tokens'])}` [{gt['cache_hit_rate_pct']}%], "
        f"Output: `{fmt_num(gt['output_tokens'])}`)\n"
        f"**Est. Actual LLM Cost**: `{fmt_usd(gt.get('estimated_cost_usd', 0.0))}` | "
        f"**Context-Graph Plugin Calls**: `{fmt_num(gt.get('plugin_calls', 0))}` | "
        f"**Plugin Tokens Saved**: `{fmt_num(gt.get('plugin_tokens_saved', 0))}` | "
        f"**Saved by Plugin**: `{fmt_usd(gt.get('estimated_cache_savings_usd', 0.0))}`\n"
    )

    if report.get("by_feature"):
        print("## 1. Cost & Token Usage per Feature (Branches & Tasks)\n")
        print(
            "| Feature / Task | Ticket(s) | Repo(s) | Convs | Turns | Total Tokens | Plugin Used | Plugin Tokens Saved | Actual Cost ($) | Saved by Plugin ($) |"
        )
        print("| :--- | :--- | :--- | ---: | ---: | ---: | :--- | ---: | ---: | ---: |")
        for f in report["by_feature"]:
            fname = (f["feature_name"] or "").replace("|", "\\|")[:42]
            ticket = f.get("ticket_id") or "-"
            repos = (f.get("repo_name") or "-").replace("|", "\\|")[:28]
            p_calls = int(f.get("plugin_calls") or 0)
            p_used = f"Yes ({p_calls})" if p_calls > 0 else "No"
            p_tok = fmt_num(int(f.get("plugin_tokens_saved") or 0)) if p_calls > 0 else "0"
            p_sav = fmt_usd(f.get("estimated_cache_savings_usd", 0.0)) if p_calls > 0 else "$0.00"
            print(
                f"| **{fname}** | `{ticket}` | `{repos}` | "
                f"{f['conversation_count']} | {f['total_turns']} | "
                f"**{fmt_num(f['total_tokens'])}** | `{p_used}` | {p_tok} | "
                f"**{fmt_usd(f.get('estimated_cost_usd', 0.0))}** | {p_sav} |"
            )
        print("")

    if report.get("by_client"):
        print("## 2. Token Usage & Cost by LLM Client\n")
        print(
            "| LLM Client | Convs | Turns | Input Tokens | API Cache Read | Output Tokens | Total Tokens | Plugin Calls | Actual Cost ($) | Saved by Plugin ($) |"
        )
        print("| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for cl in report["by_client"]:
            p_calls = int(cl.get("plugin_calls") or 0)
            p_sav = fmt_usd(cl.get("estimated_cache_savings_usd", 0.0)) if p_calls > 0 else "$0.00"
            print(
                f"| **`{cl['client_source']}`** | {cl['conversation_count']} | {cl['total_turns']} | "
                f"{fmt_num(cl['input_tokens'])} | {fmt_num(cl['cache_read_tokens'])} | "
                f"{fmt_num(cl['output_tokens'])} | **{fmt_num(cl['total_tokens'])}** | {p_calls} | "
                f"**{fmt_usd(cl.get('estimated_cost_usd', 0.0))}** | {p_sav} |"
            )
        print("")

    print("## 3. Token Usage & Cost by Project / Related Git Repo\n")
    print(
        "| Project / Git Repo | Branch | Convs | Turns | Total Tokens | Plugin Used | Plugin Tokens Saved | Actual Cost ($) | Saved by Plugin ($) |"
    )
    print("| :--- | :--- | ---: | ---: | ---: | :--- | ---: | ---: | ---: |")
    for p in report["by_project_repo"]:
        branch = p["git_branch"] or "-"
        p_calls = int(p.get("plugin_calls") or 0)
        p_used = f"Yes ({p_calls})" if p_calls > 0 else "No"
        p_tok = fmt_num(int(p.get("plugin_tokens_saved") or 0)) if p_calls > 0 else "0"
        p_sav = fmt_usd(p.get("estimated_cache_savings_usd", 0.0)) if p_calls > 0 else "$0.00"
        print(
            f"| **{p['repo_name']}** (`{p['project_root']}`) | `{branch}` | "
            f"{p['conversation_count']} | {p['total_turns']} | "
            f"**{fmt_num(p['total_tokens'])}** | `{p_used}` | {p_tok} | "
            f"**{fmt_usd(p.get('estimated_cost_usd', 0.0))}** | {p_sav} |"
        )
    print("")

    print("## 4. Token Usage & Cost per Conversation\n")
    print(
        "| Client | Conv ID | Feature / Prompt | Project / Repo | Turns | Total Tokens | Plugin Used | Cost ($) | Saved by Plugin ($) |"
    )
    print("| :--- | :--- | :--- | :--- | ---: | ---: | :--- | ---: | ---: |")
    for c in report["by_conversation"]:
        short_id = c["conversation_id"][:8]
        title = (c.get("feature_name") or c["title"] or "").replace("|", "\\|")[:42]
        p_calls = int(c.get("plugin_calls") or 0)
        p_used = f"Yes ({p_calls})" if p_calls > 0 else "No"
        p_sav = fmt_usd(c.get("estimated_cache_savings_usd", 0.0)) if p_calls > 0 else "$0.00"
        print(
            f"| `{c['client_source']}` | `{short_id}...` | {title} | **{c['repo_name']}** | {c['turn_count']} | "
            f"**{fmt_num(c['total_tokens'])}** | `{p_used}` | "
            f"**{fmt_usd(c.get('estimated_cost_usd', 0.0))}** | {p_sav} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View LLM token usage across Antigravity, Claude Code, and Codex CLI."
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
        "--client",
        default=None,
        help="Optional LLM client filter (antigravity, claude-code, codex-cli).",
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
        client_source=args.client,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_markdown_report(report)


if __name__ == "__main__":
    main()
