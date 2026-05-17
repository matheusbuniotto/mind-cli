"""Install mind skills and session hooks for Claude Code, Cursor, and Codex."""

from __future__ import annotations

import json
import shutil
import stat
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Literal

InstallMethod = Literal["symlink", "copy"]

SKILL_NAME = "mind-recap"
SKILLS_LIBRARY_REPO = "matheusbuniotto/skills-library"
HOOK_SCRIPT_NAME = "mind-check.sh"
MIND_HOOK_MARKER = "mind-check.sh"


@dataclass(frozen=True)
class AgentTarget:
    id: str
    label: str
    skill_dir: Path
    hook_agent: str | None = None
    hook_script: Path | None = None
    hooks_config: Path | None = None
    hook_event: str | None = None
    hook_matcher: str | None = None
    hooks_format: Literal["claude", "cursor"] = "claude"
    detect_path: Path | None = None


def _home() -> Path:
    return Path.home()


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def agent_targets() -> list[AgentTarget]:
    home = _home()
    return [
        AgentTarget(
            id="claude-code",
            label="Claude Code",
            skill_dir=home / ".claude" / "skills" / SKILL_NAME,
            hook_agent="claude",
            hook_script=home / ".claude" / "hooks" / HOOK_SCRIPT_NAME,
            hooks_config=home / ".claude" / "settings.json",
            hook_event="SessionStart",
            hooks_format="claude",
            detect_path=home / ".claude",
        ),
        AgentTarget(
            id="cursor",
            label="Cursor",
            skill_dir=home / ".cursor" / "skills" / SKILL_NAME,
            hook_agent="cursor",
            hook_script=home / ".cursor" / "hooks" / HOOK_SCRIPT_NAME,
            hooks_config=home / ".cursor" / "hooks.json",
            hook_event="sessionStart",
            hooks_format="cursor",
            detect_path=home / ".cursor",
        ),
        AgentTarget(
            id="codex",
            label="Codex",
            skill_dir=home / ".codex" / "skills" / SKILL_NAME,
            hook_agent="codex",
            hook_script=home / ".codex" / "hooks" / HOOK_SCRIPT_NAME,
            hooks_config=home / ".codex" / "hooks.json",
            hook_event="SessionStart",
            hook_matcher="startup|resume",
            hooks_format="claude",
            detect_path=home / ".codex",
        ),
        AgentTarget(
            id="agents",
            label="Open agents (~/.agents/skills, used by Codex and others)",
            skill_dir=home / ".agents" / "skills" / SKILL_NAME,
            detect_path=home / ".agents",
        ),
    ]


def bundled_skill_dir() -> Path:
    candidate = _package_root() / "integrations" / "skills" / SKILL_NAME
    if (candidate / "SKILL.md").is_file():
        return candidate
    raise FileNotFoundError(
        f"mind-recap skill not found (expected SKILL.md). Tried: {candidate}"
    )


def _hook_source_candidates() -> list[Path]:
    root = _package_root()
    return [
        root / "integrations" / "hooks" / HOOK_SCRIPT_NAME,
    ]


def bundled_hook_script() -> Path:
    for candidate in _hook_source_candidates():
        if candidate.is_file():
            return candidate
    tried = ", ".join(str(p) for p in _hook_source_candidates())
    raise FileNotFoundError(f"Hook script not found. Tried: {tried}")


def package_version() -> str:
    try:
        return metadata.version("mind-cli")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def detect_installed_agents() -> list[str]:
    found = []
    for agent in agent_targets():
        if agent.detect_path and agent.detect_path.exists():
            found.append(agent.id)
    return found


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def _symlink_skill(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.symlink_to(src.resolve(), target_is_directory=True)


def install_skill(
    agent: AgentTarget,
    *,
    method: InstallMethod,
    dry_run: bool = False,
) -> Path:
    src = bundled_skill_dir()
    dest = agent.skill_dir
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if method == "symlink":
        _symlink_skill(src, dest)
    else:
        _copy_tree(src, dest)
        (dest / ".mind-install").write_text(f"{package_version()}\n")
    return dest


def hook_command(script: Path, hook_agent: str) -> str:
    return f'"{script.resolve()}" {hook_agent}'


def _claude_hook_entry(command: str, *, matcher: str | None = None) -> dict:
    group: dict = {
        "hooks": [
            {
                "type": "command",
                "command": command,
                "statusMessage": "mind: checking project context…",
            }
        ]
    }
    if matcher:
        group["matcher"] = matcher
    return group


def _cursor_hook_entry(command: str) -> dict:
    return {"command": command}


def _merge_claude_hooks(
    settings_path: Path, command: str, event: str, *, matcher: str | None = None
) -> bool:
    data: dict = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text()) or {}
        except json.JSONDecodeError:
            data = {}
    hooks_root = data.setdefault("hooks", {})
    groups = hooks_root.setdefault(event, [])
    for group in groups:
        if matcher and group.get("matcher") != matcher:
            continue
        for handler in group.get("hooks", []):
            if MIND_HOOK_MARKER in handler.get("command", ""):
                handler["command"] = command
                settings_path.parent.mkdir(parents=True, exist_ok=True)
                settings_path.write_text(json.dumps(data, indent=2) + "\n")
                return False
    groups.append(_claude_hook_entry(command, matcher=matcher))
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2) + "\n")
    return True


