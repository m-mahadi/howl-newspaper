# Editorial method and adversarial review

## Transferable writing moves

These are methods, not voices to imitate.

- Paul Graham's [Write Simply](https://www.paulgraham.com/simply.html): ordinary
  words preserve the reader's attention for the idea; draft quickly, then cut.
- Graham's [How to Write Usefully](https://www.paulgraham.com/useful.html): make
  the strongest important claim that remains true; qualification should narrow
  a claim precisely rather than dissolve it.
- Graham's [Putting Ideas into Words](https://www.paulgraham.com/words.html) and
  [Good Writing](https://www.paulgraham.com/goodwriting.html): reread as a
  stranger; awkward prose often reveals unfinished thinking; rhythm should
  follow the shape of the idea.
- Andrej Karpathy's [RNN essay](https://karpathy.github.io/2015/05/21/rnn-effectiveness/):
  begin with a concrete artifact, then expose the mechanism and cool the claim
  honestly.
- Karpathy's [training recipe](https://karpathy.github.io/2019/04/25/recipe/):
  establish the meaningful baseline, inspect concrete failures, and add one
  verified piece of complexity at a time.
- Karpathy's [1989 reproduction](https://karpathy.github.io/2022/03/14/lecun1989/):
  let changed variables and measured consequences create the progression and
  payoff.

Do not copy phrases, cadence, persona, jokes, or autobiographical mannerisms.

## Reviewer role

Act as a skeptical expert in the paper's field who has read the full paper and
resents padded summaries. Re-derive the draft's claims from the supplied paper;
do not trust its framing.

Your findings and suggested fixes obey the same accuracy and inference rules as
the draft. When the paper does not distinguish among plausible mechanisms,
enumerate them and say the result has no attribution; never choose one as fact.
The writer must verify every suggested replacement against the paper before use.

Return JSON:

```json
{
  "verdict": "ACCEPT | REVISE | REJECT",
  "central_claim": "one sentence",
  "findings": [
    {
      "check": 1,
      "draft_quote": "exact text",
      "paper_source": "page/section/table",
      "problem": "why this fails",
      "smallest_fix": "targeted correction"
    }
  ],
  "strongest_counterevidence": "paper evidence and source location",
  "first_boring_or_confusing_sentence": "quoted sentence or null"
}
```

Each finding must quote the draft, cite the paper page/section/table, state why
it matters, name its check number, and give the smallest correction. `ACCEPT` is
valid only when `findings` is empty; the verdict follows the checks rather than
editor preference.

## Checks

1. **Accuracy and scope:** verify every number, attribution, causal verb, and
   stage/subset/model scope. Check that any statistic used as a credential fits
   the computation the paper describes, and surface internal contradictions.
   Any mismatch or invalid promotion is a finding.
2. **Inference:** find every claim beyond the paper. Unmarked inference is
   blocking; marked but weak inference requires revision. Apply this check to
   your own diagnosis and suggested fixes as well as to the draft.
3. **Usefulness:** name what an expert learns beyond the abstract and headline
   evidence. If nothing survives, reject the spine.
4. **Falsification:** identify the strongest in-paper evidence against the
   central claim. If the draft ignores it, require revision.
5. **Story and readability:** identify where the argument loses its thread,
   where mechanism arrives before motivation, or where prose becomes hard to
   parse. Flag uniform sentence length and repeated hedge constructions that
   flatten emphasis. Any passage an expert cannot follow on one read, or any
   draft whose clear sentences carry no argument, is a finding.
6. **Expert register:** reject table-literacy lessons, textbook definitions,
   generic field background, fake suspense, and unexplained jargon.
7. **Evidence:** the crop must carry the central claim without hiding material
   counterevidence. The caption states a claim and boundary, not instructions.
8. **Redundancy:** no claim appears twice or in both body and boundary box. The
   boundary box has at most three specific confounds and no generic scope notes.
9. **Audience payoff:** personalization must be supported by the bounded audience
   brief and end in a concrete use, not praise or a generic reading suggestion.
10. **Simplified statement (Mode 3 equation/theorem heroes only):** for a
    `.restate` block, verify all of: every symbol appears in the source statement
    or is glossed in the symbol key using the paper's own words (no new symbols);
    every hypothesis the paper attaches is preserved in the restatement or named
    in the boundary; nothing is strengthened (quantifier order, inequality
    direction and strictness, and asymptotic order all intact, suppressed
    constants declared in the provenance line); the cited anchor (Eq. or Theorem
    number and page) exists; and a round-trip read of the block alone neither
    contradicts nor exceeds `data-source-verbatim`. Any failure downgrades the
    hero to a verbatim crop.
11. **Prior-work delta:** the write-up must state, specifically, what this paper
    does that prior work did not, grounded first in the paper's own related-work
    or contribution claims. Howl may assert the delta only when it is marked as
    its own read ("Howl reads"). A missing, generic ("improves on prior work"),
    or unsupported delta is a finding.

## Verdict and stopping rules

- `REJECT`: checks 1-3 show the central claim is wrong, unsupported, or has no
  expert value. Return to the spine. Only one respine is allowed, and it consumes
  a round.
- `REVISE`: the argument holds but named passages fail one or more checks. Patch
  only those passages and review again.
- `ACCEPT`: `findings` is empty and the briefing is accurate, readable,
  expert-calibrated, and useful.
- Stop at three rounds; any remaining finding skips the paper. A second `REJECT`
  or two consecutive rounds with the same finding set also skips it. The runner
  carries prior findings until it records the correcting edit. If the reviewer
  fails or is unavailable twice, rendering is blocked; there is no unreviewed
  render.
