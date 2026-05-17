# mind

`mind` restores the mental state of an AI-assisted coding project after you have been away from it.

[![CI](https://img.shields.io/github/actions/workflow/status/matheusbuniotto/mind-cli/ci.yml?branch=main)](https://github.com/matheusbuniotto/mind-cli/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/matheusbuniotto/mind-cli)](https://github.com/matheusbuniotto/mind-cli/releases)

When you come back to a repo after a few days, you usually need to reconstruct:

- what the project is trying to do
- what already shipped
- what you were in the middle of
- what is blocked
- what to do next

`mind` rebuilds that picture from your real Claude Code, Codex, and Cursor history plus the repo itself, then gives you a restore brief in the terminal.

## The problem

AI coding tools remember a session. You still have to remember the project.

If you bounce between projects, context loss becomes a hidden tax: rereading diffs, reopening tabs, scanning chats, rediscovering blockers, and asking the model to infer what you already knew last week.

`mind` is for that re-entry moment.

## Who this is for

`mind` is useful if you work across several projects, return to repos after days or weeks away, or use multiple AI coding tools and keep paying the cost of reconstructing project state before you can make progress again.

## What you get

- a structured restore brief instead of a chat-log archaeology session
- one recap across Claude Code, Codex, and Cursor
- current git facts separated from AI-generated summaries
- a trust boundary you can inspect before sending anything to a model
- a compact social handoff when you want to share project status

Example workflow:

```bash
mind sync
# leave the project for a week
mind restore
```

If you just want to see the shape before using real data:

```bash
mind doctor --demo
```

## Try it

```bash
curl -LsSf https://raw.githubusercontent.com/matheusbuniotto/mind-cli/main/install.sh | sh
```

The installer adds `uv` if needed, installs `mind-cli` with `uv tool install`, then prints the next command to run.

Or install it directly:

```bash
# recommended
uv tool install mind-cli

# alternatives
uvx mind-cli --help
pip install mind-cli
```

```bash
# from source (dev / latest)
git clone https://github.com/matheusbuniotto/mind-cli
uv tool install ./mind-cli
```

```bash
mind init          # first time: config wizard + skill + hooks
# after upgrading mind:
mind install -y    # refresh skill + hooks only
```

## What it reads

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

It then builds a restore brief that answers:

1. What is this project trying to do?
2. What is already done?
3. What was in progress when work paused?
4. What should I do next?

## Built for trust

- `mind restore --inspect` shows what would be read before any model call
- the restore view separates AI summaries from live git facts
- session transcripts and project context are redacted for common secret patterns before provider calls
- API keys stay out of `config.yml`

See [Trust, privacy, and provenance](#trust-privacy-and-provenance) for the full boundary.

## Agent integrations

`mind` ships a **mind-recap** skill and a **session-start hook** that runs `mind check` (no LLM — only git/session staleness).

| Command | When |
|---------|------|
| `mind init` | First run — config wizard + install skill/hooks |
| `mind install -y` | After `uv tool install` upgrade — refresh skill/hooks only |

```bash
mind install -y               # refresh skill + hook (auto-detect agents)
mind install --skill          # skill only
mind install --hook           # hook only
mind init --no-agents         # config only, skip skill/hooks
```

| Agent | Skill path | Hook |
|-------|------------|------|
| Claude Code | `~/.claude/skills/mind-recap/` | `SessionStart` → `~/.claude/hooks/mind-check.sh` |
| Cursor | `~/.cursor/skills/mind-recap/` | `sessionStart` → `~/.cursor/hooks/mind-check.sh` |
| Codex | `~/.codex/skills/` + `~/.agents/skills/` | `SessionStart` → `~/.codex/hooks/mind-check.sh` |

**Without the `mind` CLI** — install the skill from [matheusbuniotto/skills-library](https://github.com/matheusbuniotto/skills-library):

```bash
npx skills add matheusbuniotto/skills-library --skill mind-recap -a claude-code -a cursor -a codex -g -y
```

When the user asks for a recap, the skill runs `mind restore` and asks before `mind sync`.
Hooks nudge on session start when the digest is missing, old, or git/sessions drifted (run `/hooks` in Codex to trust new hooks).

## Core commands

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

### Check context freshness (no API)

```bash
mind check
mind check --quiet    # for scripts / hooks
mind check --json
```

### Share a social brief

```bash
mind share --social
mind share --social --no-clip
```

`mind share --social` creates a compact markdown update designed for Slack, Discord, GitHub, or social posts.
It keeps only the high-signal status, next steps, blockers, and a short change summary since the last sync.

### First-run diagnostics

```bash
mind doctor
mind doctor --demo
```

`mind doctor` checks for a configured API key, `git` / `gh`, Claude Code / Codex / Cursor session directories, and your `~/.mind` layout, then prints a single suggested next step.

`--demo` prints a bundled sample restore brief so you can see the output shape before any real project data exists on disk.

## Releases

Tagged releases are built and validated in CI, published to PyPI through GitHub trusted publishing, and mirrored to GitHub Releases.
See [`RELEASING.md`](RELEASING.md) for the release process.

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

If you want to contribute, start with [`CONTRIBUTING.md`](CONTRIBUTING.md). It covers local setup, tests, linting, adapter extensions, and a short list of good first issues.

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

## Manual notes

```bash
mind note "remember to revisit this API"
mind note
mind note --clean
mind notes
```

`mind note "..."` appends a timestamped project note.
`mind note` opens an interactive menu so you can add a note, view existing notes, or delete selected notes.
`mind note --clean` deletes all notes for the project after confirmation.
`mind notes` prints the current note list.

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
