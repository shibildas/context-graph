#!/usr/bin/env python3
"""
Core SQLite Knowledge Graph, Query Cache, Anti-Hallucination & Multi-LLM Token Usage Engine (`context-graph`).
Supports:
  - Google Antigravity
  - Claude Code / Claude Desktop
  - Cursor / Windsurf / Cline
  - OpenAI Codex CLI
  - Google Gemini CLI
Zero external dependencies (uses Python 3 standard library only).
"""

import ast
import configparser
import datetime
import glob
import hashlib
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_DB_DIR = os.path.expanduser("~/.gemini/context-graph")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "cache.db")

ANTIGRAVITY_BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")
CLAUDE_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
CODEX_SESSIONS_DIR = os.path.expanduser("~/.codex/sessions")
GEMINI_CLI_TMP_DIR = os.path.expanduser("~/.gemini/tmp")

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".next",
    ".nuxt",
    "target",
    "vendor",
    ".idea",
    ".vscode",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
}

CODE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".swift",
    ".sql",
    ".graphql",
    ".proto",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".md",
}


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_abspath(path_str: str) -> str:
    expanded = os.path.expanduser(path_str)
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    try:
        return os.path.abspath(expanded)
    except FileNotFoundError:
        return os.path.normpath(os.path.join(os.path.expanduser("~"), expanded))


def normalize_workspace(workspace_path: Optional[str]) -> str:
    if not workspace_path:
        return "global"
    cleaned = workspace_path.strip()
    if cleaned.startswith("file://"):
        cleaned = cleaned[len("file://") :]
    if cleaned.lower() in ("global", "all", "*"):
        return "global"
    return _safe_abspath(cleaned)


def normalize_file_path(file_path: str, workspace_path: Optional[str] = None) -> str:
    cleaned = file_path.strip()
    if cleaned.startswith("file://"):
        cleaned = cleaned[len("file://") :]
    expanded = os.path.expanduser(cleaned)
    if not os.path.isabs(expanded) and workspace_path and workspace_path != "global":
        expanded = os.path.join(normalize_workspace(workspace_path), expanded)
    return _safe_abspath(expanded)


def to_rel_path(file_path: str, workspace_path: str) -> str:
    if workspace_path and workspace_path != "global":
        try:
            rel = os.path.relpath(file_path, workspace_path)
            if not rel.startswith(".."):
                return rel
        except ValueError:
            pass
    return file_path


def compute_file_signature(file_path: str) -> Tuple[Optional[str], Optional[float], Optional[int]]:
    """Returns (sha256, mtime, size_bytes) for a file on disk, or (None, None, None) if missing."""
    try:
        st = os.stat(file_path)
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest(), st.st_mtime, st.st_size
    except OSError:
        return None, None, None


