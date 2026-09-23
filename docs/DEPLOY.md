# Deploying HuStringSearch

HuStringSearch ships as one Docker image. So any container host can run it. The image is the
unit of deployment. Build it one time. Then you can run it locally, on Render, on Cloud Run, or
on your own machine. The behavior is the same in all cases.

> **Note about Hugging Face:** An earlier revision included a Gradio front-end for the Hugging
> Face free tier. We removed it to keep one UI and one backend. See `docs/DECISIONS.md`. Hugging
> Face now charges for Docker Spaces. So Render is the recommended free host.

This file uses an adapted form of ASD-STE100 Simplified Technical English. We keep the rules
that help the reader. We do not follow the full controlled dictionary.

## What the container needs

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | The port to bind. Most hosts supply this value. |
| `HUSTRING_GRAPH` | `/data/graph` | The directory of the built graph. |
| `HUSTRING_CACHE` | `/data/cache` | The directory of the raw download cache. |
| `HUSTRING_GRAPH_URL` | unset | Get a prebuilt graph archive. Do not build the graph. |
| `HUSTRING_AUTO_BUILD` | `1` | Build the graph on the first run if it is absent. |

Startup logic (`docker/entrypoint.sh`): If there is no graph, the script gets the graph from
`HUSTRING_GRAPH_URL` or it builds one. Then it serves on `$PORT`.

## Prebuilt graph

Some hosts use ephemeral storage. Render free and Cloud Run are examples. These hosts restart
with an empty filesystem. So a build on each cold start wastes time. Publish the graph one time
as a GitHub Release asset. Then point `HUSTRING_GRAPH_URL` at it.

1. Publish the asset. You can do this automatically with a `graph-*` tag, or manually:

   ```bash
   scripts/package_graph.sh data/derived/graph 2026.09.23.1
   gh release create graph-2026.09.23.1 dist/hustring-graph-2026.09.23.1.tar.gz \
     --title "Prebuilt human graph (HuRI + STRING)"
   ```

2. Use the asset URL:

   ```
   https://github.com/PipettingBeaver/HuStringSearch/releases/download/graph-2026.09.23.1/hustring-graph-2026.09.23.1.tar.gz
   ```

## Render (recommended, free)

Live demo: **https://hustringsearch.onrender.com**

1. Make an account at https://render.com. Connect your GitHub account.
2. Select **New → Web Service**. Select the `HuStringSearch` repository.
3. Render reads `render.yaml`. Select the **Free** instance type.
4. In **Environment**, set `HUSTRING_GRAPH_URL` to the asset URL above.
5. Deploy. Render builds the Dockerfile and serves the app at
   `https://<service-name>.onrender.com`.
6. Set the health check path to `/api/health`. The file `render.yaml` already has this value.

Notes:
- A free service sleeps after about 15 minutes without traffic. The next request wakes it. This
  takes a few seconds, plus the graph fetch of about 5 MB.
- The Render free tier gives the container an ephemeral disk. So the container gets the graph
  and does not build it.

## Google Cloud Run (a later exercise)

The same image runs here. The extra work is specific to GCP: a billing account, Artifact
Registry, and IAM.

```fish
gcloud run deploy hustring --source . --allow-unauthenticated \
  --set-env-vars HUSTRING_GRAPH_URL=<asset url>
```

Cloud Run supplies `PORT`. So you need no extra configuration. See `docs/DOCKER.md` for the
image details and for local tests.

## Local or self-hosted

Use `docker compose up --build`. See `docs/DOCKER.md`. The directory `./data` is a mounted
volume. So the graph stays after a restart. You do not need the URL variable.

## Troubleshooting

- **Message: `permission denied ... docker.sock`.** Add your user to the `docker` group. Then
  log in again. Command: `sudo usermod -aG docker $USER`.
- **The container cannot write to the mounted `./data`.** This occurs on Fedora and RHEL with
  SELinux in enforcing mode. The error often shows as `Path '/data/cache' is not readable`. Add
  `:z` to the volume: `./data:/data:z`.
- **The graph release workflow did not run.** GitHub reads a tag-push workflow from the tagged
  commit. Move the tag onto the current `main`:
  `git tag -f -a graph-<v> -m "..." && git push --force origin graph-<v>`. Or run **Release
  graph artifact** from the Actions tab.
- **The deploy succeeds, but the app shows no graph, or the health check fails.** Make sure that
  `HUSTRING_GRAPH_URL` is set and reachable. Run `curl -sIL <url> | grep -i http`. The result
  must show `200`.
