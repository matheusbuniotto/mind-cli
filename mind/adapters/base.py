"""Shared contracts for conversational session adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SessionRef:
    """One source artifact that may contribute project context."""

    source: str
    session_id: str
    path: Path | None
    date: str = ""
    active: bool = False
    label: str = ""
    cwd: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionCardCandidate:
    """A card-shaped artifact an adapter wants stored for a project."""

    card_id: str
    source: str
    text: str
    date: str
    session_file: str | None = None
    file_hash: str | None = None
    needs_summary: bool = True


@dataclass(frozen=True)
class AdapterInspectStats:
    """Adapter-specific counts exposed by `mind --inspect`."""

    source: str
    api_window_count: int = 0
    free_card_count: int = 0


class SessionAdapter(Protocol):
    """Small extension seam for conversational session sources."""

    name: str

    def discover(self, cwd: str) -> list[SessionRef]:
        """Return session artifacts relevant to ``cwd``."""

    def active_context(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        max_chars: int,
    ) -> list[str]:
        """Return already-formatted live context blocks for active sessions."""

    def card_candidates(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        session_limit: int,
    ) -> list[SessionCardCandidate]:
        """Return stored-card candidates in adapter-defined priority order."""

    def inspect_stats(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        session_limit: int,
    ) -> AdapterInspectStats:
        """Return counts useful for explaining what a sync would read/send."""
