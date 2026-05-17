"""Two-stage AI summarization: session cards → project digest.

Uses the Anthropic SDK when no base_url is set.
Falls back to the OpenAI-compatible SDK for any other provider (OpenRouter, opencode, Ollama, etc.).
"""

import hashlib
from typing import Any

from .config import get_config

_client: Any = None
_client_type: str = ""  # "anthropic" | "openai"


def _get_client():
    global _client, _client_type
    if _client is not None:
        return _client

    cfg = get_config()
    base_url = cfg.get("base_url", "").strip()

    if base_url:
        # Any custom base_url → OpenAI-compatible client
        from openai import OpenAI

        _client = OpenAI(api_key=cfg["api_key"], base_url=base_url)
        _client_type = "openai"
    else:
        import anthropic

        _client = anthropic.Anthropic(api_key=cfg["api_key"])
        _client_type = "anthropic"

    return _client


def _complete(prompt: str, max_tokens: int) -> str:
    cfg = get_config()
    client = _get_client()

    if _client_type == "openai":
        response = client.chat.completions.create(
            model=cfg["model"],
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    else:
        response = client.messages.create(
            model=cfg["model"],
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()


SESSION_CARD_PROMPT = """\
You are extracting a compact "session card" from an AI coding session transcript.
Output a SHORT card (5-10 bullet points max) covering:
• What was worked on (specific files, features, bugs)
• Key decisions made
• What was completed
• What was left unfinished or blocked
• Any important ideas mentioned

Be concrete. No filler. Skip greetings/meta-talk.

Session transcript:
{text}
"""

DIGEST_PROMPT = """\
You are creating a "mind restore brief" — a 2-minute read that restores a developer's full mental context for a project after being away for days or weeks.

Project: {project_name}
Path: {cwd}

The context below includes: session cards (AI coding sessions), compaction summaries, \
git commits, open GitHub issues, README/CLAUDE.md, and manual notes. Use all of it.

Produce a structured brief with these exact sections:

## Goal & Vision
One paragraph: what is this project trying to achieve? What problem does it solve?

## Current Status
Bullet list: what works right now? What's the last thing that was completed? \
Reference the most recent commits if relevant.

## Active Work
Bullet list: what was actively being built when the work paused? What files/features are mid-flight?

## Next Actions
Numbered list of 3-5 concrete next steps, ordered by priority. Each item should be actionable \
in under a day — specific enough that someone unfamiliar can pick it up cold. \
Draw from: unfinished threads in sessions, open GitHub issues, blockers, and TODOs mentioned. \
If a step has a clear owner or dependency, note it.

## Key Decisions & Architecture
Bullet list: important technical choices made, why they were made, what was rejected.

## Open Questions & Blockers
Bullet list: unresolved questions, blockers, open issues that are blocking progress.

## Notes & Ideas
Bullet list: manual notes, ideas mentioned, future features to explore.

Be specific. Use filenames, function names, issue numbers, commit hashes where known. \
This brief is for the developer who built it — they want details, not summaries of summaries.

--- CONTEXT ---
{context}
"""


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def summarize_session(text: str, source: str) -> str:
    """Stage 1: convert raw session text to a session card."""
    if not text.strip():
        return ""
    cfg = get_config()
    prompt = SESSION_CARD_PROMPT.format(text=text[:60_000])
    return _complete(prompt, cfg["session_card_max_tokens"])


def generate_digest(cwd: str, project_name: str, context: str) -> str:
    """Stage 2: combine session cards + project files into restore brief."""
    cfg = get_config()
    prompt = DIGEST_PROMPT.format(
        project_name=project_name,
        cwd=cwd,
        context=context[:80_000],
    )
    return _complete(prompt, cfg["digest_max_tokens"])
