"""Tests for git snapshot parsing and display rendering."""

from unittest.mock import patch


class TestGitSnapshotParsing:
    def test_parses_commit_log(self, tmp_path):
        from mind.adapters.project_files import git_snapshot

        log_output = "abc1234\tFix auth bug\tAlice\t2 hours ago\ndef5678\tAdd tests\tBob\t1 day ago"
        numstat_output = "5\t2\tsrc/auth.py\n1\t0\ttests/test_auth.py"

        with (
            patch("mind.adapters.project_files._run") as mock_run,
            patch("mind.adapters.project_files._gh_issues", return_value=""),
        ):
            mock_run.side_effect = [
                log_output,
                numstat_output,
                "",  # git status
            ]
            snap = git_snapshot(str(tmp_path))

        assert len(snap["commits"]) == 2
        assert snap["commits"][0]["hash"] == "abc1234"
        assert snap["commits"][0]["subject"] == "Fix auth bug"
        assert snap["commits"][1]["hash"] == "def5678"

    def test_parses_recent_files(self, tmp_path):
        from mind.adapters.project_files import git_snapshot

        numstat_output = "10\t3\tsrc/main.py\n-\t-\tbinary.png\n2\t1\tsrc/utils.py"

        with (
            patch("mind.adapters.project_files._run") as mock_run,
            patch("mind.adapters.project_files._gh_issues", return_value=""),
        ):
            mock_run.side_effect = [
                "",  # git log (commits)
                numstat_output,
                "",  # git status
            ]
            snap = git_snapshot(str(tmp_path))

        assert len(snap["recent_files"]) == 3
        assert snap["recent_files"][0]["path"] == "src/main.py"
        assert snap["recent_files"][0]["additions"] == "10"
        assert snap["recent_files"][1]["additions"] == "-"  # binary

    def test_deduplicates_recent_files(self, tmp_path):
        from mind.adapters.project_files import git_snapshot

        # same file appears in two commits
        numstat_output = "5\t2\tsrc/auth.py\n__COMMIT__\n1\t0\tsrc/auth.py"

        with (
            patch("mind.adapters.project_files._run") as mock_run,
            patch("mind.adapters.project_files._gh_issues", return_value=""),
        ):
            mock_run.side_effect = ["", numstat_output, ""]
            snap = git_snapshot(str(tmp_path))

        paths = [f["path"] for f in snap["recent_files"]]
        assert paths.count("src/auth.py") == 1

    def test_parses_dirty_status(self, tmp_path):
        from mind.adapters.project_files import git_snapshot

        status_output = " M src/main.py\n?? new_file.py"

        with (
            patch("mind.adapters.project_files._run") as mock_run,
            patch("mind.adapters.project_files._gh_issues", return_value=""),
        ):
            mock_run.side_effect = ["", "", status_output]
            snap = git_snapshot(str(tmp_path))

        assert len(snap["status"]) == 2

    def test_empty_repo_returns_empty_collections(self, tmp_path):
        from mind.adapters.project_files import git_snapshot

        with (
            patch("mind.adapters.project_files._run", return_value=""),
            patch("mind.adapters.project_files._gh_issues", return_value=""),
        ):
            snap = git_snapshot(str(tmp_path))

        assert snap["commits"] == []
        assert snap["recent_files"] == []
        assert snap["status"] == []
        assert snap["issues"] == ""


class TestGitDiffSummary:
    def test_returns_empty_when_same_commit(self, tmp_path):
        from mind.adapters.project_files import git_diff_summary

        result = git_diff_summary(str(tmp_path), "abc123", "abc123")
        assert result == {}

    def test_returns_empty_when_missing_commits(self, tmp_path):
        from mind.adapters.project_files import git_diff_summary

        assert git_diff_summary(str(tmp_path), "", "abc123") == {}
        assert git_diff_summary(str(tmp_path), "abc123", "") == {}

    def test_parses_shortstat_and_files(self, tmp_path):
        from mind.adapters.project_files import git_diff_summary

        with patch("mind.adapters.project_files._run") as mock_run:
            mock_run.side_effect = [
                "3 files changed, 42 insertions(+), 7 deletions(-)",
                "src/auth.py\nsrc/utils.py\ntests/test_auth.py",
            ]
            result = git_diff_summary(str(tmp_path), "abc123", "def456")

        assert (
            result["shortstat"] == "3 files changed, 42 insertions(+), 7 deletions(-)"
        )
        assert len(result["files"]) == 3

    def test_limits_files_to_file_limit(self, tmp_path):
        from mind.adapters.project_files import git_diff_summary

        many_files = "\n".join(f"file{i}.py" for i in range(20))
        with patch("mind.adapters.project_files._run") as mock_run:
            mock_run.side_effect = ["stat", many_files]
            result = git_diff_summary(str(tmp_path), "abc", "def", file_limit=3)

        assert len(result["files"]) == 3


class TestDisplayDigestSections:
    def test_extracts_known_sections(self):
        from mind.display import _extract_digest_sections

        digest = """
## Current Status

- Feature A is done
- Working on feature B

## Next Actions

- Deploy to staging
- Update docs

## Active Work

- Refactoring auth module
"""
        sections = _extract_digest_sections(digest)

        assert "Current Status" in sections
        assert "Next Actions" in sections
        assert "Active Work" in sections
        assert "Feature A is done" in sections["Current Status"]
        assert "Deploy to staging" in sections["Next Actions"]

    def test_ignores_h1_and_h3_headers(self):
        from mind.display import _extract_digest_sections

        digest = """
# Top level heading

### Sub section

## Valid Section

- item one
"""
        sections = _extract_digest_sections(digest)
        assert "Top level heading" not in sections
        assert "Sub section" not in sections
        assert "Valid Section" in sections

    def test_strips_markdown_bullet_prefixes(self):
        from mind.display import _extract_digest_sections

        digest = """
## Next Actions

- First item
* Second item
1. Third item
"""
        sections = _extract_digest_sections(digest)
        items = sections["Next Actions"]
        assert all(not item.startswith(("-", "*")) for item in items)

    def test_empty_digest_returns_empty(self):
        from mind.display import _extract_digest_sections

        assert _extract_digest_sections("") == {}

    def test_section_with_no_bullets_is_present_but_empty(self):
        from mind.display import _extract_digest_sections

        digest = "## Empty Section\n\n## Another\n\n- item\n"
        sections = _extract_digest_sections(digest)
        assert sections.get("Empty Section") == []
        assert sections["Another"] == ["item"]
