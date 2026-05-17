"""First-run diagnostics: environment, tooling, and session discovery paths."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table

from .config import CONFIG_FILE, DOTENV_FILE, ensure_dirs, get_config
from .display import show_demo_restore
from .install_agents import agent_targets
from .read_sources import format_tooling_paths

c = Console()


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _gh_authed() -> bool | None:
    if not _which("gh"):
        return None
    try:
        r = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=6,
        )
        return r.returncode == 0
    except Exception:
        return False


def _count_jsonl(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for _ in root.rglob("*.jsonl"))


def run_doctor(*, demo: bool = False) -> None:
    if demo:
        show_demo_restore()
        return

    ensure_dirs()
    cfg = get_config()
    paths = format_tooling_paths()

    c.print(
        "\n[bold cyan]mind doctor[/bold cyan]  [dim]environment & data paths[/dim]\n"
    )

    t = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    t.add_column("Check")
    t.add_column("Status")

    api_ok = bool(cfg.get("api_key"))
    t.add_row(
        "API key (resolved)",
        "[green]set[/green]" if api_ok else "[yellow]missing[/yellow]",
    )
    t.add_row(
        "api_key_source",
        str(cfg.get("api_key_source") or "env_first"),
    )
    t.add_row(
        "~/.mind/.env",
        f"[green]present[/green] {DOTENV_FILE}"
        if DOTENV_FILE.exists()
        else f"[dim]missing[/dim] {DOTENV_FILE}",
    )

    git_path = _which("git")
    t.add_row(
        "git", f"[green]{git_path}[/green]" if git_path else "[red]not found[/red]"
    )

    gh_path = _which("gh")
    gh_state = "not installed"
    if gh_path:
        authed = _gh_authed()
        if authed is True:
            gh_state = f"[green]{gh_path}[/green]  (authenticated)"
        elif authed is False:
            gh_state = f"[yellow]{gh_path}[/yellow]  (not authenticated — run [bold]gh auth login[/bold])"
        else:
            gh_state = f"[dim]{gh_path}[/dim]  (could not verify)"
    t.add_row("GitHub CLI (`gh`)", gh_state)

    cfg_exists = CONFIG_FILE.exists()
    t.add_row(
        "Config file",
        f"[green]{CONFIG_FILE}[/green]"
        if cfg_exists
        else f"[yellow]{CONFIG_FILE}[/yellow] (default will be created)",
    )

    claude_dir = Path(paths["claude_projects"])
    n_cc = _count_jsonl(claude_dir)
    t.add_row(
        "Claude Code sessions",
        f"[green]{n_cc}[/green] jsonl under {claude_dir}"
        if claude_dir.exists()
        else f"[yellow]missing[/yellow] {claude_dir}",
    )

    codex_dir = Path(paths["codex_sessions"])
    n_cx = _count_jsonl(codex_dir)
    t.add_row(
        "Codex sessions",
        f"[green]{n_cx}[/green] jsonl under {codex_dir}"
        if codex_dir.exists()
        else f"[dim]missing[/dim] {codex_dir}",
    )

    cur = Path(paths["cursor_user"])
    t.add_row(
        "Cursor app data",
        f"[green]present[/green] {cur}"
        if cur.exists()
        else f"[dim]missing[/dim] {cur}",
    )

    mind_home = Path(paths["mind_home"])
    t.add_row("mind home", str(mind_home))

    skill_paths = [
        a.skill_dir for a in agent_targets() if (a.skill_dir / "SKILL.md").is_file()
    ]
    hook_paths = [
        a.hook_script
        for a in agent_targets()
        if a.hook_script and a.hook_script.is_file()
    ]
    if skill_paths:
        t.add_row(
            "mind-recap skill",
            f"[green]installed[/green] ({len(skill_paths)} path(s))",
        )
    else:
        t.add_row(
            "mind-recap skill",
            "[yellow]not installed[/yellow] — run [bold]mind init[/bold] or [bold]mind install -y[/bold]",
        )
    if hook_paths:
        t.add_row(
            "mind session hook",
            f"[green]installed[/green] ({len(hook_paths)} script(s))",
        )
    else:
        t.add_row(
            "mind session hook",
            "[dim]not installed[/dim] — run [bold]mind init[/bold] or [bold]mind install -y[/bold]",
        )

    c.print(t)

    c.print("[bold]Suggested next step[/bold]")
    if not api_ok:
        c.print(
            "  • Add [bold]ANTHROPIC_API_KEY[/bold] or [bold]OPENAI_API_KEY[/bold] via shell exports "
            "and/or [bold]~/.mind/.env[/bold], then set [bold]api_key_source[/bold] in config.yml "
            "([bold]dotenv_first[/bold] vs [bold]env_first[/bold]). Re-run [bold]mind doctor[/bold].\n"
        )
    elif n_cc == 0 and n_cx == 0 and not cur.exists():
        c.print(
            "  • No agent sessions found yet. Open this repo in Claude Code, Codex, or Cursor, "
            "do a little work, then run [bold]mind sync[/bold] here.\n"
        )
    else:
        c.print(
            "  • Run [bold]mind sync[/bold] in your project, then [bold]mind restore[/bold]. "
            "Use [bold]mind restore --inspect[/bold] to preview what would be read without calling the model.\n"
        )

    c.print(
        "[dim]Demo output (no API, no private data):[/dim]  [bold]mind doctor --demo[/bold]\n"
    )
