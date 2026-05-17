"""Manual note commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .. import display, store
from ..cli_helpers import resolve_cwd
from ..config import ensure_dirs


def _note_label(row) -> str:
    timestamp = str(row["created_at"])[:16].replace("T", " ")
    text = " ".join(str(row["note_text"]).split())
    preview = text[:72] + ("…" if len(text) > 72 else "")
    short_id = str(row["id"])[:6]
    return f"[{timestamp}] {preview} · {short_id}"


def _show_notes(cwd: str) -> None:
    notes = store.list_notes(cwd)
    if not notes:
        display.show_progress('No notes yet. Use `mind note "your note"` to add one.')
        return
    display.show_notes(notes)


def _add_note(cwd: str, text: str) -> None:
    note_text = text.strip()
    if not note_text:
        display.show_error("Note text cannot be empty.")
        raise typer.Exit(1)
    store.upsert_note(cwd, note_text)
    display.show_success(f"Note saved for {Path(cwd).name}.")


def _delete_selected_notes(cwd: str, note_ids: list[str]) -> None:
    deleted = store.delete_notes(cwd, note_ids)
    if deleted:
        display.show_success(f"Deleted {deleted} note(s) for {Path(cwd).name}.")
    else:
        display.show_progress("No notes were deleted.")


def _interactive_menu(cwd: str) -> None:
    import questionary

    actions = [
        "Add note",
        "Delete notes",
        "Show notes",
        "Cancel",
    ]
    choice = questionary.select(
        "What do you want to do?",
        choices=actions,
        use_indicator=True,
        use_shortcuts=False,
    ).ask()

    if choice in (None, "Cancel"):
        raise typer.Exit(0)
    if choice == "Show notes":
        _show_notes(cwd)
        return
    if choice == "Add note":
        text = questionary.text("Note text:").ask()
        if text is None:
            raise typer.Exit(0)
        _add_note(cwd, text)
        return

    notes = store.list_notes(cwd)
    if not notes:
        display.show_progress("No notes to delete.")
        return

    label_to_id = {_note_label(row): row["id"] for row in notes}
    selected = questionary.checkbox(
        "Select notes to delete:",
        choices=list(label_to_id.keys()),
        use_indicator=True,
        use_shortcuts=False,
    ).ask()
    if not selected:
        raise typer.Exit(0)
    confirm = questionary.confirm(
        f"Delete {len(selected)} note(s)?",
        default=False,
    ).ask()
    if not confirm:
        raise typer.Exit(0)
    _delete_selected_notes(cwd, [label_to_id[label] for label in selected])


def note(
    text: Optional[str] = typer.Argument(
        None, help="Note text to add; omit to open the interactive menu"
    ),
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Project path (default: cwd)"
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        help="Delete all notes for this project after confirmation",
    ),
):
    """Add, inspect, or clean manual notes for a project."""
    ensure_dirs()
    cwd = resolve_cwd(path)

    if clean:
        notes = store.list_notes(cwd)
        if not notes:
            display.show_progress("No notes to clean.")
            return
        confirm = typer.confirm(
            f"Delete all {len(notes)} note(s) for {Path(cwd).name}?",
            default=False,
        )
        if not confirm:
            raise typer.Exit(0)
        deleted = store.delete_all_notes(cwd)
        display.show_success(f"Deleted {deleted} note(s) for {Path(cwd).name}.")
        return

    if text is None:
        _interactive_menu(cwd)
        return

    _add_note(cwd, text)


def notes(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
):
    """Show manual notes for a project."""
    ensure_dirs()
    cwd = resolve_cwd(path)
    _show_notes(cwd)


def register(app: typer.Typer) -> None:
    app.command()(note)
    app.command()(notes)
