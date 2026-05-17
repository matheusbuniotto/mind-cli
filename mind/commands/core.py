"""Core restore/sync/doctor commands."""

from __future__ import annotations

from typing import Optional

import typer

from .. import display, store, sync
from ..cli_helpers import pick_project, require_api_key, resolve_cwd
from ..config import ensure_dirs
from ..display import console
from ..doctor import run_doctor
from ..read_sources import build_restore_provenance_markdown, build_sync_read_plan


def restore(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-sync before showing"
    ),
    inspect: bool = typer.Option(
        False,
        "--inspect",
        help="List local files/commands that would be read; no model calls",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Full output: provenance, full digest, recent files",
    ),
):
    """Restore your mental context for a project. The core command."""
    ensure_dirs()
    cwd = resolve_cwd(path)
    if not path:
        cwd = pick_project(cwd)

    if inspect:
        plan = build_sync_read_plan(cwd, session_limit=2, all_sessions=False)
        display.show_sync_inspect_plan(plan, heading="mind restore --inspect")
        row = store.get_digest(cwd)
        if row:
            console.print(
                f"\n[dim]Cached digest:[/dim] yes  ·  generated {row['generated_at'][:19]} UTC"
            )
        else:
            console.print(
                "\n[dim]Cached digest:[/dim] no — a restore would run `mind sync` first"
            )
        console.print()
        return

    def _show(row: dict) -> None:
        display.show_restore(
            cwd,
            row["digest_text"],
            row["generated_at"],
            provenance_md=build_restore_provenance_markdown(cwd),
            synced_commit=row["synced_commit"],
            notes=store.list_notes(cwd),
            verbose=verbose,
        )

    if force:
        require_api_key(cwd)
        display.show_progress("Syncing sessions…")
        digest = sync.full_sync(cwd, progress=display.show_progress)
        if not digest:
            display.show_error(f"No AI sessions found for {cwd}")
            raise typer.Exit(1)
    else:
        row = store.get_digest(cwd)
        if row:
            _show(row)
            return
        require_api_key(cwd)
        display.show_progress(f"No cached digest found. Syncing {cwd}…")
        digest = sync.full_sync(cwd, progress=display.show_progress)
        if not digest:
            display.show_error(
                f"No AI sessions found for {cwd}.\n"
                "Make sure you've worked on this project with Claude Code or Codex."
            )
            raise typer.Exit(1)

    row = store.get_digest(cwd)
    if row:
        _show(row)


def sync_cmd(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
    all_sessions: bool = typer.Option(
        False, "--all", help="Summarize all sessions, not just the most recent"
    ),
    sessions: int = typer.Option(
        2, "--sessions", "-n", help="Number of recent sessions to summarize via API"
    ),
    inspect: bool = typer.Option(
        False,
        "--inspect",
        help="List local files that would be read; no model calls or writes",
    ),
):
    """Sync sessions and regenerate digest for a project."""
    cwd = resolve_cwd(path)
    if not path:
        cwd = pick_project(cwd)
    limit = 999 if all_sessions else sessions

    if inspect:
        plan = build_sync_read_plan(cwd, session_limit=limit, all_sessions=all_sessions)
        display.show_sync_inspect_plan(plan, heading="mind sync --inspect")
        console.print(
            "[dim]No digest updates, session indexing, or model calls in --inspect mode.[/dim]\n"
        )
        return

    ensure_dirs()
    require_api_key(cwd)
    display.show_progress(f"Syncing {cwd}…")
    digest = sync.full_sync(cwd, progress=display.show_progress, session_limit=limit)
    if digest:
        display.show_success("Digest ready. Run `mind restore` to view.")
    else:
        display.show_error("No sessions found for this project.")
        raise typer.Exit(1)


def doctor(
    demo: bool = typer.Option(
        False,
        "--demo",
        help="Show bundled sample restore output (no API calls, no private paths)",
    ),
):
    """Check your environment and agent session paths (first-run diagnostics)."""
    run_doctor(demo=demo)


def register(app: typer.Typer) -> None:
    app.command()(restore)
    app.command(name="sync")(sync_cmd)
    app.command()(doctor)
