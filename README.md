# HuStringSearch

[![CI](https://github.com/PipettingBeaver/HuStringSearch/actions/workflows/ci.yml/badge.svg)](https://github.com/PipettingBeaver/HuStringSearch/actions/workflows/ci.yml)

Merge multiple protein interactome sources (**HuRI**, **STRING**, **BioGRID**,
**IntAct**, custom overlays) onto a shared identifier space and run a
**target-centered Random Walk with Restart (RWR)** to isolate and visualize
functional subnetworks in an interactive web viewer.

Runs locally, in Docker, or hosted on Hugging Face Spaces. Species is a parameter
(NCBI taxon ID) — human is a default, not an assumption.

**Live demo:** https://huggingface.co/spaces/PipettingBeaver/HuStringSearch

## Status
Functional end to end: sources, mapping, graph build, RWR, CLI, API, and viewers are
implemented and tested (see `docs/DECISIONS.md` for the design log). The web UI is
deliberately **basic** — serviceable for student-level exploration, with room to grow
(persistent settings, exporters, enrichment overlays, richer node details).

## Run from scratch (zsh)
```zsh
git clone https://github.com/PipettingBeaver/HuStringSearch.git
cd HuStringSearch
python3 -m venv .venv
source .venv/bin/activate        # fish: source .venv/bin/activate.fish
pip install -e ".[all]"
hustring build-data              # fetch + merge interactomes (~1 min)
hustring serve -g data/derived/graph   # viewer at http://127.0.0.1:8000
```

## Usage
```zsh
hustring build-data                     # fetch + merge interactomes into a graph artifact
hustring inspect -g data/derived/graph  # graph size and top hubs
hustring walk TP53 -g data/derived/graph --top 25
hustring serve -g data/derived/graph    # interactive viewer at http://127.0.0.1:8000
hustring gradio -g data/derived/graph   # Gradio viewer (used by the hosted demo)
```

If you'd rather not activate the venv, call the entrypoint directly:
`.venv/bin/hustring serve -g data/derived/graph`.

## Docker
The one-command path (builds the image and runs the viewer, building the graph on
first start):
```bash
docker compose up --build      # then open http://localhost:8000
```
Or a single container:
```bash
docker build -t hustring .
docker run --rm -p 8000:8000 -v "$PWD/data:/data" hustring
```
The graph is stored in the mounted `./data` volume, so later runs reuse it. Set
`HUSTRING_AUTO_BUILD=0` to require a prebuilt graph instead. See `docs/DEPLOY.md`
for hosted deployments.

## Distributing the prebuilt graph

The merged graph is derived data and is **not committed** to `main`. Publish it as a GitHub
Release asset so a deployment can start without rebuilding:

```bash
scripts/package_graph.sh data/derived/graph 2026.09.21
gh release create graph-2026.09.21 dist/hustring-graph-2026.09.21.tar.gz \
  --title "Prebuilt human graph (HuRI + STRING)" \
  --notes "ENSG-canonical, STRING combined score >= 700. Unpack into data/derived/graph."
```

Pushing a `graph-*` tag (or running the *Release graph artifact* workflow manually) builds and
publishes the asset automatically. Unpack it into `data/derived/graph` or point
`HUSTRING_GRAPH_URL` at it. See `docs/DEPLOY.md`.
