---
name: quant-ph-scirate
description: Collects and verifies the live SciRate ranking for Howl's quant-ph field route. Use when a quant-ph Field Radar run needs current SciRate scites, rankings, or trend observations.
---

# Quant-ph SciRate

Status: provider contract, local payload validator, and daily Claude Code cloud
routine orchestration implemented; live connector collection and GitHub-backed
verified-snapshot dogfood pending.

This is one provider inside Howl's `quant-ph` field route. Never use it for
another field.

## Claude cloud collection

1. Run from a Claude Code cloud scheduled task. Attempt the live feed only
   through a supported task connector that provides an ordinary browser context;
   a fresh cloud clone never reuses the researcher's local browser profile.
2. Open `https://scirate.com/arxiv/quant-ph?range=1`. Add
   `date=YYYY-MM-DD` only when rechecking a known publication day.
3. Wait up to 15 seconds for ordinary security verification to finish.
4. Continue only if the title is `Quantum Physics`, the heading contains
   `Quantum Physics (quant-ph)`, and at least one `li.paper` exists.
5. If a CAPTCHA or unresolved challenge appears, do not bypass it. Use fallback.
6. Extract at most the first 50 `li.paper` rows in DOM order:
   - `.title a` → `title`
   - `.uid` → arXiv ID, optional version, and publication date
   - `.scites-count .count` → `scites`
   - a link matching `N comment` or `N comments` → `comments`
7. The scheduled task validates and stores this shape in the researcher's
   private GitHub-backed Howl workspace:

```json
{
  "field": "quant-ph",
  "source_url": "the final SciRate URL",
  "published_date": "YYYY-MM-DD",
  "papers": [
    {"arxiv_id": "2608.25027", "version": "v1", "title": "...", "scites": 50, "comments": 0}
  ]
}
```

During local development, pipe that JSON to `python scirate_trending.py
--stdin-json`. The validator rejects wrong fields or URLs, duplicate or malformed
IDs, negative counts, more than 50 rows, and rankings not ordered by scites.

## Fallback

1. Try the configured web-search API. Indexed results are `partial`, never live.
2. Otherwise return the newest verified workspace snapshot as `stale`, with its
   observation time and every failed-provider reason.
3. If no verified snapshot exists, report SciRate unavailable. Never substitute
   arXiv recency, citation acceleration, or model judgment for SciRate
   popularity. The field route may use its separately labeled
   `citation_acceleration` fallback while preserving the SciRate failure alert.

Never use stealth drivers, proxy rotation, fingerprint evasion, CAPTCHA solving,
or disguised traffic. One exact feed request per run is enough.
