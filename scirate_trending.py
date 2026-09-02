#!/usr/bin/env python3
"""SciRate provider for Howl's quant-ph field route."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


ROUTE_ID = "quant-ph"
FEED = ROUTE_ID
BASE_URL = f"https://scirate.com/arxiv/{FEED}"
USER_AGENT = "HowlsResearchNews/0.1 (+https://github.com/m-mahadi/howl-research-news-public)"
ARXIV_RE = re.compile(r"arXiv:(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?")
INDEX_RE = re.compile(
    r"(?P<title>[^\n]{5,240}?)\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{4}.*?"
    r"arXiv:(?P<id>\d{4}\.\d{4,5})(?P<version>v\d+)?\s+"
    r"(?:Scited\s+)?Scite!\s+(?P<scites>\d+)\b",
    re.DOTALL,
)


class CollectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Paper:
    rank: int
    arxiv_id: str
    version: str | None
    title: str
    scites: int
    comments: int


@dataclass(frozen=True)
class Snapshot:
    status: str
    source: str
    source_url: str
    published_date: str | None
    observed_at: str
    coverage: str
    papers: list[Paper]
    errors: list[str]


def feed_url(day: str | None = None, range_days: int = 1) -> str:
    if day:
        date.fromisoformat(day)
    if not 1 <= range_days <= 1100:
        raise ValueError("range must be between 1 and 1100 days")
    query = {"range": range_days}
    if day:
        query["date"] = day
    return f"{BASE_URL}?{urlencode(query)}"


def parse_feed(html: str, source_url: str = BASE_URL) -> Snapshot:
    if "Performing security verification" in html or "cf-chl-" in html:
        raise CollectionError("SciRate returned its security-verification page")

    soup = BeautifulSoup(html, "html.parser")
    heading = soup.select_one("h1")
    if not heading or "quant-ph" not in heading.get_text(" ", strip=True):
        raise CollectionError("response is not the SciRate quant-ph feed")

    papers: list[Paper] = []
    published_date: str | None = None
    for item in soup.select("li.paper"):
        title_node = item.select_one(".title a")
        uid_node = item.select_one(".uid")
        count_node = item.select_one(".scites-count .count")
        if not title_node or not uid_node or not count_node:
            continue
        match = ARXIV_RE.search(uid_node.get_text(" ", strip=True))
        if not match:
            continue
        if published_date is None:
            published_date = _published_date(uid_node.get_text(" ", strip=True))
        comment_node = next(
            (
                node
                for node in item.select('a[href^="/arxiv/"]')
                if re.fullmatch(r"\d+\s+comments?", node.get_text(" ", strip=True))
            ),
            None,
        )
        papers.append(
            Paper(
                rank=len(papers) + 1,
                arxiv_id=match.group("id"),
                version=match.group("version"),
                title=title_node.get_text(" ", strip=True),
                scites=int(count_node.get_text(strip=True)),
                comments=int(comment_node.get_text(strip=True).split()[0]) if comment_node else 0,
            )
        )

    if not papers:
        raise CollectionError("SciRate quant-ph feed contained no parseable papers")
    if any(left.scites < right.scites for left, right in zip(papers, papers[1:])):
        raise CollectionError("SciRate feed was not ordered by descending scites")

    return Snapshot(
        status="live",
        source="scirate-browser",
        source_url=source_url,
        published_date=published_date,
        observed_at=_now(),
        coverage=f"exact-feed-page-1:{len(papers)}",
        papers=papers,
        errors=[],
    )


def parse_browser_payload(payload: dict[str, Any]) -> Snapshot:
    if payload.get("field") != ROUTE_ID:
        raise CollectionError("browser payload is not for the quant-ph route")
    source_url = str(payload.get("source_url", ""))
    if source_url.partition("?")[0] != BASE_URL:
        raise CollectionError("browser payload does not come from the SciRate quant-ph feed")

    published_date = payload.get("published_date")
    if not published_date:
        raise CollectionError("browser payload has no publication date")
    date.fromisoformat(published_date)
    papers: list[Paper] = []
    seen: set[str] = set()
    for index, item in enumerate(payload.get("papers", []), 1):
        arxiv_id = str(item.get("arxiv_id", ""))
        if not re.fullmatch(r"\d{4}\.\d{4,5}", arxiv_id) or arxiv_id in seen:
            raise CollectionError(f"invalid or duplicate arXiv ID at rank {index}")
        seen.add(arxiv_id)
        version = item.get("version")
        if version is not None and not re.fullmatch(r"v\d+", str(version)):
            raise CollectionError(f"invalid arXiv version at rank {index}")
        scites = int(item.get("scites", -1))
        comments = int(item.get("comments", 0))
        title = " ".join(str(item.get("title", "")).split())
        if not title or scites < 0 or comments < 0:
            raise CollectionError(f"invalid paper data at rank {index}")
        papers.append(
            Paper(index, arxiv_id, version, title, scites, comments)
        )
    if not papers or len(papers) > 50:
        raise CollectionError("browser payload must contain 1 to 50 papers")
    if any(left.scites < right.scites for left, right in zip(papers, papers[1:])):
        raise CollectionError("browser payload is not ordered by descending scites")
    return Snapshot(
        status="live",
        source="scirate-agent-browser",
        source_url=source_url,
        published_date=published_date,
        observed_at=_now(),
        coverage=f"exact-feed-page-1:{len(papers)}",
        papers=papers,
        errors=[],
    )


def collect_browser(url: str, profile: Path, timeout: int, headless: bool) -> Snapshot:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    profile.mkdir(parents=True, exist_ok=True)
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile.resolve()}")
    options.add_argument("--window-size=1280,1000")
    if headless:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        WebDriverWait(driver, timeout, poll_frequency=0.5).until(
            lambda page: bool(page.find_elements(By.CSS_SELECTOR, "li.paper"))
        )
        snapshot = parse_feed(driver.page_source, driver.current_url)
        return replace(snapshot, source="scirate-browser-headless" if headless else "scirate-browser")
    finally:
        driver.quit()


def collect_brave(day: str | None, api_key: str, timeout: int) -> Snapshot:
    query_day = date.fromisoformat(day).strftime("%b %d %Y") if day else "latest"
    query = f'site:scirate.com/arxiv/quant-ph "{query_day}" "arXiv:" "Scite!"'
    url = "https://api.search.brave.com/res/v1/web/search?" + urlencode(
        {"q": query, "count": 20, "extra_snippets": "true"}
    )
    request = Request(
        url,
        headers={"Accept": "application/json", "X-Subscription-Token": api_key, "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)

    found: dict[str, Paper] = {}
    for result in payload.get("web", {}).get("results", []):
        text = "\n".join(
            [result.get("title", ""), result.get("description", ""), *result.get("extra_snippets", [])]
        )
        for match in INDEX_RE.finditer(text):
            arxiv_id = match.group("id")
            paper = Paper(
                rank=0,
                arxiv_id=arxiv_id,
                version=match.group("version"),
                title=" ".join(match.group("title").split())[-240:],
                scites=int(match.group("scites")),
                comments=0,
            )
            if arxiv_id not in found or paper.scites > found[arxiv_id].scites:
                found[arxiv_id] = paper

    papers = sorted(found.values(), key=lambda paper: (-paper.scites, paper.arxiv_id))
    papers = [replace(paper, rank=index) for index, paper in enumerate(papers, 1)]
    if not papers:
        raise CollectionError("Brave returned no strictly parseable SciRate observations")
    return Snapshot(
        status="partial",
        source="brave-index",
        source_url=url,
        published_date=day,
        observed_at=_now(),
        coverage=f"indexed-partial:{len(papers)}",
        papers=papers,
        errors=[],
    )


def save_snapshot(snapshot: Snapshot, data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = snapshot.observed_at.replace(":", "-")
    path = data_dir / f"{stamp}-{snapshot.source}.json"
    payload = _snapshot_dict(snapshot)
    _atomic_json(path, payload)
    if snapshot.status == "live":
        _atomic_json(data_dir / "latest-verified.json", payload)
    return path


def load_stale(data_dir: Path, errors: list[str]) -> Snapshot:
    path = data_dir / "latest-verified.json"
    if not path.exists():
        detail = "; ".join(errors)
        raise CollectionError(f"all live sources failed and no verified snapshot exists ({detail})")
    snapshot = _snapshot_from_dict(json.loads(path.read_text(encoding="utf-8")))
    return replace(snapshot, status="stale", source="last-verified", errors=errors)


def collect(args: argparse.Namespace) -> Snapshot:
    url = feed_url(args.date, args.range)
    errors: list[str] = []

    if args.stdin_json:
        snapshot = parse_browser_payload(json.load(sys.stdin))
        save_snapshot(snapshot, args.data_dir)
        return snapshot

    if args.html:
        try:
            snapshot = replace(
                parse_feed(args.html.read_text(encoding="utf-8"), url),
                status="partial",
                source="saved-html",
                coverage="saved development input",
            )
            save_snapshot(snapshot, args.data_dir)
            return snapshot
        except Exception as error:  # trust boundary: preserve every failed-provider reason
            errors.append(f"saved-html: {error}")

    if not args.skip_browser:
        try:
            snapshot = collect_browser(url, args.profile, args.timeout, args.headless)
            save_snapshot(snapshot, args.data_dir)
            return snapshot
        except Exception as error:
            errors.append(f"browser: {error}")

    brave_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if brave_key:
        try:
            snapshot = collect_brave(args.date, brave_key, args.timeout)
            snapshot = replace(snapshot, errors=errors)
            save_snapshot(snapshot, args.data_dir)
            return snapshot
        except Exception as error:
            errors.append(f"brave-index: {error}")
    else:
        errors.append("brave-index: BRAVE_SEARCH_API_KEY is not configured")

    return load_stale(args.data_dir, errors)


def _published_date(text: str) -> str | None:
    match = re.search(r"([A-Z][a-z]{2}\s+\d{1,2}\s+\d{4})", text)
    return datetime.strptime(match.group(1), "%b %d %Y").date().isoformat() if match else None


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _snapshot_dict(snapshot: Snapshot) -> dict[str, Any]:
    return {"schema_version": 1, **asdict(snapshot)}


def _snapshot_from_dict(payload: dict[str, Any]) -> Snapshot:
    return Snapshot(
        status=payload["status"],
        source=payload["source"],
        source_url=payload["source_url"],
        published_date=payload.get("published_date"),
        observed_at=payload["observed_at"],
        coverage=payload["coverage"],
        papers=[Paper(**paper) for paper in payload["papers"]],
        errors=list(payload.get("errors", [])),
    )


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _print(snapshot: Snapshot, as_json: bool) -> None:
    if as_json:
        print(json.dumps(_snapshot_dict(snapshot), indent=2, ensure_ascii=False))
        return
    print(
        f"SciRate quant-ph | {snapshot.status.upper()} | published {snapshot.published_date or 'unknown'} "
        f"| observed {snapshot.observed_at} | {snapshot.source}"
    )
    for paper in snapshot.papers:
        print(f"{paper.rank:>2}. {paper.scites:>3}  {paper.arxiv_id}{paper.version or ''}  {paper.title}")
    for error in snapshot.errors:
        print(f"warning: {error}", file=sys.stderr)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--date", help="SciRate publication date (YYYY-MM-DD); omit for latest")
    result.add_argument("--range", type=int, default=1, help="SciRate range in days (default: 1)")
    result.add_argument("--timeout", type=int, default=30)
    result.add_argument("--headless", action="store_true", help="less reliable from cloud/datacenter IPs")
    result.add_argument("--skip-browser", action="store_true")
    result.add_argument("--html", type=Path, help="ingest an already rendered SciRate page")
    result.add_argument(
        "--stdin-json",
        action="store_true",
        help="ingest validated rows extracted by a persistent agent browser",
    )
    result.add_argument("--json", action="store_true")
    result.add_argument("--data-dir", type=Path, default=Path(".howl/scirate/quant-ph"))
    result.add_argument("--profile", type=Path, default=Path(".howl/chrome-profile"))
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        snapshot = collect(args)
    except Exception as error:
        print(f"SciRate quant-ph unavailable: {error}", file=sys.stderr)
        return 1
    _print(snapshot, args.json)
    return 2 if snapshot.status == "stale" else 0


if __name__ == "__main__":
    raise SystemExit(main())
