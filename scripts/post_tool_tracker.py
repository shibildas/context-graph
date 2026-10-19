#!/usr/bin/env python3
"""
Universal PostToolUse Hook for the context-graph plugin.
Compatible with:
  - Google Antigravity (`toolCall`, `workspacePaths`, `conversationId`, `transcriptPath`)
  - Claude Code / Gemini CLI (`tool_name`, `tool_input`, `cwd`, `session_id`, `transcript_path`)
"""

import json
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "server"))

import db_engine

READ_TOOLS = {"view_file", "Read", "read_file"}
EDIT_TOOLS = {
    "replace_file_content",
    "multi_replace_file_content",
    "write_to_file",
    "Edit",
    "MultiEdit",
    "Write",
    "write_file",
    "edit_file",
}


def handle_post_tool(payload: dict) -> None:
    workspace_paths = payload.get("workspacePaths") or []
    raw_ws = (
        workspace_paths[0]
        if workspace_paths
        else (payload.get("cwd") or "global")
    )
    ws = db_engine.normalize_workspace(raw_ws)
    conv_id = payload.get("conversationId") or payload.get("session_id") or ""
    transcript_path = (
        payload.get("transcriptPath") or payload.get("transcript_path") or ""
    )
    model_name = payload.get("modelName") or payload.get("model") or ""
    ts = db_engine.now_iso()

    conn = db_engine.get_connection()
    try:
        # Sync live conversation token usage across Antigravity / Claude Code / Codex CLI
        if transcript_path and os.path.isfile(transcript_path):
            db_engine.sync_transcript_usage(
                transcript_path=transcript_path,
                conversation_id=conv_id,
                workspace_path=ws,
                model_name=model_name,
                conn=conn,
            )

        if payload.get("error"):
            conn.commit()
            return

        # Support both Antigravity (`toolCall`) and Claude Code / Gemini CLI (`tool_name` + `tool_input`)
        tool_call = payload.get("toolCall") or {}
        tool_name = tool_call.get("name") or payload.get("tool_name") or ""
        args = tool_call.get("args") or payload.get("tool_input") or {}
        if not isinstance(args, dict):
            args = {}

        target_file = (
            args.get("AbsolutePath")
            or args.get("TargetFile")
            or args.get("file_path")
            or args.get("path")
            or args.get("notebook_path")
            or args.get("SearchPath")
            or args.get("SearchDirectory")
            or ""
        )

        if tool_name:
            conn.execute(
                """
                INSERT INTO tool_activity (workspace_path, conversation_id, tool_name, target_file, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ws,
                    conv_id,
                    tool_name,
                    target_file,
                    json.dumps(
                        {
                            k: v
                            for k, v in args.items()
                            if k
                            not in (
                                "CodeContent",
                                "ReplacementContent",
                                "TargetContent",
                                "ReplacementChunks",
                                "content",
                                "new_string",
                                "old_string",
                                "edits",
                            )
                        }
                    )[:500],
                    ts,
                ),
            )

        if tool_name in READ_TOOLS and target_file:
            fp = db_engine.normalize_file_path(target_file, ws)
            row = conn.execute(
                "SELECT read_count FROM files WHERE workspace_path = ? AND file_path = ?",
                (ws, fp),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE files SET read_count = read_count + 1, updated_at = ? WHERE workspace_path = ? AND file_path = ?",
                    (ts, ws, fp),
                )
            elif os.path.isfile(fp) and os.path.getsize(fp) <= 256 * 1024:
                ext = os.path.splitext(fp)[1].lower()
                if ext in db_engine.CODE_EXTENSIONS:
                    try:
                        with open(fp, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        if ext == ".py":
                            summary, symbols, exports, _ = db_engine._analyze_python_file(fp, content)
                        else:
                            summary, symbols, exports, _ = db_engine._analyze_generic_file(fp, content, ext)
                        conn.commit()
                        db_engine.upsert_file(
                            workspace_path=ws,
                            file_path=fp,
                            summary=summary,
                            symbols=symbols,
                            exports=exports,
                            tags=[ext.lstrip(".")],
                        )
                        conn.execute(
                            "UPDATE files SET read_count = 1 WHERE workspace_path = ? AND file_path = ?",
                            (ws, fp),
                        )
                    except Exception:
                        pass

        elif tool_name in EDIT_TOOLS and target_file:
            fp = db_engine.normalize_file_path(target_file, ws)
            row = conn.execute(
                "SELECT edit_count FROM files WHERE workspace_path = ? AND file_path = ?",
                (ws, fp),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE files SET edit_count = edit_count + 1, needs_refresh = 1, updated_at = ? WHERE workspace_path = ? AND file_path = ?",
                    (ts, ws, fp),
                )

        conn.commit()
    finally:
        conn.close()


def main() -> None:
    try:
        raw = sys.stdin.read().strip()
        if raw:
            handle_post_tool(json.loads(raw))
    except Exception:
        pass

    sys.stdout.write("{}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
