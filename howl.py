import atomic
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from textwrap import dedent
from urllib.parse import urlparse

from github_profile import upload_profile_from_gh


NEWSPAPER_DEFAULTS = {
    "help_now": True,
    "help_now_papers": 3,
    "field_radar": True,
    "field_radar_papers": 3,
    "popularity_floor": "balanced",
    "section_order": ["help_now", "field_radar"],
    "cadence": "weekly",
    "weekdays": ["monday"],
    "interval_days": 3,
    "delivery_time": "09:00",
    "delivery": "folder",
    "timezone": "UTC",
}

# Every host a discovery route or full-text check reaches. Cloud routines run
# behind an egress proxy that refuses any host the routine's environment does
# not permit, and a routine that reaches none of these delivers a no-issue
# notice on every run. Measured 2026-09-03 on env_014PzUpFsq23W34CaHBQdVtF:
# all fifteen refused with `connect_rejected (organization policy)`, over both
# curl and WebFetch. The routine API strips `user_declared_urls`, so a routine
# cannot open these itself; the environment has to permit them.
# Keep in step with docs/discovery-routing.md.
PROVIDER_HOSTS = (
    "arxiv.org",
    "export.arxiv.org",
    "api.openalex.org",
    "api.semanticscholar.org",
    "api.crossref.org",
    "api.unpaywall.org",
    "api.biorxiv.org",
    "europepmc.org",
    "openreview.net",
    "api.openreview.net",
    "aclanthology.org",
    "inspirehep.net",
    "ui.adsabs.harvard.edu",
    "huggingface.co",
    "scirate.com",
)

NETWORK_NOTICE = (
    "Howl's cloud routines run in a sandbox behind an egress proxy. They can\n"
    "only reach a paper source if the environment they run in permits it.\n"
    "Howl needs all of these:\n\n"
    + "\n".join(f"  {host}" for host in PROVIDER_HOSTS)
    + "\n\nCheck them at https://claude.ai/code/routines before you rely on a\n"
    "delivery. While they are refused Howl recalls nothing, and every issue\n"
    "arrives as a no-issue notice naming the hosts it could not reach.\n"
)


def provider_allowlist_clause():
    hosts = ", ".join(PROVIDER_HOSTS)
    return dedent(
        f"""
        Network access. This routine runs behind an egress proxy. Before any
        other work, try to reach these hosts and record which ones answer:
        {hosts}
        A host that returns `connect_rejected` is refused by the environment,
        not by the publisher, and no retry or alternate path will open it. Work
        with whichever hosts do answer. If none do, stop early and deliver the
        no-issue notice naming the refused hosts and the environment id, rather
        than spending a full run rediscovering the same wall.
        """
    ).strip()


CLAUDE_WARNING = (
    "Howl reads nothing on your machine. It builds your newspaper from the "
    "profile you write here and from public paper feeds. Change what it looks "
    "for by editing your profile and running setup again."
)


def _first_party_env():
    env = os.environ.copy()
    for name in (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_API_KEY",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
        "CLAUDECODE",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_HOST_SESSION_ID",
        "CLAUDE_CODE_MESSAGING_SOCKET",
        "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_CODE_OAUTH_SCOPES",
        "CLAUDE_CODE_SDK_HAS_OAUTH_REFRESH",
        "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_HOST_AUTH",
    ):
        env.pop(name, None)
    return env


def _stage(path, data):
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def normalize_repository(value):
    value = value.strip().removesuffix(".git").rstrip("/")
    if value.startswith("git@github.com:"):
        value = value.removeprefix("git@github.com:")
    elif "://" in value:
        parsed = urlparse(value)
        if parsed.hostname != "github.com":
            raise ValueError("repository must be hosted on github.com")
        value = parsed.path.strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise ValueError("repository must be owner/name or a GitHub URL")
    return value


