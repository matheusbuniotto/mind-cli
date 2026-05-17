"""mind — frictionless AI project context manager."""

from __future__ import annotations

from importlib.metadata import version as _pkg_version

import typer

from .commands import register_commands


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"mind {_pkg_version('mind-cli')}")
        raise typer.Exit()


app = typer.Typer(
    name="mind",
    help="Restore your project mind state in 2 minutes.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    pass


register_commands(app)


if __name__ == "__main__":
    app()
