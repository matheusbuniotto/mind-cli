"""Fast-gate tests that back the CI smoke workflow."""

from __future__ import annotations

import json


class TestPromptSmoke:
    def test_session_card_prompt_renders(self):
        from mind.summarizer import SESSION_CARD_PROMPT

        rendered = SESSION_CARD_PROMPT.format(text="worked on auth flow")

        assert "Session transcript:" in rendered
        assert "worked on auth flow" in rendered
        assert "{text}" not in rendered

    def test_digest_prompt_renders(self):
        from mind.summarizer import DIGEST_PROMPT

        rendered = DIGEST_PROMPT.format(
            project_name="mind",
            cwd="/tmp/mind",
            context="recent commits and notes",
        )

        assert "## Goal & Vision" in rendered
        assert "## Next Actions" in rendered
        assert "recent commits and notes" in rendered
        assert "{context}" not in rendered


class TestRetrievalHealth:
    def test_project_files_are_enumerated(self, tmp_path, monkeypatch):
        from mind import read_sources

        (tmp_path / "README.md").write_text("hello\n")

        monkeypatch.setattr(read_sources, "get_adapters", lambda: [])
        plan = read_sources.build_sync_read_plan(str(tmp_path))

        paths = {source.path for source in plan.sources}
        assert str(tmp_path / "README.md") in paths


class TestToolSchemaValidation:
    def test_adapter_registry_exposes_expected_contract(self):
        from mind.adapters.registry import get_adapters

        adapters = get_adapters()
        names = {adapter.name for adapter in adapters}

        assert {"claude-code", "codex", "cursor"} <= names
        for adapter in adapters:
            assert callable(adapter.discover)
            assert callable(adapter.active_context)
            assert callable(adapter.card_candidates)
            assert callable(adapter.inspect_stats)


class TestGuardrailTrigger:
    def test_hook_payload_is_emitted_when_digest_is_missing(self, tmp_path, monkeypatch):
        from mind import check as check_mod

        monkeypatch.setattr(check_mod.store, "get_digest", lambda cwd: None)
        result = check_mod.run_check(str(tmp_path))
        payload = check_mod.format_hook_json("codex", result)

        assert result.ok is False
        assert result.nudge is True
        assert payload is not None

        data = json.loads(payload)
        assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "no digest for this project yet" in data["systemMessage"]
