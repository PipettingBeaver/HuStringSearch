# Running with Docker

Docker packages the app and its Python environment into one image that runs the same
everywhere. This is the portability path: local use, self-hosting, and the base image for
container hosts.

## Concepts in one table

| Term | What it is | Here |
|---|---|---|
| **Image** | A built, immutable snapshot (code + Python + files) | `hustring:latest` |
| **Container** | A running instance of an image | one live viewer process |
| **Volume** | Host storage that outlives the container | `./data` mapped to `/data` |

A container's own filesystem is thrown away when the container is removed. The **volume** is
why the graph survives restarts — it lives on your disk, not in the container.

## Quick start

```fish
docker compose up --build        # open http://localhost:8000
```

First run builds the image, then builds the graph (~1-2 min, ~105 MB downloaded) into `./data`.
Later runs reuse both the image layers and the graph, so startup is seconds.

Without Compose:

```fish
docker build -t hustring .
docker run --rm -p 8000:8000 -v "$PWD/data:/data:z" hustring
```

## Smoke test: does a fresh clone work?

This is the guarantee the README implies. Run it after changing the Dockerfile or entrypoint:

```fish
cd /tmp
git clone https://github.com/PipettingBeaver/HuStringSearch.git hss-test
cd hss-test
docker compose up --build
# expect: "Saved <n> nodes / <m> edges" then "Uvicorn running on http://0.0.0.0:8000"
```

Clean up afterwards (the container runs as root, so the files it wrote are root-owned):

```fish
docker compose down
sudo rm -rf /tmp/hss-test
```

## Daily commands

```fish
docker compose up --build      # rebuild if code changed, then run
docker compose up -d           # run in the background
docker compose logs -f         # follow logs
docker compose ps              # is it up? healthy?
docker compose exec hustring sh        # shell inside the running container
docker compose exec hustring ls /data  # inspect the volume contents
docker compose down            # stop and remove the container
docker image ls                # list images and sizes
docker stats                   # live CPU/RAM
```

## How this project uses the volume

The container writes the graph and raw cache under `/data`, which is mapped to `./data` on the
host:

```
./data/cache/            raw downloads (HuRI, STRING, mapping files)
./data/graph/            merged graph (adjacency.npz, nodes/edges.parquet, manifest.json)
```

Because it is a volume, `docker compose down` does not delete it. Delete `./data` to force a
full rebuild. To start from a prebuilt artifact instead of building, set `HUSTRING_GRAPH_URL`
(see `docs/DEPLOY.md`).

## Configuration

Environment variables (settable in `compose.yaml` or with `-e`):

| Variable | Default | Purpose |
|---|---|---|
| `HUSTRING_GRAPH` | `/data/graph` | Where the built graph lives |
| `HUSTRING_CACHE` | `/data/cache` | Where raw downloads are cached |
| `HUSTRING_GRAPH_URL` | unset | Fetch a prebuilt graph archive instead of building |
| `HUSTRING_AUTO_BUILD` | `1` | Build the graph on first run if missing |
| `PORT` | `8000` | Port to bind (Cloud Run injects this) |

## Troubleshooting

**`permission denied ... docker.sock`** — your user is not in the `docker` group:
```fish
sudo usermod -aG docker $USER
```
Then **log out and back in** (a new terminal is not enough). Until then, prefix commands with
`sudo`. Note that `sudo` makes the container write root-owned files into `./data`; fix with
`sudo chown -R $USER:$USER data`.

**Container can't write to the mounted `./data`** (Fedora/RHEL with SELinux enforcing; the
error often appears as `Path '/data/cache' is not readable`). Relabel the mount:
```yaml
volumes:
  - ./data:/data:z
```
`:z` shares the label; `:Z` makes it private to the container. Check with `getenforce`;
inspect labels with `ls -Z ./data`.

**`Conflict. The container name "/hustring" is already in use`** — a container from another
checkout is still running. `docker compose down` it first, or run from a different directory
(Compose names containers per project, so parallel checkouts coexist).

**Port 8000 already in use** — change the host side: `-p 8001:8000`, or edit `compose.yaml`.

**Edits to code don't appear** — the image captured your code at build time. Rebuild with
`docker compose up --build`.

**First run looks stuck** — it is downloading ~105 MB (the STRING links file is ~83 MB) with
no progress output. Give it a minute.

**Graph exists but you want to rebuild** — `docker compose down && sudo rm -rf data`.

## How the image is built (for the curious)

`Dockerfile` highlights:

- `FROM python:3.13-slim` — a known-good Python, independent of your host.
- `COPY pyproject.toml` **before** `COPY src` — so editing code only invalidates the tail
  layers, not the dependency install (layer caching).
- `pip install ".[web]"` runs once at build time.
- `VOLUME ["/data"]` + `ENTRYPOINT` runs `docker/entrypoint.sh`, which builds or fetches the
  graph if needed, then serves on the right port.