def create_workspace(repository, *, runner=subprocess.run):
    repository = normalize_repository(repository)
    view = runner(
        ["gh", "repo", "view", repository, "--json", "isPrivate,defaultBranchRef"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if view.returncode == 0:
        try:
            details = json.loads(view.stdout)
            if details.get("isPrivate") is not True:
                raise RuntimeError("Howl's workspace repository must be private")
        except json.JSONDecodeError as error:
            raise RuntimeError("GitHub returned an invalid repository") from error
        if details.get("defaultBranchRef"):
            return False
    else:
        missing = view.stderr.lower()
        if "404" not in missing and "could not resolve to a repository" not in missing:
            raise RuntimeError("GitHub workspace lookup failed")
        created = runner(
            ["gh", "repo", "create", repository, "--private"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if created.returncode != 0:
            raise RuntimeError("GitHub workspace creation failed")
    pushed = runner(
        [
            "git",
            "push",
            f"https://github.com/{repository}.git",
            "HEAD:main",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if pushed.returncode != 0:
        raise RuntimeError("GitHub workspace seeding failed")
    return True


def validate_answers(raw):
    if not isinstance(raw, dict):
        raise ValueError("answers must be a JSON object")
    if not isinstance(raw.get("fields"), list):
        raise ValueError("fields must be a list")
    fields = [str(value).strip() for value in raw["fields"] if str(value).strip()]
    if not 1 <= len(fields) <= 8 or any(len(value) > 80 for value in fields):
        raise ValueError("at least one research field is required")
    supplied_newspaper = raw.get("newspaper", {})
    if not isinstance(supplied_newspaper, dict):
        raise ValueError("newspaper must be an object")
    newspaper = NEWSPAPER_DEFAULTS | supplied_newspaper
    if type(newspaper["help_now"]) is not bool or type(newspaper["field_radar"]) is not bool:
        raise ValueError("newspaper sections must be enabled or disabled")
    if not newspaper["help_now"] and not newspaper["field_radar"]:
        raise ValueError("at least one newspaper section must be enabled")
    for key, label in (
        ("help_now_papers", "Help Now papers"),
        ("field_radar_papers", "Field Radar papers"),
    ):
        if type(newspaper[key]) is not int or not 1 <= newspaper[key] <= 20:
            raise ValueError(f"{label} must be between 1 and 20")
    if newspaper["popularity_floor"] not in ("relaxed", "balanced", "strict"):
        raise ValueError("popularity floor must be relaxed, balanced, or strict")
    if newspaper["section_order"] not in (
        ["help_now", "field_radar"],
        ["field_radar", "help_now"],
    ):
        raise ValueError("section order is invalid")
    cadence = str(newspaper["cadence"]).strip().lower()
    legacy_interval = re.fullmatch(r"every ([1-9]|[12]\d|30) days", cadence)
    if legacy_interval:
        cadence = "interval"
        newspaper["interval_days"] = int(legacy_interval.group(1))
    if cadence not in ("daily", "weekly", "interval"):
        raise ValueError("cadence must be daily, weekly, or interval")
    newspaper["cadence"] = cadence
    weekdays = newspaper["weekdays"]
    valid_days = {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }
    if not isinstance(weekdays, list):
        raise ValueError("weekdays must be a list")
    weekdays = [str(day).strip().lower() for day in weekdays]
    if cadence == "weekly" and (
        not weekdays or len(set(weekdays)) != len(weekdays) or any(day not in valid_days for day in weekdays)
    ):
        raise ValueError("weekly cadence requires unique weekdays")
    newspaper["weekdays"] = weekdays
    if type(newspaper["interval_days"]) is not int or not 2 <= newspaper["interval_days"] <= 30:
        raise ValueError("interval must be between 2 and 30 days")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(newspaper["delivery_time"])):
        raise ValueError("delivery time must use HH:MM")
    if not isinstance(newspaper["timezone"], str) or not re.fullmatch(
        r"[A-Za-z_+-]+(?:/[A-Za-z0-9_+-]+)*", newspaper["timezone"]
    ):
        raise ValueError("timezone is required")
    if newspaper["delivery"] not in ("folder", "inbox", "both"):
        raise ValueError("delivery must be folder, inbox, or both")
    current_research = str(raw.get("current_research", "")).strip()
    if newspaper["help_now"] and not current_research:
        raise ValueError("current research is required while Help Now is enabled")
    if len(current_research) > 4000:
        raise ValueError("current research is too long")
    work_mode = str(raw.get("work_mode", "")).strip()
    if work_mode and work_mode not in (
        "theoretical",
        "experimental",
        "computational",
        "mixed",
    ):
        raise ValueError("invalid work mode")
    result = {
        "fields": fields,
        "current_research": current_research,
        "newspaper": newspaper,
    }
    for key in ("work_mode", "methods"):
        value = str(raw.get(key, "")).strip()
        if value:
            result[key] = value
    return result


def collect_answers(ask=input, connection_step=None):
    fields = ask("Your research fields (comma-separated): ").split(",")
    current_research = ask("What are you working on right now? ")
    work_mode = ask(
        "How do you work? [theoretical/experimental/computational/mixed/skip]: "
    )
    methods = ask("Methods or tools Howl should understand (optional): ")
    ask("\n" + NETWORK_NOTICE + "\nPress Enter to allow these sources: ")
    if connection_step:
        connection_step(ask)
    customize = ask("Customize your newspaper now? [y/N]: ").strip().lower()
    newspaper = {}
    if customize in ("y", "yes"):
        help_now = (ask("Include Help Now? [Y/n]: ").strip().lower() or "y") in (
            "y",
            "yes",
        )
        field_radar = (
            ask("Include Field Radar? [Y/n]: ").strip().lower() or "y"
        ) in ("y", "yes")
        cadence = ask("Cadence [daily/weekly/interval]: ").strip().lower() or "weekly"
        weekdays = ["monday"]
        interval_days = 3
        if cadence == "weekly":
            weekdays = [
                value.strip().lower()
                for value in (
                    ask("Delivery weekdays, comma-separated [monday]: ").strip()
                    or "monday"
                ).split(",")
            ]
        elif cadence == "interval":
            interval_days = int(ask("Deliver every how many days? [3]: ") or 3)
        newspaper = {
            "help_now": help_now,
            "help_now_papers": (
                int(ask("Help Now papers per issue [3]: ") or 3) if help_now else 3
            ),
            "field_radar": field_radar,
            "field_radar_papers": (
                int(ask("Field Radar papers per issue [3]: ") or 3)
                if field_radar
                else 3
            ),
            "popularity_floor": ask(
                "Field Radar strictness [balanced]: "
            ).strip()
            or "balanced",
            "section_order": (
                ["field_radar", "help_now"]
                if ask("Which section first? [help/radar]: ").strip().lower()
                == "radar"
                else ["help_now", "field_radar"]
            ),
            "cadence": cadence,
            "weekdays": weekdays,
            "interval_days": interval_days,
            "delivery_time": ask("Delivery time [09:00]: ").strip() or "09:00",
            "timezone": ask("Timezone [UTC]: ").strip() or "UTC",
            "delivery": (
                ask("Delivery method [folder/inbox/both]: ").strip().lower()
                or "folder"
            ),
        }
    return validate_answers(
        {
            "fields": fields,
            "current_research": current_research,
            "work_mode": "" if work_mode.lower() == "skip" else work_mode,
            "methods": methods,
            "newspaper": newspaper,
        }
    )


def _run_json(command, *, env=None, allow_nonzero_json=False):
    label = Path(str(command[0])).name
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            ),
        )
        if completed.returncode and not allow_nonzero_json:
            detail = (completed.stderr or completed.stdout or "").strip()
            suffix = f": {detail[-500:]}" if detail else ""
            raise RuntimeError(
                f"{label} failed with exit {completed.returncode}{suffix}"
            )
        return json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} failed: {error}") from error


def _resolve_command(name):
    found = shutil.which(name)
    if found is None and sys.platform == "win32":
        for folder in os.environ.get("PATH", "").split(os.pathsep):
            for suffix in (".exe", ".cmd", ".bat", "", ".ps1"):
                candidate = Path(folder) / f"{name}{suffix}"
                if candidate.is_file():
                    found = str(candidate)
                    break
            if found:
                break
    if found is None:
        raise RuntimeError(f"{name} is not installed")
    path = Path(found)
    if sys.platform != "win32" or path.suffix.lower() == ".exe":
        return [str(path)]
    if path.suffix.lower() in (".cmd", ".bat"):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", str(path)]
    if path.suffix.lower() == ".ps1":
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(path),
        ]
    native = (
        path.parent
        / "node_modules"
        / "@anthropic-ai"
        / "claude-code"
        / "bin"
        / "claude.exe"
    )
    if native.is_file():
        return [str(native)]
    return [shutil.which("bash") or "bash", str(path)]


def preflight_tools():
    claude = _resolve_command("claude")
    auth = _run_json(
        [*claude, "auth", "status", "--json"],
        env=_first_party_env(),
        allow_nonzero_json=True,
    )
    if not auth.get("loggedIn") or auth.get("apiProvider") != "firstParty":
        raise RuntimeError("Claude Code must be signed in with a Claude subscription")
    gh = _resolve_command("gh")
    return claude, gh


def preflight(repository):
    _, gh = preflight_tools()
    repo = _run_json(
        [
            *gh,
            "repo",
            "view",
            repository,
            "--json",
            "nameWithOwner,isPrivate,defaultBranchRef",
        ]
    )
    if not repo.get("isPrivate"):
        raise RuntimeError("Howl's workspace repository must be private")
    return {
        "branch": (repo.get("defaultBranchRef") or {}).get("name") or "main",
    }


def _ensure_remote_schedule(prompt, marker, label):
    claude = _resolve_command("claude")
    result = _run_json(
        [
            *claude,
            "-p",
            prompt,
            "--allowedTools",
            "RemoteTrigger",
            "--permission-mode",
            "dontAsk",
            "--model",
            "haiku",
            "--output-format",
            "json",
            "--no-session-persistence",
        ],
        env=_first_party_env(),
    )
    match = re.fullmatch(
        rf"{marker}=([A-Za-z0-9_-]+)", result.get("result", "").strip()
    )
    if not match:
        raise RuntimeError(f"Claude did not confirm the {label} schedule")
    return match.group(1)


def discovery_schedule_request(repository, branch, timezone):
    return {
        "kind": "discovery",
        "marker": "HOWL_DISCOVERY_ROUTINE",
        "prompt": dedent(
        f"""
        Use RemoteTrigger to ensure exactly one enabled routine named
        "Howl: {repository}: Daily paper observations"
        exists for repository {repository} on branch {branch}. Run it daily at 05:00
        in timezone {timezone}. If that exact routine already exists for that exact repository,
        repair it instead of duplicating it. Never modify a routine for another repository.

        The routine reads only `howl-profile/config.json`, `docs/discovery-routing.md`, the
        relevant provider skill, prior provider observations, and recommendation history.
        Collect plausible papers for every declared field using the route's recall, movement,
        resolution, and honest fallback rules. Store append-only, attributable observations
        under `howl-observations/` so a paper that peaks between newspaper deliveries stays
        eligible. Do not rank for the reader, write a report, or read anything outside this
        repository. Never bypass access controls or invent popularity. Commit and push only
        changed observation files. Return exactly HOWL_DISCOVERY_ROUTINE=<routine id>.

        {provider_allowlist_clause()}
        """
        ).strip(),
    }


def ensure_discovery_schedule(repository, branch, timezone):
    request = discovery_schedule_request(repository, branch, timezone)
    return _ensure_remote_schedule(
        request["prompt"], request["marker"], "discovery"
    )


def report_schedule_request(repository, branch, newspaper):
    if newspaper["cadence"] == "weekly":
        cadence = "weekly on " + ", ".join(newspaper["weekdays"])
    elif newspaper["cadence"] == "interval":
        cadence = f'every {newspaper["interval_days"]} days'
    else:
        cadence = "daily"
    schedule = (
        f'{cadence} at {newspaper["delivery_time"]} '
        f'in timezone {newspaper["timezone"]}'
    )
    settings = json.dumps(newspaper, sort_keys=True, separators=(",", ":"))
    return {
        "kind": "report",
        "marker": "HOWL_REPORT_ROUTINE",
        "prompt": dedent(
        f"""
        Use RemoteTrigger to ensure exactly one enabled routine named
        "Howl: {repository}: Research newspaper"
        exists for repository {repository} on branch {branch}. Run it {schedule}.
        If that exact routine already exists for that exact repository, repair it instead of
        duplicating it. Never modify a routine for another repository. The validated newspaper
        settings are: {settings}

        The routine must first refresh today's provider observations using
        `docs/discovery-routing.md`. It reads only `howl-profile/config.json`, provider
        observations, recommendation history, discovery rules, and the report skills.

        For Help Now, use the two-pass recall and deep-reading funnel and rank by immediate
        usefulness to the reader's stated current research. Never pad below the relevance gate.
        For Field Radar, rank only verified field-normalized movement, and never relabel a
        model's significance as popularity. Exclude papers already delivered and deduplicate
        overlap between the two sections. Require legal full text and attributable evidence.
        Follow `.agents/skills/howl-report-writing/SKILL.md`, including a
        separate adversarial reviewer. Skip papers that cannot pass its evidence
        and review gates rather than filling space.

        Deliver each accepted paper as a self-contained HTML file under
        `output/reports/<issue-date>/`, with an optional PDF. Apply the configured delivery
        method: `folder` means the repository folder, `inbox` means links in the Claude
        scheduled-task result, and `both` means both. Update append-only provider and
        recommendation history, then commit and push only those histories and the report
        artifacts. If no paper qualifies, deliver a short honest no-issue notice instead of
        filler. Read nothing outside this repository. Return exactly
        HOWL_REPORT_ROUTINE=<routine id>.

        {provider_allowlist_clause()}
        """
        ).strip(),
    }


def ensure_report_schedule(repository, branch, newspaper):
    request = report_schedule_request(repository, branch, newspaper)
    return _ensure_remote_schedule(
        request["prompt"], request["marker"], "report"
    )


def schedule_requests(repository, branch, newspaper):
    timezone = newspaper["timezone"]
    return [
        discovery_schedule_request(repository, branch, timezone),
        report_schedule_request(repository, branch, newspaper),
    ]


def _default_config_path():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Howl" / "config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Howl" / "config.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "howl" / "config.json"


def _save_config(path, config):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _stage(path, (json.dumps(config, indent=2) + "\n").encode("utf-8"))
    try:
        atomic.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def complete_setup(profile, repository, *, config_path=None):
    repository = normalize_repository(repository)
    profile = validate_answers(profile)
    config_path = Path(config_path or _default_config_path())
    previous = {}
    if config_path.is_file():
        try:
            previous = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
    if not isinstance(previous, dict):
        previous = {}
    environment = preflight(repository)
    config = {
        "version": 1,
        "repository": repository,
        "profile": profile,
        "activated": False,
    }
    # Carry forward routines the previous install recorded. Rebuilding the
    # config without them strands routines that are still scheduled in the
    # cloud, and uninstall can then no longer say which ones to remove.
    for name in ("discovery_routine_id", "report_routine_id"):
        if previous.get(name):
            config[name] = previous[name]
    profile_commit = upload_profile_from_gh(
        {"schema_version": 1, **profile},
        repository,
        branch=environment["branch"],
    )
    config.update(
        branch=environment["branch"],
        profile_commit=profile_commit,
        setup_stage="schedules",
    )
    _save_config(config_path, config)
    return {
        **config,
        "schedule_requests": schedule_requests(
            repository, environment["branch"], profile["newspaper"]
        ),
    }


def activate_setup(discovery_routine_id, report_routine_id, *, config_path=None):
    routine_ids = {
        "discovery_routine_id": discovery_routine_id,
        "report_routine_id": report_routine_id,
    }
    if any(
        re.fullmatch(r"[A-Za-z0-9_-]+", value or "") is None
        for value in routine_ids.values()
    ):
        raise ValueError("both Claude schedule ids are required")
    config_path = Path(config_path or _default_config_path())
    if not config_path.is_file():
        raise RuntimeError("run howl setup before activation")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("setup_stage") != "schedules":
        raise RuntimeError("Howl setup is not waiting for schedules")
    config.update(**routine_ids, activated=True, setup_stage="complete")
    _save_config(config_path, config)
    return config


def status(*, config_path=None):
    config_path = Path(config_path or _default_config_path())
    if not config_path.is_file():
        return {"status": "not_set_up"}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    schedule_ids = {
        name: config[name]
        for name in ("discovery_routine_id", "report_routine_id")
        if config.get(name)
    }
    return {
        "status": "active" if config.get("activated") else "incomplete",
        "setup_stage": config.get("setup_stage"),
        "repository": config.get("repository"),
        "fields": config.get("profile", {}).get("fields", []),
        "cadence": config.get("profile", {}).get("newspaper", {}).get("cadence"),
        "delivery": config.get("profile", {}).get("newspaper", {}).get("delivery"),
        "cloud_schedule_ids": schedule_ids,
    }


def uninstall_setup(*, purge_local_data=False, config_path=None, home=None):
    config_path = Path(config_path or _default_config_path())
    root = config_path.parent
    config = (
        json.loads(config_path.read_text(encoding="utf-8"))
        if config_path.is_file()
        else {}
    )
    home = Path.home() if home is None else Path(home)
    schedule_ids = {
        name: config[name]
        for name in ("discovery_routine_id", "report_routine_id")
        if config.get(name)
    }
    if purge_local_data:
        resolved_root = root.resolve()
        if resolved_root == home.resolve() or resolved_root.parent == resolved_root:
            raise ValueError("refusing to purge an unsafe Howl data path")
        if root.exists():
            shutil.rmtree(root)
    elif config:
        config.update(activated=False, setup_stage="uninstalled")
        _save_config(config_path, config)
    return {
        "status": "uninstalled",
        "local_data": "deleted" if purge_local_data else "preserved",
        "cloud_schedule_ids": schedule_ids,
        "github_repository": config.get("repository"),
        "needs_cloud_cleanup": bool(schedule_ids),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="howl")
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup = subparsers.add_parser("setup")
    setup.add_argument("--repo", required=True)
    answers = setup.add_mutually_exclusive_group()
    answers.add_argument("--answers-stdin", action="store_true")
    answers.add_argument("--answers-file", type=Path)
    setup.add_argument("--create-workspace", action="store_true")
    setup.add_argument("--json", action="store_true")
    activate = subparsers.add_parser("activate")
    activate.add_argument("--discovery-routine-id", required=True)
    activate.add_argument("--report-routine-id", required=True)
    activate.add_argument("--json", action="store_true")
    state = subparsers.add_parser("status")
    state.add_argument("--json", action="store_true")
    uninstall = subparsers.add_parser("uninstall")
    uninstall.add_argument("--purge-local-data", action="store_true")
    uninstall.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "uninstall":
            result = uninstall_setup(purge_local_data=args.purge_local_data)
            print(json.dumps(result) if args.json else json.dumps(result, indent=2))
            return 0
        if args.command == "status":
            result = status()
            print(json.dumps(result) if args.json else json.dumps(result, indent=2))
            return 0 if result["status"] == "active" else 2
        if args.command == "activate":
            result = activate_setup(
                args.discovery_routine_id,
                args.report_routine_id,
            )
            output = {
                "status": "complete",
                "repository": result["repository"],
                "discovery_schedule": result["discovery_routine_id"],
                "report_schedule": result["report_routine_id"],
            }
            print(json.dumps(output) if args.json else json.dumps(output, indent=2))
            return 0
        if args.answers_stdin or args.answers_file:
            raw_answers = (
                args.answers_file.read_text(encoding="utf-8")
                if args.answers_file
                else sys.stdin.read()
            )
            if not raw_answers.strip():
                raise ValueError(
                    "answers input is empty; on Windows PowerShell use --answers-file PATH"
                )
            answers = validate_answers(json.loads(raw_answers))
        else:
            print(f"\n{CLAUDE_WARNING}\n")
            answers = collect_answers()
        if args.create_workspace:
            preflight_tools()
            create_workspace(args.repo)
        result = complete_setup(answers, args.repo)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        output = {"status": "error", "message": str(error)}
        print(json.dumps(output) if args.json else f"\nHowl stopped: {error}")
        return 1
    output = {
        "status": "needs_schedules",
        "repository": result["repository"],
        "schedule_requests": result["schedule_requests"],
        "report_delivery": result["profile"]["newspaper"]["delivery"],
    }
    print(json.dumps(output) if args.json else json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
