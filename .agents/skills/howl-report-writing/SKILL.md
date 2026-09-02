---
name: howl-report-writing
description: Writes and revises expert, two-page Howl paper briefings as accurate research stories rather than templated summaries. Use for any Help Now or Field Radar report draft, review, revision, or report-writing architecture change.
---

# Howl report writing

Load this after `howl-repo-hygiene`. Follow the repository privacy rules: the
audience brief may contain only the researcher-authored profile.
README owns the approved report bones; this skill governs their contents and
workflow.

## Inputs

Require the full paper text, page-level figure/table provenance, the selected
paper-native evidence crop, and the bounded audience brief. If the full paper or
claim-carrying evidence is unavailable, do not write the report.

## Write the spine before prose

Create `output/reports/<slug>/spine.json` with:

- `central_claim`: the strongest interesting claim that remains true;
- `opening`: the concrete number, result, mechanism, or contradiction that earns
  attention;
- `stakes`: what the paper was trying to settle and why it matters;
- `mechanism`: only the method needed to judge the claim;
- `hero_evidence`: crop, claim it carries, boundary, and provenance;
- `falsification`: strongest in-paper evidence against the central claim and
  where it was sought;
- `observed_failures`: errors or weaknesses the paper actually demonstrates;
- `confounds`: at most three pairs of things the design leaves fused;
- `reader_connection`: the exact artifact or question in the audience's work;
- `payoff`: the operation the reader can perform after reading.

Reject the spine if it merely restates the abstract, treats an inference as a
paper claim, or has no documented falsification attempt. A paper with no useful
spine for this reader may be skipped.

## Draft as a research story

Keep the frame, exact paper title, full-text link, metadata, one hero evidence
block, sources, and folios fixed. Length is two to four A4 pages, sized to what
the paper needs; the design must breathe and is never crammed to hit a lower
page count. Keep whole sections together: never split a section across a page
break so that a paragraph orphans at the top of the next page with no heading.
If a page overflows, add a page rather than fragment, and prefer one figure per
page sitting with the section it supports. Do not print generic section
labels such as QUESTION, METHOD, RESULT, or LIMITS. Use paper-specific claim
subheads and let the argument determine paragraph order.

Open on the concrete thing worth knowing. Establish its frame, then move through
stakes, load-bearing mechanism, evidence, the strongest complication, and the
reader payoff. Use plain words and concrete specimens. Interpret numbers against
a meaningful floor, ceiling, baseline, or comparison. Never teach an expert how
to read a table.

Keep observed failures in the narrative. Use one `What this does not show`
container for confounds only; no claim may appear both there and in the body. Use
at most three entries, each naming the design fact that fuses two quantities.
Keep ordinary scope notes attached to the relevant sentence, never as entries.
Mark every inference in the sentence (`Howl reads`, `the paper does not report`,
or equivalent). Never promote a number beyond its stage, subset, model, or
evaluation protocol.

Caption the hero with one claim, one boundary, and exact provenance. The body
extends the caption instead of repeating it. Close with a specific use for the
reader and what it does not settle. Never close with `complementary`, `side by
side`, `worth a read`, `might be useful`, or a restatement of the headline.
Vary sentence length so emphasis has somewhere to land. Use the balanced
X-not-Y construction at most twice.

Before writing any prose, and again when revising it, load and apply
[`.agents/skills/writing-clearly-and-concisely/SKILL.md`](../writing-clearly-and-concisely/SKILL.md):
active voice, positive form, definite and concrete language, omit needless
words, emphatic word last. Cut puffery, empty `-ing` phrases, promotional
adjectives, and AI vocabulary (delve, leverage, multifaceted, robust). Never
open a paragraph on jargon the reader has not been given; name the thing in
plain words first, then the term. This clarity pass is mandatory for every
draft and sits alongside the no-em-dash house style.

## Equation and theorem heroes

When an equation or theorem carries the claim better than a figure, the hero may
be an equation/theorem block. Choose faithfulness first and rendering second, in
three modes (full markup in
[`references/report-template.html`](references/report-template.html)):

1. Verbatim crop: crop the equation or theorem from the PDF like any figure;
   ivory `.plate`; provenance "not redrawn".
2. Verbatim crop plus a symbol key: the default theory hero. Add a `.symkey`
   list glossing each unfamiliar symbol in the paper's own definitional words. A
   quoted definition is not a restatement, so this stays verbatim.
3. Simplified restatement (`.restate`): only when the structure, not the symbols,
   is the barrier. Howl re-expresses the statement in informal notation. Rare by
   design; frequent use means the selection rule is too loose.

The ivory `.plate` frame means verbatim, always. A simplification never gets the
ivory frame: it uses `.restate` (parchment ground, ink-blue left rule), the flag
"Simplified, not the paper's notation", a provenance line saying "not quoted"
(mirroring "not redrawn"), and carries the exact source sentence in
`data-source-verbatim`. Render simplified math in Unicode and CSS only; if it
needs more, fall back to a verbatim crop rather than simplify. Never add KaTeX or
another math engine to the print pipeline. A Mode 3 block must pass the
simplified-statement check in the adversarial loop before it may render.

## Run the adversarial loop

After the first draft, invoke a separate reviewer agent using
[`references/editorial-review.md`](references/editorial-review.md). Give it only
the full paper text, bounded audience brief, evidence crop/provenance, and
`draft-N.md`; never give it the spine or earlier reviews.

Run at least one and at most three rounds. Store `draft-N.md` and
`review-N.json`. On `REVISE`, change only the named problems. On `REJECT`, repair
the spine once; the respine consumes a round, and a second `REJECT` skips the
paper. The runner carries every prior finding in existing build metadata and
marks it resolved only by naming the correcting edit. A carried finding blocks
rendering regardless of the latest verdict. Render only the exact draft returned
`ACCEPT`. Any finding at round three skips the paper and records the reason. Two
consecutive rounds with the same finding set also skip it. Retry one reviewer
failure once; a second failure blocks rendering because review is mandatory.

## Render and verify

Build `report.html` from the pinned baseline
[`references/report-template.html`](references/report-template.html), replacing
its content only and leaving the design tokens and block structure unchanged.
Render the accepted copy through headless Chrome to HTML and PDF, then run the
content, placeholder, style, density, and visual checks. Inspect every page
image and confirm that no section is split across a page break and that no folio
or sources line is clipped at a page bottom; each `.page` is a fixed A4 box with
`overflow:hidden`, so overflow silently drops content. Fix overflow by shrinking
a figure's `max-height` or adding a page, never by shrinking below the 9pt floor.
A copy change at this stage is a new draft and returns to the adversarial loop.

For delivery, inline the figure crops as `data:` URIs so the shipped report is a
single portable `.html` file that opens in any browser with no `assets/` folder.
The self-contained HTML is the primary deliverable; the PDF is an optional
archive and print copy.
