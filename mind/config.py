import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

MIND_DIR = Path(os.environ.get("MIND_HOME", Path.home() / ".mind"))
CACHE_DIR = MIND_DIR / "cache"
PROJECTS_DIR = MIND_DIR / "projects"
CONFIG_FILE = MIND_DIR / "config.yml"
DOTENV_FILE = MIND_DIR / ".env"

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CURSOR_USER_DIR = Path.home() / "Library" / "Application Support" / "Cursor" / "User"

_DEFAULT_CONFIG = {
    "base_url": "",  # leave empty for Anthropic; set for OpenRouter etc.
    "model": "claude-haiku-4-5-20251001",
    "session_card_max_tokens": 800,
    "digest_max_tokens": 1600,
    # Where API keys are resolved from:
    #   dotenv_first — ~/.mind/.env then <project>/.env, then shell env
    #   env_first      — shell env, then ~/.mind/.env then <project>/.env
    "api_key_source": "env_first",
}


def _load_yaml_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            # drop any accidental api_key that ended up in the file
            data.pop("api_key", None)
            return {**_DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(_DEFAULT_CONFIG)


def _merge_dotenv(project_cwd: str | None) -> dict[str, str]:
    """Load non-empty key/value pairs from dotenv files (does not mutate os.environ)."""
    merged: dict[str, str] = {}
    if DOTENV_FILE.exists():
        merged.update(
            {k: v for k, v in dotenv_values(DOTENV_FILE).items() if v not in (None, "")}
        )
    if project_cwd:
        p = Path(project_cwd).expanduser().resolve() / ".env"
        if p.exists():
            merged.update(
                {k: v for k, v in dotenv_values(p).items() if v not in (None, "")}
            )
    return merged


def _pick_api_key(dot: dict[str, str], source: str) -> str:
    """Resolve ANTHROPIC_API_KEY / OPENAI_API_KEY from dotenv + process env."""

    def from_env() -> str:
        return (
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )

    def from_dot() -> str:
        return dot.get("ANTHROPIC_API_KEY") or dot.get("OPENAI_API_KEY") or ""

    if source == "dotenv_first":
        return from_dot() or from_env()
    if source == "env_first":
        return from_env() or from_dot()
    # tolerate unknown values — behave like env_first
    return from_env() or from_dot()


def get_config(*, project_cwd: str | None = None) -> dict[str, Any]:
    """Return resolved config.

    ``project_cwd`` controls which project-level ``.env`` is merged (in addition to
    ``~/.mind/.env``). Pass the resolved project directory when resolving keys for
    a specific sync/restore target.
    """
    cfg = _load_yaml_config()
    source = str(cfg.get("api_key_source") or "env_first")
    dot = _merge_dotenv(project_cwd)
    cfg["api_key"] = _pick_api_key(dot, source)

    if os.environ.get("MIND_BASE_URL"):
        cfg["base_url"] = os.environ["MIND_BASE_URL"]
    if os.environ.get("MIND_MODEL"):
        cfg["model"] = os.environ["MIND_MODEL"]
    return cfg


def ensure_dirs():
    MIND_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)
    PROJECTS_DIR.mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        _write_default_config()


def _write_default_config():
    CONFIG_FILE.write_text(
        "# mind configuration\n"
        "# API keys: set api_key_source in this file, then use either shell exports or\n"
        "#   ~/.mind/.env (and optionally <project>/.env). Never put secrets in this YAML.\n"
        "#   export ANTHROPIC_API_KEY=sk-ant-...   (Anthropic)\n"
        "#   export OPENAI_API_KEY=sk-or-...        (OpenRouter / compatible)\n\n"
        'api_key_source: "env_first"  # env_first | dotenv_first\n'
        'base_url: ""           # leave empty for Anthropic; e.g. https://openrouter.ai/api/v1\n'
        'model: "claude-haiku-4-5-20251001"  # any model the base_url supports\n'
        "session_card_max_tokens: 800\n"
        "digest_max_tokens: 1600\n"
    )
