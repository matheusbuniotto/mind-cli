"""Tests for the Claude Code session adapter."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


class TestExtractSessionText:
    def test_extracts_user_and_assistant_messages(self):
        from mind.adapters.claude_code import extract_session_text

        fixture = FIXTURES / "claude_code_session.jsonl"
        text, date = extract_session_text(fixture)

        assert "[user]" in text
        assert "[assistant]" in text
        assert "auth module" in text
        assert date == "2025-01-15"

    def test_respects_max_chars(self):
        from mind.adapters.claude_code import extract_session_text

        fixture = FIXTURES / "claude_code_session.jsonl"
        text, _ = extract_session_text(fixture, max_chars=10)

        assert len(text) <= 10

    def test_empty_file_returns_empty(self, tmp_path):
        from mind.adapters.claude_code import extract_session_text

        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        text, date = extract_session_text(empty)

        assert text == ""
        assert date == ""

    def test_malformed_lines_are_skipped(self, tmp_path):
        from mind.adapters.claude_code import extract_session_text

        f = tmp_path / "bad.jsonl"
        f.write_text("not json\n{broken\n")
        text, date = extract_session_text(f)

        assert text == ""

    def test_list_content_blocks_extracted(self):
        from mind.adapters.claude_code import extract_session_text

        fixture = FIXTURES / "claude_code_session.jsonl"
        text, _ = extract_session_text(fixture)

        assert "refactor" in text.lower() or "auth" in text.lower()


class TestExtractCompactions:
    def test_finds_compaction_summaries(self):
        from mind.adapters.claude_code import extract_compactions

        fixture = FIXTURES / "claude_code_compaction.jsonl"
        summaries = extract_compactions(fixture)

        assert len(summaries) == 1
        assert "database migration" in summaries[0]

    def test_no_compactions_returns_empty(self):
        from mind.adapters.claude_code import extract_compactions

        fixture = FIXTURES / "claude_code_session.jsonl"
        summaries = extract_compactions(fixture)

        assert summaries == []

    def test_empty_file_returns_empty(self, tmp_path):
        from mind.adapters.claude_code import extract_compactions

        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        assert extract_compactions(empty) == []


class TestDecodeProjectDir:
    def test_decodes_path(self):
        from mind.adapters.claude_code import _decode_project_dir

        assert _decode_project_dir("-Users-alice-myproject") == "/Users/alice/myproject"

    def test_decodes_simple_path_without_hyphens(self):
        from mind.adapters.claude_code import _decode_project_dir

        # The encoding is naive (/ → -), so paths with hyphens are ambiguous.
        # This tests the simple case that Claude Code itself uses.
        assert _decode_project_dir("-home-user-myproject") == "/home/user/myproject"


class TestFindProjectDirs:
    def test_finds_exact_match(self, tmp_path, monkeypatch):
        from mind.adapters import claude_code as cc

        monkeypatch.setattr(cc, "CLAUDE_PROJECTS_DIR", tmp_path)
        encoded = "/Users/alice/myproject".replace("/", "-")
        (tmp_path / encoded).mkdir()

        dirs = cc.find_project_dirs("/Users/alice/myproject")
        assert len(dirs) == 1

    def test_finds_subdir_sessions(self, tmp_path, monkeypatch):
        from mind.adapters import claude_code as cc

        monkeypatch.setattr(cc, "CLAUDE_PROJECTS_DIR", tmp_path)
        cwd = "/Users/alice/myproject"
        encoded_base = cwd.replace("/", "-")
        encoded_sub = (cwd + "/src").replace("/", "-")
        (tmp_path / encoded_base).mkdir()
        (tmp_path / encoded_sub).mkdir()

        dirs = cc.find_project_dirs(cwd)
        assert len(dirs) == 2

    def test_excludes_unrelated_dirs(self, tmp_path, monkeypatch):
        from mind.adapters import claude_code as cc

        monkeypatch.setattr(cc, "CLAUDE_PROJECTS_DIR", tmp_path)
        (tmp_path / "-Users-bob-otherproject").mkdir()

        dirs = cc.find_project_dirs("/Users/alice/myproject")
        assert dirs == []

    def test_missing_claude_dir_returns_empty(self, monkeypatch):
        from pathlib import Path

        from mind.adapters import claude_code as cc

        monkeypatch.setattr(cc, "CLAUDE_PROJECTS_DIR", Path("/nonexistent/path"))
        assert cc.find_project_dirs("/Users/alice/myproject") == []
