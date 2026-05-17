"""Tests for handoff and social-share formatting."""

from unittest.mock import patch


def _digest() -> str:
    return """
## Current Status

- Restore flow is working
- **Docs** are updated

## Next Actions

- Publish the package
- Announce the release

## Active Work

- Tightening onboarding

## Open Questions & Blockers

- Waiting on PyPI trusted publishing
""".strip()


class TestSocialBrief:
    def test_builds_compact_shareable_markdown(self, tmp_path):
        from mind.commands.handoff import build_social_brief

        row = {
            "digest_text": _digest(),
            "generated_at": "2026-05-17T10:00:00",
            "synced_commit": "abc123",
        }
        snap = {"status": [" M README.md"]}

        with (
            patch("mind.commands.handoff.git_snapshot", create=True),
            patch("mind.adapters.project_files._run", return_value="def456"),
            patch(
                "mind.adapters.project_files.git_diff_summary",
                return_value={
                    "shortstat": "2 files changed, 10 insertions(+)",
                    "files": ["README.md", "mind/commands/handoff.py"],
                },
            ),
            patch("mind.adapters.project_files.git_snapshot", return_value=snap),
        ):
            brief = build_social_brief(str(tmp_path), row)

        assert brief.startswith(f"# {tmp_path.name} project pulse")
        assert "## Status" in brief
        assert "- Docs are updated" in brief
        assert "## Next" in brief
        assert "## Since last sync" in brief
        assert "- Committed: 2 files changed, 10 insertions(+)" in brief
        assert "- Uncommitted: 1 file" in brief

    def test_omits_empty_sections(self, tmp_path):
        from mind.commands.handoff import build_social_brief

        row = {
            "digest_text": "## Current Status\n\n- Working",
            "generated_at": "2026-05-17T10:00:00",
            "synced_commit": "",
        }

        with (
            patch("mind.adapters.project_files._run", return_value=""),
            patch("mind.adapters.project_files.git_diff_summary", return_value={}),
            patch("mind.adapters.project_files.git_snapshot", return_value={"status": []}),
        ):
            brief = build_social_brief(str(tmp_path), row)

        assert "## Status" in brief
        assert "## Next" not in brief
        assert "## Since last sync" not in brief
