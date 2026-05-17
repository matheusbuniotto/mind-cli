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
  - most touched files across recent commits
  - uncommitted changes
- config lives at `~/.mind/config.yml`
- API key is read from the environment only
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
```

`restore` is the main command. If a cached digest exists, it is shown immediately. If not, `mind` performs a sync first.

### Sync sessions

```bash
mind sync
mind sync /path/to/project
mind sync --all
mind sync -n 5
```

By default, sync summarizes the 2 most recent sessions, plus all Claude compaction summaries, then regenerates the digest.

`--all` processes every discovered session instead of only the recent subset.

## How the project is organized

The main code paths are small and easy to follow:

- `mind/main.py` — Typer CLI entry points and project root resolution
- `mind/sync.py` — session discovery, card creation, digest assembly
- `mind/summarizer.py` — AI calls for session cards and restore digests
- `mind/store.py` — SQLite storage for session cards, digests, and notes
- `mind/display.py` — Rich output for restore views and progress
- `mind/adapters/claude_code.py` — Claude Code JSONL session parsing
- `mind/adapters/codex.py` — Codex JSONL session parsing
- `mind/adapters/cursor.py` — Cursor workspace storage parsing
- `mind/adapters/project_files.py` — static docs, git snapshot, and GH issue extraction
- `mind/config.py` — config file and environment loading

## Configuration

`mind` writes its config to:

```text
~/.mind/config.yml
```

Important rules:

- API keys are never stored in the config file
- the key must come from the environment
- supported env vars:
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
2. **Deterministic git snapshot** — recent commits, hot files, status, and GH issues

That split matters because the AI layer restores intent, while the deterministic layer restores facts.

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

