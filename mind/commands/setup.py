"""Setup and config commands."""

from __future__ import annotations

from pathlib import Path

import typer

from .. import display
from .. import sync as sync_cmd
from ..cli_helpers import require_api_key
from ..config import (
    CONFIG_FILE,
    DOTENV_FILE,
    ensure_dirs,
    get_config,
    store_mind_dotenv_api_key,
)


def init(
    no_agents: bool = typer.Option(
        False,
        "--no-agents",
        help="Skip installing skill + session hooks",
    ),
    bulk_sync: bool = typer.Option(
        False,
        "--sync",
        help="After setup, scan for Claude Code projects and optionally sync them (requires API key)",
    ),
):
    """First-time setup: config wizard + agent skill/hooks (run once after install)."""
    import yaml
    from rich.console import Console
    from rich.prompt import Confirm, Prompt

    c = Console()
    ensure_dirs()

    c.print(
        "\n[bold cyan]⟳ mind init[/bold cyan]  [dim]config + agent integrations[/dim]\n"
    )

    saved_key_to_dotenv = False
    cfg = get_config()
    if cfg.get("api_key"):
        c.print("[green]✓[/green] API key detected (shell and/or ~/.mind/.env).\n")
    else:
        c.print("[yellow]No API key found yet.[/yellow]")
        c.print(
            "mind never stores keys in [bold]config.yml[/bold]. "
            "Recommended: [bold]~/.mind/.env[/bold] (chmod 0600) or shell exports.\n"
        )

        provider = Prompt.ask(
            "  Which provider?",
            choices=["anthropic", "openrouter", "other"],
            default="anthropic",
        )

        if provider == "anthropic":
            env_var = "ANTHROPIC_API_KEY"
        elif provider == "openrouter":
            env_var = "OPENAI_API_KEY"
        else:
            env_var = Prompt.ask(
                "  Which env variable should mind write?",
                choices=["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
                default="OPENAI_API_KEY",
            )

        save = Confirm.ask(
            "  Save API key to ~/.mind/.env now? (hidden paste; file chmod 0600)",
            default=True,
        )
        if save:
            c.print(
                "[dim]Paste your key (hidden). It is not echoed, not logged, and is only written to "
                "~/.mind/.env. Leave empty to skip.[/dim]"
            )
            secret = Prompt.ask(
                "  API key",
                password=True,
                show_default=False,
            )
            if secret and secret.strip():
                try:
                    store_mind_dotenv_api_key(env_var=env_var, value=secret)
                except Exception as exc:
                    display.show_error(f"Could not write ~/.mind/.env: {exc}")
                else:
                    saved_key_to_dotenv = True
                    c.print(
                        f"\n[green]✓[/green] Saved [bold]{env_var}[/bold] to [bold]{DOTENV_FILE}[/bold] "
                        "(0600). Do not commit or screenshot this file.\n"
                    )
            else:
                c.print("[yellow]Skipped[/yellow] — empty input.\n")

        if not saved_key_to_dotenv:
            c.print("[dim]Configure manually:[/dim]")
            if provider == "anthropic":
                c.print("\n  Add this to [bold]~/.zshrc[/bold]:")
                c.print(
                    "  [bold green]export ANTHROPIC_API_KEY=sk-ant-...[/bold green]"
                )
                c.print("  Then run: [bold]source ~/.zshrc[/bold]\n")
            elif provider == "openrouter":
                c.print("\n  Add this to [bold]~/.zshrc[/bold]:")
                c.print("  [bold green]export OPENAI_API_KEY=sk-or-...[/bold green]")
                c.print("  Then set base_url below.\n")
            else:
                c.print(
                    "\n  Export ANTHROPIC_API_KEY or OPENAI_API_KEY in your shell, "
                    "or re-run init and paste into ~/.mind/.env.\n"
                )

    existing: dict = {}
    if CONFIG_FILE.exists():
        try:
            existing = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            existing.pop("api_key", None)
        except Exception:
            pass

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

    default_model = existing.get("model", "claude-haiku-4-5-20251001")
    model = Prompt.ask("  Model", default=default_model)

    api_key_source = (
        "dotenv_first"
        if saved_key_to_dotenv
        else existing.get("api_key_source", "env_first")
    )
    new_cfg = {
        "api_key_source": api_key_source,
        "base_url": base_url,
        "model": model,
        "session_card_max_tokens": existing.get("session_card_max_tokens", 800),
        "digest_max_tokens": existing.get("digest_max_tokens", 1600),
        "check": existing.get(
            "check",
            {"stale_days": 7, "commits_since_sync": 5},
        ),
    }

    header = (
        "# mind configuration\n"
        "# API keys: use shell exports and/or ~/.mind/.env (never put secrets in this file).\n"
        "#   api_key_source: env_first | dotenv_first\n"
        "#   export ANTHROPIC_API_KEY=sk-ant-...   (Anthropic)\n"
        "#   export OPENAI_API_KEY=sk-or-...        (OpenRouter / compatible)\n\n"
    )
    CONFIG_FILE.write_text(header + yaml.dump(new_cfg, default_flow_style=False))
    c.print(f"\n[green]✓[/green] Config saved to [bold]{CONFIG_FILE}[/bold]")

    zshrc = Path.home() / ".zshrc"
    if (
        not saved_key_to_dotenv
        and zshrc.exists()
        and "ANTHROPIC_API_KEY" not in zshrc.read_text()
    ):
        c.print(
            "\n[dim]Tip: add your API key export to ~/.zshrc, or create ~/.mind/.env instead.[/dim]"
        )

    if not no_agents:
        from ..install_agents import (
            detect_installed_agents,
            resolve_agents,
            run_install,
        )

        targets = resolve_agents(None, all_agents=False, auto_detect=True)
        if not targets:
            targets = resolve_agents(
                ["claude-code", "cursor", "codex", "agents"],
                all_agents=False,
                auto_detect=False,
            )

        c.print("\n[bold]Agent integrations[/bold] [dim](optional)[/dim]")
        c.print(
            "  mind can install two extras that work silently in the background:\n"
            "  • [bold]mind-recap skill[/bold]  — lets your agent run [bold]mind restore[/bold] "
            "when you ask for a recap\n"
            "  • [bold]session hook[/bold]      — checks at session start if context is stale "
            "(no LLM, ~10ms)\n"
        )
        for t in targets:
            skill_path = f"[dim]{t.skill_dir}[/dim]"
            hook_path = (
                f"[dim]{t.hook_script}[/dim]" if t.hook_script else "[dim]n/a[/dim]"
            )
            c.print(f"  [cyan]{t.label}[/cyan]")
            c.print(f"    skill → {skill_path}")
            if t.hook_script:
                c.print(f"    hook  → {hook_path}")

        c.print(
            "\n  [dim]Skip now and install later with:[/dim] [bold]mind install -y[/bold]"
        )
        c.print(
            "  [dim]Skill only (no hook):[/dim] "
            "[bold]npx skills add matheusbuniotto/skills-library --skill mind-recap[/bold]\n"
        )

        do_install = Confirm.ask("  Install integrations now?", default=True)
        if do_install:
            try:
                run_install(
                    skill=True, hook=True, agents=targets, method="copy", dry_run=False
                )
                c.print(
                    f"\n  [green]✓[/green] Installed for: "
                    f"{', '.join(detect_installed_agents()) or 'default agent paths'}\n"
                )
            except FileNotFoundError as exc:
                display.show_error(str(exc))
                c.print(
                    "  [dim]Reinstall mind from the repo, then run[/dim] [bold]mind install -y[/bold]\n"
                )
        else:
            c.print(
                "  [dim]Skipped — run [bold]mind install -y[/bold] whenever you're ready.[/dim]\n"
            )

    if bulk_sync:
        c.print("[bold]Scanning for projects with AI sessions…[/bold]")
        from ..adapters import claude_code as cc

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
            if Confirm.ask(
                "  Sync them all now? (requires API key in env)", default=False
            ):
                require_api_key()
                for cwd in found[:10]:
                    c.print(f"\n  → {cwd}")
                    try:
                        sync_cmd.full_sync(
                            cwd, progress=lambda m: c.print(f"    [dim]{m}[/dim]")
                        )
                        display.show_success(f"Synced {Path(cwd).name}")
                    except Exception as exc:
                        display.show_error(f"Failed: {exc}")
        else:
            c.print("  No existing Claude Code projects found.")

    c.print(
        "\n[bold cyan]Done.[/bold cyan] "
        "Run [bold]mind restore[/bold] in a project. "
        "Refresh agents after upgrades: [bold]mind install -y[/bold]\n"
    )


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
    t.add_row("API key (resolved)", key_status)
    t.add_row("api_key_source", str(cfg.get("api_key_source") or "env_first"))
    dotenv_status = (
        f"[green]present[/green] {DOTENV_FILE}"
        if DOTENV_FILE.exists()
        else f"[dim]missing[/dim] {DOTENV_FILE}"
    )
    t.add_row("~/.mind/.env", dotenv_status)
    t.add_row("base_url", cfg.get("base_url") or "[dim]default (Anthropic)[/dim]")
    t.add_row("model", cfg.get("model", ""))
    t.add_row("session_card_max_tokens", str(cfg.get("session_card_max_tokens", "")))
    t.add_row("digest_max_tokens", str(cfg.get("digest_max_tokens", "")))
    c.print(t)
    c.print(
        "[dim]API keys: shell env and/or ~/.mind/.env (+ optional <project>/.env). "
        "See api_key_source in config.yml.[/dim]"
    )
    c.print(f"[dim]Settings: open {CONFIG_FILE}[/dim]\n")


def register_init(app: typer.Typer) -> None:
    app.command()(init)


def register_config(app: typer.Typer) -> None:
    app.command()(config)
