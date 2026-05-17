"""SQLite store for session cards and project digests."""

import json
import sqlite3
from datetime import datetime
from uuid import uuid4

from .config import MIND_DIR


def _connect() -> sqlite3.Connection:
    db_path = MIND_DIR / "mind.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_cards (
            id TEXT PRIMARY KEY,
            project_cwd TEXT NOT NULL,
            source TEXT NOT NULL,
            session_file TEXT,
            file_hash TEXT,
            card_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            session_date TEXT
        );

        CREATE TABLE IF NOT EXISTS project_digests (
            cwd TEXT PRIMARY KEY,
            digest_text TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            card_ids TEXT NOT NULL,
            synced_commit TEXT
        );

        CREATE TABLE IF NOT EXISTS project_notes (
            id TEXT PRIMARY KEY,
            project_cwd TEXT NOT NULL,
            note_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cards_cwd ON session_cards(project_cwd);
        CREATE INDEX IF NOT EXISTS idx_notes_cwd ON project_notes(project_cwd);
    """)
    # safe column migration for existing DBs
    cols = {r[1] for r in conn.execute("PRAGMA table_info(project_digests)")}
    if "synced_commit" not in cols:
        conn.execute("ALTER TABLE project_digests ADD COLUMN synced_commit TEXT")

    note_cols = {r[1] for r in conn.execute("PRAGMA table_info(project_notes)")}
    if note_cols and "note_text" not in note_cols:
        existing = conn.execute("SELECT * FROM project_notes").fetchall()
        conn.execute("ALTER TABLE project_notes RENAME TO project_notes_legacy")
        conn.execute(
            """
            CREATE TABLE project_notes (
                id TEXT PRIMARY KEY,
                project_cwd TEXT NOT NULL,
                note_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notes_cwd ON project_notes(project_cwd)"
        )
        for row in existing:
            note_text = str(row["notes"] or "").strip()
            if not note_text:
                continue
            created_at = str(row["updated_at"] or datetime.utcnow().isoformat())
            conn.execute(
                """
                INSERT OR REPLACE INTO project_notes (id, project_cwd, note_text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (f"legacy:{row['cwd']}", row["cwd"], note_text, created_at),
            )
        conn.execute("DROP TABLE project_notes_legacy")
    conn.commit()


def upsert_session_card(
    card_id: str,
    project_cwd: str,
    source: str,
    card_text: str,
    session_file: str | None = None,
    file_hash: str | None = None,
    session_date: str | None = None,
):
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO session_cards
              (id, project_cwd, source, session_file, file_hash, card_text, created_at, session_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                project_cwd,
                source,
                session_file,
                file_hash,
                card_text,
                datetime.utcnow().isoformat(),
                session_date,
            ),
        )


def get_session_card(card_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM session_cards WHERE id = ?", (card_id,)
        ).fetchone()


def get_project_cards(cwd: str) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM session_cards WHERE project_cwd = ? ORDER BY session_date DESC",
            (cwd,),
        ).fetchall()


def upsert_digest(
    cwd: str, digest_text: str, card_ids: list[str], synced_commit: str | None = None
):
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO project_digests (cwd, digest_text, generated_at, card_ids, synced_commit)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                cwd,
                digest_text,
                datetime.utcnow().isoformat(),
                json.dumps(card_ids),
                synced_commit,
            ),
        )


def get_digest(cwd: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM project_digests WHERE cwd = ?", (cwd,)
        ).fetchone()


def upsert_note(cwd: str, note_text: str):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO project_notes (id, project_cwd, note_text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                cwd,
                note_text,
                datetime.utcnow().isoformat(),
            ),
        )


def list_notes(cwd: str) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM project_notes WHERE project_cwd = ? ORDER BY created_at DESC",
            (cwd,),
        ).fetchall()


def get_notes(cwd: str) -> list[sqlite3.Row]:
    return list_notes(cwd)


def upsert_notes(cwd: str, notes: str) -> None:
    """Backward-compatible helper that stores a single note entry."""
    upsert_note(cwd, notes)


def delete_notes(cwd: str, note_ids: list[str]) -> int:
    if not note_ids:
        return 0
    with _connect() as conn:
        cur = conn.execute(
            f"DELETE FROM project_notes WHERE project_cwd = ? AND id IN ({','.join('?' for _ in note_ids)})",
            (cwd, *note_ids),
        )
        return cur.rowcount


def delete_all_notes(cwd: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM project_notes WHERE project_cwd = ?",
            (cwd,),
        )
        return cur.rowcount


def format_notes_for_context(cwd: str) -> str:
    notes = list_notes(cwd)
    if not notes:
        return ""
    return "\n".join(
        f"[{row['created_at']}] {row['note_text']}" for row in reversed(notes)
    )


def list_projects() -> list[dict]:
    """Return all known projects with digest metadata."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT
                d.cwd,
                d.generated_at,
                COUNT(c.id) AS card_count,
                MAX(c.session_date) AS last_session
            FROM project_digests d
            LEFT JOIN session_cards c ON c.project_cwd = d.cwd
            GROUP BY d.cwd
            ORDER BY d.generated_at DESC
        """).fetchall()

        # also include projects with cards but no digest
        card_only = conn.execute("""
            SELECT project_cwd AS cwd, NULL AS generated_at,
                   COUNT(*) AS card_count, MAX(session_date) AS last_session
            FROM session_cards
            WHERE project_cwd NOT IN (SELECT cwd FROM project_digests)
            GROUP BY project_cwd
            ORDER BY last_session DESC
        """).fetchall()

        result = [dict(r) for r in rows] + [dict(r) for r in card_only]
        return result
