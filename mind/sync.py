"""Sync engine: discover sessions, generate cards, build digests.

Token strategy (default):
  1. Active sessions (modified < 30min): extract raw text, inject directly — no caching, no extra API call.
  2. Compaction summaries from closed sessions: free, already dense, stored as cards.
  3. Last N closed sessions: summarized via API, cached by file hash.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import store, summarizer
from .adapters import claude_code, codex, cursor, project_files
from .config import ensure_dirs

DEFAULT_SESSION_LIMIT = 2
ACTIVE_SESSION_GRACE_MINUTES = 30


def _is_active(path: Path) -> bool:
    return (time.time() - path.stat().st_mtime) < ACTIVE_SESSION_GRACE_MINUTES * 60


def _project_name(cwd: str) -> str:
    return Path(cwd).name or cwd


def _decode_project_dir_label(dir_name: str, project_cwd: str) -> str:
    """Human-readable label showing which subdir a session came from.

    Claude Code encodes '/' as '-', so we strip the encoded cwd prefix
    and show only the relative suffix as 'project/subdir'.
    """
    encoded_prefix = project_cwd.replace("/", "-")
    project_name = Path(project_cwd).name
    if dir_name == encoded_prefix:
        return project_name
    # suffix is the encoded relative path, e.g. '-src-feature'
    suffix = dir_name[len(encoded_prefix) :]  # starts with '-'
    rel = suffix.lstrip("-").replace("-", "/")
    return f"{project_name}/{rel}" if rel else project_name


def _collect_active_session_text(cwd: str) -> str:
    """Extract raw text from any currently-open sessions across all tools. No caching."""
    parts = []

    # Claude Code — include exact dir + any subdirectory sessions
    for claude_dir in claude_code.find_project_dirs(cwd):
        for session_file in claude_code.get_session_files(claude_dir):
            if not _is_active(session_file):
                break  # sorted newest-first; once we hit a closed one, stop
            text, date = claude_code.extract_session_text(
                session_file, max_chars=20_000
            )
            if text.strip():
                subdir_label = _decode_project_dir_label(claude_dir.name, cwd)
                parts.append(
                    f"[ACTIVE claude-code session | {subdir_label} | {date}]\n{text}"
                )

    # Codex
    for session_file in codex.get_session_files()[:20]:
        if not _is_active(session_file):
            continue
        text, date, session_cwd = codex.extract_session_text(
            session_file, max_chars=20_000
        )
        if not session_cwd:
            continue
        if session_cwd != cwd and not session_cwd.startswith(cwd + "/"):
            continue
        if text.strip():
            parts.append(f"[ACTIVE codex session | {date}]\n{text}")

    return "\n\n".join(parts)


def sync_project(
    cwd: str,
    progress: Callable[[str], None] = lambda _: None,
    session_limit: int = DEFAULT_SESSION_LIMIT,
) -> int:
    """Sync closed sessions into cards. Returns count of new cards created."""
    ensure_dirs()
    new_cards = 0

    # --- Claude Code (exact dir + all subdirectory sessions) ---
    claude_dirs = claude_code.find_project_dirs(cwd)
    all_closed: list[Path] = []
    active_count = 0
    for claude_dir in claude_dirs:
        all_sessions = claude_code.get_session_files(claude_dir)
        closed = [f for f in all_sessions if not _is_active(f)]
        active_count += len(all_sessions) - len(closed)
        all_closed.extend(closed)

    # sort all closed sessions newest-first across dirs
    all_closed.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if active_count:
        progress(
            f"Found {active_count} active session(s) — will include raw (no cache)…"
        )

    total = len(all_closed)

    # Stage 1: compaction summaries from ALL closed sessions — no API cost
    for session_file in all_closed:
        compactions = claude_code.extract_compactions(session_file)
        if not compactions:
            continue
        card_id = f"cc:compaction:{session_file.stem}"
        if store.get_session_card(card_id):
            continue
        fhash = claude_code.file_hash(session_file)
        date = datetime.utcfromtimestamp(session_file.stat().st_mtime).strftime(
            "%Y-%m-%d"
        )
        store.upsert_session_card(
            card_id=card_id,
            project_cwd=cwd,
            source="claude-code-compaction",
            card_text="\n\n---\n\n".join(compactions),
            session_file=str(session_file),
            file_hash=fhash,
            session_date=date,
        )
        new_cards += 1

    # Stage 2: summarize recent closed sessions via API
    limited = all_closed[:session_limit]
    if total > len(limited):
        progress(
            f"Found {total} closed sessions — summarizing {len(limited)} most recent"
            f" (use -n {total} or --all to include all)…"
        )
    for session_file in limited:
        fhash = claude_code.file_hash(session_file)
        card_id = f"cc:{session_file.stem}:{fhash}"
        if store.get_session_card(card_id):
            continue
        progress(f"Summarizing {session_file.name[:36]}…")
        text, date = claude_code.extract_session_text(session_file)
        if not text.strip():
            continue
        card = summarizer.summarize_session(text, source="claude-code")
        if card:
            store.upsert_session_card(
                card_id=card_id,
                project_cwd=cwd,
                source="claude-code",
                card_text=card,
                session_file=str(session_file),
                file_hash=fhash,
                session_date=date,
            )
            new_cards += 1

    # --- Codex (closed only) ---
    progress("Scanning Codex sessions…")
    codex_sessions = [
        f
        for f in codex.get_session_files()[:50]
        if not _is_active(f) and _codex_matches_cwd(f, cwd)
    ]
    for session_file in codex_sessions[:session_limit]:
        fhash = codex.file_hash(session_file)
        card_id = f"codex:{session_file.stem}:{fhash}"
        if store.get_session_card(card_id):
            continue
        text, date, _ = codex.extract_session_text(session_file)
        if not text.strip():
            continue
        progress(f"Summarizing Codex {session_file.name[:36]}…")
        card = summarizer.summarize_session(text, source="codex")
        if card:
            store.upsert_session_card(
                card_id=card_id,
                project_cwd=cwd,
                source="codex",
                card_text=card,
                session_file=str(session_file),
                file_hash=fhash,
                session_date=date,
            )
            new_cards += 1

    # --- Cursor (titles only, no API call) ---
    cursor_text, cursor_date = cursor.extract_session_text(cwd)
    if cursor_text.strip():
        card_id = f"cursor:{cwd}:{summarizer.text_hash(cursor_text)}"
        if not store.get_session_card(card_id):
            store.upsert_session_card(
                card_id=card_id,
                project_cwd=cwd,
                source="cursor",
                card_text=f"Cursor chat sessions:\n{cursor_text}",
                session_date=cursor_date,
            )
            new_cards += 1

    return new_cards


def _codex_matches_cwd(session_file: Path, cwd: str) -> bool:
    _, _, session_cwd = codex.extract_session_text(session_file, max_chars=0)
    return bool(
        session_cwd and (session_cwd == cwd or session_cwd.startswith(cwd + "/"))
    )


def build_digest(
    cwd: str,
    progress: Callable[[str], None] = lambda _: None,
    active_text: str = "",
) -> str:
    """Build project digest. active_text is injected raw (no caching)."""
    ensure_dirs()
    all_cards = store.get_project_cards(cwd)
    if not all_cards and not active_text:
        return ""

    compaction_cards = [c for c in all_cards if "compaction" in c["source"]]
    session_cards = [c for c in all_cards if "compaction" not in c["source"]]

    MAX_SESSION_CARDS_PER_SOURCE = 4
    seen: dict[str, int] = {}
    capped = []
    for card in session_cards:
        src = card["source"]
        if seen.get(src, 0) < MAX_SESSION_CARDS_PER_SOURCE:
            capped.append(card)
            seen[src] = seen.get(src, 0) + 1

    cards = compaction_cards + capped
    if len(all_cards) > len(cards):
        progress(f"Using {len(cards)} of {len(all_cards)} stored cards for digest…")

    progress("Reading project files…")
    proj_context = project_files.extract_project_context(cwd)

    cards_text = "\n\n---\n\n".join(
        f"[{c['source']} | {c['session_date'] or 'unknown date'}]\n{c['card_text']}"
        for c in cards
    )

    notes_row = store.get_notes(cwd)
    notes_section = (
        f"\n\n=== Manual Notes ===\n{notes_row['notes']}" if notes_row else ""
    )

    active_section = (
        f"\n\n=== ACTIVE SESSION (live, not cached) ===\n{active_text}"
        if active_text
        else ""
    )

    context = (
        f"{proj_context}\n\n=== Session Cards ===\n\n{cards_text}"
        f"{notes_section}{active_section}"
    )

    progress("Generating AI digest…")
    digest = summarizer.generate_digest(
        cwd=cwd,
        project_name=_project_name(cwd),
        context=context,
    )

    head = project_files._run(["git", "rev-parse", "HEAD"], cwd=cwd)
    store.upsert_digest(
        cwd, digest, [c["id"] for c in cards], synced_commit=head or None
    )
    return digest


def full_sync(
    cwd: str,
    progress: Callable[[str], None] = lambda _: None,
    session_limit: int = DEFAULT_SESSION_LIMIT,
) -> str:
    """Sync closed sessions + inject active sessions raw. Returns digest text."""
    active_text = _collect_active_session_text(cwd)
    if active_text:
        progress("Active session detected — injecting live (no cache)…")

    new = sync_project(cwd, progress, session_limit=session_limit)
    progress(f"Indexed {new} new item(s). Building digest…")
    return build_digest(cwd, progress, active_text=active_text)
