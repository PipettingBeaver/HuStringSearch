"""Command-line interface: build, inspect, and query a graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from .analysis import SelectionMode, rank_target_centered
from .config import BuildConfig, NodeGranularity, RWRConfig, SourceConfig
from .graph import Graph, build_graph
from .sources import available_sources, get_source_class

app = typer.Typer(add_completion=False, help="HuStringSearch: interactome merge + RWR.")

DEFAULT_GRAPH = Path("data/derived/graph")
DEFAULT_CACHE = Path("data/cache")


@app.command("sources")
def list_sources() -> None:
    """List the registered interactome sources."""
    for name in available_sources():
        meta = get_source_class(name).metadata
        typer.echo(
            f"{name:10} {meta.display_name:30} ns={meta.namespace:14} v={meta.version}"
        )
        if meta.notes:
            typer.echo(f"           {meta.notes}")


@app.command("build-data")
def build_data(
    taxid: int = typer.Option(9606, help="NCBI taxonomy ID (9606 = human)."),
    output: Path = typer.Option(DEFAULT_GRAPH, "--output", "-o", help="Graph output dir."),
    cache: Path = typer.Option(DEFAULT_CACHE, "--cache", help="Raw download cache dir."),
    source: list[str] = typer.Option([], "--source", help="Enable only these sources (repeatable)."),
    granularity: NodeGranularity = typer.Option(NodeGranularity.GENE, help="Node granularity."),
    string_threshold: int = typer.Option(700, min=0, max=1000, help="STRING score cutoff."),
    min_degree: int = typer.Option(0, min=0, help="Drop nodes below this degree."),
    keep_largest_component: bool = typer.Option(False, help="Keep only the largest component."),
    force: bool = typer.Option(False, help="Re-download even if a cached file exists."),
) -> None:
    """Fetch enabled sources, merge, and save a canonical graph."""
    overrides = [SourceConfig(name=name) for name in source] if source else None
    config = BuildConfig(
        taxid=taxid,
        sources=overrides,
        node_granularity=granularity,
        string_score_threshold=string_threshold,
        min_node_degree=min_degree,
        keep_largest_component=keep_largest_component,
    )
    typer.echo(f"Building graph for {config.species_name()} ...")
    graph = build_graph(config, cache, force=force)
    graph.save(output)
    typer.echo(f"Saved {graph.n_nodes} nodes / {graph.n_edges} edges to {output}")
    unmapped = graph.manifest.get("unmapped_edges")
    if unmapped:
        typer.echo(f"Dropped {unmapped} edges with unmappable identifiers.")


@app.command("inspect")
def inspect(
    graph_dir: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g"),
    top: int = typer.Option(10, min=1, help="Number of hub nodes to show."),
) -> None:
    """Print graph size and the highest-degree nodes."""
    graph = Graph.load(graph_dir)
    typer.echo(f"nodes={graph.n_nodes} edges={graph.n_edges}")
    degree = graph.adjacency.getnnz(axis=1)
    for i in degree.argsort()[::-1][:top]:
        typer.echo(f"  {graph.symbols[i]:16} {graph.node_ids[i]:22} degree={int(degree[i])}")


@app.command("walk")
def walk(
    seeds: list[str] = typer.Argument(..., help="Seed symbol(s) or Ensembl Gene ID(s)."),
    graph_dir: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g"),
    restart: float = typer.Option(0.85, min=0.0, max=1.0, help="RWR restart probability."),
    top: int = typer.Option(25, min=1, help="Number of top nodes to report."),
    hops: int = typer.Option(0, min=0, help="If >0, select by k-hop instead of top-k."),
    threshold: float = typer.Option(0.0, min=0.0, help="If >0, select by score threshold."),
) -> None:
    """Run a target-centered RWR and print the ranked subnetwork."""
    graph = Graph.load(graph_dir)
    config = RWRConfig(restart_prob=restart)
    mode: SelectionMode
    hop_count: int | None
    cutoff: float | None
    if hops > 0:
        mode, hop_count, cutoff = "k_hop", hops, None
    elif threshold > 0:
        mode, hop_count, cutoff = "threshold", None, threshold
    else:
        mode, hop_count, cutoff = "top_k", None, None
    result = rank_target_centered(
        graph,
        seeds,
        rwr_config=config,
        mode=mode,
        top_k=top,
        hops=hop_count,
        threshold=cutoff,
    )
    if result.missing_seeds:
        typer.echo(f"warning: seeds not found: {result.missing_seeds}", err=True)
    typer.echo(f"seeds: {result.resolved_seeds}  mode={result.mode}")
    for node in result.ranked[:top]:
        typer.echo(f"  {node.symbol:16} {node.id:22} {node.score:.6g}")
    if len(result.ranked) > top:
        typer.echo(f"  ... {len(result.ranked) - top} more")
    typer.echo(f"({len(result.ranked)} nodes, {len(result.edges)} edges)")


@app.command("fetch-graph")
def fetch_graph(
    url: str = typer.Option(..., "--url", help="URL of a packaged graph .tar.gz (Release asset)."),
    output: Path = typer.Option(DEFAULT_GRAPH, "--output", "-o", help="Directory to unpack into."),
) -> None:
    """Download and unpack a prebuilt graph archive."""
    from .graph.fetch import fetch_graph_archive

    fetch_graph_archive(url, output)
    graph = Graph.load(output)
    typer.echo(f"Fetched {graph.n_nodes} nodes / {graph.n_edges} edges into {output}")


@app.command("serve")
def serve(
    graph_dir: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Graph directory to serve."),
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(False, help="Auto-reload (development)."),
) -> None:
    """Serve the interactive web viewer and analysis API."""
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.BadParameter(
            "serve needs the web extras: pip install 'hustring[web]'"
        ) from exc

    from .api.main import create_app

    typer.echo(f"Serving graph '{graph_dir}' at http://{host}:{port}")
    if reload:
        uvicorn.run("hustring.api.main:app", host=host, port=port, reload=True)
    else:
        uvicorn.run(
            create_app(graph_dir),
            host=host,
            port=port,
            log_config=_uvicorn_log_config(),
        )


def _uvicorn_log_config() -> dict[str, Any]:
    """Uvicorn logging config that hides the container health check from access logs."""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": "%(levelname)s:     %(message)s"},
            "access": {"format": "%(levelname)s:     %(message)s"},
        },
        "handlers": {
            "default": {"formatter": "default", "class": "logging.StreamHandler"},
            "access": {"formatter": "access", "class": "logging.StreamHandler"},
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.access": {
                "handlers": ["access"],
                "level": "INFO",
                "filters": ["hide_health"],
            },
        },
        "filters": {"hide_health": {"()": _HealthCheckFilter}},
    }


class _HealthCheckFilter:
    """Drop access-log records for /api/health so they don't spam the logs."""

    def filter(self, record: Any) -> bool:
        message = record.getMessage()
        return "/api/health" not in message and "GET /healthz" not in message


@app.command("gradio")
def gradio_serve(
    graph_dir: Path = typer.Option(DEFAULT_GRAPH, "--graph", "-g", help="Graph directory to serve."),
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(7860, help="Bind port."),
    share: bool = typer.Option(False, help="Create a temporary public Gradio link."),
) -> None:
    """Serve the Gradio interface (also used for Hugging Face Spaces)."""
    try:
        from .gradio_app import build_demo
    except ImportError as exc:
        raise typer.BadParameter(
            "gradio needs the gradio extra: pip install 'hustring[gradio]'"
        ) from exc

    typer.echo(f"Serving Gradio app for graph '{graph_dir}' at http://{host}:{port}")
    build_demo(graph_dir).queue().launch(server_name=host, server_port=port, share=share)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
