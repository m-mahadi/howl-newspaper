# Howl contributor rules

- Howl reads nothing on a user's machine. Do not add capture, hooks, background
  services, startup entries, or anything that watches the user's work. If a
  feature needs that, it belongs in a different product.
- Never store raw prompts, transcripts, source code, credentials, or a user's
  research profile in this public repository.
- Keep every user's workspace repository private.
- Never bypass access controls or CAPTCHAs while collecting papers.
- Relevance and popularity are separate facts. Never relabel one as the other,
  and never invent a movement signal for a field that has none.
- Prefer delivering nothing over delivering filler.
- Run `python -m unittest discover -s tests -v` after Python changes.
- Update `README.md` when setup or user-visible behavior changes.
