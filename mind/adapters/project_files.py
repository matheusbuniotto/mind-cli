"""Extract static context from a project directory."""

import subprocess
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


def _format_recent_file_change(additions: str, deletions: str) -> str:
    if additions == deletions == "-":
        return "binary"
    return f"+{additions}/-{deletions}"


def git_snapshot(
    cwd: str,
    commits: int = 5,
    recent_files_commits: int = 20,
    recent_files_limit: int = 10,
) -> dict:
    """Return deterministic git data — no AI, no API cost.

    Keys:
      commits      list of dicts {hash, subject, author, date}
      recent_files list of dicts {path, additions, deletions} in recency order
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

    # --- recent files: latest edit for each file across recent commits ---
    files_out = _run(
        [
            "git",
            "log",
            "--no-merges",
            f"-{recent_files_commits}",
            "--pretty=format:__COMMIT__",
            "--numstat",
        ],
        cwd=cwd,
    )
    recent_files = []
    seen_paths = set()
    for line in files_out.splitlines():
        if not line.strip() or line == "__COMMIT__":
            continue

        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue

        additions, deletions, path = parts
        if path in seen_paths:
            continue

        recent_files.append(
            {
                "path": path,
                "additions": additions,
                "deletions": deletions,
            }
        )
        seen_paths.add(path)

        if len(recent_files) >= recent_files_limit:
            break

    # --- uncommitted changes ---
    status_out = _run(["git", "status", "--short"], cwd=cwd)
    status = [line for line in status_out.splitlines() if line.strip()]

    # --- GH issues ---
    issues = _gh_issues(cwd, n=3)

    return {
        "commits": commit_list,
        "recent_files": recent_files,
        "status": status,
        "issues": issues,
    }


def git_diff_summary(
    cwd: str,
    base_commit: str,
    head_commit: str,
    *,
    file_limit: int = 5,
) -> dict[str, object]:
    """Compact summary of what changed between two commits."""
    if not base_commit or not head_commit or base_commit == head_commit:
        return {}

    shortstat = _run(
        ["git", "diff", "--shortstat", f"{base_commit}..{head_commit}"], cwd=cwd
    )
    files_out = _run(
        ["git", "diff", "--name-only", f"{base_commit}..{head_commit}"], cwd=cwd
    )
    files = [line for line in files_out.splitlines() if line.strip()][:file_limit]

    return {
        "shortstat": shortstat,
        "files": files,
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

    if snap["recent_files"]:
        lines = [
            f"{item['path']} "
            f"({_format_recent_file_change(item['additions'], item['deletions'])})"
            for item in snap["recent_files"]
        ]
        parts.append(
            "=== 10 most recently edited files (last 20 commits) ===\n"
            + "\n".join(lines)
        )

    if snap["status"]:
        noun = "file" if len(snap["status"]) == 1 else "files"
        parts.append(
            f"=== uncommitted changes ===\n{len(snap['status'])} {noun} changed; "
            "run `git status` for details"
        )

    if snap["issues"]:
        parts.append(f"=== open GitHub issues (top 3) ===\n{snap['issues']}")

    return "\n\n".join(parts)
