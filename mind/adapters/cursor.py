"""Adapter for Cursor workspace SQLite storage."""

import json
import sqlite3
from pathlib import Path

from ..config import CURSOR_USER_DIR
from .base import AdapterInspectStats, SessionCardCandidate, SessionRef


def _workspace_storage_dir() -> Path:
    return CURSOR_USER_DIR / "workspaceStorage"


def _get_workspace_cwd(db_path: Path) -> str | None:
    """Extract the workspace folder path from a Cursor state.vscdb."""
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key='history.entries'"
        ).fetchone()
        conn.close()
        if not row:
            return None
        data = json.loads(row[0])
        entries = data.get("entries", [])
        if entries:
            # entries are like {"uri": "file:///Users/matheus/Projects/foo"}
            uri = entries[0].get("uri", "")
            if uri.startswith("file://"):
                return uri[7:]
    except Exception:
        pass
    return None


def _get_chat_sessions(db_path: Path) -> list[dict]:
    """Extract chat session index from a workspace db."""
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT value FROM ItemTable WHERE key='chat.ChatSessionStore.index'"
        ).fetchone()
        conn.close()
        if not row:
            return []
        data = json.loads(row[0])
        return list(data.get("entries", {}).values())
    except Exception:
        return []


def list_workspace_dbs() -> list[Path]:
    ws_dir = _workspace_storage_dir()
    if not ws_dir.exists():
        return []
    return list(ws_dir.rglob("state.vscdb"))


def find_workspace_db(cwd: str) -> Path | None:
    """Find the Cursor workspace db for a given cwd."""
    for db_path in list_workspace_dbs():
        workspace_cwd = _get_workspace_cwd(db_path)
        if workspace_cwd and (workspace_cwd == cwd or cwd.startswith(workspace_cwd)):
            return db_path
    return None


def extract_session_text(cwd: str, max_chars: int = 20_000) -> tuple[str, str]:
    """Return (text_excerpt, last_date_iso) for Cursor sessions in cwd."""
    db_path = find_workspace_db(cwd)
    if not db_path:
        return "", ""

    sessions = _get_chat_sessions(db_path)
    if not sessions:
        return "", ""

    # sort newest first
    sessions.sort(key=lambda s: s.get("lastMessageDate", 0), reverse=True)

    last_ts = sessions[0].get("lastMessageDate", 0)
    last_date = ""
    if last_ts:
        from datetime import datetime, timezone

        last_date = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )

    lines = []
    for s in sessions[:10]:
        title = s.get("title", "New Chat")
        if title and title != "New Chat":
            lines.append(f"[cursor-chat] {title}")

    return "\n".join(lines)[:max_chars], last_date


class CursorAdapter:
    """Cursor adapter backed by one workspace state database per project."""

    name = "cursor"

    def discover(self, cwd: str) -> list[SessionRef]:
        db_path = find_workspace_db(cwd)
        if not db_path:
            return []
        return [
            SessionRef(
                source=self.name,
                session_id=str(db_path),
                path=db_path,
                label="workspace state.vscdb",
            )
        ]

    def active_context(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        max_chars: int,
    ) -> list[str]:
        return []

    def card_candidates(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        session_limit: int,
    ) -> list[SessionCardCandidate]:
        text, date = extract_session_text(cwd)
        if not text.strip():
            return []
        return [
            SessionCardCandidate(
                card_id=f"cursor:{cwd}:{_text_hash(text)}",
                source=self.name,
                text=f"Cursor chat sessions:\n{text}",
                date=date,
                needs_summary=False,
            )
        ]

    def inspect_stats(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        session_limit: int,
    ) -> AdapterInspectStats:
        return AdapterInspectStats(source=self.name)


def _text_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]
