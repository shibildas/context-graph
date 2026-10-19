#!/usr/bin/env python3
"""
Core SQLite Knowledge Graph & Query Cache Engine for the Antigravity context-graph plugin.
Zero external dependencies (uses Python standard library sqlite3, ast, hashlib, json, re).
"""

import ast
import datetime
import hashlib
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_DB_DIR = os.path.expanduser("~/.gemini/context-graph")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DB_DIR, "cache.db")

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


def normalize_workspace(workspace_path: Optional[str]) -> str:
    if not workspace_path:
        return "global"
    cleaned = workspace_path.strip()
    if cleaned.startswith("file://"):
        cleaned = cleaned[len("file://") :]
    return os.path.abspath(os.path.expanduser(cleaned))


def normalize_file_path(file_path: str, workspace_path: Optional[str] = None) -> str:
    cleaned = file_path.strip()
    if cleaned.startswith("file://"):
        cleaned = cleaned[len("file://") :]
    expanded = os.path.expanduser(cleaned)
    if not os.path.isabs(expanded) and workspace_path and workspace_path != "global":
        expanded = os.path.join(normalize_workspace(workspace_path), expanded)
    return os.path.abspath(expanded)


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


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
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

        CREATE TABLE IF NOT EXISTS tool_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_path TEXT NOT NULL,
            conversation_id TEXT DEFAULT '',
            tool_name TEXT NOT NULL,
            target_file TEXT DEFAULT '',
            details TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_files_workspace ON files(workspace_path);
        CREATE INDEX IF NOT EXISTS idx_rel_workspace_src ON relationships(workspace_path, source_file);
        CREATE INDEX IF NOT EXISTS idx_rel_workspace_tgt ON relationships(workspace_path, target_file);
        CREATE INDEX IF NOT EXISTS idx_queries_workspace ON cached_queries(workspace_path);
        """
    )
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

        if not row:
            return {
                "cached": False,
                "file_path": fp,
                "rel_path": to_rel_path(fp, ws),
                "message": "File is not yet cached. Read or index it and call cache_upsert_file.",
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
                "FRESH: Do NOT re-read this file with view_file unless you need exact lines for editing."
                if not staleness["is_stale"]
                else "STALE: File was modified on disk since last cached. Re-read changed sections and update cache."
            ),
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

        return {
            "workspace_path": ws,
            "stats": {
                "total_cached_files": len(files_out),
                "fresh_files": fresh_count,
                "stale_files": stale_count,
                "total_relationships": len(rels_out),
                "total_cached_queries": len(queries_out),
            },
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
            "matched_files": matched_files,
            "matched_relationships": matched_rels,
            "matched_queries": matched_queries,
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
