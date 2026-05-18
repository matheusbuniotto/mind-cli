"""Tests for restore-brief digest validation."""

from mind.summarizer import (
    MIN_DIGEST_CHARS,
    DigestValidationError,
    validate_digest,
)


def _valid_digest() -> str:
    padding = "x" * max(0, MIN_DIGEST_CHARS - 200)
    return f"""
## Goal & Vision

Bloom helps gifted/2e adults organize knowledge. {padding}

## Current Status

- MVP step 2 in progress
- Pro gate shipped

## Active Work

- Magic-link auth serverless functions

## Next Actions

1. Finish Vercel auth endpoints
2. Wire account UI

## Key Decisions & Architecture

- Entitlements live in client hook

## Open Questions & Blockers

- None

## Notes & Ideas

- Consider Stripe later
""".strip()


class TestValidateDigest:
    def test_accepts_structured_brief(self):
        ok, issues = validate_digest(_valid_digest())
        assert ok is True
        assert issues == []

    def test_rejects_short_unstructured_output(self):
        bad = (
            "Continuing with Step 2 — Task 3: Magic-Link Auth.\n\n"
            "[TOOL_CALL]\n{tool => run}\n[/TOOL_CALL]"
        )
        ok, issues = validate_digest(bad)
        assert ok is False
        assert any("too short" in i for i in issues)
        assert any("missing section" in i for i in issues)
        assert any("TOOL_CALL" in i for i in issues)

    def test_rejects_missing_required_sections(self):
        partial = "## Goal & Vision\n\nOnly one section.\n" + ("y" * MIN_DIGEST_CHARS)
        ok, issues = validate_digest(partial)
        assert ok is False
        assert any("Current Status" in i for i in issues)

    def test_digest_validation_error_carries_issues(self):
        exc = DigestValidationError(["too short", "no headers"])
        assert exc.issues == ["too short", "no headers"]
        assert "too short" in str(exc)
