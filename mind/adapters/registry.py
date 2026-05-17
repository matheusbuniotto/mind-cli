"""Session adapter registry."""

from __future__ import annotations

from importlib.metadata import entry_points

from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .cursor import CursorAdapter


def get_adapters():
    """Return built-ins plus third-party adapters registered via entry points."""
    return [
        ClaudeCodeAdapter(),
        CodexAdapter(),
        CursorAdapter(),
        *_load_external_adapters(),
    ]


def _load_external_adapters():
    """Load package-provided adapters from the `mind.adapters` entry-point group."""
    adapters = []
    for entry_point in entry_points(group="mind.adapters"):
        adapter_factory = entry_point.load()
        adapter = adapter_factory()
        adapters.append(adapter)
    return adapters
