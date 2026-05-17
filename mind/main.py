"""mind — frictionless AI project context manager."""

import subprocess
from pathlib import Path
from typing import Optional

import typer

from . import display, store, sync
from .config import CONFIG_FILE, ensure_dirs, get_config
from .display import console

app = typer.Typer(
    name="mind",
    help="Restore your project mind state in 2 minutes.",
    no_args_is_help=True,
    add_completion=False,
)


def _resolve_cwd(path: Optional[str]) -> str:
    if path:
        return str(Path(path).expanduser().resolve())
    return str(_find_project_root(Path.cwd()))


def _find_project_root(start: Path) -> Path:
    """Find the most likely project root from a given directory.

    Strategy (in order):
    1. Walk UP — if an ancestor has a known Claude Code session dir or git root, use it.
    2. Walk DOWN one level — if a direct child looks like a project (has git/CLAUDE.md/README),
       and has Claude Code sessions, prefer it. Handles the 'cd ..' edge case.
    3. Fall back to start as-is.
    """
    from .adapters.claude_code import find_project_dir

    # 1. Walk up — subdirectory case (you're inside a project)
    candidate = start
    while True:
        if _is_project_root(candidate) and find_project_dir(str(candidate)):
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent

    # 2. Walk up by git root alone (no Claude sessions required)
    git_root = _git_root(start)
    if git_root and git_root != start:
        return git_root

    # 3. Walk down one level — parent-directory case (you did cd ..)
    try:
        children = [
            d for d in start.iterdir() if d.is_dir() and not d.name.startswith(".")
        ]
    except PermissionError:
        children = []

    scored = []
    for child in children:
        score = 0
        if find_project_dir(str(child)):
            score += 10  # has Claude Code sessions — strong signal
        if (child / ".git").exists():
            score += 5
        for marker in [
            "CLAUDE.md",
            "AGENTS.md",
            "README.md",
            "pyproject.toml",
            "package.json",
        ]:
            if (child / marker).exists():
                score += 1
        if score > 0:
            scored.append((score, child))

    if scored:
        scored.sort(key=lambda x: -x[0])
        best_score, best = scored[0]
        if best_score >= 10:  # only auto-pick if there are Claude sessions
            return best

    return start


def _is_project_root(path: Path) -> bool:
    return any(
        (path / m).exists()
        for m in [
            ".git",
            "CLAUDE.md",
            "AGENTS.md",
            "pyproject.toml",
            "package.json",
            "README.md",
        ]
    )


def _git_root(start: Path) -> Optional[Path]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=start,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return None


def _pick_project(detected: str) -> str:
    """When detected root differs from cwd, show a picker limited to cwd + L1 children.

    Options:
    - The auto-detected root (highlighted, if it's cwd or a direct child)
    - Current directory
    - Each direct child directory that looks like a project
    - Abort
    """
    import questionary

    actual = str(Path.cwd())
    if detected == actual:
        return detected

    actual_path = Path(actual)
    candidates: dict[str, str] = {}  # display label → cwd

    # Collect cwd + L1 children that look like projects
    try:
        children = [
            d
            for d in actual_path.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
    except PermissionError:
        children = []

    options: list[Path] = [actual_path] + sorted(children)

    for opt in options:
        opt_str = str(opt)
        label = opt.name if opt != actual_path else f"{opt.name}  (current directory)"
        if opt_str == detected:
            label = f"{opt.name}  ← detected"
        candidates[label] = opt_str

    ABORT = "↩  cancel"
    choices = list(candidates.keys()) + [ABORT]

    console.print(f"\n[dim]You're in [bold]{actual}[/bold] — which project?[/dim]\n")
    choice = questionary.select(
        "Select project:",
        choices=choices,
        use_indicator=True,
        use_shortcuts=False,
    ).ask()

    if choice is None or choice == ABORT:
        raise typer.Exit(0)

    return candidates[choice]


def _require_api_key():
    cfg = get_config()
    if not cfg.get("api_key"):
        display.show_error(
            "No API key found. Set one in your shell:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...   # Anthropic\n"
            "  export OPENAI_API_KEY=sk-or-...        # OpenRouter / compatible\n\n"
            "Add it to ~/.zshrc so it persists."
        )
        raise typer.Exit(1)


@app.command()
def restore(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force re-sync before showing"
    ),
):
    """Restore your mental context for a project. The core command."""
    ensure_dirs()
    cwd = _resolve_cwd(path)
    if not path:
        cwd = _pick_project(cwd)

    if force:
        _require_api_key()
        display.show_progress("Syncing sessions…")
        digest = sync.full_sync(cwd, progress=display.show_progress)
        if not digest:
            display.show_error(f"No AI sessions found for {cwd}")
            raise typer.Exit(1)
    else:
        row = store.get_digest(cwd)
        if row:
            display.show_restore(cwd, row["digest_text"], row["generated_at"])
            return
        # no cached digest — sync now
        _require_api_key()
        display.show_progress(f"No cached digest found. Syncing {cwd}…")
        digest = sync.full_sync(cwd, progress=display.show_progress)
        if not digest:
            display.show_error(
                f"No AI sessions found for {cwd}.\n"
                "Make sure you've worked on this project with Claude Code or Codex."
            )
            raise typer.Exit(1)

    row = store.get_digest(cwd)
    if row:
        display.show_restore(cwd, row["digest_text"], row["generated_at"])


