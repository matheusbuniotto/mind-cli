"""Diff, handoff, and open commands."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import typer

from .. import display, store
from ..cli_helpers import resolve_cwd
from ..config import ensure_dirs


def diff(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
):
    """Show what changed since the last sync — commits, files, and open status."""
    ensure_dirs()
    cwd = resolve_cwd(path)
    row = store.get_digest(cwd)
    if not row:
        display.show_error("No digest cached. Run `mind sync` first.")
        raise typer.Exit(1)

    from ..adapters.project_files import _run

    since = row["synced_commit"]
    if not since:
        display.show_error(
            "Digest has no recorded commit. Run `mind sync` to capture one."
        )
        raise typer.Exit(1)

    from rich import box as rbox
    from rich.console import Console
    from rich.table import Table

    c = Console()
    c.print(
        f"\n[bold cyan]mind diff[/bold cyan]  [dim]{Path(cwd).name}[/dim]  "
        f"[dim]since[/dim] [yellow]{since[:8]}[/yellow]\n"
    )

    log = _run(
        [
            "git",
            "log",
            "--no-merges",
            f"{since}..HEAD",
            "--pretty=format:%h\t%s\t%an\t%ar",
        ],
        cwd=cwd,
    )
    commits = []
    for line in log.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            commits.append(parts)

    if commits:
        table = Table(
            box=rbox.SIMPLE, show_header=True, header_style="dim", padding=(0, 1)
        )
        table.add_column(
            "commit", style="yellow", no_wrap=True, min_width=7, max_width=7
        )
        table.add_column("message", style="white")
        table.add_column("author", style="dim", no_wrap=True)
        table.add_column("when", style="dim", no_wrap=True)
        for commit_hash, message, author, when in commits:
            table.add_row(commit_hash, message[:72], author, when)
        c.print(table)
    else:
        c.print("  [dim]No new commits since last sync.[/dim]\n")

    files_out = _run(["git", "diff", "--stat", f"{since}..HEAD"], cwd=cwd)
    if files_out:
        c.print("  [dim]Changed files[/dim]")
        for line in files_out.splitlines():
            c.print(f"  [dim]{line}[/dim]")
        c.print()

    status_out = _run(["git", "status", "--short"], cwd=cwd)
    status = [line for line in status_out.splitlines() if line.strip()]
    if status:
        c.print("  [dim]Uncommitted changes[/dim]")
        for line in status:
            flag = line[:2].strip()
            fpath = line[3:]
            style = "yellow" if "M" in flag else "green" if "A" in flag else "red"
            c.print(f"  [{style}]{flag}[/{style}]  {fpath}")
        c.print()

    age = row["generated_at"][:16] if row["generated_at"] else "unknown"
    c.print(
        f"  [dim]Last synced: {age} UTC — run [bold]mind sync[/bold] to update.[/dim]\n"
    )


def share(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
    output: Optional[str] = typer.Option(
        None, "--out", "-o", help="Write to file instead of stdout"
    ),
    no_clip: bool = typer.Option(False, "--no-clip", help="Skip clipboard copy"),
):
    """Export a clean handoff brief — stdout, clipboard, or file."""
    ensure_dirs()
    cwd = resolve_cwd(path)
    row = store.get_digest(cwd)
    if not row:
        display.show_error("No digest cached. Run `mind sync` first.")
        raise typer.Exit(1)

    header = (
        f"# mind handoff — {Path(cwd).name}\n"
        f"_path: `{cwd}`  ·  generated: {(row['generated_at'] or '')[:16]} UTC_\n\n"
        "---\n\n"
    )
    brief = header + row["digest_text"]

    if output:
        Path(output).write_text(brief)
        display.show_success(f"Handoff brief written to {output}")
    else:
        from rich.console import Console
        from rich.markdown import Markdown

        Console().print(Markdown(brief))

    if not no_clip:
        try:
            proc = subprocess.run(["pbcopy"], input=brief.encode(), capture_output=True)
            if proc.returncode == 0:
                display.show_success(
                    "Copied to clipboard — paste into chat or send to teammate."
                )
        except Exception:
            pass


def open_project(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
    skip_permissions: bool = typer.Option(
        False,
        "--dangerously-skip-permissions",
        help="Pass --dangerously-skip-permissions to Claude Code (bypasses safety prompts).",
    ),
):
    """Open project in Claude Code with context pre-loaded (copies restore brief to clipboard)."""
    ensure_dirs()
    cwd = resolve_cwd(path)
    row = store.get_digest(cwd)
    if not row:
        display.show_error("No digest cached. Run `mind sync` first.")
        raise typer.Exit(1)

    try:
        proc = subprocess.run(
            ["pbcopy"], input=row["digest_text"].encode(), capture_output=True
        )
        if proc.returncode == 0:
            display.show_success("Restore brief copied to clipboard.")
        display.show_progress("Paste it as your first message in Claude Code.")
    except Exception:
        pass

    cmd = ["claude"]
    if skip_permissions:
        cmd.append("--dangerously-skip-permissions")
    try:
        subprocess.Popen(cmd, cwd=cwd)
        display.show_success(f"Launched Claude Code in {cwd}")
    except FileNotFoundError:
        display.show_progress(f"cd {cwd} && claude")


def register(app: typer.Typer) -> None:
    app.command()(diff)
    app.command()(share)
    app.command(name="open")(open_project)
