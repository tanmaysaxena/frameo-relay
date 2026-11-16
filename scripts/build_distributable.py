#!/usr/bin/env python3
"""Build dist/frameorelay-<version>.zip, an uploadable plugin bundle (Claude Cowork / manual install).

Stdlib only. Includes the plugin manifest, skills, agents, the validator, the examples
and the docs. Excludes tests, git data, job output and any media or secrets.

Usage: python scripts/build_distributable.py

Before building, it scans EVERY text file in the repository (not only what goes into the zip) for
things that must never be published: local user paths, email addresses, token-shaped strings, and
any extra private strings you list (one per line) in ~/.frameorelay/forbidden.txt (or the older ~/.claude/frameorelay/forbidden.txt) or in the
FRAMEORELAY_FORBIDDEN environment variable (separated by ';'). It exits 1 and writes nothing if it finds any.
"""
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCLUDE = [".claude-plugin/plugin.json", "README.md", "LICENSE", "NOTICE", "SKILLS.md", "agent.json", "CHANGELOG.md"]
INCLUDE_DIRS = ["skills", "agents", "examples", "docs"]
INCLUDE_SCRIPTS = ["scripts/relay_check.py", "scripts/install.py"]
SKIP_DIRS = {".git", "dist", "__pycache__", ".pytest_cache", "node_modules"}
SKIP_SUFFIXES = (".pyc", ".zip", ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".mp3", ".wav")

# Patterns that never belong in a public repo, whoever you are.
PATTERNS = [
    ("a local Windows user path", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]", re.I)),
    ("a local macOS or Linux home path", re.compile(r"(?:/Users/|/home/)[A-Za-z0-9._-]+/")),
    ("an email address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}\b")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("an API-key-shaped string", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
]


def extra_forbidden() -> list:
    items = []
    for parts in ((".frameorelay", "forbidden.txt"), (".claude", "frameorelay", "forbidden.txt")):
        path = os.path.join(os.path.expanduser("~"), *parts)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                items += [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    items += [x.strip() for x in os.environ.get("FRAMEORELAY_FORBIDDEN", "").split(";") if x.strip()]
    return items


def scan_repo(extra: list) -> list:
    """Return a list of 'relative/path contains ...' for every text file under ROOT."""
    problems = []
    me = os.path.abspath(__file__)
    for base, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            full = os.path.join(base, n)
            if n.endswith(SKIP_SUFFIXES) or os.path.abspath(full) == me:
                continue
            rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
            try:
                with open(full, "rb") as fh:
                    text = fh.read().decode("utf-8", errors="ignore")
            except OSError:
                continue
            for label, rx in PATTERNS:
                if rx.search(text):
                    problems.append(f"{rel} contains {label}")
            low = text.lower()
            for bad in extra:
                if bad.lower() in low:
                    problems.append(f"{rel} contains a private string from your forbidden list")
                    break
    return problems


def main() -> int:
    problems = scan_repo(extra_forbidden())
    if problems:
        print("FAIL: " + "; ".join(sorted(set(problems))))
        return 1
    with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        version = json.load(fh)["version"]
    files = list(INCLUDE) + list(INCLUDE_SCRIPTS)
    for d in INCLUDE_DIRS:
        for base, dirs, names in os.walk(os.path.join(ROOT, d)):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for n in names:
                if n.endswith(".pyc"):
                    continue
                files.append(os.path.relpath(os.path.join(base, n), ROOT).replace(os.sep, "/"))
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"frameorelay-{version}.zip")
    missing = [rel for rel in sorted(set(files)) if not os.path.isfile(os.path.join(ROOT, rel))]
    if missing:
        print("FAIL: missing file(s): " + ", ".join(missing))
        return 1
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(set(files)):
            with open(os.path.join(ROOT, rel), "rb") as fh:
                z.writestr(rel, fh.read())
    print(f"OK: {out} ({len(set(files))} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
