# Field discovery routes

Status: product decision, 2026-08-28

Implementation status, 2026-09-01: setup creates or repairs a daily Claude Code
cloud observation routine independently of the researcher's report schedule.
The report routine refreshes delivery-day observations before selection.

## Decision

Howl will use a **field router**, not one universal paper scraper.

Every route has four jobs:

1. **Recall:** collect plausible papers from authoritative indexes or repositories.
2. **Movement:** collect a real, attributable attention signal when the field has one.
3. **Resolution:** obtain canonical metadata and the best legal full-text location.
4. **Fallback:** produce a radar without inventing popularity when no community signal exists.

Relevance to the user's research and measured popularity are separate facts. A
model may judge a paper important, but that judgment must be labeled
`model_significance`, never `popularity` or `trending`.

## Shared backbone

These sources support every field route:

- **OpenAlex:** broad recall, topic/author/institution filters, citation graph, and
  citation counts.
- **Semantic Scholar:** semantic recommendations from positive and negative seed
  papers, citation metadata, and PDF links where available.
- **Crossref:** canonical DOI metadata and publication updates.
- **Unpaywall:** legal open-access location resolution for DOI-bearing works.
- **Repository or publisher:** canonical abstract and full text. Repository copies
  are preferred when legally available.

The shared backbone is not itself a trend detector. Total citations are slow and
strongly biased by paper age and field size.

## Routing matrix

| Field route | Recall sources | Best available movement signal | Full-text path | Honest fallback |
|---|---|---|---|---|
| **Quantum information / quantum computing** | arXiv `quant-ph`; OpenAlex/Semantic Scholar; IACR ePrint for quantum cryptography | SciRate scites, with the observation time and coverage warning attached | arXiv, IACR, then Unpaywall | Freshness plus within-`quant-ph` citation acceleration; model significance remains separate |
| **AI / machine learning / LLMs** | arXiv `cs.AI`, `cs.LG`, `stat.ML`; Hugging Face Papers; OpenReview | Hugging Face Daily Papers `trending`; public OpenReview discussion/review activity is a separate `venue_attention` signal | arXiv, OpenReview attachments, ACL Anthology, then Unpaywall | Freshness plus citation acceleration within the same AI topic and age band |
| **NLP** | arXiv `cs.CL`; ACL Anthology; OpenReview; Semantic Scholar | Hugging Face trending, then public OpenReview venue attention | ACL Anthology or arXiv, then Unpaywall | Recent ACL-family venue publication plus citation acceleration; do not call venue acceptance popularity |
| **Computer vision** | arXiv `cs.CV`; OpenReview; Semantic Scholar | Hugging Face trending, then public OpenReview venue attention | arXiv or OpenReview, then Unpaywall | Freshness plus citation acceleration within `cs.CV` |
| **Robotics / autonomy** | arXiv `cs.RO`; relevant OpenReview venues such as CoRL; Semantic Scholar | Robotics papers that enter Hugging Face trending; public OpenReview venue attention where available | arXiv, OpenReview, proceedings, then Unpaywall | Freshness plus citation acceleration within robotics topics. There is no SciRate-equivalent source we can currently trust as a universal robotics popularity board |
| **Physics, astronomy, and HEP** | relevant arXiv categories; NASA ADS for astronomy/astrophysics; INSPIRE for HEP | Field-normalized citation acceleration from ADS/INSPIRE/OpenAlex; community signals only where a real source exposes them | arXiv, repository links, then Unpaywall | Freshness, citation acceleration, and explicit model significance |
| **Biology and medicine** | PubMed/PMC; Europe PMC; bioRxiv/medRxiv; OpenAlex | Recent citation acceleration from Europe PMC/OpenAlex. Repository-wide usage totals are not paper-level popularity | PMC/Europe PMC full text, bioRxiv/medRxiv, then Unpaywall | Freshness plus citation acceleration inside the same biomedical topic; never infer popularity from clinical importance |
| **Chemistry and materials** | Crossref/OpenAlex; ChemRxiv where its supported feed or metadata access is verified; arXiv materials categories | Field-normalized citation acceleration; add a native community signal only after verifying its provenance and access terms | ChemRxiv/repository, publisher, then Unpaywall | Freshness plus citation acceleration inside the same topic and document type |
| **Mathematics and theoretical CS** | arXiv `math.*`, `cs.CC`, and related categories; zbMATH Open | Field- and age-normalized citation acceleration; no assumed fast popularity signal | arXiv, author/repository copy, then Unpaywall | Freshness plus citation acceleration, with model significance clearly labeled |
| **Cryptography and security** | IACR ePrint; arXiv `cs.CR`; OpenAlex/Semantic Scholar | Venue attention when public, then citation acceleration; no fabricated download/upvote score | IACR ePrint, arXiv, proceedings, then Unpaywall | Freshness plus citation acceleration inside crypto/security topics |
| **Economics and social science** | RePEc metadata, field working-paper series, Crossref/OpenAlex | RePEc/LogEc usage data only where programmatic use and terms permit; otherwise citation acceleration | Working-paper repository, publisher, then Unpaywall | Freshness plus field-normalized citation acceleration. Do not scrape RePEc web pages |
| **Earth, climate, and environmental science** | EarthArXiv through OSF, relevant arXiv categories, Crossref/OpenAlex | Citation acceleration and repository/venue attention only when explicitly available | EarthArXiv/OSF, repository, then Unpaywall | Freshness plus citation acceleration inside the same topic |
| **Unknown or unsupported field** | OpenAlex search/topics plus Semantic Scholar recommendations; Crossref for DOI enrichment | None by default | Unpaywall, repository, then publisher | Return `radar_basis: significance`, not `trending`, until a field route is verified |

