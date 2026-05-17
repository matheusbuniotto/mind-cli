"""Tests for the Codex session adapter."""

from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures"


class TestExtractSessionText:
    def test_extracts_cwd_from_session_meta(self):
        from mind.adapters.codex import extract_session_text

        fixture = FIXTURES / "codex_session.jsonl"
        text, date, cwd = extract_session_text(fixture)

        assert cwd == "/Users/testuser/myproject"
        assert date == "2025-01-15"

    def test_extracts_user_and_assistant_messages(self):
        from mind.adapters.codex import extract_session_text

        fixture = FIXTURES / "codex_session.jsonl"
        text, _, _ = extract_session_text(fixture)

        assert "[user]" in text
        assert "[assistant]" in text
        assert "pagination" in text

    def test_skips_xml_prefixed_user_messages(self, tmp_path):
        from mind.adapters.codex import extract_session_text

        f = tmp_path / "session.jsonl"
        f.write_text(
            '{"type":"response_item","timestamp":"2025-01-15T11:00:00Z",'
            '"payload":{"role":"user","content":[{"type":"input_text","text":"<context>system stuff</context>"}]}}\n'
        )
        text, _, _ = extract_session_text(f)
        assert text == ""

    def test_respects_max_chars(self):
        from mind.adapters.codex import extract_session_text

        fixture = FIXTURES / "codex_session.jsonl"
        text, _, _ = extract_session_text(fixture, max_chars=5)

        assert len(text) <= 5

    def test_empty_file_returns_empty(self, tmp_path):
        from mind.adapters.codex import extract_session_text

        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        text, date, cwd = extract_session_text(empty)

        assert text == ""
        assert date == ""
        assert cwd is None

    def test_malformed_lines_are_skipped(self, tmp_path):
        from mind.adapters.codex import extract_session_text

        f = tmp_path / "bad.jsonl"
        f.write_text("not json\n{broken\n")
        text, date, cwd = extract_session_text(f)

        assert text == ""
        assert cwd is None


class TestSessionsForCwd:
    def test_returns_matching_sessions(self, tmp_path, monkeypatch):
        from mind.adapters import codex as codex_adapter

        session = tmp_path / "session1.jsonl"
        session.write_text(
            '{"type":"session_meta","timestamp":"2025-01-15T10:00:00Z",'
            '"payload":{"cwd":"/Users/alice/myproject"}}\n'
        )

        monkeypatch.setattr(codex_adapter, "get_session_files", lambda: [session])
        result = codex_adapter.sessions_for_cwd("/Users/alice/myproject")

        assert session in result

    def test_excludes_other_cwds(self, tmp_path, monkeypatch):
        from mind.adapters import codex as codex_adapter

        session = tmp_path / "session1.jsonl"
        session.write_text(
            '{"type":"session_meta","timestamp":"2025-01-15T10:00:00Z",'
            '"payload":{"cwd":"/Users/bob/otherproject"}}\n'
        )

        monkeypatch.setattr(codex_adapter, "get_session_files", lambda: [session])
        result = codex_adapter.sessions_for_cwd("/Users/alice/myproject")

        assert result == []

    def test_includes_subdir_sessions(self, tmp_path, monkeypatch):
        from mind.adapters import codex as codex_adapter

        session = tmp_path / "session1.jsonl"
        session.write_text(
            '{"type":"session_meta","timestamp":"2025-01-15T10:00:00Z",'
            '"payload":{"cwd":"/Users/alice/myproject/src"}}\n'
        )

        monkeypatch.setattr(codex_adapter, "get_session_files", lambda: [session])
        result = codex_adapter.sessions_for_cwd("/Users/alice/myproject")

        assert session in result
