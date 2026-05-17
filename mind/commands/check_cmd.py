"""mind check — stale digest nudge (no LLM)."""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

import typer

from ..check import emit_check
from ..cli_helpers import resolve_cwd


def check(
    path: Optional[str] = typer.Argument(None, help="Project path (default: cwd)"),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Only print when a nudge is needed (for hooks)",
    ),
    hook: Optional[str] = typer.Option(
        None,
        "--hook",
        help="Hook output format: claude, cursor, or auto",
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable result"),
):
    """Check if project context is stale (git + sessions). No API calls."""
    cwd = _resolve_check_cwd(path, from_hook=hook is not None)
    code = emit_check(
        cwd,
        quiet=quiet or hook is not None,
        hook_agent=hook,
        as_json=json_out,
    )
    raise typer.Exit(code)


def _resolve_check_cwd(path: Optional[str], *, from_hook: bool) -> str:
    if path:
        return resolve_cwd(path)
    for key in ("CLAUDE_PROJECT_DIR", "CURSOR_PROJECT_DIR"):
        val = os.environ.get(key)
        if val:
            return resolve_cwd(val)
    # Only read stdin when invoked as a hook (Claude/Cursor pipe JSON).
    if from_hook and not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                data = json.loads(raw)
                for field in ("cwd", "project_dir", "workspaceFolder", "projectPath"):
                    if data.get(field):
                        return resolve_cwd(str(data[field]))
        except (json.JSONDecodeError, OSError):
            pass
    return resolve_cwd(None)


def register(app: typer.Typer) -> None:
    app.command()(check)
