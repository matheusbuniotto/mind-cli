---
name: mind-recap
description: >-
  Restore project context with the mind CLI — recap, catch-up, handoff, or
  "where was I" after time away. Use when the user wants a project recap,
  session continuity, or to resume work on a repo.
---

# mind — project recap

Use the **`mind`** CLI (must be on `PATH`) to restore narrative context from Claude Code, Codex, and Cursor sessions plus git state.

## When to use

- User asks for a **recap**, **catch-up**, **handoff**, **where was I**, or **restore context**
- Returning to a repo after days away
- Switching between Claude, Codex, or Cursor on the same project

## Steps

1. Resolve the project directory (usually the git repo root / cwd).

2. Run restore (no API if a digest is cached):

   ```bash
   mind restore
   mind restore /path/to/project
   ```

3. Read the output. Prefer **Restore Highlights** (goal, in progress, next, blockers) when summarizing for the user.

4. If restore says there is **no cached digest**, or the user wants a **fresh** brief, **ask once** before spending API tokens:

   > No mind digest (or it's stale). Run `mind sync` to capture sessions and rebuild? (~1 API call)

   Only run `mind sync` after explicit confirmation.

5. Optional exports:

   ```bash
   mind share              # markdown handoff
   mind diff               # git since last sync
   mind restore --inspect  # what would be read, no model
   ```

## Rules

- **Never** run `mind sync` without user confirmation (cost + privacy).
- **Never** invent project state — use `mind restore` output and live git facts.
- If `mind` is missing, tell the user: `uv tool install <mind-repo-url>` then `mind init`.

## Install

**Skill only** (canonical source: [skills-library](https://github.com/matheusbuniotto/skills-library)):

```bash
npx skills add matheusbuniotto/skills-library --skill mind-recap -a claude-code -a cursor -a codex -g -y
```

**Skill + session hooks** (needs `mind` on PATH):

```bash
uv tool install <mind-repo-url>
mind init
```

Refresh after upgrading mind: `mind install -y`
