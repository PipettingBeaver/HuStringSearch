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
