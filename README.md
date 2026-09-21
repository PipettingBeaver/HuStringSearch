# HuStringSearch

[![CI](https://github.com/PipettingBeaver/HuStringSearch/actions/workflows/ci.yml/badge.svg)](https://github.com/PipettingBeaver/HuStringSearch/actions/workflows/ci.yml)

Merge multiple protein interactome sources (**HuRI**, **STRING**, **BioGRID**,
**IntAct**, custom overlays) onto a shared identifier space and run a
**target-centered Random Walk with Restart (RWR)** to isolate and visualize
functional subnetworks in an interactive web viewer.

Runs locally and hosted from one Docker image. Species is a parameter (NCBI
taxon ID) — human is a default, not an assumption.

## Status
Early scaffolding. Core RWR + config are implemented and tested; data sources,
mapping, API, and UI are in progress. See `docs/DECISIONS.md` for the design log.

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
If `./data/graph/adjacency.npz` already exists it is used and nothing is downloaded.

### Cloud
- **Hugging Face Spaces (Gradio, free):** `HF_TOKEN=hf_xxx scripts/deploy_hf_gradio.sh <hf-user> <space-name>`, then set the Space variable `HUSTRING_GRAPH_URL`. See `docs/DEPLOY.md`. (HF now charges for Docker/CPU Gradio Spaces; the Gradio app runs on the free ZeroGPU tier without using GPU quota.)
- **Google Cloud Run:** `gcloud run deploy hustring --source . --allow-unauthenticated`
  (Cloud Run injects `PORT`, which the entrypoint honors).

On ephemeral hosts, set `HUSTRING_GRAPH_URL` to a graph Release asset so the container downloads
the ~5 MB prebuilt graph instead of rebuilding it. See `docs/DEPLOY.md`.

Local Gradio preview: `hustring gradio -g data/derived/graph` (needs `pip install 'hustring[gradio]'`).

The image honors `HUSTRING_GRAPH`, `HUSTRING_CACHE`, `HUSTRING_WEB_DIR`, `HUSTRING_GRAPH_URL`,
`HUSTRING_AUTO_BUILD`, and `PORT`.

## Distributing the prebuilt graph

The merged graph is derived data and is **not committed** to `main`. Publish it as a GitHub
Release asset so a deployment can start without rebuilding:

```bash
scripts/package_graph.sh data/derived/graph 2026.09.21
gh release create 2026.09.21 dist/hustring-graph-2026.09.21.tar.gz \
  --title "Prebuilt human graph (HuRI + STRING)" \
  --notes "ENSG-canonical, STRING combined score >= 700. Unpack into data/derived/graph."
```

Unpack into `data/derived/graph` (or point `HUSTRING_GRAPH` at it); the container then skips the
first-run build. Automating this through CI is a planned improvement.
