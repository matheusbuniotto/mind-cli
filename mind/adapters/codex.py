"""Adapter for Codex session JSONL files (~/.codex/sessions/)."""

import hashlib
import json
import time
from pathlib import Path

from ..config import CODEX_SESSIONS_DIR
from .base import AdapterInspectStats, SessionCardCandidate, SessionRef


def get_session_files() -> list[Path]:
    """Return all Codex session JSONL files sorted newest-first."""
    if not CODEX_SESSIONS_DIR.exists():
        return []
    return sorted(
        CODEX_SESSIONS_DIR.rglob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(str(path.stat().st_size).encode())
    h.update(str(path.stat().st_mtime).encode())
    return h.hexdigest()[:16]


def extract_session_text(
    session_file: Path, max_chars: int = 40_000
) -> tuple[str, str, str | None]:
    """Extract cwd, messages from a Codex session JSONL.

    Returns (text_excerpt, session_date_iso, cwd_or_none).
    """
    messages = []
    session_date = ""
    cwd = None

    try:
        lines = session_file.read_text(errors="ignore").splitlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")
            payload = event.get("payload", {})
            ts = event.get("timestamp", "")
            if ts and not session_date:
                session_date = ts[:10]

            if etype == "session_meta":
                cwd = payload.get("cwd")

            elif etype == "turn_context":
                if not cwd:
                    cwd = payload.get("cwd")

            elif etype == "response_item":
                role = payload.get("role", "")
                content = payload.get("content", [])
                if role == "user" and isinstance(content, list):
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "input_text"
                        ):
                            text = block.get("text", "").strip()
                            if text and not text.startswith("<"):
                                messages.append(f"[user] {text[:500]}")
                elif role == "assistant" and isinstance(content, list):
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "output_text"
                        ):
                            text = block.get("text", "").strip()
                            if text:
                                messages.append(f"[assistant] {text[:300]}")
    except Exception:
        pass

    text = "\n".join(messages)
    return text[:max_chars], session_date, cwd


def sessions_for_cwd(cwd: str) -> list[Path]:
    """Return Codex sessions that ran inside cwd (or its subdirs)."""
    result = []
    for f in get_session_files():
        _, _, session_cwd = extract_session_text(f, max_chars=0)
        if session_cwd and (session_cwd == cwd or session_cwd.startswith(cwd + "/")):
            result.append(f)
    return result


class CodexAdapter:
    """Codex session adapter for cwd-matched JSONL transcripts."""

    name = "codex"

    def discover(self, cwd: str) -> list[SessionRef]:
        sessions: list[SessionRef] = []
        for rank, session_file in enumerate(get_session_files()[:50]):
            _, date, session_cwd = extract_session_text(session_file, max_chars=0)
            if not session_cwd:
                continue
            if session_cwd != cwd and not session_cwd.startswith(cwd + "/"):
                continue
            sessions.append(
                SessionRef(
                    source=self.name,
                    session_id=session_file.stem,
                    path=session_file,
                    date=date,
                    active=_is_active(session_file),
                    cwd=session_cwd,
                    metadata={"rank": rank},
                )
            )
        return sessions

    def active_context(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        max_chars: int,
    ) -> list[str]:
        parts = []
        for session in sessions:
            if not session.active or session.path is None:
                continue
            rank = int(session.metadata.get("rank", 999))
            if rank >= 20:
                continue
            text, date, _ = extract_session_text(session.path, max_chars=max_chars)
            if text.strip():
                parts.append(f"[ACTIVE codex session | {date}]\n{text}")
        return parts

    def card_candidates(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        session_limit: int,
    ) -> list[SessionCardCandidate]:
        candidates: list[SessionCardCandidate] = []
        for session in _closed_sessions(sessions)[:session_limit]:
            assert session.path is not None
            text, date, _ = extract_session_text(session.path)
            if not text.strip():
                continue
            fhash = file_hash(session.path)
            candidates.append(
                SessionCardCandidate(
                    card_id=f"codex:{session.path.stem}:{fhash}",
                    source=self.name,
                    text=text,
                    date=date,
                    session_file=str(session.path),
                    file_hash=fhash,
                )
            )
        return candidates

    def inspect_stats(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        session_limit: int,
    ) -> AdapterInspectStats:
        return AdapterInspectStats(
            source=self.name,
            api_window_count=len(_closed_sessions(sessions)[:session_limit]),
        )


def _is_active(path: Path) -> bool:
    return (time.time() - path.stat().st_mtime) < 30 * 60


def _closed_sessions(sessions: list[SessionRef]) -> list[SessionRef]:
    return [s for s in sessions if not s.active and s.path is not None]
