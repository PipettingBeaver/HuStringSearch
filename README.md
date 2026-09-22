# HuStringSearch

[![CI](https://github.com/PipettingBeaver/HuStringSearch/actions/workflows/ci.yml/badge.svg)](https://github.com/PipettingBeaver/HuStringSearch/actions/workflows/ci.yml)

Merge multiple protein interactome sources (**HuRI**, **STRING**, **BioGRID**,
**IntAct**, custom overlays) onto a shared identifier space and run a
**target-centered Random Walk with Restart (RWR)** to isolate and visualize
functional subnetworks in an interactive web viewer.

Online demo: **https://hustringsearch.onrender.com**. The same Docker image runs locally,
on Render, or on a container host. Species is a parameter (NCBI taxon ID) — human is a
default, not an assumption.

<!-- TODO (PipettingBeaver): write this section in your own words.
     Talk about why the project exists, what it does, and what you learned.
     Add a screenshot of the hosted UI below the intro, for example:
     ![HuStringSearch viewer](docs/images/viewer.png)
     The hosted UI is the same as running locally with Docker.
-->
## Overview

> **Placeholder — to be written.** A short description of the project in the author's
> own words: the goal, the motivation, and the intended use. A screenshot of the hosted
> viewer goes here.

## Status
Early scaffolding and remake. Was a class project remade from ground up to be
accessible online and as proof of concept for me to learn Docker and online hosting.
Core RWR + config are implemented and tested; data sources, mapping, API, and UI
are in progress. See `docs/DECISIONS.md` for more design log info. The web UI is
deliberately **basic** — serviceable for student-level exploration, with room to grow.

## Run from scratch (zsh)
```zsh
git clone https://github.com/PipettingBeaver/HuStringSearch.git
cd HuStringSearch
python3 -m venv .venv
# bash/zsh:
source .venv/bin/activate
# fish:
# source .venv/bin/activate.fish
pip install -e ".[all]"
hustring build-data                      # fetch + merge interactomes (~1 min)
hustring serve -g data/derived/graph     # interactive viewer at http://127.0.0.1:8000
```

## Usage
```zsh
hustring build-data                     # fetch + merge interactomes into a graph artifact
hustring build-data --enrich-gene-names  # also fetch gene names (Ensembl REST, cached)
hustring inspect -g data/derived/graph  # graph size and top hubs
hustring walk TP53 -g data/derived/graph --top 25
hustring serve -g data/derived/graph    # interactive viewer at http://127.0.0.1:8000
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
`HUSTRING_AUTO_BUILD=0` to require a prebuilt graph instead. See `docs/DOCKER.md`
for a walkthrough and troubleshooting, and `docs/DEPLOY.md` for hosted deployments.

## Distributing the prebuilt graph

The merged graph is derived data and is **not committed** to `main`. Publish it as a GitHub
Release asset so a deployment can start without rebuilding:

```bash
scripts/package_graph.sh data/derived/graph 2026.09.21
gh release create graph-2026.09.22 dist/hustring-graph-2026.09.22.tar.gz \
  --title "Prebuilt human graph (HuRI + STRING)" \
  --notes "ENSG-canonical, STRING combined score >= 700. Unpack into data/derived/graph."
```

Pushing a `graph-*` tag (or running the *Release graph artifact* workflow manually) builds and
publishes the asset automatically. Unpack it into `data/derived/graph` or point
`HUSTRING_GRAPH_URL` at it. See `docs/DEPLOY.md`.
