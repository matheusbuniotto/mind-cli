"""Adapter for Claude Code session JSONL files (~/.claude/projects/)."""

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

from ..config import CLAUDE_PROJECTS_DIR
from .base import AdapterInspectStats, SessionCardCandidate, SessionRef


def _decode_project_dir(name: str) -> str:
    """Convert '-Users-matheus-Awesome-tools-gifted-neuro' → '/Users/matheus/...'"""
    return name.replace("-", "/")


def find_project_dir(cwd: str) -> Path | None:
    """Return the exact Claude Code project dir for cwd, or None."""
    if not CLAUDE_PROJECTS_DIR.exists():
        return None
    encoded = cwd.replace("/", "-")
    candidate = CLAUDE_PROJECTS_DIR / encoded
    return candidate if candidate.exists() else None


def find_project_dirs(cwd: str) -> list[Path]:
    """Return all Claude Code project dirs that are at cwd or nested inside it.

    Claude Code creates one dir per working directory, so a session started in
    /project/src appears under -project-src, not -project. This collects both
    the exact match and any subdirectory sessions so they all roll up into one
    project digest.
    """
    if not CLAUDE_PROJECTS_DIR.exists():
        return []
    encoded_prefix = cwd.replace("/", "-")
    dirs = []
    for d in CLAUDE_PROJECTS_DIR.iterdir():
        if not d.is_dir():
            continue
        # exact match OR subdir: -project-src starts with -project-
        if d.name == encoded_prefix or d.name.startswith(encoded_prefix + "-"):
            dirs.append(d)
    return dirs


def get_session_files(project_dir: Path) -> list[Path]:
    return sorted(
        project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(str(path.stat().st_size).encode())
    h.update(str(path.stat().st_mtime).encode())
    return h.hexdigest()[:16]


def extract_compactions(session_file: Path) -> list[str]:
    """Return all compaction summaries found in a session (already dense context)."""
    summaries = []
    try:
        for line in session_file.read_text(errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "user":
                continue
            content = event.get("message", {}).get("content", "")
            if isinstance(content, str) and content.startswith(
                "This session is being continued"
            ):
                summaries.append(content)
    except Exception:
        pass
    return summaries


def extract_session_text(
    session_file: Path, max_chars: int = 40_000
) -> tuple[str, str]:
    """Extract user messages + assistant text from a session.

    Returns (text_excerpt, session_date_iso).
    Compaction summaries are included verbatim (they're already dense).
    """
    parts = []
    session_date = ""

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
            ts = event.get("timestamp", "")
            if ts and not session_date:
                session_date = ts[:10]

            if etype == "user":
                content = event.get("message", {}).get("content", "")
                if isinstance(content, str) and content.strip():
                    # compaction summaries: include in full (up to 3000 chars each)
                    if content.startswith("This session is being continued"):
                        parts.append(f"[compaction]\n{content[:3000]}")
                    else:
                        parts.append(f"[user] {content[:400]}")
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                parts.append(f"[user] {text[:400]}")

            elif etype == "assistant":
                content = event.get("message", {}).get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                parts.append(f"[assistant] {text[:300]}")
    except Exception:
        pass

    return "\n".join(parts)[:max_chars], session_date


class ClaudeCodeAdapter:
    """Claude Code session adapter, including free compaction summaries."""

    name = "claude-code"

    def discover(self, cwd: str) -> list[SessionRef]:
        sessions: list[SessionRef] = []
        for project_dir in find_project_dirs(cwd):
            for session_file in get_session_files(project_dir):
                sessions.append(
                    SessionRef(
                        source=self.name,
                        session_id=session_file.stem,
                        path=session_file,
                        active=_is_active(session_file),
                        label=project_dir.name,
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
            text, date = extract_session_text(session.path, max_chars=max_chars)
            if text.strip():
                label = _decode_project_dir_label(session.label, cwd)
                parts.append(
                    f"[ACTIVE claude-code session | {label} | {date}]\n{text}"
                )
        return parts

    def card_candidates(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        session_limit: int,
    ) -> list[SessionCardCandidate]:
        closed = _closed_sessions_newest_first(sessions)
        candidates: list[SessionCardCandidate] = []

        for session in closed:
            assert session.path is not None
            compactions = extract_compactions(session.path)
            if not compactions:
                continue
            candidates.append(
                SessionCardCandidate(
                    card_id=f"cc:compaction:{session.path.stem}",
                    source="claude-code-compaction",
                    text="\n\n---\n\n".join(compactions),
                    date=_mtime_date(session.path),
                    session_file=str(session.path),
                    file_hash=file_hash(session.path),
                    needs_summary=False,
                )
            )

        for session in closed[:session_limit]:
            assert session.path is not None
            text, date = extract_session_text(session.path)
            if not text.strip():
                continue
            fhash = file_hash(session.path)
            candidates.append(
                SessionCardCandidate(
                    card_id=f"cc:{session.path.stem}:{fhash}",
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
        closed = _closed_sessions_newest_first(sessions)
        compaction_count = 0
        for session in closed:
            assert session.path is not None
            compaction_count += len(extract_compactions(session.path))
        return AdapterInspectStats(
            source=self.name,
            api_window_count=len(closed[:session_limit]),
            free_card_count=compaction_count,
        )


def _is_active(path: Path) -> bool:
    # Keep the grace period local so the adapter remains useful without importing sync.
    return (time.time() - path.stat().st_mtime) < 30 * 60


def _closed_sessions_newest_first(sessions: list[SessionRef]) -> list[SessionRef]:
    closed = [s for s in sessions if not s.active and s.path is not None]
    return sorted(closed, key=lambda s: s.path.stat().st_mtime, reverse=True)


def _mtime_date(path: Path) -> str:
    return datetime.utcfromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def _decode_project_dir_label(dir_name: str, project_cwd: str) -> str:
    """Human-readable label showing which subdir a Claude session came from."""
    encoded_prefix = project_cwd.replace("/", "-")
    project_name = Path(project_cwd).name
    if dir_name == encoded_prefix:
        return project_name
    suffix = dir_name[len(encoded_prefix) :]
    rel = suffix.lstrip("-").replace("-", "/")
    return f"{project_name}/{rel}" if rel else project_name
