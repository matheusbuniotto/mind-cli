# Contributing to mind

## Dev setup

```bash
git clone https://github.com/matheusbuniotto/mind-cli
cd mind-cli
uv sync --all-groups          # installs deps + dev deps (pytest, ruff)
uv tool install . --editable  # editable install so `mind` picks up local changes
```

Verify:

```bash
mind --version
uv run pytest tests/ -v
uv run ruff check mind/ tests/
```

## Local installer test

To test the public installer flow without changing the script URL:

```bash
sh ./install.sh
```

The script should install `uv` only when missing, install `mind-cli` through `uv tool install`, print `mind --version`, and end with `mind init` as the next step.

## Running tests

```bash
uv run pytest tests/ -v          # all tests
uv run pytest tests/test_claude_code_adapter.py -v  # one module
```

Fixtures live in `tests/fixtures/` as JSONL files — add new ones there when writing adapter tests.

## Adding a new adapter

1. Create `mind/adapters/<source>.py` implementing the `SessionAdapter` protocol from `mind/adapters/base.py`:

   ```python
   class MySourceAdapter:
       name = "my-source"

       def discover(self, cwd: str) -> list[SessionRef]: ...
       def active_context(self, cwd: str, sessions, *, max_chars) -> list[str]: ...
       def card_candidates(self, cwd, sessions, *, session_limit) -> list[SessionCardCandidate]: ...
       def inspect_stats(self, cwd, sessions, *, session_limit) -> AdapterInspectStats: ...
   ```

2. Register it in `mind/adapters/registry.py` by adding it to the list in `get_adapters()`.

3. Add a fixture JSONL in `tests/fixtures/` and a `tests/test_<source>_adapter.py` following the pattern in `test_claude_code_adapter.py`.

Third-party adapters (outside this repo) can register via the `mind.adapters` entry-point group:

```toml
[project.entry-points."mind.adapters"]
my-source = "my_package.adapters:MySourceAdapter"
```

See `mind/adapters/base.py` for the full contract and `ADAPTERS.md` for design notes.

## Project structure

```
mind/
  adapters/       # one file per session source
    base.py       # SessionAdapter protocol + shared dataclasses
    registry.py   # built-in list + entry-point loader
  commands/       # one file per CLI command group
  display.py      # all Rich TUI rendering
  store.py        # SQLite access (digests, session cards, notes)
  sync.py         # orchestration: discover → card candidates → digest
  check.py        # staleness checks for SessionStart hooks (no LLM)
tests/
  fixtures/       # sample JSONL files for adapter tests
```

## Pull requests

- Keep PRs focused — one concern per PR.
- All tests must pass (`uv run pytest tests/`).
- Lint must pass (`uv run ruff check mind/ tests/`).
- New adapters need at least one fixture and one test class.

## Releases

Release tags follow the `vX.Y.Z` pattern.

Before tagging a release:

```bash
uv sync --all-groups --locked
uv run ruff check mind tests
uv run pytest -q
uv build
```

The release workflow publishes the source and wheel artifacts from `dist/` to PyPI via GitHub trusted publishing, then mirrors them to GitHub Releases.
Before the first release, configure the PyPI trusted publisher for this repository so the workflow can exchange GitHub's OIDC token without storing a long-lived API token in the repo.
See `RELEASING.md` for the exact first-release checklist and commands.

## Good first issues

- Add a Cursor session adapter test with a fixture JSONL.
- Add a `mind update` command that re-runs `uv tool install`.
- Add a `--json` flag to `mind ls` for scripting.
- Improve the `_decode_project_dir` function to handle paths with hyphens (currently ambiguous).
