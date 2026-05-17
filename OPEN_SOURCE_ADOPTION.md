# mind — Open Source Adoption Map

This document ranks the most relevant improvements if the goal is to make `mind`
widely adopted as an open-source CLI for AI-assisted development.

## Objective

Make `mind`:

- easy to try in under 5 minutes
- trustworthy enough to leave running on real projects
- useful before any customization
- simple to contribute to
- memorable enough that people want to show it to others

## Current evidence from the repo

The current implementation already has the core value proposition:

- `mind restore` reconstructs project state from sessions, git, docs, notes, and issues
- `mind sync` caches session cards by file hash
- support exists for Claude Code, Codex, and Cursor sources
- output is terminal-first and human-readable via Rich
- config is local and environment-based for secrets

The weak spots are not the core idea; they are adoption mechanics.

## Highest-leverage improvements

### 1. First-run experience

Why it matters:

Most adoption fails before the user experiences value.

What to improve:

- add a `mind init` or `mind doctor` command
- detect missing API keys, missing `gh`, missing session directories, and missing project root markers
- print a single actionable setup path
- include a `--demo` mode with bundled sample output

Success criteria:

- a new user can install and see a useful restore flow in < 5 minutes
- failures are self-explanatory and recoverable

### 2. Trust and safety

Why it matters:

This tool reads private session data and local project state. People will not adopt it if it feels opaque.

What to improve:

- make the data sources explicit in the restore output
- add a dry-run / inspect mode that shows exactly what would be read
- document what is stored locally and what is sent to the model
- add clear redaction rules for secrets and sensitive content

Success criteria:

- users can answer “what leaves my machine?” in one minute
- restore output shows provenance for each section

### 3. Proof of value in the output

Why it matters:

The project is only viral if the output is impressive enough to share.

What to improve:

- improve the digest structure for readability and scanning
- surface “what changed since last sync” in a compact diff
- make unresolved blockers and next actions visually prominent
- include commit hashes and file names more consistently

Success criteria:

- a restore brief feels immediately useful without scrolling
- users can quote the output as a project status update

### 4. Reliability and verifiability

Why it matters:

Open source adoption depends on confidence. Right now the repo has no visible test suite.

What to improve:

- add tests for session parsing, project root detection, digest assembly, and git snapshot formatting
- add fixture-based tests for Claude/Codex/Cursor adapters
- add a CI workflow
- add a small smoke-test command that exercises `mind restore` on sample data

Success criteria:

- core behaviors are covered by automated tests
- regressions in parsing or display are caught before release

### 5. Distribution and package polish

Why it matters:

If installation is smooth, trial rates rise.

What to improve:

- publish a minimal release checklist
- add `uv tool install` guidance, plus editable-dev setup
- support `mind --version`
- ensure the package metadata is complete for PyPI

Success criteria:

- install docs are copy-paste correct
- users can install and run with no repo knowledge

### 6. Contribution surface

Why it matters:

Projects grow faster when newcomers can make a useful change quickly.

What to improve:

- add a contributor guide
- label “good first issue” work around adapter support and tests
- separate core engine code from display code more clearly
- add examples of session JSON formats and a fixture directory

Success criteria:

- a new contributor can fix or add an adapter without reading the whole codebase

### 7. Adapter extensibility

Why it matters:

The agent ecosystem will keep fragmenting. If every new source requires editing core
sync logic, `mind` will scale slowly and contributions will bottleneck on the maintainer.

What to improve:

- define a small, stable adapter interface for session sources
- split built-in adapters behind that interface instead of special-casing each source in `sync.py`
- add an adapter registry / discovery mechanism
- make it easy to add sources like `pi-agent`, `opencode`, or future tools without changing core orchestration
- document one complete “build a new adapter” example

Success criteria:

- a contributor can add a new agent source by creating one focused adapter module
- core sync/digest code does not need source-specific edits for each new integration
- built-in adapters and third-party adapters follow the same contract

## Recommended order

If I were prioritizing for adoption, I would do this in order:

1. first-run experience
2. trust and safety
3. proof of value in the output
4. adapter extensibility
5. reliability and verifiability
6. distribution and package polish
7. contribution surface

## Execution board

### Foundation already done

| Initiative | Priority | Level | Brief / plan | Status |
| --- | --- | --- | --- | --- |
| Core restore flow | P0 | L | `mind sync` + `mind restore`, session-card caching, AI digest generation | done |
| Deterministic project snapshot | P0 | M | recent commits, recently edited files, dirty-tree count, top GitHub issues | done |
| Multi-source ingestion baseline | P0 | M | Claude Code, Codex, and Cursor support wired into the current sync flow | done |

### Adoption backlog

| Order | Initiative | Priority | Level | Brief / plan | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | First-run experience | P0 | M | Add `mind doctor`, actionable setup diagnostics, and a demo path that shows value before real data exists. | done |
| 2 | Trust and safety | P0 | M | Add `--inspect` / dry-run, make data provenance visible, document storage vs model-bound data, and introduce redaction rules. | done |
| 3 | Proof of value in the output | P0 | M | Tighten the restore brief, emphasize blockers / next actions, and add a compact “changed since last sync” section. | done |
| 4 | Adapter extensibility | P1 | L | Define adapter contracts, add a registry, move built-ins behind the interface, and document how to add `pi-agent`, `opencode`, or future sources. | done |
| 5 | Reliability and verifiability | P1 | M | Add fixture-based tests for adapters and snapshots, then wire CI around the core flow. | to-do |
| 6 | Distribution and package polish | P1 | S | Add `--version`, public install docs, release checklist, and complete package metadata for broader distribution. | to-do |
| 7 | Contribution surface | P2 | S | Add `CONTRIBUTING.md`, fixture docs, and clearly scoped good-first issues for adapters and tests. | to-do |

### Status rules

- `done` — shipped and evidenced in the repo
- `doing` — actively being implemented now
- `to-do` — planned but not started

## Concrete next work items

- add fixture-based tests for the adapters and snapshot rendering
- add a CI workflow
- add a minimal contributor guide
- tighten restore output for “proof of value” (item 3)

## Notes on current gaps

The repo currently has:

- no `tests/` directory
- no CI workflow
- no visible sample output fixtures (beyond `mind doctor --demo`)

That means the core product is present, but several adoption and contribution mechanics are still missing.
