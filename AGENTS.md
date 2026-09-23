# Agent working notes — HuStringSearch

HuStringSearch merges multiple interactome sources into one weighted graph and
runs a target-centered Random Walk with Restart (RWR) to isolate and visualize
functional subnetworks. It is meant to run both locally and hosted.

Package name is `hustring` (import), project/distribution is `HuStringSearch`.

## Layout
- `src/hustring/config.py` — build + RWR + seed configuration models (pydantic).
- `src/hustring/species.py` — curated taxon presets; no human hard-coding.
- `src/hustring/core/` — algorithm: `rwr.py`, `seeds.py`, `subgraph.py`.
- `src/hustring/sources/` — pluggable interactome sources (STRING, HuRI, ...).
- `src/hustring/mapping/` — identifier harmonization (BioMart / Ensembl Genomes).
- `src/hustring/graph/` — merge + preprocessing into the canonical graph.
- `src/hustring/api/` — FastAPI app; `web/` holds the Cytoscape.js frontend.
- `docs/DECISIONS.md` — ADR log; append a decision whenever a design choice is made.

## Commands
- Create env: `python3 -m venv .venv`
- Activate — bash/zsh: `source .venv/bin/activate` · fish: `source .venv/bin/activate.fish`
- Or skip activation entirely: run `.venv/bin/hustring ...` / `.venv/bin/pytest`
- Install (dev): `pip install -e ".[all]"`
- Test: `pytest`
- Lint: `ruff check src tests`
- Typecheck: `mypy`
- List sources: `hustring sources`
- Build data: `hustring build-data` (writes `data/derived/graph`, caches raw in `data/cache`)
- Inspect graph: `hustring inspect -g data/derived/graph`
- Query: `hustring walk TP53 -g data/derived/graph --top 25` (or `--hops N`, `--threshold S`)
- Serve: `hustring serve -g data/derived/graph` (http://127.0.0.1:8000)
- Container: `docker compose up --build` (graph auto-builds into `./data` on first run)

## Conventions
- Taxid-driven; never assume a species. Ensembl Gene ID is the canonical node key.
- All preprocessing/build options live in `BuildConfig` with user-facing
  `description`s so the UI can render an explanation window.
- Algorithms take scipy sparse matrices, not NetworkX graphs (perf).
- Deterministic builds: pin dataset versions and record hashes in a build manifest.
- No comments in code; use docstrings for intent. Config descriptions carry the
  "what/why for the user" text.

## Data policy
Raw downloads are large-ish and never committed. The repo ships a prebuilt,
compact merged-graph artifact (Git LFS / Release) for offline + fast cold start.
Rebuilding from source is opt-in via `hustring build-data`.

## Resume here (updated 2026-09-23)

State: local, Docker, and Render all work. Working tree is clean and matches
`origin/main`. `ruff`, `mypy`, and 103 tests pass; CI is green.

Live: https://hustringsearch.onrender.com (Render free tier, `render.yaml`);
serves `graph-2026.09.23.1` (verified 2026-09-23).

Shipped recently:
- Query-time preprocessing controls in the viewer: STRING cutoff (number +
  slider, default 0.70, range 0.40-1.00) and edge-weight scaling
  (none/log/linear). Backend: `core/subgraph.filter_edges` and
  `normalize_weights`; `analysis.rank_target_centered` takes `min_edge_weight`,
  `max_edge_weight`, `weight_normalization`, `seed_weights`; the API mirrors them.
- The graph artifact is now a STRING>=400 superset so the cutoff is meaningful.
- Gene names: Ensembl REST primary, BioMart fallback, cached at build time.
- `EnsemblRestClient.lookup_ids` retries transient failures (1s/2s/4s backoff,
  3 retries). `fetch_gene_names` merges cached names with a fetch for the
  missing IDs only, and keeps cached names when all sources fail.

Artifact facts:
- Published `graph-2026.09.23.1`: 19,539 nodes / 977,155 edges, min weight
  0.400, 19,454 named (~13.7 MB). CI build verified from the release asset.
- `graph-2026.09.23`: tag exists; its release has no assets (pre-fix CI run).
- `graph-2026.09.22`: 17,379 nodes / 286,850 edges (STRING>=700), named.
- Render `HUSTRING_GRAPH_URL` points at `graph-2026.09.23.1`.

Do not commit `data/` (ignored) or `docs/TECH_DEBT.md` (ignored, kept local).

Test recipe:
- `.venv/bin/pytest tests/test_enrich.py tests/test_ensembl_rest.py tests/test_analysis.py`
- Live check: `.venv/bin/python -c "from hustring.mapping.enrich import
  fetch_gene_names; ..."` against a fresh cache dir.
