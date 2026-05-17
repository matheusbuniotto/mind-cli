"""Shared CLI helpers used by command modules."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import typer

from . import display
from .config import get_config
from .display import console


def resolve_cwd(path: Optional[str]) -> str:
    if path:
        return str(Path(path).expanduser().resolve())
    return str(_find_project_root(Path.cwd()))


def pick_project(detected: str) -> str:
    """When detected root differs from cwd, ask which nearby project to use."""
    import questionary

    actual = str(Path.cwd())
    if detected == actual:
        return detected

    actual_path = Path(actual)
    candidates: dict[str, str] = {}

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

    abort = "↩  cancel"
    choices = list(candidates.keys()) + [abort]

    console.print(f"\n[dim]You're in [bold]{actual}[/bold] — which project?[/dim]\n")
    choice = questionary.select(
        "Select project:",
        choices=choices,
        use_indicator=True,
        use_shortcuts=False,
    ).ask()

    if choice is None or choice == abort:
        raise typer.Exit(0)

    return candidates[choice]


def require_api_key(project_cwd: str | None = None) -> None:
    cfg = get_config(project_cwd=project_cwd)
    if not cfg.get("api_key"):
        display.show_error(
            "No API key found. Configure one of:\n"
            "  • Shell: export ANTHROPIC_API_KEY=sk-ant-...  or  OPENAI_API_KEY=...\n"
            "  • Files: ~/.mind/.env and/or <project>/.env (see README)\n"
            "  • Priority: set api_key_source in ~/.mind/config.yml to env_first or dotenv_first\n\n"
            "Add shell exports to ~/.zshrc if you want them to persist."
        )
        raise typer.Exit(1)


def _find_project_root(start: Path) -> Path:
    """Find the most likely project root from a given directory."""
    from .adapters.claude_code import find_project_dir

    candidate = start
    while True:
        if _is_project_root(candidate) and find_project_dir(str(candidate)):
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent

    git_root = _git_root(start)
    if git_root and git_root != start:
        return git_root

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
            score += 10
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
        if best_score >= 10:
            return best

    return start


def _is_project_root(path: Path) -> bool:
    return any(
        (path / marker).exists()
        for marker in [
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