## What “moving” means

Each returned paper carries one of these evidence labels:

- `community_attention`: a native, user-generated rank such as SciRate scites or
  Hugging Face trending.
- `venue_attention`: observable public activity around a submission or venue; it
  is not equivalent to broad field popularity.
- `citation_acceleration`: unusually fast citation growth compared with papers in
  the same field and age band.
- `model_significance`: Howl's explained judgment that the work may matter. This
  is useful, but it is not measured popularity.

Raw counts are never compared across fields. Ranking and thresholds are computed
within the same source, field/topic, document type, and age window. Every signal
stores its provider, retrieval time, covered date range, raw value, normalized
value, and any known coverage limitation.

## Help Now selection

For each candidate paper, Howl evaluates its usefulness against every active
research question and retains the paper's strongest match. It then ranks all
candidates globally by that best-match score and fills the researcher-selected
number of Help Now slots. There is no per-question quota or forced diversity: if
the best papers all serve one question, they may take every slot. Papers below
the Help Now relevance threshold are never included merely to fill the report.
After that gate, expected immediate utility outranks semantic similarity. A
paper that can resolve a blocker, supply a usable method, or materially change
the researcher's next action ranks above a closer topical match that merely
repeats known work.

Selection uses a two-pass funnel. Recall targets roughly 100 plausible papers.
The first pass ranks titles and abstracts, then retains a deep-reading shortlist
of about three to four times the requested final count—typically around ten
papers when the researcher requests two or three. The second pass examines each
shortlisted paper's abstract, results, limitations, and any methods, conclusions,
figures, or other sections needed to verify utility before choosing the final
requested number.

Before finalization, Howl removes practical redundancy. When two papers provide
essentially the same method or insight, only the stronger one keeps a slot and
the next useful candidate is promoted. Multiple papers may still serve the same
research question when each contributes distinct value.

A final recommendation in either Help Now or Field Radar requires legally
accessible, sufficiently complete full text. Abstract-only records may help
recall but are ineligible for the deep-reading shortlist and the generated
report. If full text cannot be resolved, Howl skips the paper and considers the
next candidate.

Field Radar is independent of active research questions. It selects and orders
papers only by verified movement within the researcher's declared field; user
relevance never gates or reranks them. If a Field Radar paper also matches the
researcher's current work, the report may explain that connection without
changing the movement ranking.

When a researcher declares multiple fields, Howl normalizes each movement
signal inside its own field and source, then ranks the normalized candidates
globally. The hottest papers take the requested slots without per-field quotas;
raw counts from different fields or providers are never compared directly.

