"""Enumerate local files and commands `mind` reads — used for --inspect and provenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .adapters.registry import get_adapters
from .config import CLAUDE_PROJECTS_DIR, CODEX_SESSIONS_DIR, CURSOR_USER_DIR


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


@dataclass
class ReadSource:
    """One readable artifact mind may ingest."""

    category: str
    path: str
    size_bytes: int | None = None
    active: bool = False
    detail: str = ""


@dataclass
class SyncReadPlan:
    """Full enumeration for a project cwd."""

    cwd: str
    sources: list[ReadSource] = field(default_factory=list)
    api_window_counts: dict[str, int] = field(default_factory=dict)
    free_card_counts: dict[str, int] = field(default_factory=dict)


def enumerate_project_context_files(cwd: str) -> list[tuple[str, Path]]:
    """Static project files (same selection as extract_project_context)."""
    root = Path(cwd)
    out: list[tuple[str, Path]] = []
    for name in ["README.md", "CLAUDE.md", "AGENTS.md"]:
        p = root / name
        if p.exists():
            out.append((name, p))
    spec_log = root / ".spec" / "log.md"
    if spec_log.exists():
        out.append((".spec/log.md", spec_log))
    memory_dir = Path.home() / ".claude" / "projects" / cwd.replace("/", "-") / "memory"
    if memory_dir.exists():
        for md in sorted(memory_dir.glob("*.md"))[:5]:
            out.append((f"~/.claude/.../memory/{md.name}", md))
    return out


def build_sync_read_plan(
    cwd: str, session_limit: int = 2, all_sessions: bool = False
) -> SyncReadPlan:
    """List paths that sync/restore digest pipeline may read (local only)."""
    plan = SyncReadPlan(cwd=cwd)
    limit = 999 if all_sessions else session_limit

    for adapter in get_adapters():
        sessions = adapter.discover(cwd)
        stats = adapter.inspect_stats(cwd, sessions, session_limit=limit)
        plan.api_window_counts[stats.source] = stats.api_window_count
        if stats.free_card_count:
            plan.free_card_counts[stats.source] = stats.free_card_count

        for session in sessions:
            if session.path is None:
                continue
            plan.sources.append(
                ReadSource(
                    category=session.source,
                    path=str(session.path),
                    size_bytes=_file_size(session.path),
                    active=session.active,
                    detail=session.label,
                )
            )

    for label, p in enumerate_project_context_files(cwd):
        plan.sources.append(
            ReadSource(
                category="project-file",
                path=str(p),
                size_bytes=_file_size(p),
                detail=label,
            )
        )

    return plan


def format_tooling_paths() -> dict[str, str]:
    """Well-known directories for diagnostics."""
    return {
        "mind_home": str(Path.home() / ".mind"),
        "claude_projects": str(CLAUDE_PROJECTS_DIR),
        "codex_sessions": str(CODEX_SESSIONS_DIR),
        "cursor_user": str(CURSOR_USER_DIR),
    }


def build_restore_provenance_markdown(cwd: str) -> str:
    """Human-readable provenance block for `mind restore` output."""
    from . import store

    cards = store.get_project_cards(cwd)
    counts: dict[str, int] = {}
    for c in cards:
        src = c["source"]
        counts[src] = counts.get(src, 0) + 1

    notes = store.list_notes(cwd)

    lines: list[str] = [
        "### Data sources for this digest",
        "",
        "**Cached closed-session cards** (SQLite `~/.mind/mind.db`)",
    ]
    if counts:
        for k, v in sorted(counts.items()):
            lines.append(f"- `{k}`: {v} card(s)")
    else:
        lines.append("- _(none yet — run `mind sync` to build cards)_")

    lines.extend(
        [
            "",
            "**Live active-session context**",
            "- Open sessions are injected during `mind sync` and are **not cached as cards**.",
        ]
    )

    lines.extend(["", "**Project files** (re-read on each sync)"])
    pf = enumerate_project_context_files(cwd)
    if pf:
        for label, _p in pf:
            lines.append(f"- {label}")
    else:
        lines.append(
            "- _(none of README.md / CLAUDE.md / AGENTS.md / .spec/log.md / memory found)_"
        )

    lines.extend(
        [
            "",
            "**Manual notes** (stored locally in SQLite)",
        ]
    )
    if notes:
        lines.append(f"- `{len(notes)}` note(s) added with `mind note`")
    else:
        lines.append("- _(none yet — run `mind note` to add one)_")

    lines.extend(
        [
            "",
            "**Live on each `mind restore` (not from SQLite)**",
            "- `git log --numstat`, `git status --short` — local repo only",
            "- `gh issue list` — if `gh` is installed and the repo has a GitHub remote",
            "",
            "**Model boundary**",
            "- API keys are resolved from shell env / `~/.mind/.env` / `<project>/.env` per `api_key_source` in config — never from `config.yml`.",
            "- Session transcripts and project context are **redacted for common secret patterns** before any API request.",
            "- Only the summarization / digest prompts are sent to your configured provider; nothing is written back to session files.",
        ]
    )
    return "\n".join(lines)