@app.command()
def sync_cmd(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
    all_sessions: bool = typer.Option(
        False, "--all", help="Summarize all sessions, not just the most recent"
    ),
    sessions: int = typer.Option(
        2, "--sessions", "-n", help="Number of recent sessions to summarize via API"
    ),
):
    """Sync sessions and regenerate digest for a project.

    By default summarizes the 2 most recent sessions + all compaction summaries (free).
    Also pulls last 5 git commits and top 3 open GitHub issues.
    Use --all to process every session (more thorough, more tokens).
    """
    _require_api_key()
    ensure_dirs()
    cwd = _resolve_cwd(path)
    if not path:
        cwd = _pick_project(cwd)
    limit = 999 if all_sessions else sessions
    display.show_progress(f"Syncing {cwd}…")
    digest = sync.full_sync(cwd, progress=display.show_progress, session_limit=limit)
    if digest:
        display.show_success("Digest ready. Run `mind restore` to view.")
    else:
        display.show_error("No sessions found for this project.")
        raise typer.Exit(1)


# register with the name "sync" (not "sync-cmd")
app.registered_commands[-1].name = "sync"


@app.command()
def ls():
    """List all indexed projects."""
    ensure_dirs()
    projects = store.list_projects()
    display.show_project_list(projects)


@app.command()
def note(
    text: str = typer.Argument(..., help="Note to append to this project"),
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Project path (default: cwd)"
    ),
):
    """Add a manual note to a project's context."""
    ensure_dirs()
    cwd = _resolve_cwd(path)
    existing = store.get_notes(cwd)
    current = existing["notes"] if existing else ""
    from datetime import datetime

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    updated = (
        current + f"\n[{timestamp}] {text}" if current else f"[{timestamp}] {text}"
    )
    store.upsert_notes(cwd, updated)
    display.show_success(f"Note saved for {Path(cwd).name}.")


@app.command()
def notes(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
):
    """Show manual notes for a project."""
    ensure_dirs()
    cwd = _resolve_cwd(path)
    row = store.get_notes(cwd)
    if row:
        from rich.console import Console

        Console().print(row["notes"])
    else:
        display.show_progress('No notes yet. Use `mind note "your note"` to add one.')


@app.command()
def open_project(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
):
    """Open project in Claude Code with context pre-loaded (copies restore brief to clipboard)."""
    ensure_dirs()
    cwd = _resolve_cwd(path)
    row = store.get_digest(cwd)
    if not row:
        display.show_error("No digest cached. Run `mind sync` first.")
        raise typer.Exit(1)

    # copy to clipboard
    try:
        proc = subprocess.run(
            ["pbcopy"], input=row["digest_text"].encode(), capture_output=True
        )
        if proc.returncode == 0:
            display.show_success("Restore brief copied to clipboard.")
        display.show_progress("Paste it as your first message in Claude Code.")
    except Exception:
        pass

    # open claude code
    try:
        subprocess.Popen(["claude", "--dangerously-skip-permissions"], cwd=cwd)
        display.show_success(f"Launched Claude Code in {cwd}")
    except FileNotFoundError:
        display.show_progress(f"cd {cwd} && claude")


