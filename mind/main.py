"""mind — frictionless AI project context manager."""

from __future__ import annotations

import typer

from .commands import register_commands

app = typer.Typer(
    name="mind",
    help="Restore your project mind state in 2 minutes.",
    no_args_is_help=True,
    add_completion=False,
)

register_commands(app)


if __name__ == "__main__":
    app()
