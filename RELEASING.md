# Releasing mind

This project publishes tagged releases to PyPI through GitHub Actions trusted publishing, then mirrors the built artifacts to GitHub Releases.

## One-time PyPI setup

For the first public release of `mind-cli`, configure a **pending trusted publisher** on PyPI:

1. Sign in to PyPI.
2. Open your account menu, then `Publishing`.
3. Add a new GitHub publisher with:
   - PyPI project name: `mind-cli`
   - GitHub owner: `matheusbuniotto`
   - GitHub repository: `mind-cli`
   - Workflow filename: `release.yml`
   - Environment name: `pypi`
4. In GitHub, create a repository environment named `pypi`.

Why pending publisher: it lets the first successful GitHub Actions publish create the PyPI project automatically. After first use, PyPI converts it into a normal trusted publisher.

If `mind-cli` already exists under your PyPI account before release day, use the same values above from the project's `Publishing` page instead of creating a pending publisher.

## Before the first public release

The public release should come from `main`, not from `dev` or a topic branch.

Make sure `main` contains:

- the open-source readiness work from `dev`
- the current functional fixes
- the release workflow
- the public installer
- the current README / metadata polish

## Exact first-release commands

Run these after the release changes are committed and reviewed:

```bash
git fetch origin
git switch main
git pull --ff-only origin main

uv sync --all-groups --locked
uv run ruff check mind tests
uv run pytest -q
uv build

git tag -a v0.1.0 -m "v0.1.0"
git push origin main
git push origin v0.1.0
```

If the release work is still on a reviewed topic branch instead of `main`, fast-forward `main` first:

```bash
git merge --ff-only <release-branch>
```

Pushing `v0.1.0` starts `.github/workflows/release.yml`, which will:

1. validate the build
2. publish `mind-cli` to PyPI using OIDC trusted publishing
3. create the GitHub Release with the `dist/` artifacts

## After the workflow succeeds

Verify:

```bash
uv tool install mind-cli
mind --version
uvx mind-cli --help
```

Then test the public installer path:

```bash
curl -LsSf https://raw.githubusercontent.com/matheusbuniotto/mind-cli/main/install.sh | sh
```

## If the tag already exists

Do not reuse or move a published tag.

Create the next version instead:

```bash
git tag -a v0.1.1 -m "v0.1.1"
git push origin v0.1.1
```
