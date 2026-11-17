"""Tests for scripts/install.py: the multi-host installer. Everything uses temp folders, never the real home."""
import importlib.util
import os
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_PATH = pathlib.Path(ROOT)
SCRIPT = os.path.join(ROOT, "scripts", "install.py")


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, cwd=ROOT)


def skill_dirs():
    base = os.path.join(ROOT, "skills")
    return sorted(n for n in os.listdir(base) if os.path.isfile(os.path.join(base, n, "SKILL.md")))


def frontmatter_name(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    assert lines[0] == "---"
    for ln in lines[1:]:
        if ln == "---":
            break
        if ln.startswith("name:"):
            return ln.split(":", 1)[1].strip()
    raise AssertionError("no name")


def test_install_codex_layout(tmp_path):
    t, h, a = tmp_path / "skills", tmp_path / "home", tmp_path / "agents"
    r = run("--host", "codex", "--target", str(t), "--home", str(h), "--agents-dir", str(a))
    assert r.returncode == 0, r.stderr
    for n in skill_dirs():
        d = t / ("frameorelay-" + n)
        assert d.is_dir(), n
        # Agent Skills format: the name must match the folder
        assert frontmatter_name(str(d / "SKILL.md")) == "frameorelay-" + n
    # bundle has the validator and the sibling skills the references point at
    assert (h / "scripts" / "relay_check.py").is_file()
    assert (h / "skills" / "script-injector" / "references" / "user-defaults.md").is_file()
    assert (h / "docs" / "hosts.md").is_file()
    # no stray bytecode copied
    assert not list(tmp_path.rglob("*.pyc"))
    # Claude namespace mentions were rewritten to folder names
    src = (ROOT_PATH / "skills" / "scene-prep" / "SKILL.md").read_text(encoding="utf-8")
    assert "frameorelay:conductor" in src  # the source keeps the Claude namespace
    text = (t / "frameorelay-scene-prep" / "SKILL.md").read_text(encoding="utf-8")
    assert "frameorelay:" not in text
    assert "frameorelay-conductor" in text
    # two Codex agent files
    tomls = sorted(p.name for p in a.glob("*.toml"))
    assert tomls == ["frameorelay_bible_scout.toml", "frameorelay_chapter_planner.toml",
                     "frameorelay_review.toml", "frameorelay_scene_prep.toml"]


def test_codex_agent_toml_parses(tmp_path):
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+
    a = tmp_path / "agents"
    r = run("--host", "codex", "--target", str(tmp_path / "s"), "--home", str(tmp_path / "h"), "--agents-dir", str(a))
    assert r.returncode == 0, r.stderr
    for p in a.glob("*.toml"):
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        assert set(data) == {"name", "description", "developer_instructions"}
        assert data["name"].startswith("frameorelay_")
        assert "free Frameo tools" in data["developer_instructions"]
        assert len(data["developer_instructions"]) > 400


def test_toml_escaping_roundtrip():
    spec = importlib.util.spec_from_file_location("install_mod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    nasty = 'a "quoted" \\ back\\slash """triple""" and\nnewline'
    tomllib = pytest.importorskip("tomllib")
    doc = f"x = {mod.toml_multiline(nasty)}\ny = {mod.toml_basic(nasty)}\n"
    data = tomllib.loads(doc)
    assert data["y"] == nasty
    assert data["x"].rstrip("\n") == nasty or data["x"] == nasty


def test_dry_run_changes_nothing(tmp_path):
    r = run("--host", "agents", "--target", str(tmp_path / "s"), "--home", str(tmp_path / "h"), "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "would" in r.stdout
    assert not (tmp_path / "s").exists() and not (tmp_path / "h").exists()


def test_reinstall_and_uninstall(tmp_path):
    t, h, a = tmp_path / "s", tmp_path / "h", tmp_path / "a"
    args = ["--host", "codex", "--target", str(t), "--home", str(h), "--agents-dir", str(a)]
    assert run(*args).returncode == 0
    assert run(*args).returncode == 0  # idempotent
    # a skill the user owns, next to ours, must survive an uninstall
    other = t / "my-own-skill"
    other.mkdir()
    (other / "SKILL.md").write_text("---\nname: my-own-skill\ndescription: x\n---\n", encoding="utf-8")
    assert run(*args, "--uninstall").returncode == 0
    assert other.is_dir()
    assert not [p for p in t.iterdir() if p.name.startswith("frameorelay-")]
    assert not list(a.glob("*.toml")) and not h.exists()


def test_no_claude_only_variable_left_in_skills():
    bad = []
    for base, _d, names in os.walk(os.path.join(ROOT, "skills")):
        for n in names:
            if n.endswith(".md"):
                p = os.path.join(base, n)
                for i, ln in enumerate(open(p, encoding="utf-8"), 1):
                    # the host note may name it once as one of the hosts' values
                    if "CLAUDE_PLUGIN_ROOT" in ln and "**Host note.**" not in ln:
                        bad.append(f"{p}:{i}")
    assert not bad, bad


def test_every_relay_home_reference_exists():
    """Each `$RELAY_HOME/...` path written in a skill must exist in the repo (same layout as the bundle)."""
    missing = []
    for base, _d, names in os.walk(os.path.join(ROOT, "skills")):
        for n in names:
            if not n.endswith(".md"):
                continue
            text = open(os.path.join(base, n), encoding="utf-8").read()
            for m in re.finditer(r"\$RELAY_HOME/([A-Za-z0-9_./-]+\.(?:md|py|json))", text):
                if not os.path.exists(os.path.join(ROOT, m.group(1))):
                    missing.append(m.group(1))
    assert not missing, sorted(set(missing))


def _frontmatter(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    assert lines[0] == "---", path
    end = lines.index("---", 1)
    return lines[1:end]


def test_frontmatter_scalars_are_yaml_safe():
    """An unquoted `description:` containing ': ' or ' #' makes YAML parsers drop the whole frontmatter
    (a skill that then loads with empty metadata and never triggers). Lint every SKILL.md and agent file."""
    files = [os.path.join(ROOT, "skills", n, "SKILL.md") for n in skill_dirs()]
    agents = os.path.join(ROOT, "agents")
    files += [os.path.join(agents, f) for f in os.listdir(agents) if f.endswith(".md")]
    problems = []
    for p in files:
        for ln in _frontmatter(p):
            if ":" not in ln:
                continue
            key, val = ln.split(":", 1)
            val = val.strip()
            if not val or val[0] in "\"'[{|>":
                continue
            if ": " in val or " #" in val or val.endswith(":"):
                problems.append(f"{os.path.relpath(p, ROOT)}: {key} has an unquoted ': ' or ' #'")
    assert not problems, problems
    yaml = pytest.importorskip("yaml")
    for p in files:
        data = yaml.safe_load("\n".join(_frontmatter(p)))
        assert data.get("name") and data.get("description"), p


def test_license_is_apache_everywhere():
    """LICENSE is the standard Apache-2.0 text and every manifest agrees (a stale MIT field would mislead users)."""
    import json
    lic = open(os.path.join(ROOT, "LICENSE"), encoding="utf-8").read()
    assert "Apache License" in lic and "Version 2.0, January 2004" in lic
    assert "MIT License" not in lic
    assert os.path.isfile(os.path.join(ROOT, "NOTICE"))
    for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "agent.json"):
        assert json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))["license"] == "Apache-2.0", rel
    market = json.load(open(os.path.join(ROOT, ".claude-plugin", "marketplace.json"), encoding="utf-8"))
    assert all(p.get("license") == "Apache-2.0" for p in market["plugins"] if "license" in p)
