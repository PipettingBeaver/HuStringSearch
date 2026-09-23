"""FastAPI application serving the analysis API and the web viewer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..analysis import rank_target_centered
from ..config import BuildConfig, RWRConfig, describe
from ..graph import Graph
from ..sources import available_sources, get_source_class

DEFAULT_GRAPH_DIR = Path("data/derived/graph")


class SubnetworkRequest(BaseModel):
    seeds: list[str] = Field(..., min_length=1, description="Gene symbols or Ensembl Gene IDs.")
    mode: Literal["top_k", "threshold", "k_hop"] = "top_k"
    top_k: int = Field(50, ge=1, le=5000)
    threshold: float | None = Field(None, ge=0.0)
    hops: int | None = Field(None, ge=1, le=10)
    restart_prob: float = Field(0.85, gt=0, lt=1)
    max_iter: int = Field(1000, ge=1)
    tol: float = Field(1e-6, gt=0)
    exclude_seeds: bool = True
    min_edge_weight: float | None = Field(None, ge=0.0, le=1.0)
    max_edge_weight: float | None = Field(None, ge=0.0, le=1.0)
    weight_normalization: Literal["none", "linear", "log"] = "none"
    seed_weights: list[float] | None = None


class RankedNodeModel(BaseModel):
    id: str
    symbol: str
    score: float
    source_class: str = "unknown"
    gene_name: str = ""


class SeedNodeModel(BaseModel):
    id: str
    label: str
    source_class: str = "unknown"
    gene_name: str = ""


class EdgeModel(BaseModel):
    a: str
    b: str
    weight: float


class SubnetworkResponse(BaseModel):
    seeds: list[str]
    resolved_seeds: list[str]
    missing_seeds: list[str]
    seed_ids: list[str]
    seed_nodes: list[SeedNodeModel]
    mode: str
    ranked: list[RankedNodeModel]
    edges: list[EdgeModel]
    parameters: dict[str, Any]


def _default_web_dir() -> Path:
    override = os.environ.get("HUSTRING_WEB_DIR")
    if override:
        return Path(override)
    repo_candidate = Path(__file__).resolve().parents[3] / "web"
    if (repo_candidate / "index.html").is_file():
        return repo_candidate
    try:
        from importlib.resources import files

        packaged = files("hustring").joinpath("web")
        if packaged.joinpath("index.html").is_file():
            return Path(str(packaged))
    except (ImportError, ModuleNotFoundError, FileNotFoundError):
        pass
    return repo_candidate


def _search_index(graph: Graph) -> list[tuple[str, str, str, str]]:
    return [
        (symbol.lower(), node_id.lower(), node_id, symbol)
        for node_id, symbol in zip(graph.node_ids, graph.symbols, strict=True)
    ]


def create_app(
    graph_dir: str | Path | None = None,
    web_dir: str | Path | None = None,
) -> FastAPI:
    """Build the FastAPI app. The graph is loaded lazily on first use."""
    graph_path = Path(graph_dir) if graph_dir is not None else Path(
        os.environ.get("HUSTRING_GRAPH", str(DEFAULT_GRAPH_DIR))
    )
    resolved_web = Path(web_dir) if web_dir is not None else _default_web_dir()
    app = FastAPI(title="HuStringSearch", version=__version__)
    cache: dict[str, Any] = {}

    def get_graph() -> Graph:
        graph = cache.get("graph")
        if graph is None:
            if not (graph_path / "adjacency.npz").exists():
                raise HTTPException(
                    status_code=503,
                    detail=f"no graph at '{graph_path}'; run `hustring build-data` first",
                )
            graph = Graph.load(graph_path)
            cache["graph"] = graph
            cache["search"] = _search_index(graph)
        return graph

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "graph_dir": str(graph_path),
            "graph_present": (graph_path / "adjacency.npz").exists(),
            "loaded": "graph" in cache,
        }

    @app.get("/api/graph/summary")
    def summary() -> dict[str, Any]:
        graph = get_graph()
        return {
            "nodes": graph.n_nodes,
            "edges": graph.n_edges,
            "manifest": graph.manifest,
        }

    @app.get("/api/sources")
    def sources() -> list[dict[str, Any]]:
        result = []
        for name in available_sources():
            meta = get_source_class(name).metadata
            result.append(
                {
                    "name": meta.name,
                    "display_name": meta.display_name,
                    "namespace": meta.namespace,
                    "version": meta.version,
                    "citation": meta.citation,
                    "homepage": meta.homepage,
                    "notes": meta.notes,
                }
            )
        return result

    @app.get("/api/config/descriptions")
    def config_descriptions() -> dict[str, dict[str, str]]:
        return {
            "build": describe(BuildConfig),
            "rwr": describe(RWRConfig),
        }

    @app.get("/api/search")
    def search(
        q: str = Query(..., min_length=1),
        limit: int = Query(20, ge=1, le=100),
    ) -> list[dict[str, str]]:
        get_graph()
        needle = q.lower()
        matches = [
            entry
            for entry in cache["search"]
            if needle in entry[0] or needle in entry[1]
        ]
        matches.sort(key=lambda entry: (not entry[0].startswith(needle), len(entry[0])))
        return [
            {"id": node_id, "symbol": symbol}
            for _, _, node_id, symbol in matches[:limit]
        ]

    @app.post("/api/subnetwork", response_model=SubnetworkResponse)
    def subnetwork(request: SubnetworkRequest) -> dict[str, Any]:
        graph = get_graph()
        rwr_config = RWRConfig(
            restart_prob=request.restart_prob,
            max_iter=request.max_iter,
            tol=request.tol,
        )
        result = rank_target_centered(
            graph,
            request.seeds,
            rwr_config=rwr_config,
            mode=request.mode,
            top_k=request.top_k,
            threshold=request.threshold,
            hops=request.hops,
            exclude_seeds=request.exclude_seeds,
            min_edge_weight=request.min_edge_weight,
            max_edge_weight=request.max_edge_weight,
            weight_normalization=request.weight_normalization,
            seed_weights=request.seed_weights,
        )
        return result.to_dict()

    if resolved_web.exists():
        app.mount("/static", StaticFiles(directory=resolved_web), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(resolved_web / "index.html")

    return app


app = create_app()

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(app)
