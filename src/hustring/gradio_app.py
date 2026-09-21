"""Gradio front-end, used for Hugging Face Spaces.

Rendering (Cytoscape.js) happens in the browser via a Gradio JS callback, while
ranking is computed server-side by the shared :mod:`hustring.analysis` module, so
results match the CLI and the FastAPI viewer exactly.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, cast

import gradio as gr

from .analysis import SelectionMode, rank_target_centered
from .config import BuildConfig, RWRConfig
from .errors import SeedError
from .graph import Graph, build_graph, fetch_graph_archive

DEFAULT_GRAPH_DIR = Path(os.environ.get("HUSTRING_GRAPH", "data/graph"))
CYTOSCAPE_URL = "https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"

try:  # pragma: no cover - only meaningful on Hugging Face ZeroGPU hardware
    import spaces

    @spaces.GPU  # type: ignore[untyped-decorator]
    def _zero_gpu_ping() -> None:
        """No-op GPU function so the Space is valid on ZeroGPU; never called."""
except Exception:  # pragma: no cover
    def _zero_gpu_ping() -> None:
        return None


ABOUT = """
### HuStringSearch

Explore protein interaction networks by merging interactome sources and running a
**Random Walk with Restart (RWR)** centered on a gene of interest.

- **Merged interactomes:** HuRI (experimental binary) + STRING (confidence-scored).
- **Canonical IDs:** Ensembl Gene IDs, so sources merge cleanly.
- **Target-centered subnetworks:** ranked by network proximity; select by top-k,
  score threshold, or k-hop.

Node colors show where each protein is observed: **HuRI** (red), **STRING** (blue),
or **both** (purple).

Built by PipettingBeaver · MIT licensed.
"""

LEGEND_HTML = """
<div style="display:flex;gap:1rem;font-size:0.78rem;color:#8b96ad;margin-bottom:0.25rem">
  <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;
    background:#ff5d73;margin-right:0.3rem"></span>HuRI</span>
  <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;
    background:#4aa3ff;margin-right:0.3rem"></span>STRING</span>
  <span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;
    background:#a06bff;margin-right:0.3rem"></span>Both</span>
