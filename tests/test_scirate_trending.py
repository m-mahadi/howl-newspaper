import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scirate_trending import (
    CollectionError,
    Paper,
    collect,
    parse_browser_payload,
    parse_feed,
    save_snapshot,
)


HTML = """
<html><body><h1>Quantum Physics (quant-ph)</h1><ul>
<li class="paper"><div class="title"><a>First paper</a></div>
<div class="uid">Aug 27 2026 quant-ph arXiv:2608.00001v1</div>
<div class="scites-count"><button class="count">12</button></div>
<a href="/arxiv/2608.00001">2 comments</a></li>
<li class="paper"><div class="title"><a>Second paper</a></div>
<div class="uid">Aug 27 2026 quant-ph arXiv:2608.00002v2</div>
<div class="scites-count"><button class="count">7</button></div></li>
</ul></body></html>
"""


class SciRateTrendingTests(unittest.TestCase):
    def test_parses_exact_feed(self):
        snapshot = parse_feed(HTML)
        self.assertEqual(snapshot.published_date, "2026-08-27")
        self.assertEqual(snapshot.papers[0], Paper(1, "2608.00001", "v1", "First paper", 12, 2))
        self.assertEqual(snapshot.papers[1].scites, 7)

    def test_rejects_challenge_page(self):
        with self.assertRaisesRegex(CollectionError, "security-verification"):
            parse_feed("<h2>Performing security verification</h2>")

    def test_validates_agent_browser_payload(self):
        snapshot = parse_browser_payload(
            {
                "field": "quant-ph",
                "source_url": "https://scirate.com/arxiv/quant-ph?range=1",
                "published_date": "2026-08-27",
                "papers": [
                    {"arxiv_id": "2608.00001", "version": "v1", "title": "First", "scites": 12},
                    {"arxiv_id": "2608.00002", "version": "v1", "title": "Second", "scites": 7},
                ],
            }
        )
        self.assertEqual(snapshot.source, "scirate-agent-browser")
        self.assertEqual(snapshot.papers[0].rank, 1)

    def test_rejects_misordered_agent_browser_payload(self):
        with self.assertRaisesRegex(CollectionError, "descending"):
            parse_browser_payload(
                {
                    "field": "quant-ph",
                    "source_url": "https://scirate.com/arxiv/quant-ph?range=1",
                    "published_date": "2026-08-27",
                    "papers": [
                        {"arxiv_id": "2608.00001", "title": "First", "scites": 1},
                        {"arxiv_id": "2608.00002", "title": "Second", "scites": 2},
                    ],
                }
            )

    def test_uses_last_verified_snapshot_without_calling_browser(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            live = parse_feed(HTML)
            save_snapshot(live, data_dir)
            args = argparse.Namespace(
                date="2026-08-27",
                range=1,
                timeout=1,
                headless=True,
                skip_browser=True,
                html=None,
                stdin_json=False,
                json=False,
                data_dir=data_dir,
                profile=data_dir / "profile",
            )
            stale = collect(args)
            self.assertEqual(stale.status, "stale")
            self.assertEqual(stale.source, "last-verified")
            self.assertIn("BRAVE_SEARCH_API_KEY", stale.errors[0])
            saved = json.loads((data_dir / "latest-verified.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "live")

    def test_saved_html_cannot_become_a_verified_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            html_path = data_dir / "feed.html"
            html_path.write_text(HTML, encoding="utf-8")
            args = argparse.Namespace(
                date="2026-08-27",
                range=1,
                timeout=1,
                headless=True,
                skip_browser=True,
                html=html_path,
                stdin_json=False,
                json=False,
                data_dir=data_dir,
                profile=data_dir / "profile",
            )
            snapshot = collect(args)
            self.assertEqual(snapshot.status, "partial")
            self.assertFalse((data_dir / "latest-verified.json").exists())

    def test_reports_provider_failures_when_no_snapshot_exists(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            args = argparse.Namespace(
                date="2026-08-27",
                range=1,
                timeout=1,
                headless=True,
                skip_browser=True,
                html=None,
                stdin_json=False,
                json=False,
                data_dir=data_dir,
                profile=data_dir / "profile",
            )
            with self.assertRaisesRegex(CollectionError, "BRAVE_SEARCH_API_KEY"):
                collect(args)


if __name__ == "__main__":
    unittest.main()
