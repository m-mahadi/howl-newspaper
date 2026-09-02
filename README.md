# Howl

A research newspaper that arrives on a schedule. You describe what you work on
once. Howl watches public paper feeds for your fields and delivers a short
issue: a few papers that help with what you are doing now, and a few that are
genuinely moving in your field.

It reads nothing on your machine. No hooks, no background service, no watching
your editor or your conversations. The only thing it knows about you is the
profile you write during setup, which lives in your own private GitHub
repository.

## What you get

Two cloud routines run on your Claude subscription:

- **Daily paper observations** collects candidate papers for your declared
  fields and records attributable attention signals, so a paper that peaks
  between issues is still eligible when your issue is built.
- **Research newspaper** builds and delivers the issue on your cadence.

Each issue has up to two sections, both optional and both sized by you:

- **Help Now** — papers ranked by usefulness to your stated current research.
- **Field Radar** — papers ranked only by verified, field-normalized movement.

If nothing clears the bar, you get a short honest notice instead of filler.

## Install with Claude Code

Point Claude Code at this repository and ask it to install Howl. It will run
the onboarding in [`CLAUDE.md`](CLAUDE.md), asking one question at a time.

## Install in a terminal

You need Python 3.11+, Git, the GitHub CLI (`gh auth login`), and Claude Code.

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\howl.exe setup --repo <you>/howl-workspace --create-workspace
```

### macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/howl setup --repo <you>/howl-workspace --create-workspace
```

Setup asks for your fields, what you are working on, and your newspaper
settings, then returns two `schedule_requests`. Hand each one to Claude to
create the routine, then record the identifiers:

```bash
howl activate --discovery-routine-id <id> --report-routine-id <id> --json
```

`howl status --json` shows what is configured and which routines are recorded.

## Where issues arrive

Reports are written as self-contained HTML under
`output/reports/<issue-date>/` in your private workspace repository. Set
`delivery` to `inbox` to get links in the Claude scheduled-task result instead,
or `both`.

## Changing what it looks for

Edit your profile and run `howl setup` again. Re-running setup keeps the
routine identifiers it already recorded, so it repairs your routines instead of
stranding them.

## Uninstall

```bash
howl uninstall --json
```

This forgets the local configuration and tells you the exact routine
identifiers to delete. Deleting the cloud routines and the GitHub repository is
left to you on purpose, so nothing of yours is removed without you asking.

Add `--purge-local-data` to delete Howl's local config directory as well.

## What Howl never does

- Read your files, your editor, your terminal, or your conversations.
- Install hooks, background services, or startup entries.
- Upload anything except the profile you wrote during setup.
- Invent a popularity signal for a field that has none.

## Develop

```bash
python -m unittest discover -s tests
```