</div>
"""

DRAW_JS_TEMPLATE = """
(payload) => {
  const el = document.getElementById('hu-cy');
  if (!el || !payload || !payload.nodes) { return; }
  const load = () => new Promise((resolve, reject) => {
    if (window.cytoscape) { resolve(); return; }
    const existing = window._huCytoPromise;
    if (existing) {
      existing.then(() => resolve()).catch((e) => reject(e));
      return;
    }
    window._huCytoPromise = new Promise((res, rej) => {
      const script = document.createElement('script');
      script.src = '__CYTOSCAPE_URL__';
      script.onload = () => res();
      script.onerror = () => rej(new Error('cytoscape failed to load'));
      document.head.appendChild(script);
    });
    window._huCytoPromise.then(() => resolve()).catch((e) => reject(e));
  });
  load().then(() => {
    const elements = [];
    for (const node of payload.nodes) {
      elements.push({ data: { id: node.id, label: node.label, seed: node.seed,
                              color: node.color, source_class: node.source_class } });
    }
    for (const edge of payload.edges) {
      elements.push({ data: { id: edge.id, source: edge.source, target: edge.target } });
    }
    if (window._huCy) { window._huCy.destroy(); }
    window._huCy = window.cytoscape({
      container: el,
      elements: elements,
      wheelSensitivity: 0.2,
      style: [
        { selector: 'node', style: {
            'background-color': 'data(color)', label: 'data(label)', 'font-size': 9,
            color: '#c9d4e6', 'text-valign': 'bottom', 'text-margin-y': 3,
            width: 16, height: 16 } },
        { selector: 'node[?seed]', style: {
            width: 32, height: 32, 'font-size': 12, color: '#ffffff',
            'border-width': 3, 'border-color': '#ffffff' } },
        { selector: 'edge', style: {
            width: 1, 'line-color': '#33405f', 'curve-style': 'haystack', opacity: 0.5 } }
      ],
      layout: { name: 'cose', animate: false, padding: 20, nodeRepulsion: 8000, idealEdgeLength: 80 }
    });
  }).catch(() => { el.textContent = 'Graph library could not be loaded.'; });
}
"""

DRAW_JS = DRAW_JS_TEMPLATE.replace("__CYTOSCAPE_URL__", CYTOSCAPE_URL)


def load_or_build_graph(
    graph_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
) -> Graph:
    """Load a graph, fetching a Release asset or building it if absent."""
    path = Path(graph_dir) if graph_dir is not None else DEFAULT_GRAPH_DIR
    if (path / "adjacency.npz").exists():
        return Graph.load(path)

    url = os.environ.get("HUSTRING_GRAPH_URL")
    if url:
        fetch_graph_archive(url, path)
    else:
        cache = Path(cache_dir) if cache_dir is not None else Path(
            os.environ.get("HUSTRING_CACHE", "data/cache")
        )
        config = BuildConfig(taxid=int(os.environ.get("HUSTRING_TAXID", "9606")))
        build_graph(config, cache).save(path)
    return Graph.load(path)


def compute_subnetwork(
    graph: Graph,
    seeds_text: str,
    mode: str,
    top_k: float,
    threshold: float,
    hops: float,
    restart: float,
    exclude_seeds: bool,
) -> tuple[dict[str, Any], list[list[str]], str]:
    """Run the walk and return (cytoscape payload, table rows, status text)."""
    seeds = [token for token in re.split(r"[,\s]+", seeds_text or "") if token]
    empty: dict[str, Any] = {"nodes": [], "edges": [], "seed_ids": []}
    if not seeds:
        return empty, [], "Enter at least one target gene."

    try:
        result = rank_target_centered(
            graph,
            seeds,
            rwr_config=RWRConfig(restart_prob=float(restart)),
            mode=cast(SelectionMode, mode),
            top_k=int(top_k),
            threshold=float(threshold),
            hops=int(hops),
            exclude_seeds=bool(exclude_seeds),
        )
    except SeedError as exc:
        return empty, [], f"No matching target: {exc}"

    rows = [[node.symbol, node.id, f"{node.score:.3e}"] for node in result.ranked]
    status = f"{len(result.ranked):,} nodes · {len(result.edges):,} edges · mode {result.mode}"
    if result.missing_seeds:
        status = f"{status} · not found: {', '.join(result.missing_seeds)}"
    return result.to_cytoscape(), rows, status


def build_demo(graph_dir: str | Path | None = None) -> gr.Blocks:
    """Construct the Gradio interface (graph loaded lazily on first query)."""
    cache: dict[str, Graph] = {}

    def get_graph() -> Graph:
        if "graph" not in cache:
            cache["graph"] = load_or_build_graph(graph_dir)
        return cache["graph"]

    with gr.Blocks(title="HuStringSearch") as demo:
        gr.Markdown(ABOUT)
        with gr.Row():
            with gr.Column(scale=1):
                seeds = gr.Textbox(
                    label="Target gene(s)",
                    placeholder="TP53  or  TP53, MDM2",
                    info="HGNC symbols or Ensembl Gene IDs; separate multiple with commas. "
                    "Multiple seeds find the neighborhood they share.",
                )
                mode = gr.Dropdown(
                    choices=[
                        ("Top-k by score", "top_k"),
                        ("Score threshold", "threshold"),
                        ("k-hop neighborhood", "k_hop"),
                    ],
                    value="top_k",
                    label="Selection mode",
                    info="Top-k = highest-scoring nodes; Threshold = all nodes above a cutoff; "
                    "k-hop = everything within k edges of the seed(s).",
                )
                top_k = gr.Slider(
                    1, 500, value=50, step=1, label="Top-k",
                    info="Highest-scoring nodes to return (Top-k mode).",
                )
                threshold = gr.Number(
                    value=0.001, label="Threshold",
                    info="Include nodes scoring above this value (Threshold mode). Useful "
                    "cutoffs are often 1e-4 to 1e-3.",
                )
                hops = gr.Slider(
                    1, 6, value=2, step=1, label="Hops",
                    info="Maximum edges from the seed(s) (k-hop mode). Hub targets expand "
                    "very quickly, so keep this small.",
                )
                restart = gr.Slider(
                    0.1, 0.99, value=0.85, step=0.01, label="Restart probability",
                    info="Probability the walk jumps back to the seed(s) each step. Higher "
                    "keeps scores near the target; lower diffuses further.",
                )
                exclude = gr.Checkbox(
                    value=True,
                    label="Exclude seed(s) from ranking",
                    info="Remove the seed gene(s) from the ranked results so you see their "
                    "partners. They stay highlighted in the network.",
                )
                run = gr.Button("Run RWR", variant="primary")
                status = gr.Markdown("")
            with gr.Column(scale=2):
                gr.HTML(LEGEND_HTML)
                gr.HTML(
                    '<div id="hu-cy" style="height:480px;width:100%;'
                    'background:#171e2e;border:1px solid #26304a;border-radius:8px"></div>'
                )
                table = gr.Dataframe(
                    headers=["Symbol", "Ensembl ID", "Score"],
                    interactive=False,
                    wrap=False,
                )
        payload = gr.JSON(visible=False)

        run.click(
            fn=lambda *args: compute_subnetwork(get_graph(), *args),
            inputs=[seeds, mode, top_k, threshold, hops, restart, exclude],
            outputs=[payload, table, status],
        ).then(fn=None, inputs=[payload], outputs=[], js=DRAW_JS)

    return cast(gr.Blocks, demo)


def main() -> None:
    """Entry point for the Hugging Face Space and `hustring gradio`."""
    build_demo().queue().launch()


if __name__ == "__main__":  # pragma: no cover
    main()
