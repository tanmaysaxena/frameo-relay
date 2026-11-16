#!/usr/bin/env python3
"""install.py: install frameorelay for an agent host that is not Claude Code's plugin system.

Stdlib only. Works for Codex, Gemini CLI, Cursor and any tool that reads Agent Skills (a folder with a SKILL.md).

What it does:
  1. Copies the whole bundle (scripts, skills, agents, examples, docs) to a stable folder, RELAY_HOME
     (default ~/.frameorelay, or $FRAMEORELAY_HOME). The skills find the validator and each other there.
  2. Copies each skill into the host's skills folder as `frameorelay-<name>` (the SKILL.md `name` is changed to
     match its folder, as the Agent Skills format requires, and `frameorelay:<name>` mentions become `frameorelay-<name>`).
  3. For Codex, writes the two subagent roles as custom agent files (~/.codex/agents/*.toml).

Usage:
  python scripts/install.py [--host agents|codex|gemini|cursor|claude] [--scope user|project]
                            [--target DIR] [--home DIR] [--agents-dir DIR] [--dry-run] [--uninstall]

Hosts (skills folder, user scope / project scope):
  agents  ~/.agents/skills        / ./.agents/skills       (the cross-tool folder; Codex, Gemini CLI and Cursor read it)
  codex   ~/.agents/skills        / ./.agents/skills       plus custom agents in ~/.codex/agents or ./.codex/agents
  gemini  ~/.gemini/skills        / ./.gemini/skills
  cursor  ~/.cursor/skills        / ./.cursor/skills
  claude  ~/.claude/skills        / ./.claude/skills       (standalone skills; the plugin route is better for Claude Code)
--target overrides the skills folder, --agents-dir the Codex agents folder, --home the bundle folder.
Re-run to update; --uninstall removes what this script installed (and the bundle folder).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = "frameorelay-"
BUNDLE_DIRS = ["scripts", "skills", "agents", "examples", "docs"]
BUNDLE_FILES = ["LICENSE", "NOTICE", "README.md", "CHANGELOG.md"]
HOSTS = {
    "agents": {"user": "~/.agents/skills", "project": ".agents/skills"},
    "codex": {"user": "~/.agents/skills", "project": ".agents/skills",
              "agents_user": "~/.codex/agents", "agents_project": ".codex/agents"},
    "gemini": {"user": "~/.gemini/skills", "project": ".gemini/skills"},
    "cursor": {"user": "~/.cursor/skills", "project": ".cursor/skills"},
    "claude": {"user": "~/.claude/skills", "project": ".claude/skills"},
}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


def expand(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))


def skill_names() -> list:
    base = os.path.join(ROOT, "skills")
    return sorted(n for n in os.listdir(base) if os.path.isfile(os.path.join(base, n, "SKILL.md")))


def rename_mentions(text: str) -> str:
    """`frameorelay:conductor` (Claude plugin namespace) -> `frameorelay-conductor` (folder name elsewhere)."""
    return re.sub(r"frameorelay:([a-z][a-z-]*)", r"frameorelay-\1", text)


def set_skill_name(text: str, new: str) -> str:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise SystemExit("SKILL.md has no frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            break
        if lines[i].startswith("name:"):
            lines[i] = "name: " + new
            return "\n".join(lines)
    raise SystemExit("SKILL.md frontmatter has no name")


def copy_tree(src: str, dst: str, rewrite: bool) -> None:
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=IGNORE)
    if not rewrite:
        return
    for base, _dirs, names in os.walk(dst):
        for n in names:
            if n.endswith(".md"):
                p = os.path.join(base, n)
                with open(p, encoding="utf-8") as fh:
                    t = fh.read()
                with open(p, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(rename_mentions(t))


def parse_agent(path: str):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    lines = text.split("\n")
    if lines[0].strip() != "---":
        raise SystemExit(f"{path}: no frontmatter")
    end = lines.index("---", 1)
    meta = {}
    for ln in lines[1:end]:
        if ":" in ln:
            k, v = ln.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, "\n".join(lines[end + 1:]).strip() + "\n"


def toml_multiline(s: str) -> str:
    s = s.replace("\\", "\\\\").replace('"""', '""\\"')
    return '"""\n' + s + '"""'


def toml_basic(s: str) -> str:
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ord(ch) < 32:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


