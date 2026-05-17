# mind

`mind` is a frictionless CLI context manager for AI-assisted development.

It exists to solve a specific problem: when you switch away from a project for days or weeks, you lose the project’s mental state — what was built, what was decided, what is blocked, and what should happen next. `mind` reconstructs that state in about two minutes with zero manual note-taking.

It is terminal-first, uses a Rich TUI, and is installed as a local tool with `uv tool install`.

## What it does

`mind` collects context from:

- Claude Code sessions
- Codex sessions
- Cursor workspace chat history
- recent git history
- uncommitted changes
- open GitHub issues
- project docs like `README.md`, `CLAUDE.md`, `AGENTS.md`
- `.spec/log.md`
- Claude memory files under `~/.claude/projects/.../memory`

It then builds a restore brief that is meant to answer:

1. What is this project trying to do?
2. What is already done?
3. What was in progress when work paused?
4. What should I do next?

## Current status

This repo is the active `mind` CLI.

Implemented today:

- `mind sync <project>` extracts Claude Code and Codex session cards, builds an AI digest, and caches by file hash
- `mind restore <project>` shows the digest plus a deterministic git snapshot
- default sync scope: 2 recent sessions + all compaction summaries + last 5 commits + top 3 GitHub issues
- deterministic git snapshot includes:
  - last 5 commits with hash, message, author, and relative date
  - 10 most recently edited files across recent commits, with line additions/deletions
  - uncommitted change count (use `git status` for the full list)
- config lives at `~/.mind/config.yml`
- API keys come from shell env and/or `~/.mind/.env` (+ optional `<project>/.env`), controlled by `api_key_source`
- provider base URL is configurable for OpenAI-compatible backends

## Install

This project is meant to be installed locally from the repo:

```bash
uv tool install /Users/matheus/Awesome-tools/mind
```

## Usage

### Restore context

```bash
mind restore
mind restore /path/to/project
mind restore --force
mind restore -f
mind restore --inspect
```

`restore` is the main command. If a cached digest exists, it is shown immediately. If not, `mind` performs a sync first.

`--inspect` lists the local files `mind` would read for a digest and shows whether a cached digest exists, **without** calling a model or syncing.

### Sync sessions

```bash
mind sync
mind sync /path/to/project
mind sync --all
mind sync -n 5
mind sync --inspect
```

By default, sync summarizes the 2 most recent sessions, plus all Claude compaction summaries, then regenerates the digest.

`--all` processes every discovered session instead of only the recent subset.

`--inspect` prints the same local file inventory `sync` would use, **without** writing SQLite rows or calling a model.

### First-run diagnostics

```bash
mind doctor
mind doctor --demo
```

`mind doctor` checks for a configured API key, `git` / `gh`, Claude Code / Codex / Cursor session directories, and your `~/.mind` layout, then prints a single suggested next step.

`--demo` prints a bundled sample restore brief so you can see the output shape before any real project data exists on disk.
## How the project is organized

The main code paths are small and easy to follow:

- `mind/main.py` — thin Typer app wiring
- `mind/commands/` — command handlers split by workflow area
- `mind/cli_helpers.py` — shared CLI root-detection and API-key helpers
- `mind/doctor.py` — first-run environment diagnostics
- `mind/read_sources.py` — local source enumeration for `--inspect` and provenance
- `mind/redact.py` — secret redaction before model calls
- `mind/sync.py` — session discovery, card creation, digest assembly
- `mind/summarizer.py` — AI calls for session cards and restore digests
- `mind/store.py` — SQLite storage for session cards, digests, and notes
- `mind/display.py` — Rich output for restore views and progress
- `mind/adapters/base.py` — shared session adapter contract
- `mind/adapters/registry.py` — built-in adapter registration
- `mind/adapters/claude_code.py` — Claude Code JSONL session parsing
- `mind/adapters/codex.py` — Codex JSONL session parsing
- `mind/adapters/cursor.py` — Cursor workspace storage parsing
- `mind/adapters/project_files.py` — static docs, git snapshot, and GH issue extraction
- `mind/config.py` — config file and environment loading

See `ADAPTERS.md` for the extension contract and the steps to add a new session source.

## Configuration

`mind` writes its config to:

```text
~/.mind/config.yml
```

Important rules:

- API keys are never stored in `config.yml`.
- Keys can come from **shell environment variables** and/or **dotenv files**:
  - `~/.mind/.env` (global)
  - `<project>/.env` (merged when `mind` resolves a project path)
- Set `api_key_source` in `~/.mind/config.yml`:
  - `env_first` (default) — shell wins, then dotenv files
  - `dotenv_first` — dotenv files win, then shell
- supported env vars / dotenv keys:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `MIND_BASE_URL`
  - `MIND_MODEL`

Example:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or, for an OpenAI-compatible provider
export OPENAI_API_KEY=sk-or-...
export MIND_BASE_URL=https://openrouter.ai/api/v1
export MIND_MODEL=claude-haiku-4-5-20251001
```

## Data model

`mind` stores local state in SQLite under `~/.mind/mind.db`.

Tables:

- `session_cards` — summarized session artifacts keyed by source and file hash
- `project_digests` — restore briefs for each project cwd
- `project_notes` — manual notes attached to a project

This makes repeated restores cheap: if the underlying session file has not changed, the card can be reused.

## Restore output

`mind restore` combines two layers:

1. **AI digest** — a structured brief built from sessions, docs, notes, and static context
2. **Deterministic git snapshot** — recent commits, recently edited files, dirty-tree count, and GH issues

That split matters because the AI layer restores intent, while the deterministic layer restores facts.

Each restore also prints a short **Sources & trust boundary** section that explains which artifacts came from SQLite, which project files are re-read on sync, and what is recomputed live from `git` / `gh`.
It also calls out the freshness boundary explicitly: the AI digest is cached from the last sync, while the live Git snapshot is recomputed on every restore.
The restore view now also adds a compact **Since last sync** diff and a **Restore Highlights** panel so blockers and next actions are visible before you scroll.

## Trust, privacy, and provenance

**What stays on disk locally**

- Session cards and digests in `~/.mind/mind.db` (see **Data model**).
- Optional API key material in `~/.mind/.env` and/or a project-level `.env` (never in `config.yml`).
- Your agent tools’ own session files under `~/.claude/projects`, `~/.codex/sessions`, and Cursor workspace storage.
- `mind` never writes back into those agent session files.

**What leaves your machine**

- Only the **summarization** and **digest** prompts sent to your configured provider (Anthropic by default, or an OpenAI-compatible `base_url`).
- Before those calls, `mind` applies **best-effort redaction** for common secret patterns (API keys, GitHub tokens, `Bearer` headers, AWS access key ids, PEM private-key headers, etc.). This is not a guarantee against all leaks — treat transcripts like sensitive source code.

**How to verify before you run anything costly**

- `mind sync --inspect` / `mind restore --inspect` — enumerate inputs with no model calls.
- `mind doctor` — confirm tooling and session directories exist.

## Development notes

- Python requirement: `>=3.11`
- CLI entry point: `mind = "mind.main:app"`
- depends on `typer`, `rich`, `anthropic`, `openai`, `pyyaml`, `questionary`

## Practical workflow

1. Work on a project in Claude Code, Codex, or Cursor.
2. Run `mind sync <project>` when you want to capture the current state.
3. Later, run `mind restore <project>` to recover the mental model quickly.

## Project intent

The goal is not to create a generic note-taking system.

The goal is to make project re-entry cheap enough that context loss stops being a real cost.
