# HuStringSearch

[![CI](https://github.com/PipettingBeaver/HuStringSearch/actions/workflows/ci.yml/badge.svg)](https://github.com/PipettingBeaver/HuStringSearch/actions/workflows/ci.yml)

Merge multiple protein interactome sources (**HuRI**, **STRING**, **BioGRID**,
**IntAct**, custom overlays) onto a shared identifier space and run a
**target-centered Random Walk with Restart (RWR)** to isolate and visualize
functional subnetworks in an interactive web viewer.

Online version is currently accessible [here](https://huggingface.co/spaces/PipettingBeaver/HuStringSearch) on HuggingFace.

## Status
Early scaffolding and remake. Was a class project remade from ground up to be
accessible online and as proof of concept for me to learn Docker and online hosting.
Core RWR + config are implemented and tested; data sources, mapping, API, and UI
are in progress. See `docs/DECISIONS.md` for more design log info.

## Quickstart (development)
```bash
python3 -m venv .venv
# bash/zsh:
source .venv/bin/activate
# fish:
# source .venv/bin/activate.fish
pip install -e ".[all]"
pytest
```

## Usage
```bash
hustring build-data                     # fetch + merge interactomes into a graph artifact
hustring inspect -g data/derived/graph  # graph size and top hubs
hustring walk TP53 -g data/derived/graph --top 25
hustring serve -g data/derived/graph    # interactive viewer at http://127.0.0.1:8000
```

If you'd rather not activate the venv, call the entrypoint directly:
`.venv/bin/hustring serve -g data/derived/graph`.

## Deploy / install

### Docker Compose (one command, local or self-hosted)
```bash
docker compose up --build      # then open http://localhost:8000
```
On first run the container builds the graph (~1–2 min) into the mounted `./data` volume;
later runs reuse it. Set `HUSTRING_AUTO_BUILD=0` to require a prebuilt graph.

### Single container
```bash
docker build -t hustring .
docker run --rm -p 8000:8000 -v "$PWD/data:/data" hustring
```
If `./data/graph/adjacency.npz` already exists it is used and nothing is downloaded
