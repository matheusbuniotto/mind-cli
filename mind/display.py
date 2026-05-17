"""Rich TUI display for mind restore briefs."""

import re
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

# Catppuccin Mocha accent — used sparingly
_ACCENT = "#cba6f7"
_GREEN = "#a6e3a1"
_RED = "#f38ba8"


def show_restore(
    cwd: str,
    digest: str,
    generated_at: str | None = None,
    *,
    provenance_md: str | None = None,
    synced_commit: str | None = None,
    notes: list | None = None,
    verbose: bool = False,
):
    from .adapters.project_files import _run, git_diff_summary, git_snapshot

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
    header.append("mind restore  ", style=f"bold {_ACCENT}")
    header.append(project_name, style="bold white")
    if age:
        header.append(f"  · {age}", style="dim")

    console.print()
    console.print(Panel(header, border_style=_ACCENT, padding=(0, 2)))

    current_head = _run(["git", "rev-parse", "HEAD"], cwd=cwd)
    snap = git_snapshot(cwd)

    if verbose and provenance_md:
        console.print(
            Panel(
                Markdown(provenance_md),
                title="[dim]sources[/dim]",
                border_style="dim",
                padding=(0, 1),
            )
        )

    _show_digest_freshness(synced_commit=synced_commit, current_head=current_head)
    _show_since_last_sync(
        synced_commit=synced_commit,
        current_head=current_head,
        diff=git_diff_summary(cwd, synced_commit or "", current_head or ""),
        dirty_files=snap,
    )

    if verbose:
        # Full markdown digest — no extracted highlights, avoids duplication
        console.rule(f"[{_ACCENT}]digest[/{_ACCENT}]", style=_ACCENT)
        console.print()
        console.print(Markdown(digest))
        if notes or []:
            console.rule(f"[{_ACCENT}]notes[/{_ACCENT}]", style=_ACCENT)
            console.print()
            for row in notes or []:
                text = str(row["note_text"]).strip()
                text = re.sub(r"^\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*", "", text)
                ts = str(row["created_at"] if "created_at" in row.keys() else "")[:10]
                console.print(f"    [{_ACCENT}]·[/{_ACCENT}] [dim]{ts}[/dim]  {text}")
            console.print()
    else:
        _show_restore_highlights(digest, notes=notes or [])

    _show_git_snapshot(snap, verbose=verbose)
    console.print()


def _show_digest_freshness(*, synced_commit: str | None, current_head: str) -> None:
    if synced_commit and current_head and synced_commit != current_head:
        console.print(
            Panel(
                f"Digest at [dim]{synced_commit[:7]}[/dim], HEAD is "
                f"[dim]{current_head[:7]}[/dim]. "
                "Run `mind restore --force` to refresh.",
                title="[dim]stale[/dim]",
                border_style="dim",
                padding=(0, 1),
            )
        )


