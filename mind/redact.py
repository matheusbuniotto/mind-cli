"""Redact likely secrets from text before sending to a model API."""

from __future__ import annotations

import re


def redact_secrets(text: str) -> str:
    """Best-effort redaction for common API keys and tokens.

    This is intentionally conservative: patterns aim to catch obvious secrets
    without mangling normal prose. False positives are acceptable for LLM-bound
    payloads because the model does not need exact secret strings.
    """
    if not text:
        return text

    patterns: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"sk-ant-api\d{2}-[\w-]{10,}", re.I), "sk-ant-api…[REDACTED]"),
        (re.compile(r"sk-ant-[\w-]{10,}", re.I), "sk-ant-…[REDACTED]"),
        (re.compile(r"sk-or-v\d-[\w-]{10,}", re.I), "sk-or-…[REDACTED]"),
        (re.compile(r"sk_live_[\w]{10,}", re.I), "sk_live_…[REDACTED]"),
        (re.compile(r"sk_test_[\w]{10,}", re.I), "sk_test_…[REDACTED]"),
        (re.compile(r"xox[baprs]-[\w-]{10,}", re.I), "xox…[REDACTED]"),
        (re.compile(r"ghp_[\w]{10,}", re.I), "ghp_…[REDACTED]"),
        (re.compile(r"github_pat_[\w_]{10,}", re.I), "github_pat_…[REDACTED]"),
        (re.compile(r"Bearer\s+[\w._=-]{12,}", re.I), "Bearer [REDACTED]"),
        (
            re.compile(r"(?i)api[_-]?key[\"']?\s*[:=]\s*[\"']?[\w._=-]{8,}"),
            "api_key=[REDACTED]",
        ),
        (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA[REDACTED]"),
        (
            re.compile(r"(?i)(BEGIN\s+(RSA|OPENSSH|EC)\s+PRIVATE\s+KEY)"),
            r"\1 [REDACTED]",
        ),
    ]

    out = text
    for rx, repl in patterns:
        out = rx.sub(repl, out)
    return out
