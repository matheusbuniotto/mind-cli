"""Manual note commands."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from .. import display, store
from ..cli_helpers import resolve_cwd
from ..config import ensure_dirs


def note(
    text: str = typer.Argument(..., help="Note to append to this project"),
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Project path (default: cwd)"
    ),
):
    """Add a manual note to a project's context."""
    ensure_dirs()
    cwd = resolve_cwd(path)
    existing = store.get_notes(cwd)
    current = existing["notes"] if existing else ""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    updated = current + f"\n[{timestamp}] {text}" if current else f"[{timestamp}] {text}"
    store.upsert_notes(cwd, updated)
    display.show_success(f"Note saved for {Path(cwd).name}.")


def notes(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
):
    """Show manual notes for a project."""
    ensure_dirs()
    cwd = resolve_cwd(path)
    row = store.get_notes(cwd)
    if row:
        from rich.console import Console

        Console().print(row["notes"])
    else:
        display.show_progress('No notes yet. Use `mind note "your note"` to add one.')


def register(app: typer.Typer) -> None:
    app.command()(note)
    app.command()(notes)
