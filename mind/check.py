"""Stale-context checks for mind install hooks (no LLM)."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .adapters import claude_code as cc
from .adapters import codex as codex_adapter
from .adapters import project_files as pf
from .config import get_config


@dataclass(frozen=True)
class CheckIssue:
    code: str
    message: str


@dataclass(frozen=True)
class CheckResult:
    cwd: str
    ok: bool
    issues: tuple[CheckIssue, ...]

    @property
    def nudge(self) -> bool:
        return not self.ok and bool(self.issues)

    def summary_line(self) -> str:
        if self.ok:
            return ""
        parts = [i.message for i in self.issues]
        return "mind: " + " · ".join(parts) + " — run `mind sync` when ready."


def _check_config() -> dict:
    cfg = get_config()
    check = cfg.get("check") if isinstance(cfg.get("check"), dict) else {}
    return {
        "stale_days": int(check.get("stale_days", 7)),
        "commits_since_sync": int(check.get("commits_since_sync", 5)),
    }


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _commits_since(cwd: str, since: str | None) -> int:
    if not since:
        return 0
    out = pf._run(
        ["git", "rev-list", "--count", f"{since}..HEAD"],
        cwd=cwd,
    )
    try:
        return int(out.strip())
    except ValueError:
        return 0


def _claude_sessions_newer_than(cwd: str, cutoff: float) -> tuple[int, float]:
    count = 0
    newest: float = 0.0
    for project_dir in cc.find_project_dirs(cwd):
        for path in project_dir.glob("*.jsonl"):
            try:
                mtime = path.stat().st_mtime
                if mtime > cutoff:
                    count += 1
                    if mtime > newest:
                        newest = mtime
            except OSError:
                pass
    return count, newest


def _codex_sessions_newer_than(cwd: str, cutoff: float) -> tuple[int, float]:
    """Check recent Codex JSONL only (bounded scan)."""
    count = 0
    newest: float = 0.0
    for path in codex_adapter.get_session_files()[:50]:
        try:
            mtime = path.stat().st_mtime
            if mtime <= cutoff:
                continue
        except OSError:
            continue
        _, _, session_cwd = codex_adapter.extract_session_text(path, max_chars=0)
        if not session_cwd:
            continue
        if session_cwd == cwd or session_cwd.startswith(cwd + "/"):
            count += 1
            if mtime > newest:
                newest = mtime
    return count, newest


def _fmt_age(seconds: float) -> str:
    m = int(seconds / 60)
    if m < 60:
        return f"{m}m ago" if m > 1 else "just now"
    h = m // 60
    if h < 24:
        return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"


def _session_files_newer_than(cwd: str, since: datetime | None) -> tuple[int, str]:
    if since is None:
        return 0, ""
    cutoff = since.timestamp()
    c_count, c_newest = _claude_sessions_newer_than(cwd, cutoff)
    x_count, x_newest = _codex_sessions_newer_than(cwd, cutoff)
    count = c_count + x_count
    newest = max(c_newest, x_newest)
    if count == 0 or newest == 0.0:
        return count, ""
    age = _fmt_age(datetime.now(timezone.utc).timestamp() - newest)
    return count, age


def run_check(cwd: str) -> CheckResult:
    """Evaluate whether the user should run `mind sync` (local heuristics only)."""
    cwd = str(Path(cwd).expanduser().resolve())
    thresholds = _check_config()
    issues: list[CheckIssue] = []

    row = store.get_digest(cwd)
    if not row:
        issues.append(CheckIssue("no_digest", "no digest for this project yet"))
        return CheckResult(cwd=cwd, ok=False, issues=tuple(issues))

    generated = _parse_ts(row["generated_at"])
    if generated:
        age_days = (datetime.now(timezone.utc) - generated).days
        if age_days >= thresholds["stale_days"]:
            issues.append(
                CheckIssue(
                    "old_digest",
                    f"digest is {age_days}d old",
                )
            )

    synced = row["synced_commit"]
    n_commits = _commits_since(cwd, synced)
    if n_commits >= thresholds["commits_since_sync"]:
        issues.append(
            CheckIssue(
                "git_drift",
                f"{n_commits} commits since last sync",
            )
        )

    n_sessions, session_age = _session_files_newer_than(cwd, generated)
    if n_sessions > 0:
        label = "session" if n_sessions == 1 else "sessions"
        age_part = f", last {session_age}" if session_age else ""
        issues.append(
            CheckIssue(
                "new_sessions",
                f"{n_sessions} {label} unsynced{age_part}",
            )
        )

    return CheckResult(
        cwd=cwd,
        ok=len(issues) == 0,
        issues=tuple(issues),
    )


def format_hook_json(agent: str, result: CheckResult) -> str | None:
    if not result.nudge:
        return None
    msg = result.summary_line()
    agent = (agent or "auto").lower()
    if agent in ("claude", "claude-code", "claude_code"):
        return json.dumps({"systemMessage": msg})
    if agent in ("cursor",):
        return json.dumps(
            {
                "additional_context": msg,
                "additionalContext": msg,
            }
        )
    if agent in ("codex",):
        return json.dumps(
            {
                "systemMessage": msg,
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": msg,
                },
            }
        )
    return json.dumps(
        {
            "systemMessage": msg,
            "additional_context": msg,
            "additionalContext": msg,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": msg,
            },
        }
    )


def emit_check(
    cwd: str,
    *,
    quiet: bool = False,
    hook_agent: str | None = None,
    as_json: bool = False,
) -> int:
    result = run_check(cwd)

    if hook_agent is not None:
        payload = format_hook_json(hook_agent, result)
        if payload:
            print(payload)
        return 0

    if as_json:
        print(
            json.dumps(
                {
                    "cwd": result.cwd,
                    "ok": result.ok,
                    "issues": [
                        {"code": i.code, "message": i.message} for i in result.issues
                    ],
                    "summary": result.summary_line(),
                }
            )
        )
        return 0 if result.ok else 1

    if result.ok:
        if not quiet:
            print("mind: context looks current.")
        return 0

    line = result.summary_line()
    if quiet:
        if line:
            print(line, file=sys.stderr)
    else:
        print(line)
    return 1