FREE_NOTE = ("Hard rule for this role: use only free Frameo tools (get_skill, view_image, list_library, list_characters, "
             "list_models, list_presets, get_presets, read_note) plus reading files and writing your own note file. "
             "Never call a tool that generates, upscales, analyzes or runs ffmpeg, and never spend credits. "
             "Your host does not enforce this allow-list, so you must.\n\n")


def codex_agent_toml(path: str) -> tuple:
    meta, body = parse_agent(path)
    name = "frameorelay_" + meta["name"].replace("-", "_")
    instr = FREE_NOTE + rename_mentions(body)
    toml = (f"name = {toml_basic(name)}\n"
            f"description = {toml_basic(meta['description'])}\n"
            f"developer_instructions = {toml_multiline(instr)}\n")
    return name, toml


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install frameorelay for Codex, Gemini CLI, Cursor or another Agent Skills host.")
    ap.add_argument("--host", choices=sorted(HOSTS), default="agents")
    ap.add_argument("--scope", choices=["user", "project"], default="user")
    ap.add_argument("--target", help="skills folder (overrides the host default)")
    ap.add_argument("--home", help="bundle folder RELAY_HOME (default $FRAMEORELAY_HOME or ~/.frameorelay)")
    ap.add_argument("--agents-dir", help="Codex custom agents folder (overrides the default)")
    ap.add_argument("--dry-run", action="store_true", help="print what would happen, change nothing")
    ap.add_argument("--uninstall", action="store_true", help="remove what this script installed")
    a = ap.parse_args(argv)

    h = HOSTS[a.host]
    target = expand(a.target or h[a.scope])
    home = expand(a.home or os.environ.get("FRAMEORELAY_HOME") or "~/.frameorelay")
    agents_dir = None
    if a.host == "codex":
        agents_dir = expand(a.agents_dir or h["agents_" + a.scope])
    elif a.agents_dir:
        agents_dir = expand(a.agents_dir)
    names = skill_names()
    agent_files = sorted(f for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md"))
    say = print
    act = "would" if a.dry_run else "did"

    if a.uninstall:
        for n in names:
            d = os.path.join(target, PREFIX + n)
            if os.path.isdir(d):
                say(f"{act} remove {d}")
                if not a.dry_run:
                    shutil.rmtree(d)
        if agents_dir:
            for f in agent_files:
                p = os.path.join(agents_dir, "frameorelay_" + f[:-3].replace("-", "_") + ".toml")
                if os.path.isfile(p):
                    say(f"{act} remove {p}")
                    if not a.dry_run:
                        os.remove(p)
        if os.path.abspath(home) != ROOT and os.path.isfile(os.path.join(home, "scripts", "relay_check.py")):
            say(f"{act} remove {home}")
            if not a.dry_run:
                shutil.rmtree(home)
        return 0

    if os.path.abspath(home) == ROOT:
        say(f"bundle: using this folder in place ({home})")
    else:
        say(f"{act} install the bundle to {home}")
        if not a.dry_run:
            os.makedirs(home, exist_ok=True)
            for d in BUNDLE_DIRS:
                copy_tree(os.path.join(ROOT, d), os.path.join(home, d), rewrite=True)
            for f in BUNDLE_FILES:
                if os.path.isfile(os.path.join(ROOT, f)):
                    shutil.copyfile(os.path.join(ROOT, f), os.path.join(home, f))
    for n in names:
        dst = os.path.join(target, PREFIX + n)
        say(f"{act} install skill {n} -> {dst}")
        if a.dry_run:
            continue
        os.makedirs(target, exist_ok=True)
        copy_tree(os.path.join(ROOT, "skills", n), dst, rewrite=True)
        p = os.path.join(dst, "SKILL.md")
        with open(p, encoding="utf-8") as fh:
            t = fh.read()
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(set_skill_name(t, PREFIX + n))
    if agents_dir:
        for f in agent_files:
            name, toml = codex_agent_toml(os.path.join(ROOT, "agents", f))
            p = os.path.join(agents_dir, name + ".toml")
            say(f"{act} write Codex agent {name} -> {p}")
            if not a.dry_run:
                os.makedirs(agents_dir, exist_ok=True)
                with open(p, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(toml)

    say("")
    say("Next:")
    say(f"  1. Make sure the Frameo MCP server is connected in your host (see docs/hosts.md).")
    say(f"  2. The skills look for the bundle at {home}. If you chose a different --home, set FRAMEORELAY_HOME to it.")
    say(f"  3. Restart or reload the host so it sees the new skills, then ask it to use `{PREFIX}script-injector`"
        f" (or `{PREFIX}panel-writer` first for a plain story).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
