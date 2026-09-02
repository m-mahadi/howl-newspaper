import unittest
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from howl import (
    _run_json,
    activate_setup,
    collect_answers,
    complete_setup,
    create_workspace,
    ensure_discovery_schedule,
    ensure_report_schedule,
    main,
    normalize_repository,
    preflight,
    status,
    uninstall_setup,
    validate_answers,
)


class TestHowlSetup(unittest.TestCase):
    def test_create_workspace_creates_private_repo_and_pushes_without_force(self):
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            if command[:3] == ["gh", "repo", "view"]:
                return type(
                    "Result", (), {"returncode": 1, "stdout": "", "stderr": "HTTP 404"}
                )()
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        create_workspace("owner/howl-research-memory", runner=run)

        self.assertIn(
            ["gh", "repo", "create", "owner/howl-research-memory", "--private"],
            [command for command, _ in calls],
        )
        push = next(command for command, _ in calls if command[:2] == ["git", "push"])
        self.assertEqual(
            push,
            [
                "git",
                "push",
                "https://github.com/owner/howl-research-memory.git",
                "HEAD:main",
            ],
        )
        self.assertNotIn("--force", push)

    def test_create_workspace_accepts_github_graphql_missing_message(self):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["gh", "repo", "view"]:
                return type(
                    "Result",
                    (),
                    {
                        "returncode": 1,
                        "stdout": "",
                        "stderr": "GraphQL: Could not resolve to a Repository with the name 'owner/memory'.",
                    },
                )()
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        create_workspace("owner/memory", runner=run)

        self.assertIn(["gh", "repo", "create", "owner/memory", "--private"], calls)

    def test_create_workspace_seeds_existing_empty_private_repo(self):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if command[:3] == ["gh", "repo", "view"]:
                return type(
                    "Result",
                    (),
                    {
                        "returncode": 0,
                        "stdout": '{"isPrivate":true,"defaultBranchRef":null}',
                        "stderr": "",
                    },
                )()
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        self.assertTrue(create_workspace("owner/memory", runner=run))
        self.assertNotIn(["gh", "repo", "create", "owner/memory", "--private"], calls)
        self.assertIn(
            ["git", "push", "https://github.com/owner/memory.git", "HEAD:main"],
            calls,
        )

    def test_agent_answers_are_normalized_without_faking_consent(self):
        answers = validate_answers(
            {
                "fields": [" Artificial intelligence ", "Law"],
                "current_research": "How can research agents retain useful context?",
                "work_mode": "computational",
            }
        )

        self.assertEqual(answers["fields"], ["Artificial intelligence", "Law"])
        self.assertEqual(answers["newspaper"]["popularity_floor"], "balanced")
        self.assertNotIn("permissions", answers)
        self.assertEqual(
            normalize_repository("https://github.com/m-mahadi/howls-research-news.git"),
            "m-mahadi/howls-research-news",
        )

    def test_guided_setup_asks_one_question_at_a_time(self):
        replies = iter(
            [
                "AI, software engineering",
                "Build durable research memory without disrupting agent work",
                "computational",
                "Python, retrieval evaluation",
                "",
            ]
        )
        prompts = []

        answers = collect_answers(lambda prompt: prompts.append(prompt) or next(replies))

        self.assertEqual(len(prompts), 5)
        self.assertEqual(answers["fields"], ["AI", "software engineering"])
        self.assertEqual(answers["newspaper"]["cadence"], "weekly")
        self.assertEqual(answers["newspaper"]["weekdays"], ["monday"])

    def test_guided_setup_collects_the_full_delivery_card(self):
        replies = iter(
            [
                "Biochemistry",
                "Protein folding under crowding",
                "experimental",
                "mass spectrometry",
                "yes",
                "yes",
                "yes",
                "weekly",
                "monday,thursday",
                "2",
                "4",
                "strict",
                "radar",
                "17:30",
                "Europe/Brussels",
                "both",
            ]
        )

        answers = collect_answers(lambda _prompt: next(replies))
        newspaper = answers["newspaper"]

        self.assertEqual(newspaper["help_now_papers"], 2)
        self.assertEqual(newspaper["field_radar_papers"], 4)
        self.assertEqual(newspaper["popularity_floor"], "strict")
        self.assertEqual(newspaper["section_order"][0], "field_radar")
        self.assertEqual(newspaper["weekdays"], ["monday", "thursday"])
        self.assertEqual(newspaper["delivery_time"], "17:30")
        self.assertEqual(newspaper["timezone"], "Europe/Brussels")
        self.assertEqual(newspaper["delivery"], "both")

    def test_answers_reject_invalid_newspaper_boundaries(self):
        with self.assertRaisesRegex(ValueError, "Help Now papers"):
            validate_answers(
                {
                    "fields": ["Physics"],
                    "current_research": "Precision sensing",
                    "newspaper": {"help_now_papers": 0},
                }
            )

    @patch("howl._run_json", return_value={"result": "HOWL_REPORT_ROUTINE=trig_report"})
    def test_report_schedule_delivers_reviewed_html_on_configured_cadence(
        self, mocked_run
    ):
        newspaper = validate_answers(
            {
                "fields": ["AI"],
                "current_research": "Agent memory",
                "newspaper": {
                    "cadence": "interval",
                    "interval_days": 3,
                    "delivery_time": "09:00",
                    "timezone": "Asia/Dhaka",
                    "delivery": "both",
                },
            }
        )["newspaper"]
        routine_id = ensure_report_schedule(
            "owner/memory",
            "main",
            newspaper,
        )

        command = mocked_run.call_args.args[0]
        prompt = command[command.index("-p") + 1]
        self.assertEqual(routine_id, "trig_report")
        self.assertIn("every 3 days at 09:00 in timezone Asia/Dhaka", prompt)
        self.assertIn("separate adversarial reviewer", prompt)
        self.assertIn("output/reports/<issue-date>/", prompt)
        self.assertIn("two-pass recall and deep-reading funnel", prompt)
        self.assertIn('"delivery":"both"', prompt)

    @patch(
        "howl._run_json",
        return_value={"result": "HOWL_DISCOVERY_ROUTINE=trig_discovery"},
    )
    def test_discovery_runs_daily_independent_of_report_cadence(self, mocked_run):
        routine_id = ensure_discovery_schedule(
            "owner/memory", "main", "Europe/Brussels"
        )

        command = mocked_run.call_args.args[0]
        prompt = command[command.index("-p") + 1]
        self.assertEqual(routine_id, "trig_discovery")
        self.assertIn("Run it daily at 05:00", prompt)
        self.assertIn("in timezone Europe/Brussels", prompt)
        self.assertIn("peaks between newspaper deliveries", prompt)
        self.assertIn("howl-observations/", prompt)

    @patch("howl._run_json", return_value={"result": "HOWL_REPORT_ROUTINE=weekly"})
    def test_report_schedule_keeps_selected_weekdays(self, mocked_run):
        newspaper = validate_answers(
            {
                "fields": ["Physics"],
                "current_research": "Quantum sensing",
                "newspaper": {
                    "weekdays": ["monday", "thursday"],
                    "delivery_time": "17:30",
                    "timezone": "Europe/Brussels",
                },
            }
        )["newspaper"]

        ensure_report_schedule("owner/memory", "main", newspaper)

        command = mocked_run.call_args.args[0]
        self.assertIn(
            "weekly on monday, thursday at 17:30 in timezone Europe/Brussels",
            command[command.index("-p") + 1],
        )


    @patch("howl.upload_profile_from_gh", return_value="c" * 40)
    @patch("howl.preflight")
    def test_rerunning_setup_keeps_the_recorded_cloud_routines(
        self,
        mocked_preflight,
        mocked_upload,
    ):
        """A second setup must not strand routines the first one created.

        uninstall reports which cloud routines to remove by reading these ids
        out of the config. Rebuilding the config without them leaves routines
        running with nothing on disk pointing at them.
        """
        with TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "repository": "m-mahadi/howls-research-news",
                        "activated": True,
                        "setup_stage": "complete",
                                                "discovery_routine_id": "trig_discovery",
                        "report_routine_id": "trig_report",
                    }
                ),
                encoding="utf-8",
            )
            mocked_preflight.return_value = {
                "settings_path": root / ".claude" / "settings.json",
                "branch": "main",
                "timezone": "Asia/Dhaka",
            }
            profile = validate_answers(
                {
                    "fields": ["AI"],
                    "current_research": "Durable agent memory",
                }
            )

            complete_setup(
                profile,
                "m-mahadi/howls-research-news",
                config_path=config_path,
            )

            saved = json.loads(config_path.read_text("utf-8"))
            self.assertEqual(saved["discovery_routine_id"], "trig_discovery")
            self.assertEqual(saved["report_routine_id"], "trig_report")
            # The rerun still starts from an unactivated, schedule-pending state.
            self.assertFalse(saved["activated"])
            self.assertEqual(saved["setup_stage"], "schedules")

    @patch("howl.upload_profile_from_gh", return_value="c" * 40)
    @patch("howl.preflight")
    def test_first_setup_records_no_routines(
        self,
        mocked_preflight,
        mocked_upload,
    ):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            mocked_preflight.return_value = {
                "settings_path": root / ".claude" / "settings.json",
                "branch": "main",
                "timezone": "Asia/Dhaka",
            }
            profile = validate_answers(
                {
                    "fields": ["AI"],
                    "current_research": "Durable agent memory",
                }
            )

            complete_setup(
                profile,
                "m-mahadi/howls-research-news",
                config_path=root / "config.json",
            )

            saved = json.loads((root / "config.json").read_text("utf-8"))
            self.assertNotIn("discovery_routine_id", saved)
    @patch("howl.upload_profile_from_gh", return_value="c" * 40)
    @patch("howl.preflight")
    def test_complete_setup_pauses_for_agent_owned_cloud_schedules(
        self,
        mocked_preflight,
        mocked_upload,
    ):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            settings = root / ".claude" / "settings.json"
            mocked_preflight.return_value = {
                "settings_path": settings,
                "branch": "main",
                "timezone": "Asia/Dhaka",
            }
            profile = validate_answers(
                {
                    "fields": ["AI"],
                    "current_research": "Durable agent memory",
                }
            )

            result = complete_setup(
                profile,
                "m-mahadi/howls-research-news",
                config_path=root / "config.json",
            )

            saved = json.loads((root / "config.json").read_text("utf-8"))
            self.assertFalse(saved["activated"])
            self.assertEqual(saved["setup_stage"], "schedules")
            self.assertEqual(len(result["schedule_requests"]), 2)
            self.assertEqual(
                [request["kind"] for request in result["schedule_requests"]],
                ["discovery", "report"],
            )
            self.assertIn(
                "Howl: m-mahadi/howls-research-news: Daily paper observations",
                result["schedule_requests"][0]["prompt"],
            )
            mocked_upload.assert_called_once()

            activated = activate_setup(
                "trig_discovery",
                "trig_report",
                config_path=root / "config.json",
            )
            self.assertTrue(activated["activated"])
            self.assertEqual(activated["setup_stage"], "complete")

    def test_agent_setup_returns_json_for_invalid_answers(self):
        output = StringIO()
        with patch("howl.sys.stdin", StringIO("not-json")), redirect_stdout(output):
            exit_code = main(
                [
                    "setup",
                    "--repo",
                    "owner/private-memory",
                    "--answers-stdin",
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "error")

    def test_empty_stdin_explains_windows_answers_file_fallback(self):
        output = StringIO()
        with patch("howl.sys.stdin", StringIO("")), redirect_stdout(output):
            exit_code = main(
                [
                    "setup",
                    "--repo",
                    "owner/private-memory",
                    "--answers-stdin",
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("--answers-file", json.loads(output.getvalue())["message"])

    def test_answers_file_works_without_powershell_stdin(self):
        with TemporaryDirectory() as temp:
            answers_path = Path(temp) / "answers.json"
            answers_path.write_text(
                json.dumps(
                    {
                        "fields": ["Biochemistry"],
                        "current_research": "Protein folding",
                    }
                ),
                encoding="utf-8",
            )
            output = StringIO()
            stub = {
                "repository": "owner/private-memory",
                "schedule_requests": [],
                "profile": {"newspaper": {"delivery": "folder"}},
            }
            with (
                patch("howl.complete_setup", return_value=stub),
                redirect_stdout(output),
            ):
                exit_code = main(
                    [
                        "setup",
                        "--repo",
                        "owner/private-memory",
                        "--answers-file",
                        str(answers_path),
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(output.getvalue())["status"], "needs_schedules"
        )

    def test_workspace_is_created_only_after_tool_preflight(self):
        order = []
        with TemporaryDirectory() as temp:
            answers_path = Path(temp) / "answers.json"
            profile = validate_answers(
                {"fields": ["AI"], "current_research": "Agent memory"}
            )
            answers_path.write_text(json.dumps(profile), encoding="utf-8")
            result = {
                "repository": "owner/memory",
                "profile": profile,
                "schedule_requests": [],
            }
            with (
                patch("howl.preflight_tools", side_effect=lambda: order.append("preflight")),
                patch("howl.create_workspace", side_effect=lambda _repo: order.append("create")),
                patch(
                    "howl.complete_setup",
                    side_effect=lambda *args, **kwargs: order.append("setup") or result,
                ),
                redirect_stdout(StringIO()),
            ):
                exit_code = main(
                    [
                        "setup",
                        "--repo",
                        "owner/memory",
                        "--create-workspace",
                        "--answers-file",
                        str(answers_path),
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(order, ["preflight", "create", "setup"])

    @patch("howl._run_json")
    @patch("howl.shutil.which")
    def test_preflight_runs_resolved_windows_wrappers(self, mocked_which, mocked_run):
        mocked_which.side_effect = [r"C:\Tools\claude.CMD", r"C:\Tools\gh.exe"]
        mocked_run.side_effect = [
            {"loggedIn": True, "apiProvider": "firstParty"},
            {"isPrivate": True, "defaultBranchRef": {"name": "main"}},
        ]

        preflight("owner/memory")

        self.assertEqual(mocked_run.call_args_list[0].args[0][-4], r"C:\Tools\claude.CMD")
        self.assertEqual(mocked_run.call_args_list[1].args[0][0], r"C:\Tools\gh.exe")

    @patch("howl.subprocess.run", side_effect=FileNotFoundError("missing"))
    def test_subprocess_error_names_the_failing_command(self, _mocked_run):
        with self.assertRaisesRegex(RuntimeError, "claude.CMD failed"):
            _run_json([r"C:\Tools\claude.CMD", "auth", "status"])

    def test_uninstall_reports_the_routines_the_user_must_remove(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "repository": "owner/papers",
                        "discovery_routine_id": "trig_discovery",
                        "report_routine_id": "trig_report",
                        "activated": True,
                        "setup_stage": "complete",
                    }
                ),
                encoding="utf-8",
            )

            result = uninstall_setup(config_path=config_path, home=root)

            self.assertEqual(result["local_data"], "preserved")
            self.assertTrue(result["needs_cloud_cleanup"])
            self.assertEqual(
                result["cloud_schedule_ids"],
                {
                    "discovery_routine_id": "trig_discovery",
                    "report_routine_id": "trig_report",
                },
            )
            self.assertEqual(result["github_repository"], "owner/papers")
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["setup_stage"], "uninstalled")
            self.assertFalse(saved["activated"])

    def test_uninstall_purge_deletes_only_howl_data_root(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            data_root = home / "Howl"
            config_path = data_root / "config.json"
            data_root.mkdir(parents=True)
            config_path.write_text("{}", encoding="utf-8")
            keep = home / "keep.txt"
            keep.write_text("safe", encoding="utf-8")

            result = uninstall_setup(
                purge_local_data=True,
                config_path=config_path,
                home=home,
            )

            self.assertEqual(result["local_data"], "deleted")
            self.assertFalse(data_root.exists())
            self.assertEqual(keep.read_text(encoding="utf-8"), "safe")

    def test_uninstall_refuses_to_purge_the_home_directory(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            with self.assertRaises(ValueError):
                uninstall_setup(
                    purge_local_data=True,
                    config_path=home / "config.json",
                    home=home,
                )
            self.assertTrue(home.exists())


if __name__ == "__main__":
    unittest.main()
