# Deploying HuStringSearch

The project ships as a single Docker image, so any container host works. This
document covers Hugging Face Spaces (recommended for a free public demo) and notes
Cloud Run.

## Ports

The entrypoint binds to:

- `$PORT` if set (Cloud Run injects it),
- **7860** when `SPACE_ID` is present (Hugging Face Spaces),
- otherwise **8000** (local / Docker Compose).

## Graph on ephemeral hosts

Spaces and Cloud Run have ephemeral storage, so the container would otherwise
rebuild the merged graph (~105 MB download, ~1 min) on every cold start. Instead,
fetch the small prebuilt artifact from a GitHub Release:

1. Publish a graph release (see the README; the `graph-*` tag workflow does this
   automatically).
2. Point the container at it:

   ```
   HUSTRING_GRAPH_URL=https://github.com/PipettingBeaver/HuStringSearch/releases/download/graph-2026.09.21/hustring-graph-2026.09.21.tar.gz
   ```

On startup the entrypoint runs `hustring fetch-graph`, which downloads and unpacks
the ~5 MB archive. If `HUSTRING_GRAPH_URL` is unset, it falls back to
`hustring build-data` (controlled by `HUSTRING_AUTO_BUILD`).

## Hugging Face Spaces (Gradio — free)

> As of 2026, Hugging Face requires a **paid plan** to create Docker or CPU Gradio Spaces.
> Static Spaces are free, and free personal accounts can host up to **two Gradio Spaces on
> ZeroGPU**. This project therefore ships a Gradio app.

Prerequisites: a Hugging Face account and an access token with **write** scope
(https://huggingface.co/settings/tokens).

1. Create a Space: https://huggingface.co/new-space, **SDK = Gradio**, any name
   (for example `HuStringSearch`).
2. Deploy the app (three small files):

   ```fish
   set -x HF_TOKEN hf_xxxxxxxxxxxxxxxxx
   scripts/deploy_hf_gradio.sh <hf-user> <space-name>
   ```

   `requirements.txt` installs the package straight from GitHub, so the Space runs the
   pushed `main`.
3. In the Space **Settings → Variables and secrets**, add:

   ```
   HUSTRING_GRAPH_URL = <your graph release asset URL>
   ```

   Without it, the Space builds the graph on first use (slower).
4. Open `https://huggingface.co/spaces/<hf-user>/<space-name>`.

Notes:
- Ranking runs server-side on CPU via the shared analysis module; the graph is drawn in the
  browser with Cytoscape.js (loaded from a CDN).
- A no-op ZeroGPU function is defined so the Space is valid on the free tier; it never
  requests a GPU, so no quota is consumed.
- Free Spaces **sleep after inactivity**; the first request restarts the container and
  re-fetches the ~5 MB graph.

### Docker Space (requires a paid plan)

The Docker image also works as a Docker Space (`sdk: docker`, `app_port: 7860`), but that
needs PRO/Team. Docker remains the recommended path for local use and other container hosts.

## Google Cloud Run (brief)

```fish
gcloud run deploy hustring --source . --allow-unauthenticated \
  --set-env-vars HUSTRING_GRAPH_URL=<your graph release asset URL>
```

Cloud Run injects `PORT`, so no extra configuration is needed.

## Troubleshooting

- **The graph release workflow didn't run.** Tag-push workflows are read from the *tagged
  commit*, so a tag pointing at a commit older than `.github/workflows/release-graph.yml` will
  not trigger it. Move the tag onto current `main`:

  ```fish
  git tag -f -a graph-<version> -m "Prebuilt graph"
  git push --force origin graph-<version>
  ```

  Alternatively, run the workflow manually from the repository's **Actions** tab
  (`Release graph artifact` → *Run workflow*), which takes a version input.
- **Space shows no graph / health fails.** Confirm `HUSTRING_GRAPH_URL` is set and the asset is
  reachable: `curl -sIL <url> | grep -i http` should show `200`.