def detect_git_repo_info(path_str: Optional[str]) -> Dict[str, str]:
    """
    Walks up from path_str to find a .git directory/file and extracts:
    repo_root, repo_name, git_remote, git_branch without spawning subprocesses.
    """
    if not path_str or path_str == "global":
        return {
            "repo_root": "",
            "repo_name": "unscoped / global",
            "git_remote": "",
            "git_branch": "",
        }

    curr = os.path.abspath(os.path.expanduser(path_str))
    if os.path.isfile(curr):
        curr = os.path.dirname(curr)

    repo_root = ""
    git_dir = ""
    probe = curr
    while True:
        cand = os.path.join(probe, ".git")
        if os.path.isdir(cand):
            repo_root = probe
            git_dir = cand
            break
        elif os.path.isfile(cand):
            repo_root = probe
            try:
                with open(cand, "r", encoding="utf-8", errors="replace") as f:
                    line = f.readline().strip()
                if line.startswith("gitdir:"):
                    rel_git = line.split(":", 1)[1].strip()
                    git_dir = os.path.abspath(os.path.join(probe, rel_git))
            except OSError:
                pass
            break
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent

    if not repo_root:
        return {
            "repo_root": curr,
            "repo_name": os.path.basename(curr) or curr,
            "git_remote": "",
            "git_branch": "",
        }

    git_branch = ""
    git_remote = ""
    if git_dir and os.path.isdir(git_dir):
        head_file = os.path.join(git_dir, "HEAD")
        if os.path.isfile(head_file):
            try:
                with open(head_file, "r", encoding="utf-8", errors="replace") as f:
                    head_val = f.readline().strip()
                if head_val.startswith("ref: refs/heads/"):
                    git_branch = head_val[len("ref: refs/heads/") :]
                else:
                    git_branch = head_val[:12]
            except OSError:
                pass

        cfg_file = os.path.join(git_dir, "config")
        if os.path.isfile(cfg_file):
            try:
                cp = configparser.ConfigParser()
                cp.read(cfg_file, encoding="utf-8")
                if 'remote "origin"' in cp and "url" in cp['remote "origin"']:
                    git_remote = cp['remote "origin"']["url"].strip()
                else:
                    for sec in cp.sections():
                        if sec.startswith("remote ") and "url" in cp[sec]:
                            git_remote = cp[sec]["url"].strip()
                            break
            except Exception:
                pass

    repo_name = os.path.basename(repo_root)
    if git_remote:
        cleaned_url = git_remote.rstrip("/")
        if cleaned_url.endswith(".git"):
            cleaned_url = cleaned_url[:-4]
        parts = re.split(r"[:/]", cleaned_url)
        if len(parts) >= 2:
            repo_name = f"{parts[-2]}/{parts[-1]}"

    return {
        "repo_root": repo_root,
        "repo_name": repo_name,
        "git_remote": git_remote,
        "git_branch": git_branch,
    }


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    if not db_path:
        db_path = os.environ.get("CONTEXT_GRAPH_DB_PATH") or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            workspace_path TEXT NOT NULL,
            file_path TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            sha256 TEXT,
            mtime REAL,
            size_bytes INTEGER,
            summary TEXT DEFAULT '',
            symbols_json TEXT DEFAULT '[]',
            exports_json TEXT DEFAULT '[]',
            tags_json TEXT DEFAULT '[]',
            needs_refresh INTEGER DEFAULT 0,
            read_count INTEGER DEFAULT 0,
            edit_count INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (workspace_path, file_path)
        );

        CREATE TABLE IF NOT EXISTS relationships (
            workspace_path TEXT NOT NULL,
            source_file TEXT NOT NULL,
            target_file TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            description TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (workspace_path, source_file, target_file, relation_type)
        );

        CREATE TABLE IF NOT EXISTS cached_queries (
            workspace_path TEXT NOT NULL,
            query_key TEXT NOT NULL,
            category TEXT DEFAULT 'queried_data',
            query_text TEXT DEFAULT '',
            result_summary TEXT NOT NULL,
            data_json TEXT DEFAULT '{}',
            artifact_path TEXT DEFAULT '',
            related_files_json TEXT DEFAULT '[]',
            tags_json TEXT DEFAULT '[]',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (workspace_path, query_key)
        );

        CREATE TABLE IF NOT EXISTS ground_truth_overrides (
            workspace_path TEXT NOT NULL,
            override_key TEXT NOT NULL,
            hallucination_or_mistake TEXT DEFAULT '',
            verified_truth TEXT NOT NULL,
            scope_files_json TEXT DEFAULT '[]',
            priority TEXT DEFAULT 'high',
            active INTEGER DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (workspace_path, override_key)
        );

        CREATE TABLE IF NOT EXISTS tool_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_path TEXT NOT NULL,
            conversation_id TEXT DEFAULT '',
            tool_name TEXT NOT NULL,
            target_file TEXT DEFAULT '',
            details TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_usage (
            conversation_id TEXT PRIMARY KEY,
            client_source TEXT DEFAULT 'antigravity',
            workspace_path TEXT NOT NULL,
            repo_root TEXT DEFAULT '',
            repo_name TEXT DEFAULT '',
            git_remote TEXT DEFAULT '',
            git_branch TEXT DEFAULT '',
            model_name TEXT DEFAULT '',
            title TEXT DEFAULT '',
            turn_count INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            plugin_calls INTEGER DEFAULT 0,
            plugin_tokens_saved INTEGER DEFAULT 0,
            transcript_path TEXT DEFAULT '',
            transcript_mtime REAL DEFAULT 0,
            started_at TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_files_workspace ON files(workspace_path);
        CREATE INDEX IF NOT EXISTS idx_rel_workspace_src ON relationships(workspace_path, source_file);
        CREATE INDEX IF NOT EXISTS idx_rel_workspace_tgt ON relationships(workspace_path, target_file);
        CREATE INDEX IF NOT EXISTS idx_queries_workspace ON cached_queries(workspace_path);
        CREATE INDEX IF NOT EXISTS idx_overrides_workspace ON ground_truth_overrides(workspace_path);
        CREATE INDEX IF NOT EXISTS idx_conv_usage_repo ON conversation_usage(repo_root);
        CREATE INDEX IF NOT EXISTS idx_conv_usage_ws ON conversation_usage(workspace_path);
        """
    )
    cols = [
        r["name"]
        for r in conn.execute("PRAGMA table_info(conversation_usage)").fetchall()
    ]
    if "client_source" not in cols:
        conn.execute(
            "ALTER TABLE conversation_usage ADD COLUMN client_source TEXT DEFAULT 'antigravity'"
        )
    if "plugin_calls" not in cols:
        conn.execute(
            "ALTER TABLE conversation_usage ADD COLUMN plugin_calls INTEGER DEFAULT 0"
        )
        conn.execute(
            "ALTER TABLE conversation_usage ADD COLUMN plugin_tokens_saved INTEGER DEFAULT 0"
        )
        conn.execute("UPDATE conversation_usage SET transcript_mtime = 0")
    conn.commit()


def check_file_staleness(row: sqlite3.Row) -> Dict[str, Any]:
    """Checks if a cached file entry matches the current file on disk."""
    fpath = row["file_path"]
    cached_sha = row["sha256"]
    cached_mtime = row["mtime"]
    needs_refresh = bool(row["needs_refresh"])

    try:
        st = os.stat(fpath)
    except OSError:
        return {"exists": False, "is_stale": True, "reason": "file_deleted_or_missing"}

    if needs_refresh:
        return {"exists": True, "is_stale": True, "reason": "marked_dirty_by_edit"}

    if cached_mtime is not None and abs(st.st_mtime - cached_mtime) < 0.001:
        return {"exists": True, "is_stale": False, "reason": "fresh_mtime_match"}

    current_sha, _, _ = compute_file_signature(fpath)
    if cached_sha and current_sha == cached_sha:
        return {"exists": True, "is_stale": False, "reason": "fresh_sha256_match"}

    return {"exists": True, "is_stale": True, "reason": "content_modified_on_disk"}


def upsert_file(
    workspace_path: str,
    file_path: str,
    summary: str,
    symbols: Optional[List[Any]] = None,
    exports: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    dependencies: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    ws = normalize_workspace(workspace_path)
    fp = normalize_file_path(file_path, ws)
    rel = to_rel_path(fp, ws)
    sha, mtime, size_bytes = compute_file_signature(fp)
    ts = now_iso()

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT symbols_json, exports_json, tags_json, read_count, edit_count FROM files WHERE workspace_path = ? AND file_path = ?",
            (ws, fp),
        ).fetchone()

        sym_json = (
            json.dumps(symbols)
            if symbols is not None
            else (existing["symbols_json"] if existing else "[]")
        )
        exp_json = (
            json.dumps(exports)
            if exports is not None
            else (existing["exports_json"] if existing else "[]")
        )
        tag_json = (
            json.dumps(tags)
            if tags is not None
            else (existing["tags_json"] if existing else "[]")
        )
        read_count = existing["read_count"] if existing else 0
        edit_count = existing["edit_count"] if existing else 0

        conn.execute(
            """
            INSERT INTO files (
                workspace_path, file_path, rel_path, sha256, mtime, size_bytes,
                summary, symbols_json, exports_json, tags_json, needs_refresh,
                read_count, edit_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            ON CONFLICT(workspace_path, file_path) DO UPDATE SET
                rel_path = excluded.rel_path,
                sha256 = excluded.sha256,
                mtime = excluded.mtime,
                size_bytes = excluded.size_bytes,
                summary = CASE WHEN excluded.summary != '' THEN excluded.summary ELSE files.summary END,
                symbols_json = excluded.symbols_json,
                exports_json = excluded.exports_json,
                tags_json = excluded.tags_json,
                needs_refresh = 0,
                updated_at = excluded.updated_at
            """,
            (
                ws,
                fp,
                rel,
                sha,
                mtime,
                size_bytes,
                summary,
                sym_json,
                exp_json,
                tag_json,
                read_count,
                edit_count,
                ts,
            ),
        )

        added_rels = 0
        if dependencies:
            for dep in dependencies:
                target = dep.get("target_file") or dep.get("target")
                rel_type = dep.get("relation_type") or dep.get("type") or "depends_on"
                desc = dep.get("description") or ""
                if target:
                    target_norm = normalize_file_path(target, ws)
                    conn.execute(
                        """
                        INSERT INTO relationships (workspace_path, source_file, target_file, relation_type, description, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(workspace_path, source_file, target_file, relation_type) DO UPDATE SET
                            description = CASE WHEN excluded.description != '' THEN excluded.description ELSE relationships.description END,
                            updated_at = excluded.updated_at
                        """,
                        (ws, fp, target_norm, rel_type, desc, ts),
                    )
                    added_rels += 1

        conn.commit()
        return {
            "status": "ok",
            "workspace_path": ws,
            "file_path": fp,
            "rel_path": rel,
            "sha256": sha,
            "size_bytes": size_bytes,
            "relationships_recorded": added_rels,
        }
    finally:
        conn.close()


def add_relationship(
    workspace_path: str,
    source_file: str,
    target_file: str,
    relation_type: str,
    description: str = "",
) -> Dict[str, Any]:
    ws = normalize_workspace(workspace_path)
    src = normalize_file_path(source_file, ws)
    tgt = normalize_file_path(target_file, ws)
    ts = now_iso()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO relationships (workspace_path, source_file, target_file, relation_type, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_path, source_file, target_file, relation_type) DO UPDATE SET
                description = excluded.description,
                updated_at = excluded.updated_at
            """,
            (ws, src, tgt, relation_type, description, ts),
        )
        conn.commit()
        return {
            "status": "ok",
            "source_file": to_rel_path(src, ws),
            "target_file": to_rel_path(tgt, ws),
            "relation_type": relation_type,
            "description": description,
        }
    finally:
        conn.close()


def store_query(
    workspace_path: str,
    query_key: str,
    result_summary: str,
    query_text: str = "",
    category: str = "queried_data",
    data: Optional[Any] = None,
    artifact_path: str = "",
    related_files: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    ws = normalize_workspace(workspace_path)
    ts = now_iso()
    norm_files = [normalize_file_path(f, ws) for f in (related_files or [])]
    data_str = json.dumps(data if data is not None else {})
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cached_queries (
                workspace_path, query_key, category, query_text, result_summary,
                data_json, artifact_path, related_files_json, tags_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_path, query_key) DO UPDATE SET
                category = excluded.category,
                query_text = CASE WHEN excluded.query_text != '' THEN excluded.query_text ELSE cached_queries.query_text END,
                result_summary = excluded.result_summary,
                data_json = excluded.data_json,
                artifact_path = CASE WHEN excluded.artifact_path != '' THEN excluded.artifact_path ELSE cached_queries.artifact_path END,
                related_files_json = excluded.related_files_json,
                tags_json = excluded.tags_json,
                updated_at = excluded.updated_at
            """,
            (
                ws,
                query_key,
                category,
                query_text,
                result_summary,
                data_str,
                artifact_path,
                json.dumps(norm_files),
                json.dumps(tags or []),
                ts,
            ),
        )
        conn.commit()
        return {
            "status": "ok",
            "workspace_path": ws,
            "query_key": query_key,
            "category": category,
            "updated_at": ts,
        }
    finally:
        conn.close()


def get_file_context(
    workspace_path: str, file_path: str, depth: int = 1
) -> Dict[str, Any]:
    ws = normalize_workspace(workspace_path)
    fp = normalize_file_path(file_path, ws)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM files WHERE workspace_path = ? AND file_path = ?",
            (ws, fp),
        ).fetchone()

        outgoing = conn.execute(
            "SELECT target_file, relation_type, description FROM relationships WHERE workspace_path = ? AND source_file = ?",
            (ws, fp),
        ).fetchall()

        incoming = conn.execute(
            "SELECT source_file, relation_type, description FROM relationships WHERE workspace_path = ? AND target_file = ?",
            (ws, fp),
        ).fetchall()

        related_queries = conn.execute(
            "SELECT query_key, category, result_summary, updated_at FROM cached_queries WHERE workspace_path = ? AND related_files_json LIKE ?",
            (ws, f"%{fp}%"),
        ).fetchall()

        overrides = conn.execute(
            """
            SELECT override_key, hallucination_or_mistake, verified_truth, priority, updated_at
            FROM ground_truth_overrides
            WHERE (workspace_path = ? OR workspace_path = 'global')
              AND active = 1
              AND (scope_files_json = '[]' OR scope_files_json LIKE ?)
            ORDER BY updated_at DESC
            """,
            (ws, f"%{fp}%"),
        ).fetchall()

        override_list = [
            {
                "override_key": ov["override_key"],
                "hallucination_or_mistake": ov["hallucination_or_mistake"],
                "verified_truth": ov["verified_truth"],
                "priority": ov["priority"],
                "updated_at": ov["updated_at"],
            }
            for ov in overrides
        ]

        if not row:
            return {
                "cached": False,
                "file_path": fp,
                "rel_path": to_rel_path(fp, ws),
                "message": "File is not yet cached. Read or index it and call cache_upsert_file.",
                "ground_truth_overrides": override_list,
                "outgoing_relationships": [
                    {
                        "target": to_rel_path(r["target_file"], ws),
                        "type": r["relation_type"],
                        "description": r["description"],
                    }
                    for r in outgoing
                ],
                "incoming_relationships": [
                    {
                        "source": to_rel_path(r["source_file"], ws),
                        "type": r["relation_type"],
                        "description": r["description"],
                    }
                    for r in incoming
                ],
            }

        staleness = check_file_staleness(row)
        result: Dict[str, Any] = {
            "cached": True,
            "file_path": fp,
            "rel_path": row["rel_path"],
            "is_stale": staleness["is_stale"],
            "staleness_reason": staleness["reason"],
            "token_saving_advice": (
                "FRESH: Do NOT re-read this file with view_file/Read unless you need exact lines for editing."
                if not staleness["is_stale"]
                else "STALE: File was modified on disk since last cached. Re-read changed sections and update cache."
            ),
            "ground_truth_overrides": override_list,
            "summary": row["summary"],
            "symbols": json.loads(row["symbols_json"] or "[]"),
            "exports": json.loads(row["exports_json"] or "[]"),
            "tags": json.loads(row["tags_json"] or "[]"),
            "read_count": row["read_count"],
            "edit_count": row["edit_count"],
            "updated_at": row["updated_at"],
            "outgoing_relationships": [
                {
                    "target": to_rel_path(r["target_file"], ws),
                    "target_abs": r["target_file"],
                    "type": r["relation_type"],
                    "description": r["description"],
                }
                for r in outgoing
            ],
            "incoming_relationships": [
                {
                    "source": to_rel_path(r["source_file"], ws),
                    "source_abs": r["source_file"],
                    "type": r["relation_type"],
                    "description": r["description"],
                }
                for r in incoming
            ],
            "related_cached_queries": [
                {
                    "query_key": q["query_key"],
                    "category": q["category"],
                    "result_summary": q["result_summary"],
                    "updated_at": q["updated_at"],
                }
                for q in related_queries
            ],
        }

        if depth > 1:
            neighbors = set()
            for r in outgoing:
                neighbors.add(r["target_file"])
            for r in incoming:
                neighbors.add(r["source_file"])
            neighbor_summaries = {}
            for nf in neighbors:
                nrow = conn.execute(
                    "SELECT rel_path, summary, symbols_json FROM files WHERE workspace_path = ? AND file_path = ?",
                    (ws, nf),
                ).fetchone()
                if nrow:
                    neighbor_summaries[nrow["rel_path"]] = {
                        "summary": nrow["summary"],
                        "symbols": json.loads(nrow["symbols_json"] or "[]")[:10],
                    }
            result["neighbor_summaries"] = neighbor_summaries

        return result
    finally:
        conn.close()


def get_overview(workspace_path: str, max_items: int = 50) -> Dict[str, Any]:
    ws = normalize_workspace(workspace_path)
    conn = get_connection()
    try:
        file_rows = conn.execute(
            "SELECT * FROM files WHERE workspace_path = ? ORDER BY updated_at DESC LIMIT ?",
            (ws, max_items),
        ).fetchall()

        rel_rows = conn.execute(
            "SELECT * FROM relationships WHERE workspace_path = ? ORDER BY updated_at DESC LIMIT ?",
            (ws, max_items * 2),
        ).fetchall()

        query_rows = conn.execute(
            "SELECT * FROM cached_queries WHERE workspace_path = ? ORDER BY updated_at DESC LIMIT ?",
            (ws, max_items),
        ).fetchall()

        override_rows = conn.execute(
            """
            SELECT * FROM ground_truth_overrides
            WHERE (workspace_path = ? OR workspace_path = 'global') AND active = 1
            ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END, updated_at DESC
            LIMIT ?
            """,
            (ws, max_items),
        ).fetchall()

        files_out = []
        stale_count = 0
        fresh_count = 0
        for r in file_rows:
            st = check_file_staleness(r)
            if st["is_stale"]:
                stale_count += 1
            else:
                fresh_count += 1
            syms = json.loads(r["symbols_json"] or "[]")
            files_out.append(
                {
                    "rel_path": r["rel_path"],
                    "file_path": r["file_path"],
                    "is_stale": st["is_stale"],
                    "summary": r["summary"],
                    "symbol_count": len(syms),
                    "key_symbols": [
                        s.get("name", s) if isinstance(s, dict) else str(s)
                        for s in syms[:8]
                    ],
                    "tags": json.loads(r["tags_json"] or "[]"),
                }
            )

        rels_out = [
            {
                "source": to_rel_path(r["source_file"], ws),
                "target": to_rel_path(r["target_file"], ws),
                "type": r["relation_type"],
                "description": r["description"],
            }
            for r in rel_rows
        ]

        queries_out = [
            {
                "query_key": q["query_key"],
                "category": q["category"],
                "query_text": q["query_text"],
                "result_summary": q["result_summary"],
                "artifact_path": q["artifact_path"],
                "tags": json.loads(q["tags_json"] or "[]"),
                "updated_at": q["updated_at"],
            }
            for q in query_rows
        ]

        overrides_out = [
            {
                "override_key": ov["override_key"],
                "hallucination_or_mistake": ov["hallucination_or_mistake"],
                "verified_truth": ov["verified_truth"],
                "scope_files": [
                    to_rel_path(f, ws) for f in json.loads(ov["scope_files_json"] or "[]")
                ],
                "priority": ov["priority"],
                "updated_at": ov["updated_at"],
            }
            for ov in override_rows
        ]

        repo_info = detect_git_repo_info(ws)

        return {
            "workspace_path": ws,
            "repo_info": repo_info,
            "stats": {
                "total_cached_files": len(files_out),
                "fresh_files": fresh_count,
                "stale_files": stale_count,
                "total_relationships": len(rels_out),
                "total_cached_queries": len(queries_out),
                "active_ground_truth_overrides": len(overrides_out),
            },
            "ground_truth_overrides": overrides_out,
            "files": files_out,
            "relationships": rels_out,
            "cached_queries": queries_out,
        }
    finally:
        conn.close()


def search_cache(
    workspace_path: str, query: str, category: str = "all"
) -> Dict[str, Any]:
    ws = normalize_workspace(workspace_path)
    q_like = f"%{query.strip()}%"
    conn = get_connection()
    try:
        matched_overrides = []
        if category in ("all", "overrides", "ground_truth"):
            rows = conn.execute(
                """
                SELECT * FROM ground_truth_overrides
                WHERE (workspace_path = ? OR workspace_path = 'global')
                  AND active = 1
                  AND (override_key LIKE ? OR hallucination_or_mistake LIKE ? OR verified_truth LIKE ? OR scope_files_json LIKE ?)
                ORDER BY updated_at DESC LIMIT 25
                """,
                (ws, q_like, q_like, q_like, q_like),
            ).fetchall()
            for ov in rows:
                matched_overrides.append(
                    {
                        "override_key": ov["override_key"],
                        "hallucination_or_mistake": ov["hallucination_or_mistake"],
                        "verified_truth": ov["verified_truth"],
                        "priority": ov["priority"],
                        "scope_files": [
                            to_rel_path(f, ws)
                            for f in json.loads(ov["scope_files_json"] or "[]")
                        ],
                        "updated_at": ov["updated_at"],
                    }
                )

        matched_files = []
        if category in ("all", "files", "symbols"):
            rows = conn.execute(
                """
                SELECT * FROM files
                WHERE workspace_path = ?
                  AND (rel_path LIKE ? OR summary LIKE ? OR symbols_json LIKE ? OR exports_json LIKE ? OR tags_json LIKE ?)
                ORDER BY updated_at DESC LIMIT 25
                """,
                (ws, q_like, q_like, q_like, q_like, q_like),
            ).fetchall()
            for r in rows:
                st = check_file_staleness(r)
                matched_files.append(
                    {
                        "rel_path": r["rel_path"],
                        "file_path": r["file_path"],
                        "is_stale": st["is_stale"],
                        "summary": r["summary"],
                        "symbols": json.loads(r["symbols_json"] or "[]"),
                        "exports": json.loads(r["exports_json"] or "[]"),
                    }
                )

        matched_rels = []
        if category in ("all", "relationships"):
            rows = conn.execute(
                """
                SELECT * FROM relationships
                WHERE workspace_path = ?
                  AND (source_file LIKE ? OR target_file LIKE ? OR relation_type LIKE ? OR description LIKE ?)
                ORDER BY updated_at DESC LIMIT 30
                """,
                (ws, q_like, q_like, q_like, q_like),
            ).fetchall()
            for r in rows:
                matched_rels.append(
                    {
                        "source": to_rel_path(r["source_file"], ws),
                        "target": to_rel_path(r["target_file"], ws),
                        "type": r["relation_type"],
                        "description": r["description"],
                    }
                )

        matched_queries = []
        if category in ("all", "queries", "queried_data", "generated_data"):
            rows = conn.execute(
                """
                SELECT * FROM cached_queries
                WHERE workspace_path = ?
                  AND (query_key LIKE ? OR query_text LIKE ? OR result_summary LIKE ? OR data_json LIKE ? OR tags_json LIKE ?)
                ORDER BY updated_at DESC LIMIT 25
                """,
                (ws, q_like, q_like, q_like, q_like, q_like),
            ).fetchall()
            for q in rows:
                matched_queries.append(
                    {
                        "query_key": q["query_key"],
                        "category": q["category"],
                        "query_text": q["query_text"],
                        "result_summary": q["result_summary"],
                        "data": json.loads(q["data_json"] or "{}"),
                        "artifact_path": q["artifact_path"],
                        "related_files": [
                            to_rel_path(f, ws)
                            for f in json.loads(q["related_files_json"] or "[]")
                        ],
                        "updated_at": q["updated_at"],
                    }
                )

        return {
            "workspace_path": ws,
            "query": query,
            "matched_overrides": matched_overrides,
            "matched_files": matched_files,
            "matched_relationships": matched_rels,
            "matched_queries": matched_queries,
        }
    finally:
        conn.close()


# --- Override, Refresh & Anti-Hallucination Engine ---


def record_correction(
    workspace_path: str,
    override_key: str,
    verified_truth: str,
    hallucination_or_mistake: str = "",
    scope_files: Optional[List[str]] = None,
    priority: str = "high",
    invalidate_related_cache: bool = True,
) -> Dict[str, Any]:
    """
    Pins an authoritative ground-truth correction to prevent repeating a hallucination
    or false assumption, and optionally invalidates/updates tainted cache entries.
    """
    ws = normalize_workspace(workspace_path)
    ts = now_iso()
    norm_files = [normalize_file_path(f, ws) for f in (scope_files or [])]

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO ground_truth_overrides (
                workspace_path, override_key, hallucination_or_mistake,
                verified_truth, scope_files_json, priority, active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(workspace_path, override_key) DO UPDATE SET
                hallucination_or_mistake = CASE WHEN excluded.hallucination_or_mistake != '' THEN excluded.hallucination_or_mistake ELSE ground_truth_overrides.hallucination_or_mistake END,
                verified_truth = excluded.verified_truth,
                scope_files_json = excluded.scope_files_json,
                priority = excluded.priority,
                active = 1,
                updated_at = excluded.updated_at
            """,
            (
                ws,
                override_key,
                hallucination_or_mistake,
                verified_truth,
                json.dumps(norm_files),
                priority,
                ts,
            ),
        )

        flagged_files = 0
        if invalidate_related_cache and norm_files:
            for fp in norm_files:
                cur = conn.execute(
                    "UPDATE files SET needs_refresh = 1, updated_at = ? WHERE workspace_path = ? AND file_path = ?",
                    (ts, ws, fp),
                )
                flagged_files += cur.rowcount

        conn.commit()
        return {
            "status": "ok",
            "workspace_path": ws,
            "override_key": override_key,
            "verified_truth": verified_truth,
            "hallucination_or_mistake": hallucination_or_mistake,
            "scope_files": [to_rel_path(f, ws) for f in norm_files],
            "flagged_files_for_refresh": flagged_files,
        }
    finally:
        conn.close()


def override_or_delete_entry(
    workspace_path: str,
    target_type: str,
    target_key: str,
    new_value: str = "",
    delete: bool = False,
    target_file_secondary: str = "",
) -> Dict[str, Any]:
    """
    Directly overrides or deletes a cached file summary, relationship, query, or ground-truth pin.
    target_type: 'file' | 'query' | 'relationship' | 'override'
    """
    ws = normalize_workspace(workspace_path)
    ts = now_iso()
    conn = get_connection()
    try:
        ttype = target_type.strip().lower()
        if ttype == "file":
            fp = normalize_file_path(target_key, ws)
            if delete:
                cur = conn.execute(
                    "DELETE FROM files WHERE workspace_path = ? AND file_path = ?",
                    (ws, fp),
                )
                conn.execute(
                    "DELETE FROM relationships WHERE workspace_path = ? AND (source_file = ? OR target_file = ?)",
                    (ws, fp, fp),
                )
                conn.commit()
                return {"status": "deleted", "target_type": "file", "file_path": fp, "rows_affected": cur.rowcount}
            else:
                conn.close()
                return upsert_file(workspace_path=ws, file_path=fp, summary=new_value)

        elif ttype == "query":
            if delete:
                cur = conn.execute(
                    "DELETE FROM cached_queries WHERE workspace_path = ? AND query_key = ?",
                    (ws, target_key),
                )
                conn.commit()
                return {"status": "deleted", "target_type": "query", "query_key": target_key, "rows_affected": cur.rowcount}
            else:
                conn.close()
                return store_query(
                    workspace_path=ws,
                    query_key=target_key,
                    result_summary=new_value,
                    category="queried_data",
                )

        elif ttype == "relationship":
            src = normalize_file_path(target_key, ws)
            if delete:
                if target_file_secondary:
                    tgt = normalize_file_path(target_file_secondary, ws)
                    cur = conn.execute(
                        "DELETE FROM relationships WHERE workspace_path = ? AND source_file = ? AND target_file = ?",
                        (ws, src, tgt),
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM relationships WHERE workspace_path = ? AND (source_file = ? OR target_file = ?)",
                        (ws, src, src),
                    )
                conn.commit()
                return {"status": "deleted", "target_type": "relationship", "rows_affected": cur.rowcount}
            else:
                tgt = normalize_file_path(target_file_secondary, ws) if target_file_secondary else src
                conn.close()
                return add_relationship(
                    workspace_path=ws,
                    source_file=src,
                    target_file=tgt,
                    relation_type="depends_on",
                    description=new_value,
                )

        elif ttype == "override":
            if delete:
                cur = conn.execute(
                    "DELETE FROM ground_truth_overrides WHERE workspace_path = ? AND override_key = ?",
                    (ws, target_key),
                )
                conn.commit()
                return {"status": "deleted", "target_type": "override", "override_key": target_key, "rows_affected": cur.rowcount}
            else:
                conn.close()
                return record_correction(
                    workspace_path=ws,
                    override_key=target_key,
                    verified_truth=new_value,
                )
        else:
            return {"status": "error", "message": f"Unknown target_type: {target_type}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def verify_and_fix_hallucinations(
    workspace_path: str,
    file_path: Optional[str] = None,
    auto_fix: bool = True,
) -> Dict[str, Any]:
    """
    Audits the cached knowledge graph against actual disk reality to detect and fix hallucinations:
      1. Ghost files (cached files that no longer exist on disk)
      2. Broken relationships (edges pointing to/from non-existent files)
      3. Hallucinated or drifted symbols (cached functions/classes that don't exist in the actual file AST)
      4. Stale queries (cached queries whose underlying related_files were modified after the query was stored)
    """
    ws = normalize_workspace(workspace_path)
    conn = get_connection()
    ghost_files: List[str] = []
    broken_relationships: List[Dict[str, str]] = []
    drifted_symbol_files: List[Dict[str, Any]] = []
    stale_queries: List[Dict[str, Any]] = []
    fixed_actions: List[str] = []

    try:
        if file_path:
            fp_filter = normalize_file_path(file_path, ws)
            file_rows = conn.execute(
                "SELECT * FROM files WHERE workspace_path = ? AND file_path = ?",
                (ws, fp_filter),
            ).fetchall()
        else:
            file_rows = conn.execute(
                "SELECT * FROM files WHERE workspace_path = ?",
                (ws,),
            ).fetchall()

        for row in file_rows:
            fp = row["file_path"]
            rel = row["rel_path"]
            if not os.path.isfile(fp):
                ghost_files.append(rel)
                if auto_fix:
                    conn.execute(
                        "DELETE FROM files WHERE workspace_path = ? AND file_path = ?",
                        (ws, fp),
                    )
                    conn.execute(
                        "DELETE FROM relationships WHERE workspace_path = ? AND (source_file = ? OR target_file = ?)",
                        (ws, fp, fp),
                    )
                    fixed_actions.append(f"Purged non-existent ghost file `{rel}` and its edges.")
                continue

            # Compare cached symbols against live AST/regex symbols on disk
            ext = os.path.splitext(fp)[1].lower()
            if ext in CODE_EXTENSIONS and os.path.getsize(fp) <= 512 * 1024:
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if ext == ".py":
                        live_sum, live_syms, live_exp, _ = _analyze_python_file(fp, content)
                    else:
                        live_sum, live_syms, live_exp, _ = _analyze_generic_file(fp, content, ext)

                    cached_syms = json.loads(row["symbols_json"] or "[]")
                    cached_names = {
                        s.get("name") for s in cached_syms if isinstance(s, dict) and s.get("name")
                    }
                    live_names = {
                        s.get("name") for s in live_syms if isinstance(s, dict) and s.get("name")
                    }
                    hallucinated_names = sorted(list(cached_names - live_names))
                    missing_names = sorted(list(live_names - cached_names))
                    st = check_file_staleness(row)

                    if hallucinated_names or missing_names or st["is_stale"]:
                        drifted_symbol_files.append(
                            {
                                "rel_path": rel,
                                "hallucinated_or_removed_symbols": hallucinated_names,
                                "unindexed_new_symbols": missing_names,
                                "was_stale": st["is_stale"],
                            }
                        )
                        if auto_fix:
                            sha, mtime, size_bytes = compute_file_signature(fp)
                            conn.execute(
                                """
                                UPDATE files
                                SET sha256 = ?, mtime = ?, size_bytes = ?,
                                    symbols_json = ?, exports_json = ?, needs_refresh = 0, updated_at = ?
                                WHERE workspace_path = ? AND file_path = ?
                                """,
                                (
                                    sha,
                                    mtime,
                                    size_bytes,
                                    json.dumps(live_syms),
                                    json.dumps(live_exp),
                                    now_iso(),
                                    ws,
                                    fp,
                                ),
                            )
                            fixed_actions.append(
                                f"Re-synced symbols & SHA-256 for `{rel}` (removed {len(hallucinated_names)} phantom symbols, added {len(missing_names)} live symbols)."
                            )
                except OSError:
                    pass

        # Check all relationships for broken endpoints
        rel_rows = conn.execute(
            "SELECT * FROM relationships WHERE workspace_path = ?",
            (ws,),
        ).fetchall()
        for r in rel_rows:
            src = r["source_file"]
            tgt = r["target_file"]
            if not os.path.exists(src) or not os.path.exists(tgt):
                broken_relationships.append(
                    {
                        "source": to_rel_path(src, ws),
                        "target": to_rel_path(tgt, ws),
                        "type": r["relation_type"],
                    }
                )
                if auto_fix:
                    conn.execute(
                        "DELETE FROM relationships WHERE workspace_path = ? AND source_file = ? AND target_file = ? AND relation_type = ?",
                        (ws, src, tgt, r["relation_type"]),
                    )
                    fixed_actions.append(
                        f"Removed broken relationship `{to_rel_path(src, ws)}` -> `{to_rel_path(tgt, ws)}`."
                    )

        # Check cached queries for underlying file modifications
        q_rows = conn.execute(
            "SELECT * FROM cached_queries WHERE workspace_path = ?",
            (ws,),
        ).fetchall()
        for q in q_rows:
            rel_files = json.loads(q["related_files_json"] or "[]")
            missing_or_newer = []
            for rf in rel_files:
                if not os.path.exists(rf):
                    missing_or_newer.append(f"{to_rel_path(rf, ws)} (deleted)")
            if missing_or_newer:
                stale_queries.append(
                    {
                        "query_key": q["query_key"],
                        "affected_files": missing_or_newer,
                    }
                )

        issues_detected = {
            "ghost_files_count": len(ghost_files),
            "broken_relationships_count": len(broken_relationships),
            "drifted_or_hallucinated_symbol_files_count": len(drifted_symbol_files),
            "stale_queries_count": len(stale_queries),
        }
        total_issues = sum(issues_detected.values())
        conn.commit()
        return {
            "status": "ok",
            "workspace_path": ws,
            "auto_fix_applied": auto_fix,
            "issues_found": total_issues,
            "auto_fixed": len(fixed_actions),
            "issues_detected": issues_detected,
            "ghost_files": ghost_files,
            "broken_relationships": broken_relationships,
            "drifted_symbol_files": drifted_symbol_files,
            "stale_queries": stale_queries,
            "fixed_actions": fixed_actions,
        }
    finally:
        conn.close()


def refresh_context(
    workspace_path: str,
    mode: str = "stale_only",
    target: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Refreshes or resets cached workspace context.
    Modes:
      - 'stale_only': Re-indexes only modified/stale files and purges ghost files.
      - 'force_all': Re-indexes all files in the workspace from scratch and verifies edges.
      - 'file': Forces re-indexing of a single file (`target`).
      - 'purge_queries': Deletes cached queries (all, or matching `target`).
      - 'hard_reset': Wipes cached files, relationships, and queries for the workspace (preserves ground_truth_overrides and token usage).
    """
    ws = normalize_workspace(workspace_path)
    m = mode.strip().lower()

    if m == "file" and target:
        fp = normalize_file_path(target, ws)
        if not os.path.isfile(fp):
            return override_or_delete_entry(ws, "file", fp, delete=True)
        ext = os.path.splitext(fp)[1].lower()
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if ext == ".py":
            summary, symbols, exports, _ = _analyze_python_file(fp, content)
        else:
            summary, symbols, exports, _ = _analyze_generic_file(fp, content, ext)
        return upsert_file(
            workspace_path=ws,
            file_path=fp,
            summary=summary,
            symbols=symbols,
            exports=exports,
            tags=[ext.lstrip(".")],
        )

    elif m == "purge_queries":
        conn = get_connection()
        try:
            if target:
                cur = conn.execute(
                    "DELETE FROM cached_queries WHERE workspace_path = ? AND (query_key = ? OR tags_json LIKE ?)",
                    (ws, target, f"%{target}%"),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM cached_queries WHERE workspace_path = ?",
                    (ws,),
                )
            conn.commit()
            return {"status": "ok", "mode": m, "purged_queries": cur.rowcount}
        finally:
            conn.close()

    elif m == "hard_reset":
        conn = get_connection()
        try:
            f_del = conn.execute("DELETE FROM files WHERE workspace_path = ?", (ws,)).rowcount
            r_del = conn.execute("DELETE FROM relationships WHERE workspace_path = ?", (ws,)).rowcount
            q_del = conn.execute("DELETE FROM cached_queries WHERE workspace_path = ?", (ws,)).rowcount
            conn.commit()
        finally:
            conn.close()
        reindexed = (
            auto_index_workspace(ws, max_files=200, force=True)
            if os.path.isdir(ws)
            else {}
        )
        return {
            "status": "ok",
            "mode": "hard_reset",
            "cleared": {"files": f_del, "relationships": r_del, "queries": q_del},
            "reindexed": reindexed,
        }

    elif m == "force_all":
        audit = verify_and_fix_hallucinations(ws, auto_fix=True)
        idx = auto_index_workspace(ws, max_files=250, force=True)
        return {"status": "ok", "mode": "force_all", "audit": audit["issues_detected"], "index_result": idx}

    else:
        # Default: 'stale_only'
        audit = verify_and_fix_hallucinations(ws, auto_fix=True)
        idx = auto_index_workspace(ws, max_files=250, force=False)
        return {"status": "ok", "mode": "stale_only", "audit": audit["issues_detected"], "index_result": idx}


# --- Multi-LLM Token Usage & Related Repo Tracking ---

_SECRET_PATTERNS = [
    (re.compile(r"([a-zA-Z0-9+.-]+://[^/\s:@]+:)([^@\s/]+)(@)"), r"\1[REDACTED]\3"),
    (re.compile(r"\b(AVNS_[A-Za-z0-9_\-]{10,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|sk-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z\-_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[0-9A-Za-z\-]{10,})\b"), "[REDACTED_SECRET]"),
]


def redact_secrets(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    for pat, repl in _SECRET_PATTERNS:
        cleaned = pat.sub(repl, cleaned)
    return cleaned


def _extract_user_request_title(content: str) -> str:
    m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, re.DOTALL)
    text = m.group(1).strip() if m else content.strip()
    first_line = text.splitlines()[0].strip() if text else ""
    return redact_secrets(first_line)[:100]


def _unquote_arg(val: Any) -> str:
    if not isinstance(val, str):
        return ""
    s = val.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    return s


def _upsert_conversation_usage(
    conn: sqlite3.Connection,
    conversation_id: str,
    client_source: str,
    ws: str,
    model_name: str,
    title: str,
    turn_count: int,
    input_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    plugin_calls: int,
    plugin_tokens_saved: int,
    transcript_path: str,
    st_mtime: float,
    started_at: str,
    updated_at: str,
) -> Dict[str, Any]:
    repo_info = detect_git_repo_info(ws)
    total_tokens = input_tokens + cache_read_tokens + output_tokens
    ts = updated_at or now_iso()
    title = redact_secrets(title)
    git_remote = redact_secrets(repo_info["git_remote"])

    conn.execute(
        """
        INSERT INTO conversation_usage (
            conversation_id, client_source, workspace_path, repo_root, repo_name,
            git_remote, git_branch, model_name, title,
            turn_count, input_tokens, cache_read_tokens, output_tokens,
            total_tokens, plugin_calls, plugin_tokens_saved,
            transcript_path, transcript_mtime, started_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(conversation_id) DO UPDATE SET
            client_source = excluded.client_source,
            workspace_path = CASE WHEN excluded.workspace_path != 'global' THEN excluded.workspace_path ELSE conversation_usage.workspace_path END,
            repo_root = CASE WHEN excluded.repo_root != '' THEN excluded.repo_root ELSE conversation_usage.repo_root END,
            repo_name = CASE WHEN excluded.repo_name != 'unscoped / global' THEN excluded.repo_name ELSE conversation_usage.repo_name END,
            git_remote = CASE WHEN excluded.git_remote != '' THEN excluded.git_remote ELSE conversation_usage.git_remote END,
            git_branch = CASE WHEN excluded.git_branch != '' THEN excluded.git_branch ELSE conversation_usage.git_branch END,
            model_name = CASE WHEN excluded.model_name != 'auto' AND excluded.model_name != '' THEN excluded.model_name ELSE conversation_usage.model_name END,
            title = CASE WHEN excluded.title != '' THEN excluded.title ELSE conversation_usage.title END,
            turn_count = excluded.turn_count,
            input_tokens = excluded.input_tokens,
            cache_read_tokens = excluded.cache_read_tokens,
            output_tokens = excluded.output_tokens,
            total_tokens = excluded.total_tokens,
            plugin_calls = excluded.plugin_calls,
            plugin_tokens_saved = excluded.plugin_tokens_saved,
            transcript_path = excluded.transcript_path,
            transcript_mtime = excluded.transcript_mtime,
            started_at = CASE WHEN conversation_usage.started_at != '' THEN conversation_usage.started_at ELSE excluded.started_at END,
            updated_at = excluded.updated_at
        """,
        (
            conversation_id,
            client_source,
            ws,
            repo_info["repo_root"],
            repo_info["repo_name"],
            git_remote,
            repo_info["git_branch"],
            model_name or "auto",
            title,
            turn_count,
            input_tokens,
            cache_read_tokens,
            output_tokens,
            total_tokens,
            plugin_calls,
            plugin_tokens_saved,
            transcript_path,
            st_mtime,
            started_at or ts,
            ts,
        ),
    )
    return {
        "conversation_id": conversation_id,
        "client_source": client_source,
        "workspace_path": ws,
        "repo_name": repo_info["repo_name"],
        "turn_count": turn_count,
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "plugin_calls": plugin_calls,
        "plugin_tokens_saved": plugin_tokens_saved,
    }


def sync_transcript_usage(
    transcript_path: str,
    conversation_id: str = "",
    workspace_path: str = "",
    model_name: str = "",
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[Dict[str, Any]]:
    """
    Universal transcript parser supporting:
      1. Google Antigravity (`transcript.jsonl`)
      2. Claude Code (`~/.claude/projects/*/*.jsonl`)
      3. OpenAI Codex CLI (`~/.codex/sessions/**/*.jsonl`)
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return None

    try:
        st_mtime = os.path.getmtime(transcript_path)
    except OSError:
        return None

    norm_tpath = os.path.normpath(transcript_path)
    parts = norm_tpath.split(os.sep)

    client_source = "antigravity"
    if ".claude" in parts:
        client_source = "claude-code"
    elif ".codex" in parts:
        client_source = "codex-cli"

    if not conversation_id:
        if "brain" in parts:
            idx = parts.index("brain")
            if idx + 1 < len(parts):
                conversation_id = parts[idx + 1]
        if not conversation_id:
            base = os.path.splitext(os.path.basename(transcript_path))[0]
            if base and base != "transcript":
                conversation_id = base
            else:
                conversation_id = hashlib.sha256(transcript_path.encode("utf-8")).hexdigest()[:16]

    own_conn = False
    if conn is None:
        conn = get_connection()
        own_conn = True

    try:
        existing = conn.execute(
            "SELECT transcript_mtime, workspace_path, model_name FROM conversation_usage WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()

        if (
            existing
            and existing["transcript_mtime"]
            and abs(st_mtime - existing["transcript_mtime"]) < 0.001
            and (not workspace_path or workspace_path == "global" or existing["workspace_path"] != "global")
        ):
            return None

        input_tokens = 0
        cache_read_tokens = 0
        output_tokens = 0
        turn_count = 0
        plugin_calls = 0
        title = ""
        started_at = ""
        last_step_at = ""
        inferred_paths: List[str] = []

        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    step = json.loads(line)
                except json.JSONDecodeError:
                    continue

                stype = step.get("type", "")
                if stype in ("USER_INPUT", "PLANNER_RESPONSE", "GENERIC"):
                    created_at = step.get("created_at", "")
                    if created_at:
                        if not started_at:
                            started_at = created_at
                        last_step_at = created_at

                    content = step.get("content", "")
                    if stype == "USER_INPUT" and content:
                        if not title:
                            title = _extract_user_request_title(content)
                        if "[Context Graph & Query Cache]" in content or "/context-graph" in content:
                            plugin_calls += 1

                    if not model_name and "USER_SETTINGS_CHANGE" in content:
                        m_mod = re.search(r"Model Selection` from .*? to ([^\.\n]+)", content)
                        if m_mod:
                            model_name = m_mod.group(1).strip()

                    if stype == "PLANNER_RESPONSE":
                        in_tok = int(step.get("input_tokens") or 0)
                        cr_tok = int(step.get("cache_read_tokens") or 0)
                        out_tok = int(step.get("output_tokens") or 0)
                        if in_tok or cr_tok or out_tok:
                            input_tokens += in_tok
                            cache_read_tokens += cr_tok
                            output_tokens += out_tok
                            turn_count += 1

                        for tc in step.get("tool_calls") or []:
                            tname = str(tc.get("name") or "")
                            targs = tc.get("args") or {}
                            srv_name = _unquote_arg(str(targs.get("ServerName") or ""))
                            mcp_tool = _unquote_arg(str(targs.get("ToolName") or ""))
                            if (
                                "context-graph" in srv_name
                                or "context-graph" in tname
                                or mcp_tool.startswith("cache_")
                                or tname.startswith("cache_")
                            ):
                                plugin_calls += 1

                            for key in ("TargetFile", "AbsolutePath", "SearchPath", "Cwd", "workspace_path"):
                                val = _unquote_arg(targs.get(key, ""))
                                if (
                                    val
                                    and val.startswith("/")
                                    and "/.gemini/antigravity/" not in val
                                    and "/.gemini/config/" not in val
                                    and not val.startswith("/tmp")
                                ):
                                    inferred_paths.append(val)
                    continue

                if "message" in step and isinstance(step["message"], dict):
                    client_source = "claude-code"
                    ts_val = step.get("timestamp", "")
                    if ts_val:
                        if not started_at:
                            started_at = ts_val
                        last_step_at = ts_val

                    if step.get("cwd") and step["cwd"].startswith("/"):
                        inferred_paths.append(step["cwd"])

                    msg = step["message"]
                    role = msg.get("role") or step.get("type")
                    if role == "user" and not title:
                        msg_content = msg.get("content")
                        if isinstance(msg_content, str):
                            title = msg_content.strip().splitlines()[0][:100]
                        elif isinstance(msg_content, list):
                            for part in msg_content:
                                if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                                    title = part["text"].strip().splitlines()[0][:100]
                                    break

                    if role == "assistant":
                        if msg.get("model") and not model_name:
                            model_name = str(msg["model"])
                        msg_content = msg.get("content")
                        if isinstance(msg_content, list):
                            for part in msg_content:
                                if isinstance(part, dict) and part.get("type") == "tool_use":
                                    pname = str(part.get("name") or "")
                                    if "context-graph" in pname or pname.startswith("cache_"):
                                        plugin_calls += 1
                        usage = msg.get("usage") or {}
                        in_tok = int(usage.get("input_tokens") or 0) + int(
                            usage.get("cache_creation_input_tokens") or 0
                        )
                        cr_tok = int(usage.get("cache_read_input_tokens") or 0)
                        out_tok = int(usage.get("output_tokens") or 0)
                        if in_tok or cr_tok or out_tok:
                            input_tokens += in_tok
                            cache_read_tokens += cr_tok
                            output_tokens += out_tok
                            turn_count += 1
                    continue

                if stype in ("event_msg", "turn_context", "session_meta"):
                    client_source = "codex-cli"
                    ts_val = step.get("timestamp", "")
                    if ts_val:
                        if not started_at:
                            started_at = ts_val
                        last_step_at = ts_val
                    pl = step.get("payload") or {}
                    if isinstance(pl, dict):
                        if pl.get("cwd"):
                            inferred_paths.append(pl["cwd"])
                        if pl.get("model") and not model_name:
                            model_name = str(pl["model"])
                        if pl.get("type") == "token_count":
                            info = pl.get("info") or {}
                            last_u = info.get("last_token_usage") or {}
                            in_tok = int(last_u.get("input_tokens") or 0)
                            cr_tok = int(last_u.get("cached_input_tokens") or 0)
                            out_tok = int(last_u.get("output_tokens") or 0)
                            if in_tok or cr_tok or out_tok:
                                input_tokens += in_tok
                                cache_read_tokens += cr_tok
                                output_tokens += out_tok
                                turn_count += 1

        ws = normalize_workspace(workspace_path)
        if ws == "global" and existing and existing["workspace_path"] != "global":
            ws = existing["workspace_path"]

        if ws == "global" and inferred_paths:
            for p in reversed(inferred_paths):
                info = detect_git_repo_info(p)
                if info["repo_root"] and os.path.exists(os.path.join(info["repo_root"], ".git")):
                    ws = info["repo_root"]
                    break
            if ws == "global":
                first_p = inferred_paths[-1]
                ws = first_p if os.path.isdir(first_p) else os.path.dirname(first_p)

        # Only compute plugin_tokens_saved when the context-graph plugin was actually invoked
        plugin_tokens_saved = 0
        if plugin_calls > 0:
            ws_bytes_row = conn.execute(
                "SELECT COALESCE(SUM(size_bytes), 0) AS total_bytes FROM files WHERE workspace_path = ?",
                (ws,),
            ).fetchone()
            ws_bytes = int(ws_bytes_row["total_bytes"] or 0) if ws_bytes_row else 0
            # 1 token ~= 4 bytes of source code avoided per plugin lookup across turns
            avg_avoided_per_call = max(3500, min(25000, int(ws_bytes / 4)))
            plugin_tokens_saved = plugin_calls * avg_avoided_per_call * max(1, min(turn_count, 8))

        final_model = model_name or (existing["model_name"] if existing else "auto") or "auto"
        res = _upsert_conversation_usage(
            conn=conn,
            conversation_id=conversation_id,
            client_source=client_source,
            ws=ws,
            model_name=final_model,
            title=title,
            turn_count=turn_count,
            input_tokens=input_tokens,
            cache_read_tokens=cache_read_tokens,
            output_tokens=output_tokens,
            plugin_calls=plugin_calls,
            plugin_tokens_saved=plugin_tokens_saved,
            transcript_path=transcript_path,
            st_mtime=st_mtime,
            started_at=started_at,
            updated_at=last_step_at,
        )
        if own_conn:
            conn.commit()
        return res
    finally:
        if own_conn:
            conn.close()


def scan_all_llm_transcripts(conn: sqlite3.Connection) -> int:
    """
    Scans transcript logs across Antigravity, Claude Code, and Codex CLI,
    syncing token usage and Git repository links into SQLite.
    """
    synced = 0

    if os.path.isdir(ANTIGRAVITY_BRAIN_DIR):
        pattern = os.path.join(
            ANTIGRAVITY_BRAIN_DIR, "*", ".system_generated", "logs", "transcript.jsonl"
        )
        for tpath in glob.glob(pattern):
            if sync_transcript_usage(tpath, conn=conn):
                synced += 1

    if os.path.isdir(CLAUDE_PROJECTS_DIR):
        pattern = os.path.join(CLAUDE_PROJECTS_DIR, "*", "*.jsonl")
        for tpath in glob.glob(pattern):
            if sync_transcript_usage(tpath, conn=conn):
                synced += 1

    if os.path.isdir(CODEX_SESSIONS_DIR):
        pattern = os.path.join(CODEX_SESSIONS_DIR, "**", "*.jsonl")
        for tpath in glob.glob(pattern, recursive=True):
            if sync_transcript_usage(tpath, conn=conn):
                synced += 1

    conn.commit()
    return synced


DEFAULT_GIT_BRANCHES = {
    "",
    "-",
    "main",
    "master",
    "develop",
    "dev",
    "staging",
    "production",
    "head",
}


def estimate_token_cost(
    model_name: str,
    input_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    plugin_tokens_saved: int = 0,
) -> Dict[str, float]:
    """
    Estimates LLM API cost in USD and context-graph plugin savings based on model family rates (per 1M tokens).
    Note: `estimated_cache_savings_usd` (Plugin Savings USD) is strictly $0.00 when `plugin_tokens_saved == 0`
    (i.e. when the conversation did not use the `context-graph` plugin).
    """
    m = (model_name or "auto").lower()
    if "flash" in m:
        in_rate, cache_rate, out_rate = 0.15, 0.0375, 0.60
    elif "opus" in m:
        in_rate, cache_rate, out_rate = 15.00, 1.50, 75.00
    elif "sonnet" in m or "claude" in m:
        in_rate, cache_rate, out_rate = 3.00, 0.30, 15.00
    elif any(k in m for k in ("codex", "gpt", "o1", "o3", "o4")):
        in_rate, cache_rate, out_rate = 2.50, 1.25, 10.00
    else:
        # Gemini Pro / Gemini 3 / Gemini 4 Argon / default
        in_rate, cache_rate, out_rate = 1.25, 0.3125, 5.00

    in_cost = (max(0, input_tokens) / 1_000_000.0) * in_rate
    cache_cost = (max(0, cache_read_tokens) / 1_000_000.0) * cache_rate
    out_cost = (max(0, output_tokens) / 1_000_000.0) * out_rate
    actual_cost = in_cost + cache_cost + out_cost

    # Plugin savings: strictly 0 when plugin_tokens_saved == 0
    plugin_saved_cost = (max(0, plugin_tokens_saved) / 1_000_000.0) * in_rate
    without_plugin_cost = actual_cost + plugin_saved_cost

    return {
        "input_cost_usd": round(in_cost, 4),
        "cache_read_cost_usd": round(cache_cost, 4),
        "output_cost_usd": round(out_cost, 4),
        "estimated_cost_usd": round(actual_cost, 2),
        "uncached_cost_usd": round(without_plugin_cost, 2),
        "estimated_cache_savings_usd": round(plugin_saved_cost, 2),
    }


def derive_feature_info(repo_name: str, git_branch: str, title: str) -> Dict[str, str]:
    """
    Infers the feature name, normalized feature key, and optional ticket ID from a conversation's
    Git branch (preferred) or prompt title (fallback when on main/master/unscoped).
    """
    branch = (git_branch or "").strip()
    repo = (repo_name or "unscoped / global").strip()
    clean_title = redact_secrets((title or "").strip())

    if branch.lower() not in DEFAULT_GIT_BRANCHES:
        m = re.match(r"^(\d+)[-_](.+)$", branch)
        if m:
            ticket = f"#{m.group(1)}"
            slug = m.group(2).strip()
            return {
                "feature_key": f"branch::{slug.lower()}",
                "feature_name": slug,
                "ticket_id": ticket,
                "feature_source": "git_branch",
            }
        if "/" in branch:
            prefix, slug = branch.split("/", 1)
            slug_clean = slug.strip() or branch
            m2 = re.match(r"^(\d+)[-_](.+)$", slug_clean)
            if m2:
                return {
                    "feature_key": f"branch::{m2.group(2).lower()}",
                    "feature_name": m2.group(2),
                    "ticket_id": f"#{m2.group(1)}",
                    "feature_source": "git_branch",
                }
            return {
                "feature_key": f"branch::{slug_clean.lower()}",
                "feature_name": f"{slug_clean} ({prefix})",
                "ticket_id": "",
                "feature_source": "git_branch",
            }
        return {
            "feature_key": f"branch::{branch.lower()}",
            "feature_name": branch,
            "ticket_id": "",
            "feature_source": "git_branch",
        }

    if clean_title and clean_title != "(Untitled conversation)":
        short_task = re.sub(r"\s+", " ", clean_title)[:60].strip()
        return {
            "feature_key": f"task::{repo.lower()}::{short_task[:40].lower()}",
            "feature_name": short_task,
            "ticket_id": "",
            "feature_source": "prompt_task",
        }

    return {
        "feature_key": f"repo::{repo.lower()}::main",
        "feature_name": f"{repo} (main)",
        "ticket_id": "",
        "feature_source": "default_branch",
    }


def get_token_usage_report(
    workspace_path: Optional[str] = None,
    conversation_id: Optional[str] = None,
    client_source: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Returns token usage, actual LLM cost, and context-graph plugin savings per feature,
    per conversation, per LLM client, and aggregated by project / Git repository.
    """
    conn = get_connection()
    try:
        scan_all_llm_transcripts(conn)

        params: List[Any] = []
        where_clauses: List[str] = []

        if conversation_id:
            where_clauses.append("conversation_id = ?")
            params.append(conversation_id.strip())

        if client_source and client_source.lower() not in ("all", "*"):
            where_clauses.append("client_source = ?")
            params.append(client_source.strip().lower())

        ws = normalize_workspace(workspace_path)
        if ws != "global":
            repo_info = detect_git_repo_info(ws)
            target_root = repo_info["repo_root"] or ws
            where_clauses.append("(workspace_path = ? OR repo_root = ?)")
            params.extend([ws, target_root])

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        all_conv_rows = conn.execute(
            f"""
            SELECT * FROM conversation_usage
            {where_sql}
            ORDER BY updated_at DESC
            """,
            tuple(params),
        ).fetchall()

        conv_rows = all_conv_rows[:limit]

        repo_rows = conn.execute(
            f"""
            SELECT
                CASE WHEN repo_root != '' THEN repo_root ELSE workspace_path END AS project_root,
                repo_name,
                git_remote,
                git_branch,
                COUNT(*) AS conversation_count,
                SUM(turn_count) AS total_turns,
                SUM(input_tokens) AS input_tokens,
                SUM(cache_read_tokens) AS cache_read_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(plugin_calls) AS plugin_calls,
                SUM(plugin_tokens_saved) AS plugin_tokens_saved,
                MAX(updated_at) AS last_active_at
            FROM conversation_usage
            {where_sql}
            GROUP BY project_root
            ORDER BY total_tokens DESC
            """,
            tuple(params),
        ).fetchall()

        client_rows = conn.execute(
            f"""
            SELECT
                client_source,
                COUNT(*) AS conversation_count,
                SUM(turn_count) AS total_turns,
                SUM(input_tokens) AS input_tokens,
                SUM(cache_read_tokens) AS cache_read_tokens,
                SUM(output_tokens) AS output_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(plugin_calls) AS plugin_calls,
                SUM(plugin_tokens_saved) AS plugin_tokens_saved
            FROM conversation_usage
            {where_sql}
            GROUP BY client_source
            ORDER BY total_tokens DESC
            """,
            tuple(params),
        ).fetchall()

        feature_map: Dict[str, Dict[str, Any]] = {}
        repo_cost_map: Dict[str, Dict[str, float]] = {}
        client_cost_map: Dict[str, Dict[str, float]] = {}
        grand_cost = 0.0
        grand_uncached_cost = 0.0
        grand_savings = 0.0
        grand_in_cost = 0.0
        grand_cache_cost = 0.0
        grand_out_cost = 0.0
        grand_plugin_calls = 0
        grand_plugin_tokens_saved = 0

        for c in all_conv_rows:
            in_t = int(c["input_tokens"] or 0)
            cr_t = int(c["cache_read_tokens"] or 0)
            out_t = int(c["output_tokens"] or 0)
            tot_t = int(c["total_tokens"] or 0)
            turns = int(c["turn_count"] or 0)
            p_calls = int(c["plugin_calls"] or 0) if "plugin_calls" in c.keys() else 0
            p_saved_tok = int(c["plugin_tokens_saved"] or 0) if "plugin_tokens_saved" in c.keys() else 0
            model = c["model_name"] or "auto"
            c_src = c["client_source"] or "antigravity"
            proj_root = c["repo_root"] or c["workspace_path"]
            r_name = c["repo_name"] or "unscoped / global"
            g_branch = c["git_branch"] or ""
            c_title = redact_secrets(c["title"] or "(Untitled conversation)")
            updated = c["updated_at"] or ""

            cost = estimate_token_cost(model, in_t, cr_t, out_t, plugin_tokens_saved=p_saved_tok)
            grand_in_cost += cost["input_cost_usd"]
            grand_cache_cost += cost["cache_read_cost_usd"]
            grand_out_cost += cost["output_cost_usd"]
            grand_cost += cost["input_cost_usd"] + cost["cache_read_cost_usd"] + cost["output_cost_usd"]
            grand_uncached_cost += cost["uncached_cost_usd"]
            grand_savings += cost["estimated_cache_savings_usd"]
            grand_plugin_calls += p_calls
            grand_plugin_tokens_saved += p_saved_tok

            rc = repo_cost_map.setdefault(proj_root, {"cost": 0.0, "uncached": 0.0, "savings": 0.0})
            rc["cost"] += cost["input_cost_usd"] + cost["cache_read_cost_usd"] + cost["output_cost_usd"]
            rc["uncached"] += cost["uncached_cost_usd"]
            rc["savings"] += cost["estimated_cache_savings_usd"]

            cc = client_cost_map.setdefault(c_src, {"cost": 0.0, "uncached": 0.0, "savings": 0.0})
            cc["cost"] += cost["input_cost_usd"] + cost["cache_read_cost_usd"] + cost["output_cost_usd"]
            cc["uncached"] += cost["uncached_cost_usd"]
            cc["savings"] += cost["estimated_cache_savings_usd"]

            f_info = derive_feature_info(r_name, g_branch, c_title)
            fkey = f_info["feature_key"]
            if fkey not in feature_map:
                feature_map[fkey] = {
                    "feature_key": fkey,
                    "feature_name": f_info["feature_name"],
                    "feature_source": f_info["feature_source"],
                    "tickets": [],
                    "repos": [],
                    "branches": [],
                    "conversation_count": 0,
                    "total_turns": 0,
                    "input_tokens": 0,
                    "cache_read_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "plugin_calls": 0,
                    "plugin_tokens_saved": 0,
                    "input_cost_usd": 0.0,
                    "cache_read_cost_usd": 0.0,
                    "output_cost_usd": 0.0,
                    "estimated_cost_usd": 0.0,
                    "uncached_cost_usd": 0.0,
                    "estimated_cache_savings_usd": 0.0,
                    "last_active_at": updated,
                }
            f_entry = feature_map[fkey]
            if f_info["ticket_id"] and f_info["ticket_id"] not in f_entry["tickets"]:
                f_entry["tickets"].append(f_info["ticket_id"])
            if r_name and r_name not in f_entry["repos"]:
                f_entry["repos"].append(r_name)
            if g_branch and g_branch not in f_entry["branches"]:
                f_entry["branches"].append(g_branch)
            f_entry["conversation_count"] += 1
            f_entry["total_turns"] += turns
            f_entry["input_tokens"] += in_t
            f_entry["cache_read_tokens"] += cr_t
            f_entry["output_tokens"] += out_t
            f_entry["total_tokens"] += tot_t
            f_entry["plugin_calls"] += p_calls
            f_entry["plugin_tokens_saved"] += p_saved_tok
            f_entry["input_cost_usd"] += cost["input_cost_usd"]
            f_entry["cache_read_cost_usd"] += cost["cache_read_cost_usd"]
            f_entry["output_cost_usd"] += cost["output_cost_usd"]
            f_entry["estimated_cost_usd"] += (
                cost["input_cost_usd"] + cost["cache_read_cost_usd"] + cost["output_cost_usd"]
            )
            f_entry["uncached_cost_usd"] += cost["uncached_cost_usd"]
            f_entry["estimated_cache_savings_usd"] += cost["estimated_cache_savings_usd"]
            if updated > (f_entry["last_active_at"] or ""):
                f_entry["last_active_at"] = updated

        by_feature = []
        for f_entry in feature_map.values():
            p_tot = f_entry["input_tokens"] + f_entry["cache_read_tokens"]
            f_entry["cache_hit_rate_pct"] = (
                round((f_entry["cache_read_tokens"] / p_tot) * 100, 1) if p_tot > 0 else 0.0
            )
            f_entry["plugin_used"] = f_entry["plugin_calls"] > 0
            f_entry["input_cost_usd"] = round(f_entry["input_cost_usd"], 2)
            f_entry["cache_read_cost_usd"] = round(f_entry["cache_read_cost_usd"], 2)
            f_entry["output_cost_usd"] = round(f_entry["output_cost_usd"], 2)
            f_entry["estimated_cost_usd"] = round(f_entry["estimated_cost_usd"], 2)
            f_entry["uncached_cost_usd"] = round(f_entry["uncached_cost_usd"], 2)
            f_entry["estimated_cache_savings_usd"] = round(f_entry["estimated_cache_savings_usd"], 2)
            f_entry["repo_name"] = ", ".join(f_entry["repos"]) if f_entry["repos"] else "unscoped / global"
            f_entry["git_branch"] = ", ".join(f_entry["branches"]) if f_entry["branches"] else "-"
            f_entry["ticket_id"] = ", ".join(f_entry["tickets"]) if f_entry["tickets"] else ""
            by_feature.append(f_entry)

        by_feature.sort(key=lambda x: (x["estimated_cost_usd"], x["total_tokens"]), reverse=True)

        by_project_repo = []
        grand_input = 0
        grand_cache = 0
        grand_output = 0
        grand_total = 0
        grand_convs = 0

        for r in repo_rows:
            in_t = int(r["input_tokens"] or 0)
            cr_t = int(r["cache_read_tokens"] or 0)
            out_t = int(r["output_tokens"] or 0)
            tot_t = int(r["total_tokens"] or 0)
            c_cnt = int(r["conversation_count"] or 0)
            p_calls = int(r["plugin_calls"] or 0)
            p_saved_tok = int(r["plugin_tokens_saved"] or 0)

            grand_input += in_t
            grand_cache += cr_t
            grand_output += out_t
            grand_total += tot_t
            grand_convs += c_cnt

            prompt_total = in_t + cr_t
            cache_hit_pct = round((cr_t / prompt_total) * 100, 1) if prompt_total > 0 else 0.0
            rc = repo_cost_map.get(r["project_root"], {"cost": 0.0, "uncached": 0.0, "savings": 0.0})

            by_project_repo.append(
                {
                    "project_root": r["project_root"],
                    "repo_name": r["repo_name"] or "unscoped / global",
                    "git_remote": redact_secrets(r["git_remote"] or ""),
                    "git_branch": r["git_branch"] or "",
                    "conversation_count": c_cnt,
                    "total_turns": int(r["total_turns"] or 0),
                    "input_tokens": in_t,
                    "cache_read_tokens": cr_t,
                    "output_tokens": out_t,
                    "total_tokens": tot_t,
                    "cache_hit_rate_pct": cache_hit_pct,
                    "plugin_used": p_calls > 0,
                    "plugin_calls": p_calls,
                    "plugin_tokens_saved": p_saved_tok,
                    "estimated_cost_usd": round(rc["cost"], 2),
                    "uncached_cost_usd": round(rc["uncached"], 2),
                    "estimated_cache_savings_usd": round(rc["savings"], 2),
                    "last_active_at": r["last_active_at"],
                }
            )

        by_client = []
        for cl in client_rows:
            in_t = int(cl["input_tokens"] or 0)
            cr_t = int(cl["cache_read_tokens"] or 0)
            out_t = int(cl["output_tokens"] or 0)
            tot_t = int(cl["total_tokens"] or 0)
            p_calls = int(cl["plugin_calls"] or 0)
            p_saved_tok = int(cl["plugin_tokens_saved"] or 0)
            prompt_total = in_t + cr_t
            cache_hit_pct = round((cr_t / prompt_total) * 100, 1) if prompt_total > 0 else 0.0
            c_src = cl["client_source"] or "antigravity"
            cc = client_cost_map.get(c_src, {"cost": 0.0, "uncached": 0.0, "savings": 0.0})
            by_client.append(
                {
                    "client_source": c_src,
                    "conversation_count": int(cl["conversation_count"] or 0),
                    "total_turns": int(cl["total_turns"] or 0),
                    "input_tokens": in_t,
                    "cache_read_tokens": cr_t,
                    "output_tokens": out_t,
                    "total_tokens": tot_t,
                    "cache_hit_rate_pct": cache_hit_pct,
                    "plugin_used": p_calls > 0,
                    "plugin_calls": p_calls,
                    "plugin_tokens_saved": p_saved_tok,
                    "estimated_cost_usd": round(cc["cost"], 2),
                    "uncached_cost_usd": round(cc["uncached"], 2),
                    "estimated_cache_savings_usd": round(cc["savings"], 2),
                }
            )

        conversations = []
        for c in conv_rows:
            in_t = int(c["input_tokens"] or 0)
            cr_t = int(c["cache_read_tokens"] or 0)
            out_t = int(c["output_tokens"] or 0)
            tot_t = int(c["total_tokens"] or 0)
            p_calls = int(c["plugin_calls"] or 0) if "plugin_calls" in c.keys() else 0
            p_saved_tok = int(c["plugin_tokens_saved"] or 0) if "plugin_tokens_saved" in c.keys() else 0
            prompt_total = in_t + cr_t
            cache_hit_pct = round((cr_t / prompt_total) * 100, 1) if prompt_total > 0 else 0.0
            c_title = redact_secrets(c["title"] or "(Untitled conversation)")
            r_name = c["repo_name"] or "unscoped / global"
            g_branch = c["git_branch"] or ""
            model = c["model_name"] or "auto"
            cost = estimate_token_cost(model, in_t, cr_t, out_t, plugin_tokens_saved=p_saved_tok)
            f_info = derive_feature_info(r_name, g_branch, c_title)

            conversations.append(
                {
                    "conversation_id": c["conversation_id"],
                    "client_source": c["client_source"] or "antigravity",
                    "title": c_title,
                    "feature_name": f_info["feature_name"],
                    "ticket_id": f_info["ticket_id"],
                    "project_root": c["repo_root"] or c["workspace_path"],
                    "repo_name": r_name,
                    "git_remote": redact_secrets(c["git_remote"] or ""),
                    "git_branch": g_branch,
                    "model_name": model,
                    "turn_count": int(c["turn_count"] or 0),
                    "input_tokens": in_t,
                    "cache_read_tokens": cr_t,
                    "output_tokens": out_t,
                    "total_tokens": tot_t,
                    "cache_hit_rate_pct": cache_hit_pct,
                    "plugin_used": p_calls > 0,
                    "plugin_calls": p_calls,
                    "plugin_tokens_saved": p_saved_tok,
                    "estimated_cost_usd": cost["estimated_cost_usd"],
                    "uncached_cost_usd": cost["uncached_cost_usd"],
                    "estimated_cache_savings_usd": cost["estimated_cache_savings_usd"],
                    "started_at": c["started_at"],
                    "updated_at": c["updated_at"],
                }
            )

        grand_prompt = grand_input + grand_cache
        grand_cache_pct = round((grand_cache / grand_prompt) * 100, 1) if grand_prompt > 0 else 0.0

        return {
            "filter_workspace": ws,
            "grand_totals": {
                "total_conversations": grand_convs,
                "total_features": len(by_feature),
                "input_tokens": grand_input,
                "cache_read_tokens": grand_cache,
                "output_tokens": grand_output,
                "total_tokens": grand_total,
                "cache_hit_rate_pct": grand_cache_pct,
                "plugin_calls": grand_plugin_calls,
                "plugin_tokens_saved": grand_plugin_tokens_saved,
                "input_cost_usd": round(grand_in_cost, 2),
                "cache_read_cost_usd": round(grand_cache_cost, 2),
                "output_cost_usd": round(grand_out_cost, 2),
                "estimated_cost_usd": round(grand_cost, 2),
                "uncached_cost_usd": round(grand_uncached_cost, 2),
                "estimated_cache_savings_usd": round(grand_savings, 2),
            },
            "by_feature": by_feature,
            "by_client": by_client,
            "by_project_repo": by_project_repo,
            "by_conversation": conversations,
        }
    finally:
        conn.close()


# --- Static Code & Relationship Analyzer (Zero LLM Tokens) ---


def _analyze_python_file(file_path: str, content: str) -> Tuple[str, List[Dict[str, Any]], List[str], List[str]]:
    symbols: List[Dict[str, Any]] = []
    exports: List[str] = []
    imports: List[str] = []
    summary = ""

    try:
        tree = ast.parse(content, filename=file_path)
        doc = ast.get_docstring(tree)
        if doc:
            summary = doc.strip().splitlines()[0][:200]

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                symbols.append(
                    {
                        "name": node.name,
                        "kind": "function",
                        "line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "signature": f"def {node.name}({', '.join(args)})",
                    }
                )
                if not node.name.startswith("_"):
                    exports.append(node.name)
            elif isinstance(node, ast.ClassDef):
                methods = [
                    n.name
                    for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                symbols.append(
                    {
                        "name": node.name,
                        "kind": "class",
                        "line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "methods": methods[:15],
                    }
                )
                if not node.name.startswith("_"):
                    exports.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    prefix = "." * (node.level or 0)
                    imports.append(f"{prefix}{node.module}")
    except SyntaxError:
        pass

    if not summary:
        summary = f"Python module defining {len(symbols)} top-level symbols ({', '.join(exports[:6])})."
    return summary, symbols, exports, imports


def _analyze_generic_file(file_path: str, content: str, ext: str) -> Tuple[str, List[Dict[str, Any]], List[str], List[str]]:
    symbols: List[Dict[str, Any]] = []
    exports: List[str] = []
    imports: List[str] = []
    lines = content.splitlines()

    header_comments = []
    for line in lines[:15]:
        s = line.strip()
        if s.startswith(("//", "#", "/*", "*")) and len(s) > 3:
            header_comments.append(s.lstrip("/*# ").rstrip("*/ "))
        elif header_comments:
            break
    summary = " ".join(header_comments)[:200] if header_comments else ""

    fn_pattern = re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|def|fn|func)\s+([A-Za-z_][A-Za-z0-9_]*)"
    )
    class_pattern = re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(?:class|struct|interface|type|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)"
    )
    const_fn_pattern = re.compile(
        r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*="
    )
    import_pattern = re.compile(
        r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|use\s+([A-Za-z0-9_:]+))"""
    )

    for idx, line in enumerate(lines, start=1):
        m_class = class_pattern.match(line)
        if m_class:
            name = m_class.group(1)
            symbols.append({"name": name, "kind": "type_or_class", "line": idx})
            if "export" in line or name[0].isupper():
                exports.append(name)
            continue

        m_fn = fn_pattern.match(line)
        if m_fn:
            name = m_fn.group(1)
            symbols.append({"name": name, "kind": "function", "line": idx})
            if "export" in line or name[0].isupper():
                exports.append(name)
            continue

        m_const = const_fn_pattern.match(line)
        if m_const:
            name = m_const.group(1)
            symbols.append({"name": name, "kind": "exported_symbol", "line": idx})
            exports.append(name)
            continue

        for m_imp in import_pattern.finditer(line):
            imp = m_imp.group(1) or m_imp.group(2) or m_imp.group(3)
            if imp:
                imports.append(imp)

    if not summary:
        summary = f"{ext.lstrip('.').upper()} file with {len(lines)} lines and {len(symbols)} extracted symbols ({', '.join(exports[:6])})."
    return summary, symbols[:40], exports[:30], imports[:30]


def _resolve_import_to_file(
    source_file: str, imp: str, workspace_path: str, all_files_set: set
) -> Optional[str]:
    src_dir = os.path.dirname(source_file)
    candidates = []

    if imp.startswith("."):
        rel_clean = imp.lstrip(".")
        dots = len(imp) - len(rel_clean)
        base_dir = src_dir
        for _ in range(max(0, dots - 1)):
            base_dir = os.path.dirname(base_dir)
        rel_path = rel_clean.replace(".", "/") if not ("/" in rel_clean) else rel_clean
        raw_target = os.path.normpath(os.path.join(base_dir, rel_path))
        candidates.append(raw_target)
    else:
        rel_path = imp.replace(".", "/")
        candidates.append(os.path.normpath(os.path.join(workspace_path, rel_path)))
        candidates.append(os.path.normpath(os.path.join(src_dir, rel_path)))

    for cand in candidates:
        if cand in all_files_set:
            return cand
        for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"):
            if (cand + ext) in all_files_set:
                return cand + ext
            idx_cand = os.path.join(cand, "index" + ext)
            if idx_cand in all_files_set:
                return idx_cand
            init_cand = os.path.join(cand, "__init__.py")
            if init_cand in all_files_set:
                return init_cand
    return None


def auto_index_workspace(
    workspace_path: str, max_files: int = 200, force: bool = False
) -> Dict[str, Any]:
    """
    Walks workspace_path, statically analyzes source files that are uncached or stale,
    extracts symbols and file-to-file import relationships, and stores them in SQLite.
    """
    ws = normalize_workspace(workspace_path)
    if not os.path.isdir(ws):
        return {"status": "error", "message": f"Directory not found: {ws}"}

    discovered_files: List[str] = []
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in CODE_EXTENSIONS:
                fpath = os.path.abspath(os.path.join(root, fname))
                discovered_files.append(fpath)
                if len(discovered_files) >= max_files:
                    break
        if len(discovered_files) >= max_files:
            break

    all_files_set = set(discovered_files)
    conn = get_connection()
    indexed_count = 0
    skipped_fresh = 0
    relationships_found = 0

    try:
        for fpath in discovered_files:
            existing = conn.execute(
                "SELECT * FROM files WHERE workspace_path = ? AND file_path = ?",
                (ws, fpath),
            ).fetchone()

            if existing and not force:
                st = check_file_staleness(existing)
                if not st["is_stale"]:
                    skipped_fresh += 1
                    continue

            try:
                if os.path.getsize(fpath) > 512 * 1024:
                    continue
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            ext = os.path.splitext(fpath)[1].lower()
            if ext == ".py":
                summary, symbols, exports, imports = _analyze_python_file(fpath, content)
            else:
                summary, symbols, exports, imports = _analyze_generic_file(
                    fpath, content, ext
                )

            if existing and existing["summary"] and not existing["summary"].startswith(("Python module defining", f"{ext.lstrip('.').upper()} file with")):
                summary = existing["summary"]

            deps = []
            for imp in imports:
                resolved = _resolve_import_to_file(fpath, imp, ws, all_files_set)
                if resolved and resolved != fpath:
                    deps.append(
                        {
                            "target_file": resolved,
                            "relation_type": "imports",
                            "description": f"Imports `{imp}`",
                        }
                    )
                    relationships_found += 1

            upsert_file(
                workspace_path=ws,
                file_path=fpath,
                summary=summary,
                symbols=symbols,
                exports=exports,
                tags=[ext.lstrip(".")],
                dependencies=deps,
            )
            indexed_count += 1

        return {
            "status": "ok",
            "workspace_path": ws,
            "discovered_files": len(discovered_files),
            "indexed_or_updated": indexed_count,
            "skipped_already_fresh": skipped_fresh,
            "relationships_mapped": relationships_found,
        }
    finally:
        conn.close()


def get_ground_truth_overrides(workspace_path: str) -> List[Dict[str, Any]]:
    """
    Returns all active ground-truth overrides for a workspace (including global overrides).
    """
    ws = normalize_workspace(workspace_path)
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM ground_truth_overrides
            WHERE (workspace_path = ? OR workspace_path = 'global') AND active = 1
            ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END, updated_at DESC
            """,
            (ws,),
        ).fetchall()
        return [
            {
                "override_key": r["override_key"],
                "hallucination_or_mistake": r["hallucination_or_mistake"],
                "verified_truth": r["verified_truth"],
                "scope_files": [
                    to_rel_path(f, ws) for f in json.loads(r["scope_files_json"] or "[]")
                ],
                "priority": r["priority"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def export_overrides_to_file(
    workspace_path: str, file_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Exports active ground-truth overrides for a workspace to `.context-graph/overrides.json`
    (or a custom file path) so team members can commit and share verified domain rules in Git.
    """
    ws = normalize_workspace(workspace_path)
    out_file = (
        os.path.abspath(os.path.expanduser(file_path))
        if file_path
        else os.path.join(ws, ".context-graph", "overrides.json")
    )
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    overrides = get_ground_truth_overrides(ws)
    payload = {
        "schema_version": "1.3.0",
        "exported_at": now_iso(),
        "overrides": [
            {
                "override_key": o["override_key"],
                "hallucination_or_mistake": o.get("hallucination_or_mistake", ""),
                "verified_truth": o["verified_truth"],
                "scope_files": o.get("scope_files", []),
                "priority": o.get("priority", "high"),
            }
            for o in overrides
        ],
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return {
        "status": "ok",
        "workspace_path": ws,
        "exported_count": len(payload["overrides"]),
        "file_path": out_file,
    }


def import_overrides_from_file(
    workspace_path: str, file_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Imports ground-truth overrides from `.context-graph/overrides.json` (or a custom file path)
    into the local SQLite database.
    """
    ws = normalize_workspace(workspace_path)
    in_file = (
        os.path.abspath(os.path.expanduser(file_path))
        if file_path
        else os.path.join(ws, ".context-graph", "overrides.json")
    )
    if not os.path.isfile(in_file):
        return {
            "status": "skipped",
            "workspace_path": ws,
            "imported_count": 0,
            "file_path": in_file,
        }
    with open(in_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("overrides", []) if isinstance(data, dict) else []
    imported = 0
    for item in items:
        if not isinstance(item, dict) or not item.get("override_key") or not item.get("verified_truth"):
            continue
        record_correction(
            workspace_path=ws,
            override_key=item["override_key"],
            verified_truth=item["verified_truth"],
            hallucination_or_mistake=item.get("hallucination_or_mistake", ""),
            scope_files=item.get("scope_files", []),
            priority=item.get("priority", "high"),
        )
        imported += 1
    return {
        "status": "ok",
        "workspace_path": ws,
        "imported_count": imported,
        "file_path": in_file,
    }


def install_git_hooks(workspace_path: str) -> Dict[str, Any]:
    """
    Installs lightweight `post-checkout` and `post-merge` Git hooks in the target repository
    so switching branches or pulling changes automatically refreshes stale files in the background.
    """
    ws = normalize_workspace(workspace_path)
    repo_info = detect_git_repo_info(ws)
    repo_root = repo_info["repo_root"] or ws
    hooks_dir = os.path.join(repo_root, ".git", "hooks")
    if not os.path.isdir(hooks_dir):
        return {
            "status": "error",
            "message": f"No .git/hooks directory found at {hooks_dir}",
        }
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ctl_script = os.path.join(plugin_root, "scripts", "context_ctl.py")
    marker = "# [context-graph-auto-refresh]"
    hook_cmd = (
        f"\n{marker}\n"
        f'python3 "{ctl_script}" refresh --workspace "{repo_root}" --mode stale_only >/dev/null 2>&1 &\n'
    )
    installed = []
    for hook_name in ("post-checkout", "post-merge"):
        hp = os.path.join(hooks_dir, hook_name)
        existing = ""
        if os.path.isfile(hp):
            with open(hp, "r", encoding="utf-8", errors="replace") as f:
                existing = f.read()
        if marker not in existing:
            prefix = existing if existing.startswith("#!") else "#!/usr/bin/env sh\n" + existing
            with open(hp, "w", encoding="utf-8") as f:
                f.write(prefix.rstrip() + "\n" + hook_cmd)
            os.chmod(hp, 0o755)
        installed.append(hp)
    return {
        "status": "ok",
        "repo_root": repo_root,
        "installed_hooks": installed,
    }

