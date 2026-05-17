import os
from pathlib import Path

import yaml

MIND_DIR = Path(os.environ.get("MIND_HOME", Path.home() / ".mind"))
CACHE_DIR = MIND_DIR / "cache"
PROJECTS_DIR = MIND_DIR / "projects"
CONFIG_FILE = MIND_DIR / "config.yml"

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CURSOR_USER_DIR = Path.home() / "Library" / "Application Support" / "Cursor" / "User"

_DEFAULT_CONFIG = {
    "base_url": "",  # leave empty for Anthropic; set for OpenRouter etc.
    "model": "claude-haiku-4-5-20251001",
    "session_card_max_tokens": 800,
    "digest_max_tokens": 1200,
}


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = yaml.safe_load(CONFIG_FILE.read_text()) or {}
            # drop any accidental api_key that ended up in the file
            data.pop("api_key", None)
            return {**_DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(_DEFAULT_CONFIG)


def get_config() -> dict:
    cfg = _load_config()
    # API key comes ONLY from environment
    cfg["api_key"] = (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")  # for OpenRouter / compatible providers
        or ""
    )
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
        "# API key is read from environment only — never put it here.\n"
        "#   export ANTHROPIC_API_KEY=sk-ant-...   (Anthropic)\n"
        "#   export OPENAI_API_KEY=sk-or-...        (OpenRouter / compatible)\n\n"
        'base_url: ""           # leave empty for Anthropic; e.g. https://openrouter.ai/api/v1\n'
        'model: "claude-haiku-4-5-20251001"  # any model the base_url supports\n'
        "session_card_max_tokens: 800\n"
        "digest_max_tokens: 1200\n"
    )
