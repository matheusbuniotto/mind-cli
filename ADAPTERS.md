# Session adapters

`mind` keeps source-specific parsing inside `mind/adapters/` and keeps sync orchestration generic.

A session adapter owns three things:

1. how to discover source artifacts for a project cwd
2. how to turn active sessions into live context
3. how to turn closed sessions into card candidates

The shared contract lives in `mind/adapters/base.py`:

- `SessionRef`
- `SessionCardCandidate`
- `AdapterInspectStats`
- `SessionAdapter`

Built-ins are registered in `mind/adapters/registry.py`. Third-party packages can
register adapters through the `mind.adapters` Python entry-point group.

## Add a built-in adapter

For a new source such as `opencode`:

1. create `mind/adapters/opencode.py`
2. implement an adapter class with:
   - `discover(cwd)`
   - `active_context(cwd, sessions, max_chars=...)`
   - `card_candidates(cwd, sessions, session_limit=...)`
   - `inspect_stats(cwd, sessions, session_limit=...)`
3. register it in `mind/adapters/registry.py`
4. add fixture-based tests for the parser and card-candidate behavior

Minimal shape:

```python
from .base import AdapterInspectStats, SessionCardCandidate, SessionRef


class OpenCodeAdapter:
    name = "opencode"

    def discover(self, cwd: str) -> list[SessionRef]:
        ...

    def active_context(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        max_chars: int,
    ) -> list[str]:
        ...

    def card_candidates(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        session_limit: int,
    ) -> list[SessionCardCandidate]:
        ...

    def inspect_stats(
        self,
        cwd: str,
        sessions: list[SessionRef],
        *,
        session_limit: int,
    ) -> AdapterInspectStats:
        ...
```

## Boundary rule

Adding a new source should not require source-specific edits in:

- `mind/sync.py`
- `mind/read_sources.py`

If either file needs a new `if adapter == ...` branch, the adapter boundary is leaking.

`mind/adapters/project_files.py` is intentionally separate. It provides project context, not conversational session history.

## Publish an external adapter

A package can expose an adapter without changing the `mind` repo:

```toml
[project.entry-points."mind.adapters"]
opencode = "mind_opencode:OpenCodeAdapter"
```

The entry point should resolve to an adapter class with the same contract shown
above. `mind.adapters.registry.get_adapters()` instantiates external adapters
after the built-ins.

## Why the contract looks like this

The adapters are not identical:

- Claude Code has free compaction summaries plus normal session transcripts
- Codex has cwd-matched JSONL transcripts
- Cursor currently contributes workspace chat titles without model summarization

`SessionCardCandidate.needs_summary` lets each adapter preserve those differences without pushing special cases back into the sync engine.
