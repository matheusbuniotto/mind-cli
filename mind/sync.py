"""Sync engine: discover sessions, generate cards, build digests.

Token strategy (default):
  1. Active sessions (modified < 30min): extract raw text, inject directly — no caching, no extra API call.
  2. Compaction summaries from closed sessions: free, already dense, stored as cards.
  3. Last N closed sessions: summarized via API, cached by file hash.
"""

from pathlib import Path
from typing import Callable

from . import store, summarizer
from .adapters import project_files
from .adapters.registry import get_adapters
from .config import ensure_dirs

DEFAULT_SESSION_LIMIT = 2


def _project_name(cwd: str) -> str:
    return Path(cwd).name or cwd


def _collect_active_session_text(cwd: str) -> str:
    """Extract raw text from any currently-open sessions across all tools. No caching."""
    parts = []
    for adapter in get_adapters():
        sessions = adapter.discover(cwd)
        parts.extend(adapter.active_context(cwd, sessions, max_chars=20_000))

    return "\n\n".join(parts)


def sync_project(
    cwd: str,
    progress: Callable[[str], None] = lambda _: None,
    session_limit: int = DEFAULT_SESSION_LIMIT,
) -> int:
    """Sync closed sessions into cards. Returns count of new cards created."""
    ensure_dirs()
    new_cards = 0

    for adapter in get_adapters():
        sessions = adapter.discover(cwd)
        active_count = sum(1 for s in sessions if s.active)
        if active_count:
            progress(
                f"Found {active_count} active {adapter.name} session(s) — will include raw (no cache)…"
            )

        stats = adapter.inspect_stats(cwd, sessions, session_limit=session_limit)
        closed_count = sum(1 for s in sessions if not s.active)
        if closed_count > stats.api_window_count and stats.api_window_count:
            progress(
                f"Found {closed_count} closed {adapter.name} session(s) — summarizing "
                f"{stats.api_window_count} most recent"
                f" (use -n {closed_count} or --all to include all)…"
            )

        for candidate in adapter.card_candidates(
            cwd, sessions, session_limit=session_limit
        ):
            if store.get_session_card(candidate.card_id):
                continue

            card_text = candidate.text
            if candidate.needs_summary:
                label = Path(candidate.session_file).name[:36] if candidate.session_file else candidate.source
                progress(f"Summarizing {candidate.source} {label}…")
                card_text = summarizer.summarize_session(
                    candidate.text,
                    source=candidate.source,
                    project_cwd=cwd,
                )
                if not card_text:
                    continue

            store.upsert_session_card(
                card_id=candidate.card_id,
                project_cwd=cwd,
                source=candidate.source,
                card_text=card_text,
                session_file=candidate.session_file,
                file_hash=candidate.file_hash,
                session_date=candidate.date,
            )
            new_cards += 1

    return new_cards


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
