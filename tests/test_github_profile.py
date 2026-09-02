import base64
import json
import unittest
from types import SimpleNamespace

from github_profile import upload_profile_from_gh


class Response:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps({"commit": {"sha": "c" * 40}}).encode("utf-8")


class TestGitHubMemory(unittest.TestCase):
    def test_identical_profile_is_not_committed_again(self):
        profile = {"schema_version": 1, "fields": ["Biochemistry"]}
        canonical = json.dumps(
            profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "sha": "a" * 40,
                        "content": base64.b64encode(canonical).decode("ascii"),
                    }
                ),
                stderr="",
            )

        result = upload_profile_from_gh(profile, "owner/memory", runner=run)

        self.assertEqual(result, "a" * 40)
        self.assertEqual(len(calls), 1)

    def test_profile_upload_uses_stdin_and_updates_existing_file(self):
        calls = []
        profile = {"schema_version": 1, "fields": ["Biochemistry"]}

        def run(command, **kwargs):
            calls.append((command, kwargs))
            if "GET" in command:
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps({"sha": "a" * 40}),
                    stderr="",
                )
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"commit": {"sha": "b" * 40}}),
                stderr="",
            )

        commit = upload_profile_from_gh(
            profile, "owner/memory", branch="main", runner=run
        )

        self.assertEqual(commit, "b" * 40)
        self.assertIn("GET", calls[0][0])
        self.assertIn("PUT", calls[1][0])
        body = json.loads(calls[1][1]["input"])
        self.assertEqual(body["sha"], "a" * 40)
        self.assertEqual(json.loads(base64.b64decode(body["content"])), profile)
        self.assertNotIn("Biochemistry", " ".join(calls[1][0]))

if __name__ == "__main__":
    unittest.main()