Field Radar returns up to the requested number, not a fixed count. A candidate
fills a slot only when its age-normalized movement clears the researcher's
popularity floor; on a quiet period Field Radar shows fewer papers, or states
that nothing cleared the floor rather than padding with cold papers. The floor
is a researcher setting from onboarding, expressed as a strictness level rather
than a raw scite count because movement is normalized within the field and age
window; its default is balanced.

Claude Code cloud scheduled collectors run daily regardless of the researcher's
delivery schedule. Their GitHub-backed observations remain eligible for the next
scheduled report, so a paper that peaks between deliveries is not lost before a
weekly or custom-day report runs.

Before each Field Radar selection, Howl excludes every canonical paper already
shown to that researcher. Continued or repeated popularity never makes the same
paper eligible for another report; the next hottest unseen paper takes the slot.

If one unseen paper qualifies for both sections of the same report, Howl shows
it once in Help Now and annotates its Field Radar movement signal. The next
hottest unseen paper fills the Field Radar slot, preserving the requested number
of unique papers.

## SciRate route

SciRate is the preferred movement signal for quantum information, but its current
Cloudflare configuration blocks ordinary HTTP clients. The authoritative
collection contract lives in `.agents/skills/quant-ph-scirate/SKILL.md`:

1. From the Claude Code cloud scheduled task, use a supported connector that
   provides an ordinary browser context. Never reuse a local browser profile.
2. If ordinary browser verification does not resolve, use search-indexed SciRate
   pages labeled `partial`.
3. If indexed coverage is unavailable, return the last verified snapshot from
   the private GitHub-backed Howl workspace labeled `stale`.
4. If no verified snapshot exists, report SciRate unavailable, raise an
   operational alert, and fill the Field Radar slots from the separately labeled
   `citation_acceleration` fallback. Never return an empty Field Radar as valid
   and never present the fallback as SciRate popularity.

Every successful observation remains `community_attention` and records its
provider, coverage, source URL, publication date, and observation time. Howl
never bypasses a CAPTCHA, disguises traffic, or labels indexed or stored data as
live SciRate popularity.

The user-facing alert points researchers to
[`@howl_codes`](https://x.com/howl_codes) when the failure persists.

## Build order

1. **Quantum route:** arXiv recall + resilient SciRate movement + shared enrichment.
   Faisal is the first tester.
2. **AI/LLM route:** arXiv + Hugging Face trending + OpenReview/ACL enrichment.
3. **Robotics route:** arXiv + Hugging Face/OpenReview signals where present +
   citation-acceleration fallback.
4. **Generic route:** OpenAlex/Semantic Scholar + Crossref/Unpaywall, with no
   popularity claim.
5. Add another field-specific connector only when a real user needs it and the
   source's access terms and signal semantics have been verified.

This keeps the first product small while preserving a clean path to generality.

## Source notes

- [OpenAlex Works API](https://developers.openalex.org/api-reference/works/list-works)
- [Semantic Scholar APIs](https://www.semanticscholar.org/product/api)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [Unpaywall API](https://unpaywall.org/api)
- [Hugging Face `list_daily_papers`](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api#huggingface_hub.HfApi.list_daily_papers)
- [OpenReview API](https://docs.openreview.net/getting-started/using-the-api)
- [ACL Anthology programmatic access](https://aclanthology.org/faq/api/)
- [Europe PMC REST API](https://europepmc.org/RestfulWebService)
- [NCBI APIs](https://www.ncbi.nlm.nih.gov/home/develop/api/)
- [bioRxiv API](https://api.biorxiv.org/)
- [NASA ADS API](https://ui.adsabs.harvard.edu/help/api/)
- [INSPIRE API announcement and documentation link](https://blog.inspirehep.net/2020/06/we-released-the-new-inspire-api/)
- [zbMATH Open API client and endpoints](https://github.com/zbMATHOpen/zbRestApiClient)
- [RePEc metadata access](https://ideas.repec.org/getdata.html)
- [OSF API](https://developer.osf.io/)
- [SciRate source repository](https://github.com/scirate/scirate)
- [SciRate read-access issue](https://github.com/scirate/scirate/issues/544)
- [SciRate JSON API pull request](https://github.com/scirate/scirate/pull/535)
- [SciRate RSS issue](https://github.com/scirate/scirate/issues/547)
