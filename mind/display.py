"""Rich TUI display for mind restore briefs."""

from datetime import datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .read_sources import SyncReadPlan

console = Console()


def show_restore(
    cwd: str,
    digest: str,
    generated_at: str | None = None,
    *,
    provenance_md: str | None = None,
    synced_commit: str | None = None,
):
    from .adapters.project_files import _run, git_snapshot

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
    if provenance_md:
        console.print(
            Panel(
                Markdown(provenance_md),
                title="[dim]Sources & trust boundary[/dim]",
                border_style="dim",
                padding=(0, 1),
            )
        )
    current_head = _run(["git", "rev-parse", "HEAD"], cwd=cwd)
    _show_digest_freshness(synced_commit=synced_commit, current_head=current_head)
    console.print(Markdown(digest))

    # --- deterministic git section (live, no AI) ---
    snap = git_snapshot(cwd)
    _show_git_snapshot(snap)
    console.print()


def _show_digest_freshness(*, synced_commit: str | None, current_head: str) -> None:
    """Explain the cached-vs-live boundary before rendering the brief."""
    if synced_commit and current_head and synced_commit != current_head:
        console.print(
            Panel(
                "AI digest was synced at "
                f"[yellow]{synced_commit[:7]}[/yellow], but repo HEAD is now "
                f"[yellow]{current_head[:7]}[/yellow]. "
                "The live snapshot below is current; run `mind restore --force` "
                "to refresh the brief.",
                title="[yellow]Freshness[/yellow]",
                border_style="yellow",
                padding=(0, 1),
            )
        )
        return

    console.print(
        "[dim]AI digest is cached from the last sync; the live Git snapshot below is recomputed on every restore.[/dim]\n"
    )


def _show_git_snapshot(snap: dict):
    """Render live git data directly — deterministic, no AI."""
    commits = snap.get("commits", [])
    recent_files = snap.get("recent_files", [])
    status = snap.get("status", [])
    issues = snap.get("issues", "")

    if not any([commits, recent_files, status, issues]):
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

    if recent_files:
        console.print("  [dim]10 most recently edited files (last 20 commits)[/dim]")
        for item in recent_files:
            additions = item["additions"]
            deletions = item["deletions"]
            if additions == deletions == "-":
                console.print(f"  [dim]binary[/dim]  {item['path']}")
            else:
                console.print(
                    f"  [green]+{additions}[/green]/[red]-{deletions}[/red]  "
                    f"{item['path']}"
                )
        console.print()

    if status:
        console.print("  [dim]Uncommitted changes[/dim]")
        noun = "file" if len(status) == 1 else "files"
        console.print(
            f"  [yellow]{len(status)} {noun} changed[/yellow]  "
            "[dim]run `git status` for details[/dim]"
        )
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


DEMO_RESTORE_MARKDOWN = """\
## Goal & Vision

SampleCo is a CLI that turns scattered AI session history into a **two-minute re-entry brief** after time away.

## Current Status

- `mind sync` ingests Claude Code, Codex, and Cursor artifacts for a repo.
- `mind restore` prints an AI digest plus a live `git` snapshot.
- Local cache lives in `~/.mind/mind.db` (session cards + digests).

## Active Work

- Hardening first-run diagnostics (`mind doctor`).
- Adding `--inspect` so users can see **exactly which files** feed a digest.

## Next Actions

1. Run `mind doctor` after install.
2. Export `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`.
3. `mind sync` in your repo, then `mind restore`.

## Key Decisions & Architecture

- API keys stay out of `config.yml`; use shell env, `~/.mind/.env`, and/or `<project>/.env` with `api_key_source`.
- Deterministic facts (commits, status) stay separate from the AI brief.

## Open Questions & Blockers

- None in this demo — this text is bundled and **contains no private paths** from your machine.

## Notes & Ideas

- Try `mind restore --inspect` on a real project to preview reads without calling a model.
"""


def show_demo_restore():
    """Bundled sample output for onboarding demos (no API calls, no private data)."""
    console.print()
    console.print(
        Panel(
            "[bold cyan]mind restore[/bold cyan]  [dim]demo / sample output[/dim]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print(
        Panel(
            Markdown(
                "### Sources & trust boundary\n\n"
                "- **Bundled markdown** — not from your disk.\n"
                "- **Real restore** uses cached cards in `~/.mind/mind.db`, project docs, and live `git` / `gh`.\n"
                "- **Secrets** in transcripts are redacted before any model request."
            ),
            title="[dim]Sources & trust boundary[/dim]",
            border_style="dim",
            padding=(0, 1),
        )
    )
    console.print(Markdown(DEMO_RESTORE_MARKDOWN))
    console.print(
        "[dim]Below, a real restore would show a live git snapshot from your repo.[/dim]\n"
    )


def show_sync_inspect_plan(plan: SyncReadPlan, *, heading: str) -> None:
    """Print a dry-run view of local files `mind` may read for sync/digest."""
    console.print(f"\n[bold cyan]{heading}[/bold cyan]  [dim]{plan.cwd}[/dim]\n")
    console.print(
        "[dim]No model calls or `mind sync` — local enumeration of inputs.[/dim]\n"
    )
    if plan.api_window_counts:
        console.print("  [dim]Closed sessions in API window[/dim]")
        for source, count in sorted(plan.api_window_counts.items()):
            console.print(f"    [dim]{source}:[/dim] {count}")
        console.print()
    if plan.free_card_counts:
        console.print("  [dim]Free cards available[/dim]")
        for source, count in sorted(plan.free_card_counts.items()):
            console.print(f"    [dim]{source}:[/dim] {count}")
        console.print()

    by_cat: dict[str, list] = {}
    for src in plan.sources:
        by_cat.setdefault(src.category, []).append(src)

    for cat in sorted(by_cat.keys()):
        console.print(f"  [bold]{cat}[/bold]")
        t = Table(box=box.SIMPLE, show_header=True, header_style="dim", padding=(0, 1))
        t.add_column("path")
        t.add_column("bytes", justify="right", style="dim")
        t.add_column("flags", style="dim")
        for s in by_cat[cat][:200]:
            flags = []
            if s.active:
                flags.append("active")
            if s.detail:
                flags.append(s.detail)
            flag_s = ", ".join(flags) if flags else ""
            sz = "—" if s.size_bytes is None else str(s.size_bytes)
            t.add_row(s.path, sz, flag_s)
        console.print(t)
        if len(by_cat[cat]) > 200:
            console.print(f"    [dim]… {len(by_cat[cat]) - 200} more[/dim]\n")
        else:
            console.print()

    if not plan.sources:
        console.print("  [yellow]No matching sources found for this cwd.[/yellow]\n")
