"""Adapter for Claude Code session JSONL files (~/.claude/projects/)."""

import hashlib
import json
from pathlib import Path

from ..config import CLAUDE_PROJECTS_DIR


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
