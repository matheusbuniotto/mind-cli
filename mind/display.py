"""Rich TUI display for mind restore briefs."""

from datetime import datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def show_restore(cwd: str, digest: str, generated_at: str | None = None):
    from .adapters.project_files import git_snapshot

    project_name = Path(cwd).name or cwd
    age = ""
    if generated_at:
        try:
            dt = datetime.fromisoformat(generated_at)
            delta = datetime.utcnow() - dt
            hours = int(delta.total_seconds() // 3600)
            if hours < 1:
                age = "just now"
            elif hours < 24:
                age = f"{hours}h ago"
            else:
                age = f"{delta.days}d ago"
        except Exception:
            age = generated_at[:10]

    header = Text()
    header.append("⟳ mind restore  ", style="bold cyan")
    header.append(project_name, style="bold white")
    if age:
        header.append(f"  · synced {age}", style="dim")

    console.print()
    console.print(Panel(header, border_style="cyan", padding=(0, 2)))
    console.print(Markdown(digest))

    # --- deterministic git section (live, no AI) ---
    snap = git_snapshot(cwd)
    _show_git_snapshot(snap)
    console.print()


def _show_git_snapshot(snap: dict):
    """Render live git data directly — deterministic, no AI."""
    commits = snap.get("commits", [])
    hotfiles = snap.get("hotfiles", [])
    status = snap.get("status", [])
    issues = snap.get("issues", "")

    if not any([commits, hotfiles, status, issues]):
        return

    console.print(
        Panel("[bold]Live snapshot[/bold]", border_style="dim", padding=(0, 2))
    )

    if commits:
        t = Table(box=box.SIMPLE, show_header=True, header_style="dim", padding=(0, 1))
        t.add_column("commit", style="yellow", no_wrap=True, min_width=7, max_width=7)
        t.add_column("message", style="white")
        t.add_column("author", style="dim", no_wrap=True)
        t.add_column("when", style="dim", no_wrap=True)
        for c in commits:
            t.add_row(c["hash"], c["subject"][:72], c["author"], c["date"])
        console.print(t)

    if hotfiles:
        console.print("  [dim]Most touched files (last 20 commits)[/dim]")
        for filepath, count in hotfiles:
            bar = "█" * min(count, 12)
            console.print(f"  [cyan]{bar}[/cyan] [dim]{count}x[/dim]  {filepath}")
        console.print()

    if status:
        console.print("  [dim]Uncommitted changes[/dim]")
        for line in status:
            flag = line[:2].strip()
            path = line[3:]
            style = "yellow" if "M" in flag else "green" if "A" in flag else "red"
            console.print(f"  [{style}]{flag}[/{style}]  {path}")
        console.print()

    if issues:
        console.print("  [dim]Open GitHub issues[/dim]")
        for line in issues.splitlines():
            console.print(f"  [magenta]·[/magenta] {line}")
        console.print()


def show_project_list(projects: list[dict]):
    if not projects:
        console.print(
            "[dim]No projects indexed yet. Run [bold]mind sync <path>[/bold] to start.[/dim]"
        )
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    table.add_column("Project", style="bold white", min_width=24)
    table.add_column("Path", style="dim", min_width=30)
    table.add_column("Sessions", justify="right")
    table.add_column("Last session", justify="right")
    table.add_column("Digest", justify="center")

    for p in projects:
        cwd = p["cwd"]
        name = Path(cwd).name or cwd
        cards = str(p.get("card_count") or 0)
        last = (p.get("last_session") or "—")[:10]
        has_digest = "✓" if p.get("generated_at") else "·"
        table.add_row(name, cwd, cards, last, has_digest)

    console.print()
    console.print(table)
    console.print()


def show_progress(msg: str):
    console.print(f"  [dim cyan]→[/dim cyan] {msg}")


def show_error(msg: str):
    console.print(f"[bold red]error:[/bold red] {msg}")


def show_success(msg: str):
    console.print(f"[bold green]✓[/bold green] {msg}")
