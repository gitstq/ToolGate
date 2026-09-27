"""SQLite-backed storage layer.

A single database file holds credentials (ciphertext only), tool definitions,
token hashes and the audit trail.  Connections are opened with
``check_same_thread=False`` because the HTTP server is multi-threaded; every
public method takes a process-wide re-entrant lock to serialise writes.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from .errors import ConflictError, NotFoundError
from .models import Credential, GatewayToken, Tool, utcnow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS credentials (
    name        TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    ciphertext  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tools (
    name        TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    enabled     INTEGER NOT NULL DEFAULT 1,
    config      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    scope         TEXT NOT NULL,
    token_hash    TEXT NOT NULL UNIQUE,
    prefix        TEXT NOT NULL,
    rate_limit    INTEGER NOT NULL DEFAULT 0,
    enabled       INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    token_name   TEXT,
    tool         TEXT,
    op           TEXT NOT NULL,
    target       TEXT,
    status       INTEGER,
    duration_ms  INTEGER,
    bytes_in     INTEGER DEFAULT 0,
    bytes_out    INTEGER DEFAULT 0,
    ip           TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);
CREATE INDEX IF NOT EXISTS idx_tools_kind ON tools(kind);
"""


class Storage:
    """All persistence for one ToolGate instance."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---------------------------------------------------------- credentials
    def put_credential(self, name: str, ciphertext: str, description: str = "", *, create_only: bool = False) -> Credential:
        now = utcnow()
        with self._lock:
            existing = self._conn.execute(
                "SELECT name, created_at FROM credentials WHERE name=?", (name,)
            ).fetchone()
            if create_only and existing:
                raise ConflictError(f"Credential '{name}' already exists")
            if existing:
                self._conn.execute(
                    "UPDATE credentials SET description=?, ciphertext=?, updated_at=? WHERE name=?",
                    (description, ciphertext, now, name),
                )
                created = existing["created_at"]
            else:
                self._conn.execute(
                    "INSERT INTO credentials(name, description, ciphertext, created_at, updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (name, description, ciphertext, now, now),
                )
                created = now
        return Credential(name=name, description=description, created_at=created, updated_at=now)

    def get_ciphertext(self, name: str) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT ciphertext FROM credentials WHERE name=?", (name,)
            ).fetchone()
        if not row:
            raise NotFoundError(f"Credential '{name}' does not exist")
        return row["ciphertext"]

    def list_credentials(self) -> list[Credential]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, description, created_at, updated_at FROM credentials ORDER BY name"
            ).fetchall()
        return [
            Credential(
                name=r["name"], description=r["description"],
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def delete_credential(self, name: str) -> None:
        with self._lock:
            cur = self._conn.execute("DELETE FROM credentials WHERE name=?", (name,))
        if cur.rowcount == 0:
            raise NotFoundError(f"Credential '{name}' does not exist")

    # ------------------------------------------------------------------ tools
    def put_tool(self, tool: Tool, *, create_only: bool = False) -> Tool:
        row = tool.to_row()
        with self._lock:
            existing = self._conn.execute("SELECT name FROM tools WHERE name=?", (tool.name,)).fetchone()
            if create_only and existing:
                raise ConflictError(f"Tool '{tool.name}' already exists")
            if existing:
                self._conn.execute(
                    "UPDATE tools SET kind=?, description=?, tags=?, enabled=?, config=?, updated_at=? "
                    "WHERE name=?",
                    (row["kind"], row["description"], row["tags"], row["enabled"],
                     row["config"], row["updated_at"], row["name"]),
                )
            else:
                self._conn.execute(
                    "INSERT INTO tools(name, kind, description, tags, enabled, config, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (row["name"], row["kind"], row["description"], row["tags"], row["enabled"],
                     row["config"], row["created_at"], row["updated_at"]),
                )
        return tool

    def get_tool(self, name: str) -> Tool:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tools WHERE name=?", (name,)).fetchone()
        if not row:
            raise NotFoundError(f"Tool '{name}' does not exist")
        return Tool.from_row(dict(row))

    def list_tools(self, *, kind: str | None = None, include_disabled: bool = True) -> list[Tool]:
        sql = "SELECT * FROM tools"
        clauses, params = [], []
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        if not include_disabled:
            clauses.append("enabled=1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY name"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [Tool.from_row(dict(r)) for r in rows]

    def set_tool_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tools SET enabled=?, updated_at=? WHERE name=?",
                (1 if enabled else 0, utcnow(), name),
            )
        if cur.rowcount == 0:
            raise NotFoundError(f"Tool '{name}' does not exist")

    def delete_tool(self, name: str) -> None:
        with self._lock:
            cur = self._conn.execute("DELETE FROM tools WHERE name=?", (name,))
        if cur.rowcount == 0:
            raise NotFoundError(f"Tool '{name}' does not exist")

    # ----------------------------------------------------------------- tokens
    def create_token(self, token: GatewayToken) -> GatewayToken:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO tokens(name, scope, token_hash, prefix, rate_limit, enabled, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (token.name, token.scope, token.token_hash, token.prefix, token.rate_limit,
                 1 if token.enabled else 0, token.created_at),
            )
            token.id = cur.lastrowid
        return token

    def get_token_by_hash(self, token_hash: str) -> GatewayToken | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tokens WHERE token_hash=?", (token_hash,)).fetchone()
        return self._token_from_row(row) if row else None

    def list_tokens(self) -> list[GatewayToken]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM tokens ORDER BY id").fetchall()
        return [self._token_from_row(r) for r in rows]

    def set_token_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tokens SET enabled=? WHERE name=?", (1 if enabled else 0, name)
            )
        if cur.rowcount == 0:
            raise NotFoundError(f"Token '{name}' does not exist")

    def touch_token(self, token_hash: str, when: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE tokens SET last_used_at=? WHERE token_hash=?", (when, token_hash)
            )

    def delete_token(self, name: str) -> None:
        with self._lock:
            cur = self._conn.execute("DELETE FROM tokens WHERE name=?", (name,))
        if cur.rowcount == 0:
            raise NotFoundError(f"Token '{name}' does not exist")

    @staticmethod
    def _token_from_row(row: sqlite3.Row) -> GatewayToken:
        return GatewayToken(
            id=row["id"], name=row["name"], scope=row["scope"], token_hash=row["token_hash"],
            prefix=row["prefix"], rate_limit=row["rate_limit"], enabled=bool(row["enabled"]),
            created_at=row["created_at"], last_used_at=row["last_used_at"],
        )

    # ------------------------------------------------------------------ audit
    def record_audit(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit(ts, token_name, tool, op, target, status, duration_ms, "
                "bytes_in, bytes_out, ip) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    event.get("ts", utcnow()), event.get("token_name"), event.get("tool"),
                    event.get("op"), event.get("target"), event.get("status"),
                    event.get("duration_ms"), event.get("bytes_in", 0),
                    event.get("bytes_out", 0), event.get("ip"),
                ),
            )

    def list_audit(self, *, limit: int = 100, tool: str | None = None,
                   since_id: int | None = None) -> list[dict]:
        sql = "SELECT * FROM audit"
        clauses, params = [], []
        if tool:
            clauses.append("tool=?")
            params.append(tool)
        if since_id:
            clauses.append("id>?")
            params.append(since_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ stats
    def counts(self) -> dict[str, int]:
        with self._lock:
            out = {}
            for table in ("credentials", "tools", "tokens", "audit"):
                out[table] = self._conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
        return out
