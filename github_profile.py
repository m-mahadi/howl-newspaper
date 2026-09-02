import base64
import json
import os
import re
import subprocess


def _no_window_run(*args, **kwargs):
    # Console-subsystem children (gh) pop a window on Windows unless told
    # not to. Setup runs these, and a flashing console is visible noise.
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    return subprocess.run(*args, **kwargs)


API_VERSION = "2026-03-10"
MAX_PROFILE_BYTES = 64 * 1024


def upload_profile_from_gh(
    profile,
    repository,
    *,
    branch="main",
    runner=_no_window_run,
):
    if not isinstance(profile, dict):
        raise ValueError("profile must be an object")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid repository")
    if not isinstance(branch, str) or not branch:
        raise ValueError("missing GitHub configuration")
    content = json.dumps(
        profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(content) > MAX_PROFILE_BYTES:
        raise ValueError("profile is too large")
    endpoint = f"repos/{repository}/contents/howl-profile/config.json"
    lookup = runner(
        ["gh", "api", "--method", "GET", endpoint, "-f", f"ref={branch}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    sha = None
    if lookup.returncode == 0:
        try:
            existing = json.loads(lookup.stdout)
            sha = existing["sha"]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError("GitHub returned an invalid profile") from error
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40,64}", sha):
            raise RuntimeError("GitHub returned an invalid profile")
        encoded_existing = existing.get("content")
        if isinstance(encoded_existing, str):
            try:
                existing_content = base64.b64decode(
                    encoded_existing.replace("\n", ""), validate=True
                )
            except ValueError:
                existing_content = None
            if existing_content == content:
                return sha
    elif "404" not in lookup.stderr:
        raise RuntimeError("GitHub profile lookup failed")
    body = {
        "message": "profile: update onboarding",
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    result = runner(
        ["gh", "api", "--method", "PUT", endpoint, "--input", "-"],
        input=json.dumps(body),
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError("GitHub profile upload failed")
    try:
        commit = json.loads(result.stdout)["commit"]["sha"]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("GitHub returned an invalid commit") from error
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise RuntimeError("GitHub returned an invalid commit")
    return commit
