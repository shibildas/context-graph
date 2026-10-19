#!/usr/bin/env python3
"""
PostToolUse Hook for the Antigravity context-graph plugin.
Passively tracks file reads, edits, searches, and live conversation token usage
(linked to the project/Git repository) so the knowledge graph stays in sync.
"""

import json
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "server"))

import db_engine


def handle_post_tool(payload: dict) -> None:
    workspace_paths = payload.get("workspacePaths") or []
    ws = db_engine.normalize_workspace(workspace_paths[0] if workspace_paths else "global")
    conv_id = payload.get("conversationId", "")
    transcript_path = payload.get("transcriptPath", "")
    model_name = payload.get("modelName", "")
    ts = db_engine.now_iso()

    conn = db_engine.get_connection()
    try:
        # Sync live conversation token usage and Git repo association
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

        tool_call = payload.get("toolCall") or {}
        tool_name = tool_call.get("name", "")
        args = tool_call.get("args") or {}

        target_file = (
            args.get("AbsolutePath")
            or args.get("TargetFile")
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
                            )
                        }
                    )[:500],
                    ts,
                ),
            )

        if tool_name == "view_file" and target_file:
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
                            (ts, ws, fp),
                        )
                    except Exception:
                        pass

        elif (
            tool_name
            in ("replace_file_content", "multi_replace_file_content", "write_to_file")
            and target_file
        ):
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