app.registered_commands[-1].name = "open"


@app.command()
def diff(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
):
    """Show what changed since the last sync — commits, files, and open status."""
    ensure_dirs()
    cwd = _resolve_cwd(path)
    row = store.get_digest(cwd)
    if not row:
        display.show_error("No digest cached. Run `mind sync` first.")
        raise typer.Exit(1)

    from .adapters.project_files import _run

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

    # commits since synced_commit
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
        t = Table(box=rbox.SIMPLE, show_header=True, header_style="dim", padding=(0, 1))
        t.add_column("commit", style="yellow", no_wrap=True, min_width=7, max_width=7)
        t.add_column("message", style="white")
        t.add_column("author", style="dim", no_wrap=True)
        t.add_column("when", style="dim", no_wrap=True)
        for h, msg, author, when in commits:
            t.add_row(h, msg[:72], author, when)
        c.print(t)
    else:
        c.print("  [dim]No new commits since last sync.[/dim]\n")

    # files changed since synced_commit
    files_out = _run(
        ["git", "diff", "--stat", f"{since}..HEAD"],
        cwd=cwd,
    )
    if files_out:
        c.print("  [dim]Changed files[/dim]")
        for line in files_out.splitlines():
            c.print(f"  [dim]{line}[/dim]")
        c.print()

    # uncommitted changes
    status_out = _run(["git", "status", "--short"], cwd=cwd)
    status = [l for l in status_out.splitlines() if l.strip()]
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


@app.command()
def share(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
    output: Optional[str] = typer.Option(
        None, "--out", "-o", help="Write to file instead of stdout"
    ),
    no_clip: bool = typer.Option(False, "--no-clip", help="Skip clipboard copy"),
):
    """Export a clean handoff brief — stdout, clipboard, or file.

    Useful for handing off to a teammate or pasting into a new AI session.
    The brief includes the full digest plus a timestamp and project path header.
    """
    ensure_dirs()
    cwd = _resolve_cwd(path)
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


@app.command()
def config():
    """Show config file path and current settings."""
    ensure_dirs()
    from rich import box as rbox
    from rich.console import Console
    from rich.table import Table

    c = Console()
    c.print(f"\n[bold cyan]Config file:[/bold cyan] {CONFIG_FILE}\n")

    cfg = get_config()
    t = Table(box=rbox.SIMPLE, show_header=False)
    t.add_column("key", style="dim")
    t.add_column("value", style="white")
    key_status = "[green]set[/green]" if cfg.get("api_key") else "[red]not set[/red]"
    t.add_row("API key (env)", key_status)
    t.add_row("base_url", cfg.get("base_url") or "[dim]default (Anthropic)[/dim]")
    t.add_row("model", cfg.get("model", ""))
    t.add_row("session_card_max_tokens", str(cfg.get("session_card_max_tokens", "")))
    t.add_row("digest_max_tokens", str(cfg.get("digest_max_tokens", "")))
    c.print(t)
    c.print("[dim]API key: export ANTHROPIC_API_KEY=... or OPENAI_API_KEY=...[/dim]")
    c.print(f"[dim]Settings: open {CONFIG_FILE}[/dim]\n")


