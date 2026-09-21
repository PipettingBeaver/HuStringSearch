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

## Hugging Face Spaces

Prerequisites: a Hugging Face account and an access token with **write** scope
(https://huggingface.co/settings/tokens).

1. Create a Space: https://huggingface.co/new-space, **SDK = Docker**, any name
   (for example `HuStringSearch`).
2. Deploy from this repository:

   ```fish
   set -x HF_TOKEN hf_xxxxxxxxxxxxxxxxx
   scripts/deploy_hf.sh <hf-user> <space-name>
   ```

   The script pushes the current `git HEAD` to the Space, substituting
   `deploy/huggingface/README.md` (which carries the Space metadata) for the
   project README.
3. In the Space **Settings → Variables and secrets**, add:

   ```
   HUSTRING_GRAPH_URL = <your graph release asset URL>
   ```

4. The Space builds the image and, once running, fetches the graph and serves the
   viewer at `https://huggingface.co/spaces/<hf-user>/<space-name>`.

Notes:
- Free CPU Spaces **sleep after inactivity**; the first request after sleeping
  restarts the container (a few seconds plus the ~5 MB graph fetch).
- Persistent storage is a paid feature; without it, fetches repeat per restart,
  which is why the artifact is kept small.

## Google Cloud Run (brief)

```fish
gcloud run deploy hustring --source . --allow-unauthenticated \
  --set-env-vars HUSTRING_GRAPH_URL=<your graph release asset URL>
```

Cloud Run injects `PORT`, so no extra configuration is needed.