def _extract_digest_sections(digest: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for raw_line in digest.splitlines():
        line = raw_line.strip()
        header = re.match(r"^##\s+(.+)$", line)
        if header:
            current = header.group(1).strip()
            sections.setdefault(current, [])
            continue
        if not current or not line:
            continue
        bullet = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", line)
        if bullet:
            sections.setdefault(current, []).append(bullet.group(1).strip())
    return sections


def _show_restore_highlights(digest: str, *, notes: list) -> None:
    sections = _extract_digest_sections(digest)

    def render_section(label: str, items: list[str]) -> None:
        if not items:
            return
        console.print(f"  [bold white]{label}[/bold white]")
        for item in items:
            # strip markdown bold/code markers — not going through Markdown renderer
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", item)
            clean = re.sub(r"`(.+?)`", r"\1", clean)
            console.print(f"    [{_ACCENT}]·[/{_ACCENT}] {clean}")
        console.print()

    has_any = any(
        sections.get(k)
        for k in (
            "Current Status",
            "Next Actions",
            "Active Work",
            "Open Questions & Blockers",
        )
    )
    if not has_any and not notes:
        return

    console.rule(f"[{_ACCENT}]context[/{_ACCENT}]", style=_ACCENT)
    console.print()
    render_section("Status", sections.get("Current Status", []))
    render_section("Next", sections.get("Next Actions", []))
    render_section("Active", sections.get("Active Work", []))
    render_section("Blockers", sections.get("Open Questions & Blockers", []))

    if notes:
        console.print("  [bold white]Notes[/bold white]")
        for row in notes:
            text = str(row["note_text"]).strip()
            # strip baked-in [YYYY-MM-DD HH:MM] prefix if present
            text = re.sub(r"^\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*", "", text)
            ts = str(row["created_at"] if "created_at" in row.keys() else "")[:10]
            console.print(f"    [{_ACCENT}]·[/{_ACCENT}] [dim]{ts}[/dim]  {text}")
        console.print()


def _show_since_last_sync(
    synced_commit: str | None,
    current_head: str,
    diff: dict[str, object],
    dirty_files: dict,
) -> None:
    if not synced_commit:
        return

    shortstat = str(diff.get("shortstat") or "").strip()
    changed_files = diff.get("files") or []
    status = dirty_files.get("status", [])
    if not shortstat and not changed_files and not status:
        return

    lines = []
    if shortstat:
        lines.append(f"- committed: {shortstat}")
    elif current_head and synced_commit != current_head:
        lines.append("- HEAD moved (no diff stat)")

    if changed_files:
        lines.append(f"- files: {', '.join(changed_files)}")

    if status:
        noun = "file" if len(status) == 1 else "files"
        dirty_paths = [
            line[3:].strip() if len(line) > 3 else line for line in status[:5]
        ]
        lines.append(f"- uncommitted: {len(status)} {noun} ({', '.join(dirty_paths)})")

    console.print(
        Panel(
            Markdown("\n".join(lines)),
            title=f"[{_ACCENT}]since last sync[/{_ACCENT}]",
            border_style=_ACCENT,
            padding=(0, 1),
        )
    )


def _show_git_snapshot(snap: dict, *, verbose: bool = False):
    """Render live git data — deterministic, no AI."""
    commits = snap.get("commits", [])
    recent_files = snap.get("recent_files", [])
    status = snap.get("status", [])
    issues = snap.get("issues", "")

    if not any([commits, recent_files, status, issues]):
        return

    console.rule(f"[{_ACCENT}]live[/{_ACCENT}]", style=_ACCENT)
    console.print()

    if commits:
        t = Table(box=box.SIMPLE, show_header=True, header_style="dim", padding=(0, 1))
        t.add_column("commit", style="dim", no_wrap=True, min_width=7, max_width=7)
        t.add_column("message", style="white")
        t.add_column("when", style="dim", no_wrap=True)
        for c in commits:
            t.add_row(c["hash"], c["subject"][:72], c["date"])
        console.print(t)

    if recent_files:
        shown = recent_files if verbose else recent_files[:5]
        console.print("  [bold white]Recently edited[/bold white]")
        for item in shown:
            additions = item["additions"]
            deletions = item["deletions"]
            if additions == deletions == "-":
                console.print(f"    [dim]binary[/dim]  {item['path']}")
            else:
                console.print(
                    f"    [{_GREEN}]+{additions}[/{_GREEN}] [{_RED}]-{deletions}[/{_RED}]  {item['path']}"
                )
        if not verbose and len(recent_files) > 5:
            console.print(f"    [dim]… {len(recent_files) - 5} more[/dim]")
        console.print()

    if status:
        noun = "file" if len(status) == 1 else "files"
        console.print(f"  [dim]{len(status)} {noun} uncommitted[/dim]")
        console.print()

    if issues:
        console.print("  [bold white]Open issues[/bold white]")
        for line in issues.splitlines():
            console.print(f"  [{_ACCENT}]·[/{_ACCENT}]  {line}")
        console.print()


def show_project_list(projects: list[dict]):
    if not projects:
        console.print(
            "[dim]No projects indexed yet. Run [bold]mind sync <path>[/bold] to start.[/dim]"
        )
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=f"bold {_ACCENT}")
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


def show_notes(notes: list) -> None:
    t = Table(box=box.SIMPLE, show_header=True, header_style="dim", padding=(0, 1))
    t.add_column("id", style="dim", no_wrap=True, width=7)
    t.add_column("date", style="dim", no_wrap=True, width=16)
    t.add_column("note")
    for row in notes:
        short_id = str(row["id"])[:6]
        date = str(row["created_at"])[:16].replace("T", " ")
        t.add_row(short_id, date, str(row["note_text"]))
    console.print()
    console.print(t)


def show_progress(msg: str):
    console.print(f"  [dim]→ {msg}[/dim]")


def show_error(msg: str):
    console.print(f"[{_RED}]error:[/{_RED}] {msg}")


def show_success(msg: str):
    console.print(f"[{_GREEN}]✓[/{_GREEN}] {msg}")


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
            f"[bold {_ACCENT}]mind restore[/bold {_ACCENT}]  [dim]demo[/dim]",
            border_style=_ACCENT,
            padding=(0, 2),
        )
    )
    console.print(Markdown(DEMO_RESTORE_MARKDOWN))
    console.print("[dim]A real restore would show a live git snapshot below.[/dim]\n")


def show_sync_inspect_plan(plan: SyncReadPlan, *, heading: str) -> None:
    """Print a dry-run view of local files `mind` may read for sync/digest."""
    console.print(
        f"\n[bold {_ACCENT}]{heading}[/bold {_ACCENT}]  [dim]{plan.cwd}[/dim]\n"
    )
    console.print(
        "[dim]No model calls or `mind sync` — local enumeration of inputs.[/dim]\n"
    )
    if plan.api_window_counts:
        console.print("  [dim]closed sessions in API window[/dim]")
        for source, count in sorted(plan.api_window_counts.items()):
            console.print(f"    [dim]{source}:[/dim] {count}")
        console.print()
    if plan.free_card_counts:
        console.print("  [dim]free cards available[/dim]")
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
        console.print(f"  [{_RED}]No matching sources found for this cwd.[/{_RED}]\n")
