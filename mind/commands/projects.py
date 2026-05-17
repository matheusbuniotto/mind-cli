"""Project index commands."""

from __future__ import annotations

import typer

from .. import display, store
from ..config import ensure_dirs


def ls():
    """List all indexed projects."""
    ensure_dirs()
    projects = store.list_projects()
    display.show_project_list(projects)


def register(app: typer.Typer) -> None:
    app.command()(ls)
