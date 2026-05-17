"""Extract static context from a project directory."""

import subprocess
from collections import Counter
from pathlib import Path


def _read_file(path: Path, max_chars: int = 3000) -> str:
    try:
        return path.read_text(errors="ignore")[:max_chars]
    except Exception:
        return ""


def _run(cmd: list[str], cwd: str, timeout: int = 8) -> str:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _gh_issues(cwd: str, n: int = 3) -> str:
    out = _run(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "open",
            "--limit",
            str(n),
            "--json",
            "number,title,updatedAt",
            "--template",
            '{{range .}}#{{.number}} {{.title}} (updated {{.updatedAt | timeago}}){{"\n"}}{{end}}',
        ],
        cwd=cwd,
    )
    if not out:
        out = _run(
            ["gh", "issue", "list", "--state", "open", "--limit", str(n)], cwd=cwd
        )
    return out


def git_snapshot(cwd: str, commits: int = 5, hotfiles_commits: int = 20) -> dict:
    """Return deterministic git data — no AI, no API cost.

    Keys:
      commits      list of dicts {hash, subject, author, date}
      hotfiles     list of (filepath, change_count) sorted desc
      status       list of 'XY path' strings (uncommitted changes)
      issues       raw text of open GH issues (empty if no gh/remote)
    """
    # --- commits ---
    log_out = _run(
        [
            "git",
            "log",
            "--no-merges",
            f"-{commits}",
            "--pretty=format:%h\t%s\t%an\t%ar",
        ],
        cwd=cwd,
    )
    commit_list = []
    for line in log_out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            commit_list.append(
                {
                    "hash": parts[0],
                    "subject": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                }
            )

    # --- hotfiles: files changed most often across last N commits ---
    files_out = _run(
        [
            "git",
            "log",
            "--no-merges",
            f"-{hotfiles_commits}",
            "--name-only",
            "--pretty=format:",
        ],
        cwd=cwd,
    )
    file_counts: Counter = Counter(f for f in files_out.splitlines() if f.strip())
    hotfiles = file_counts.most_common(8)

    # --- uncommitted changes ---
    status_out = _run(["git", "status", "--short"], cwd=cwd)
    status = [l for l in status_out.splitlines() if l.strip()]

    # --- GH issues ---
    issues = _gh_issues(cwd, n=3)

    return {
        "commits": commit_list,
        "hotfiles": hotfiles,
        "status": status,
        "issues": issues,
    }


def extract_project_context(cwd: str) -> str:
    """Text block fed into the AI digest (static docs + session signals)."""
    root = Path(cwd)
    parts = []

    for name in ["README.md", "CLAUDE.md", "AGENTS.md"]:
        p = root / name
        if p.exists():
            parts.append(f"=== {name} ===\n{_read_file(p)}")

    spec_log = root / ".spec" / "log.md"
    if spec_log.exists():
        text = _read_file(spec_log, max_chars=999_999)
        parts.append(f"=== .spec/log.md (tail) ===\n{text[-3000:]}")

    memory_dir = Path.home() / ".claude" / "projects" / cwd.replace("/", "-") / "memory"
    if memory_dir.exists():
        for md in sorted(memory_dir.glob("*.md"))[:5]:
            parts.append(f"=== memory/{md.name} ===\n{_read_file(md)}")

    snap = git_snapshot(cwd)

    if snap["commits"]:
        lines = [
            f"{c['hash']} {c['subject']} ({c['author']}, {c['date']})"
            for c in snap["commits"]
        ]
        parts.append("=== last 5 commits ===\n" + "\n".join(lines))

    if snap["hotfiles"]:
        lines = [f"{f} ({n}x)" for f, n in snap["hotfiles"]]
        parts.append(
            "=== most touched files (last 20 commits) ===\n" + "\n".join(lines)
        )

    if snap["status"]:
        parts.append("=== git status ===\n" + "\n".join(snap["status"]))

    if snap["issues"]:
        parts.append(f"=== open GitHub issues (top 3) ===\n{snap['issues']}")

    return "\n\n".join(parts)
