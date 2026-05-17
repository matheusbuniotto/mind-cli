"""CLI command registration."""

from __future__ import annotations

from typer import Typer

from . import core, handoff, notes, projects, setup


def register_commands(app: Typer) -> None:
    """Register commands in the order shown by `mind --help`."""
    core.register(app)
    setup.register_init(app)
    projects.register(app)
    handoff.register(app)
    notes.register(app)
    setup.register_config(app)