@app.command()
def init():
    """Interactive setup wizard — run once after installing."""

    import yaml
    from rich.console import Console
    from rich.prompt import Confirm, Prompt

    c = Console()
    ensure_dirs()

    c.print("\n[bold cyan]⟳ mind setup wizard[/bold cyan]\n")

    # --- API key guidance ---
    cfg = get_config()
    if cfg.get("api_key"):
        c.print("[green]✓[/green] API key detected in environment.\n")
    else:
        c.print("[yellow]No API key found in environment.[/yellow]")
        c.print("mind reads the key from your shell — never stores it on disk.\n")

        provider = Prompt.ask(
            "  Which provider?",
            choices=["anthropic", "openrouter", "other"],
            default="anthropic",
        )

        if provider == "anthropic":
            c.print("\n  Add this to [bold]~/.zshrc[/bold]:")
            c.print("  [bold green]export ANTHROPIC_API_KEY=sk-ant-...[/bold green]")
            c.print("  Then run: [bold]source ~/.zshrc[/bold]\n")
        elif provider == "openrouter":
            c.print("\n  Add this to [bold]~/.zshrc[/bold]:")
            c.print("  [bold green]export OPENAI_API_KEY=sk-or-...[/bold green]")
            c.print("  Then set base_url below.\n")
        else:
            c.print("\n  Export ANTHROPIC_API_KEY or OPENAI_API_KEY in your shell.\n")

    # --- Load existing config ---
    existing: dict = {}
    if CONFIG_FILE.exists():
        try:
            existing = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            existing.pop("api_key", None)
        except Exception:
            pass

    # --- base_url ---
    current_url = existing.get("base_url", "")
    use_openrouter = Confirm.ask(
        "  Use a custom base_url? (OpenRouter, local Ollama, etc.)",
        default=bool(current_url),
    )
    if use_openrouter:
        base_url = Prompt.ask(
            "  base_url",
            default=current_url or "https://openrouter.ai/api/v1",
        )
    else:
        base_url = ""

    # --- model ---
    default_model = existing.get("model", "claude-haiku-4-5-20251001")
    model = Prompt.ask("  Model", default=default_model)

    # --- write config ---
    new_cfg = {
        "base_url": base_url,
        "model": model,
        "session_card_max_tokens": existing.get("session_card_max_tokens", 800),
        "digest_max_tokens": existing.get("digest_max_tokens", 1200),
    }

    header = (
        "# mind configuration\n"
        "# API key is read from environment only — never put it here.\n"
        "#   export ANTHROPIC_API_KEY=sk-ant-...   (Anthropic)\n"
        "#   export OPENAI_API_KEY=sk-or-...        (OpenRouter / compatible)\n\n"
    )
    CONFIG_FILE.write_text(header + yaml.dump(new_cfg, default_flow_style=False))
    c.print(f"\n[green]✓[/green] Config saved to [bold]{CONFIG_FILE}[/bold]")

    # --- shell rc suggestion ---
    zshrc = Path.home() / ".zshrc"
    if zshrc.exists() and "ANTHROPIC_API_KEY" not in zshrc.read_text():
        c.print(
            "\n[dim]Tip: add your API key export to ~/.zshrc so it's always available.[/dim]"
        )

    # --- detect projects ---
    c.print("\n[bold]Scanning for projects with AI sessions…[/bold]")
    from .adapters import claude_code as cc

    found = []
    if cc.CLAUDE_PROJECTS_DIR.exists():
        for d in cc.CLAUDE_PROJECTS_DIR.iterdir():
            if d.is_dir() and list(d.glob("*.jsonl")):
                cwd = cc._decode_project_dir(d.name)
                if Path(cwd).exists():
                    found.append(cwd)

    if found:
        c.print(
            f"  Found [bold]{len(found)}[/bold] project(s) with Claude Code sessions."
        )
        if Confirm.ask("  Sync them all now? (requires API key in env)", default=False):
            _require_api_key()
            for cwd in found[:10]:
                c.print(f"\n  → {cwd}")
                try:
                    sync.full_sync(
                        cwd, progress=lambda m: c.print(f"    [dim]{m}[/dim]")
                    )
                    display.show_success(f"Synced {Path(cwd).name}")
                except Exception as e:
                    display.show_error(f"Failed: {e}")
    else:
        c.print("  No existing Claude Code projects found.")

    c.print(
        "\n[bold cyan]Done.[/bold cyan] "
        "Run [bold]mind ls[/bold] to see projects, "
        "[bold]mind restore <path>[/bold] to load context.\n"
    )


if __name__ == "__main__":
    app()
