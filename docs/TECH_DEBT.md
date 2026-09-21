# Technical debt register

Tracked debt with enough context to act on later. Keep this honest and current;
add items when we knowingly take a shortcut, and remove them when resolved.

## Data / distribution
- **Prebuilt graph is distributed manually** as a GitHub Release asset
  (`scripts/package_graph.sh`). No CI job builds/publishes it, and no dataset
  versioning yet, so artifacts can drift from `main` and go stale. Plan: a
  GitHub Actions release workflow, and evaluate DVC or Git LFS if artifacts grow.
- **No dataset hashes in the build manifest.** We pin STRING versions by URL but
  don't record downloaded file checksums, so a build isn't byte-for-byte
  verifiable. Plan: record sha256 of each raw download in `manifest.json`.
- **BioMart fallback is unverified live.** Its endpoints were serving "Service
  unavailable" during development, so only the query builder/parser are tested.
  Plan: add an opt-in integration test and exercise a real bacteria/fungi lookup.
- **BioGRID column mapping comes from documentation**, not a live file. Plan:
  validate against a real `BIOGRID-ALL-*.tab3.zip` sample.
- **IntAct (1.35 GB) and COG (755 MB) paths are not end-to-end tested**; only
  parsers are. Plan: a small recorded fixture plus a documented manual run.

## Graph build
- **Parsing is not streaming.** STRING links (6.8M rows) and COG mappings are read
  fully into pandas before filtering. Fine at human scale; revisit with chunked
  reads if graphs grow substantially.
- **`protein` / `as_provided` node granularity are only partially implemented.**
  Gene-level is the supported default; the other modes are best-effort. Either
  finish them or mark them experimental in the UI.
- **Orthology bridging caps COG groups** (`max_group_size`) to avoid O(n^2)
  blow-ups; this silently drops edges beyond the cap. Plan: surface a warning
  and/or a smarter strategy.

## Interfaces / code
- **Web UI has no automated tests.** Only HTML/JS presence and `node --check` are
  validated; behavior is checked by hand. Plan: a lightweight Playwright smoke
  test.
- **No CLI end-to-end test for `build-data`** against fixtures (it needs network).
  Other commands are covered.
- **scipy is untyped** (`scipy.*` in the mypy override), so sparse-matrix types
  are effectively `Any`. Plan: adopt `scipy-stubs` when stable.

## Operations
- **No CI.** Plan: GitHub Actions running `ruff`, `mypy`, and `pytest`.
- **API has no auth, rate limiting, or request size caps.** Acceptable for a
  read-only local/self-hosted tool; revisit before any public multi-tenant use.
- **Docker image build is unverified locally** (Docker absent on the dev box);
  entrypoint and wheel contents were validated directly.
