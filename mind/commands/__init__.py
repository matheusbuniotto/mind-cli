"""CLI command registration."""

from __future__ import annotations

from typer import Typer

from . import check_cmd, core, handoff, install_cmd, notes, projects, setup


def register_commands(app: Typer) -> None:
    """Register commands in the order shown by `mind --help`."""
    core.register(app)
    check_cmd.register(app)
    install_cmd.register(app)
    setup.register_init(app)
    setup.register_set_key(app)
    projects.register(app)
    handoff.register(app)
    notes.register(app)
    setup.register_config(app)
