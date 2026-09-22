# Deploying HuStringSearch

HuStringSearch ships as a single Docker image, so any container host works. The image is the
unit of deployment: build it once, run it locally, on Render, Cloud Run, or a self-hosted
machine, and behavior is identical.

> **Note on Hugging Face:** earlier revisions included a Gradio front-end for Hugging Face's
> free tier. That was retired to keep a single UI and backend (see `docs/DECISIONS.md`).
> Hugging Face now charges for Docker Spaces, so Render is the recommended free host.

## What the container needs

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Port to bind (injected by most hosts) |
| `HUSTRING_GRAPH` | `/data/graph` | Where the built graph lives |
| `HUSTRING_CACHE` | `/data/cache` | Where raw downloads are cached |
| `HUSTRING_GRAPH_URL` | unset | Fetch a prebuilt graph archive instead of building |
| `HUSTRING_AUTO_BUILD` | `1` | Build the graph on first run if missing |

Startup logic (`docker/entrypoint.sh`): if there is no graph, fetch `HUSTRING_GRAPH_URL` or
build one; then serve on `$PORT`.

## Prebuilt graph

Hosts with ephemeral storage (Render free, Cloud Run) restart with an empty filesystem, so
building the graph on every cold start is wasteful. Publish it once as a GitHub Release asset
and point `HUSTRING_GRAPH_URL` at it:

1. Publish (automatically on a `graph-*` tag, or manually):

   ```bash
   scripts/package_graph.sh data/derived/graph 2026.09.21
   gh release create graph-2026.09.21 dist/hustring-graph-2026.09.21.tar.gz \
     --title "Prebuilt human graph (HuRI + STRING)"
   ```

2. Use the asset URL:

   ```
   https://github.com/PipettingBeaver/HuStringSearch/releases/download/graph-2026.09.21/hustring-graph-2026.09.21.tar.gz
   ```

## Render (recommended, free)

1. Create an account at https://render.com and connect your GitHub account.
2. **New → Web Service**, pick the `HuStringSearch` repository.
3. Render reads `render.yaml`; choose the **Free** instance type.
4. In **Environment**, set `HUSTRING_GRAPH_URL` to the asset URL above.
5. Deploy. Render builds the Dockerfile and serves the app at
   `https://<service-name>.onrender.com`.

Notes:
- Free services **sleep after ~15 minutes** of inactivity; the next request wakes them
  (a few seconds, plus the ~5 MB graph fetch).
- Render's free tier gives the container an ephemeral disk, which is exactly why the graph is
  fetched rather than built.

## Google Cloud Run (later exercise)

The same image runs here; the extra work is GCP-specific (billing account, Artifact Registry,
IAM):

```fish
gcloud run deploy hustring --source . --allow-unauthenticated \
  --set-env-vars HUSTRING_GRAPH_URL=<asset url>
```

Cloud Run injects `PORT`, so no extra configuration is needed. See `docs/DOCKER.md` for the
image details and local testing.

## Local / self-hosted

Use `docker compose up --build` (see `docs/DOCKER.md`). Because `./data` is a mounted volume,
the graph persists across restarts and no URL variable is needed.

## Troubleshooting

- **`permission denied ... docker.sock`** — add your user to the `docker` group and log back in
  (`sudo usermod -aG docker $USER`).
- **Container can't write to a mounted `./data`** (Fedora/RHEL, SELinux enforcing; often shows
  as `Path '/data/cache' is not readable`). Add `:z` to the volume: `./data:/data:z`.
- **The graph release workflow didn't run.** Tag-push workflows are read from the *tagged
  commit*; move the tag onto current `main` (`git tag -f -a graph-<v> -m "..." && git push
  --force origin graph-<v>`), or run **Release graph artifact** from the Actions tab.
- **Deploy succeeds but the app shows no graph / health fails.** Confirm `HUSTRING_GRAPH_URL`
  is set and reachable: `curl -sIL <url> | grep -i http` should show `200`.
