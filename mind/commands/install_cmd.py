"""Install bundled skills and hooks for Claude Code, Cursor, and Codex."""

from __future__ import annotations

from typing import List, Optional

import typer

from .. import display
from ..config import ensure_dirs
from ..install_agents import (
    detect_installed_agents,
    npx_skills_hint,
    resolve_agents,
    run_install,
)

InstallMethodOpt = typer.Option(
    "copy",
    "--method",
    help="copy (default, survives uv tool upgrades) or symlink",
)


def install(
    skill: bool = typer.Option(
        True,
        "--skill/--no-skill",
        help="Install mind-recap skill",
    ),
    hook: bool = typer.Option(
        True,
        "--hook/--no-hook",
        help="Install session-start check hook (Claude, Cursor, Codex)",
    ),
    agent: Optional[List[str]] = typer.Option(
        None,
        "--agent",
        "-a",
        help="Target agent(s): claude-code, cursor, codex, agents",
    ),
    all_agents: bool = typer.Option(
        False,
        "--all-agents",
        help="Install to every known agent path",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be installed",
    ),
    method: str = InstallMethodOpt,
):
    """Install or refresh agent skill + hooks. First time? Use `mind init` instead."""
    ensure_dirs()
    if method not in ("copy", "symlink"):
        display.show_error("--method must be copy or symlink")
        raise typer.Exit(1)

    try:
        targets = resolve_agents(
            agent,
            all_agents=all_agents,
            auto_detect=agent is None and not all_agents,
        )
    except ValueError as exc:
        display.show_error(str(exc))
        raise typer.Exit(1) from exc

    if not skill and not hook:
        display.show_error("Nothing to install — enable --skill and/or --hook")
        raise typer.Exit(1)

    from rich.console import Console

    c = Console()
    detected = detect_installed_agents()
    c.print("\n[bold cyan]mind install[/bold cyan]\n")
    if detected:
        c.print(f"[dim]Detected on disk:[/dim] {', '.join(detected)}\n")
    else:
        c.print(
            "[dim]No agent config dirs detected — installing to standard paths anyway.[/dim]\n"
        )

    for t in targets:
        parts = []
        if skill:
            parts.append(f"skill → {t.skill_dir}")
        if hook and t.hook_script:
            parts.append(f"hook → {t.hook_script}")
        elif hook and not t.hook_script:
            parts.append("hook — [dim]not supported[/dim]")
        c.print(f"  [bold]{t.label}[/bold]  {' · '.join(parts)}")

    if dry_run:
        c.print("\n[dim]Dry run — no files written.[/dim]\n")
        return

    if not yes:
        if not typer.confirm("\nProceed?", default=True):
            raise typer.Exit(0)

    try:
        actions = run_install(
            skill=skill,
            hook=hook,
            agents=targets,
            method=method,  # type: ignore[arg-type]
            dry_run=False,
        )
    except FileNotFoundError as exc:
        display.show_error(str(exc))
        raise typer.Exit(1) from exc
    c.print()
    for act in actions:
        display.show_success(f"{act.kind} → {act.agent}: {act.path}")

    c.print(f"\n[dim]Skill only (no hooks):[/dim]\n  {npx_skills_hint()}\n")
    c.print(
        "[dim]Hooks call[/dim] [bold]mind check[/bold] [dim](no LLM). "
        "Recap still uses[/dim] [bold]mind restore[/bold] [dim]or the skill when you ask.[/dim]\n"
    )


def integrations_path():
    """Print bundled integrations directory (skills + hooks)."""
    from rich.console import Console

    from ..install_agents import bundled_hook_script, bundled_skill_dir

    c = Console()
    c.print(f"skill: {bundled_skill_dir()}")
    c.print(f"hook:  {bundled_hook_script()}\n")


def register(app: typer.Typer) -> None:
    app.command()(install)
    app.command("integrations-path")(integrations_path)