def _merge_cursor_hooks(hooks_path: Path, command: str, event: str) -> bool:
    data: dict = {"version": 1, "hooks": {}}
    if hooks_path.exists():
        try:
            data = json.loads(hooks_path.read_text()) or data
        except json.JSONDecodeError:
            pass
    data.setdefault("version", 1)
    hooks_root = data.setdefault("hooks", {})
    entries = hooks_root.setdefault(event, [])
    for entry in entries:
        if MIND_HOOK_MARKER in entry.get("command", ""):
            entry["command"] = command
            hooks_path.parent.mkdir(parents=True, exist_ok=True)
            hooks_path.write_text(json.dumps(data, indent=2) + "\n")
            return False
    entries.append(_cursor_hook_entry(command))
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(json.dumps(data, indent=2) + "\n")
    return True


def install_hook(agent: AgentTarget, *, dry_run: bool = False) -> Path | None:
    if not agent.hook_script or not agent.hooks_config or not agent.hook_event:
        return None
    if not agent.hook_agent:
        return None
    src = bundled_hook_script()
    dest = agent.hook_script
    if dry_run:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    command = hook_command(dest, agent.hook_agent)
    if agent.hooks_format == "cursor":
        _merge_cursor_hooks(agent.hooks_config, command, agent.hook_event)
    else:
        _merge_claude_hooks(
            agent.hooks_config,
            command,
            agent.hook_event,
            matcher=agent.hook_matcher,
        )
    return dest


def resolve_agents(
    agent_ids: list[str] | None,
    *,
    all_agents: bool,
    auto_detect: bool,
) -> list[AgentTarget]:
    by_id = {a.id: a for a in agent_targets()}
    if all_agents:
        return list(by_id.values())
    if agent_ids:
        out = []
        for aid in agent_ids:
            key = aid.replace("_", "-")
            if key not in by_id:
                raise ValueError(
                    f"Unknown agent {aid!r}. Choose from: {', '.join(sorted(by_id))}"
                )
            out.append(by_id[key])
        return out
    if auto_detect:
        detected = set(detect_installed_agents())
        if "codex" in detected:
            detected.add("agents")
        return [by_id[i] for i in by_id if i in detected]
    default = ["claude-code", "cursor", "codex", "agents"]
    return [by_id[i] for i in default]


@dataclass
class InstallAction:
    agent: str
    kind: str
    path: str
    created: bool


def run_install(
    *,
    skill: bool,
    hook: bool,
    agents: list[AgentTarget],
    method: InstallMethod,
    dry_run: bool,
) -> list[InstallAction]:
    # Fail fast with a clear error before touching agent dirs
    if skill:
        bundled_skill_dir()
    if hook:
        bundled_hook_script()

    actions: list[InstallAction] = []
    for agent in agents:
        if skill:
            path = install_skill(agent, method=method, dry_run=dry_run)
            actions.append(
                InstallAction(
                    agent=agent.id,
                    kind="skill",
                    path=str(path),
                    created=not dry_run,
                )
            )
        if hook:
            path = install_hook(agent, dry_run=dry_run)
            if path:
                actions.append(
                    InstallAction(
                        agent=agent.id,
                        kind="hook",
                        path=str(path),
                        created=not dry_run,
                    )
                )
    return actions


def npx_skills_hint() -> str:
    return (
        "Install skill only (no mind CLI):\n"
        f"  npx skills add {SKILLS_LIBRARY_REPO} --skill {SKILL_NAME} "
        "-a claude-code -a cursor -a codex -g -y"
    )
