# Install and onboard Howl

When the user asks you to install or onboard this repository, act as the
onboarding interface. Ask one question at a time and do the technical setup for
them. Do not inspect product source unless a setup command fails.

Howl reads nothing on the user's machine. There is no capture, no hook, no
background service, and no permission to negotiate. Do not offer any.

1. Clone this repository into a stable local folder if it is not already local.
2. Confirm Python 3.11+, Git, GitHub CLI, and Claude Code are installed. Ask the
   user to complete official sign-in flows when needed. Never invoke another
   `claude` process from inside an active Claude Code session, and never
   enumerate the user's GitHub repositories.
3. Create a repository-local virtual environment and install Howl:

   - Windows: `python -m venv .venv`, then
     `.\.venv\Scripts\python.exe -m pip install -e .`
   - macOS/Linux: `python3 -m venv .venv`, then
     `.venv/bin/python -m pip install -e .`

4. Run the onboarding flow. Ask only one question at a time.

   1. Fields and subfields, with free text allowed.
   2. Current research in one natural answer. Do not split blockers,
      constraints, or multiple projects into separate profile questions.
   3. Optional work mode, methods, and tools.
   4. Show the prefilled newspaper card, then ask whether to accept it or change
      settings. The card covers Help Now on/off and paper count; Field Radar
      on/off, paper count, and relaxed/balanced/strict popularity floor; section
      order; daily, weekly, or interval cadence; weekdays for weekly delivery or
      interval days; delivery time; timezone; and folder, inbox, or both. Ask
      only about the settings the researcher chooses to change.

5. Ask permission to create `<github-owner>/howl-workspace` as a **private**
   GitHub repository. It holds their profile, the observation history, and their
   delivered issues. Do not use this public repository as the workspace.
6. Save the answers as a temporary JSON file and pass it to the virtual
   environment's `howl` command (`.\.venv\Scripts\howl.exe` on Windows or
   `.venv/bin/howl` on macOS/Linux). Delete the temporary file immediately
   afterward. Use `--answers-file` on Windows; do not pipe JSON through Windows
   PowerShell 5.1.

   ```json
   {
     "fields": ["field", "subfield"],
     "current_research": "one natural answer",
     "newspaper": {
       "help_now": true,
       "help_now_papers": 3,
       "field_radar": true,
       "field_radar_papers": 3,
       "popularity_floor": "balanced",
       "section_order": ["help_now", "field_radar"],
       "cadence": "weekly",
       "weekdays": ["monday"],
       "interval_days": 3,
       "delivery_time": "09:00",
       "timezone": "UTC",
       "delivery": "folder"
     }
   }
   ```

   ```text
   howl setup --repo <github-owner>/howl-workspace --create-workspace --answers-file <temporary-json-path> --json
   ```

7. Setup returns `needs_schedules` with two `schedule_requests`, in order:
   discovery, then report. For each request, call `RemoteTrigger` yourself using
   its prompt exactly. Do not run `claude -p` or start another Claude process.
   After both calls return identifiers, finish the resumable setup:

   ```text
   howl activate --discovery-routine-id <id> --report-routine-id <id> --json
   ```

   The routine names include the private repository. Never repair or repoint a
   same-named routine belonging to another repository. Default MCP connectors
   may appear as account metadata; the routines' allowed tools must contain no
   MCP tools.
8. Run `howl status --json` and report plainly: the two schedule identifiers,
   the selected cadence and delivery time, and where issues will appear.
   Reports land under `output/reports/<issue-date>/` in the private repository
   and are linked from the scheduled-task result.

Do not modify product source during onboarding.

## Uninstall Howl

When the user asks to uninstall Howl:

1. Run the installed virtual environment's `howl uninstall --json`. It forgets
   the local configuration and returns the exact `cloud_schedule_ids`.
2. Delete the cloud routines using only those exact identifiers. Never delete or
   repoint another routine.
3. Tell the user that their private GitHub repository, its delivered issues, and
   the cloned source folder are all still there.
4. If they want a full uninstall, ask separately before each destructive scope:
   local Howl data, the named private GitHub repository, and the local cloned
   folder. One explicit answer must not authorize a different scope.
5. After permission to erase local data, run
   `howl uninstall --purge-local-data --json`. After separate permission for the
   repository, delete only the exact repository named in the first result.
   Delete the clone only after the Howl command exits, and only after confirming
   its exact path is the installation clone.
