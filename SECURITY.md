# Security policy

## What this project does and does not touch

frameorelay is Markdown instructions for Claude plus two Python scripts (`scripts/relay_check.py`, `skills/finish-cut/scripts/`). The scripts read and write local JSON files, make no network calls and ship no credentials. All Frameo access goes through the Frameo MCP that you connect and sign in to yourself.

The main risk is **spending**: a bug or a bad instruction could cause paid Frameo calls you did not intend. The design limits this (only the conductor spends, an up-front approval, saved calls, a ledger audit) but does not enforce a hard cap. If that matters, top up your wallet only to the approved total.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private vulnerability reporting on this repository (Security tab, "Report a vulnerability"). Include what you found, how to reproduce it and the impact. You can expect an acknowledgement within a few days.

Examples worth reporting: a path in the scripts that writes outside the job folder, a way for a crafted `relay.json` to execute code, a skill instruction that causes spending without approval, or a secret committed to the repository.

## Supported versions

Only the latest release is supported.
