"""Two-stage AI summarization: session cards → project digest.

Uses the Anthropic SDK when no base_url is set.
Falls back to the OpenAI-compatible SDK for any other provider (OpenRouter, opencode, Ollama, etc.).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .config import get_config
from .redact import redact_secrets

_client: Any = None
_client_type: str = ""  # "anthropic" | "openai"
_client_sig: tuple[str, str, str] | None = None


def _get_client(cfg: dict):
    global _client, _client_type, _client_sig
    sig = (
        cfg.get("api_key") or "",
        (cfg.get("base_url") or "").strip(),
        cfg.get("model") or "",
    )
    if _client is not None and _client_sig == sig:
        return _client

    base_url = sig[1]
    api_key = sig[0]
    if base_url:
        from openai import OpenAI

        _client = OpenAI(api_key=api_key, base_url=base_url)
        _client_type = "openai"
    else:
        import anthropic

        _client = anthropic.Anthropic(api_key=api_key)
        _client_type = "anthropic"

    _client_sig = sig
    return _client


def _complete(prompt: str, max_tokens: int, cfg: dict) -> str:
    client = _get_client(cfg)

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
One compact paragraph, max 3 sentences: what is this project trying to achieve? What problem does it solve?

## Current Status
3-5 concise bullets: what works right now? What's the last thing that was completed? \
Reference the most recent commits if relevant.

## Active Work
2-4 concise bullets: what was actively being built when the work paused? What files/features are mid-flight?

## Next Actions
Numbered list of 3-5 concrete next steps, ordered by priority. Each item should be actionable \
in under a day — specific enough that someone unfamiliar can pick it up cold. \
Draw from: unfinished threads in sessions, open GitHub issues, blockers, and TODOs mentioned. \
If a step has a clear owner or dependency, note it. Keep each item to one short paragraph.

## Key Decisions & Architecture
2-5 concise bullets: important technical choices made, why they were made, what was rejected.

## Open Questions & Blockers
0-4 concise bullets: unresolved questions, blockers, open issues that are blocking progress.

## Notes & Ideas
0-4 concise bullets: manual notes, ideas mentioned, future features to explore.
If Manual Notes exist in the context, surface the key notes here as well.

Be specific. Use filenames, function names, issue numbers, commit hashes where known. \
Prefer a complete brief over an exhaustive one: never let an early section become so verbose that later sections are cut off. \
This brief is for the developer who built it — they want details, not summaries of summaries.

--- CONTEXT ---
{context}
"""


REQUIRED_DIGEST_SECTIONS = (
    "Goal & Vision",
    "Current Status",
    "Active Work",
    "Next Actions",
)

MIN_DIGEST_CHARS = 400

_SESSION_LEAK_MARKERS = (
    "[TOOL_CALL]",
    "[/TOOL_CALL]",
    "=== ACTIVE SESSION",
)


class DigestValidationError(Exception):
    """Model output did not match the restore-brief contract."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("; ".join(issues))


def digest_section_names(text: str) -> set[str]:
    names: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"^##\s+(.+)$", line.strip())
        if match:
            names.add(match.group(1).strip())
    return names


def validate_digest(text: str) -> tuple[bool, list[str]]:
    """Return whether text looks like a structured restore brief."""
    issues: list[str] = []
    stripped = text.strip()

    if len(stripped) < MIN_DIGEST_CHARS:
        issues.append(
            f"too short ({len(stripped)} chars, expected {MIN_DIGEST_CHARS}+)"
        )

    if not re.search(r"^##\s+", stripped, re.MULTILINE):
        issues.append("no markdown section headers (## …)")

    present = digest_section_names(stripped)
    for section in REQUIRED_DIGEST_SECTIONS:
        if section not in present:
            issues.append(f"missing section: ## {section}")

    for marker in _SESSION_LEAK_MARKERS:
        if marker in text:
            issues.append(f"looks like raw session output ({marker})")
            break

    return len(issues) == 0, issues


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def summarize_session(text: str, source: str, project_cwd: str | None = None) -> str:
    """Stage 1: convert raw session text to a session card."""
    if not text.strip():
        return ""
    cfg = get_config(project_cwd=project_cwd)
    prompt = SESSION_CARD_PROMPT.format(text=redact_secrets(text[:60_000]))
    return _complete(prompt, cfg["session_card_max_tokens"], cfg)


def generate_digest(cwd: str, project_name: str, context: str) -> str:
    """Stage 2: combine session cards + project files into restore brief."""
    cfg = get_config(project_cwd=cwd)
    prompt = DIGEST_PROMPT.format(
        project_name=project_name,
        cwd=cwd,
        context=redact_secrets(context[:80_000]),
    )
    return _complete(prompt, cfg["digest_max_tokens"], cfg)
