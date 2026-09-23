const MAX_RENDER = 1500;
const $ = (id) => document.getElementById(id);

let cy = null;
let scoreById = new Map();

async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_) {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return response.json();
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function setStatus(message) {
  $("status").textContent = message;
}

function setBusy(busy) {
  $("run").disabled = busy;
  $("run").textContent = busy ? "Running…" : "Run RWR";
}

async function init() {
  try {
    const summary = await api("/api/graph/summary");
    const config = (summary.manifest && summary.manifest.config) || {};
    $("graph-stats").textContent =
      `${summary.nodes.toLocaleString()} nodes · ${summary.edges.toLocaleString()} edges · ` +
      `taxid ${config.taxid ?? "?"} · STRING≥${config.string_score_threshold ?? "?"}`;
  } catch (error) {
    $("graph-stats").textContent = error.message;
  }

  try {
    const descriptions = await api("/api/config/descriptions");
    const restartHelp = document.querySelector('.help[data-field="restart_prob"]');
    if (restartHelp && descriptions.rwr && descriptions.rwr.restart_prob) {
      restartHelp.dataset.tip = descriptions.rwr.restart_prob;
    }
  } catch (_) {
    /* descriptions are optional */
  }

  initTooltips();
  initAbout();
  initWeightControl();
  $("run").addEventListener("click", run);
  $("seeds").addEventListener("input", debounce(autocomplete, 200));
  $("seeds").addEventListener("keydown", (event) => {
    if (event.key === "Enter") run();
  });
}

function initWeightControl() {
  const number = $("min_weight");
  const range = $("min_weight_range");
  const sync = (value) => {
    const clamped = clamp01(Number(value));
    number.value = clamped.toFixed(2);
    range.value = clamped;
  };
  number.addEventListener("input", () => sync(number.value));
  range.addEventListener("input", () => sync(range.value));
  sync(number.value);
}

function initTooltips() {
  const tooltip = $("tooltip");

  const show = (element) => {
    const tip = element.dataset.tip;
    if (!tip) return;
    tooltip.textContent = tip;
    tooltip.classList.remove("hidden");

    const margin = 8;
    const rect = element.getBoundingClientRect();
    const width = tooltip.offsetWidth;
    const height = tooltip.offsetHeight;

    let left = rect.left;
    if (left + width > window.innerWidth - margin) left = window.innerWidth - margin - width;
    if (left < margin) left = margin;

    let top = rect.bottom + 6;
    if (top + height > window.innerHeight - margin) top = rect.top - height - 6;
    if (top < margin) top = margin;

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  };

  const hide = () => tooltip.classList.add("hidden");

  for (const element of document.querySelectorAll(".help")) {
    element.addEventListener("mouseenter", () => show(element));
    element.addEventListener("focus", () => show(element));
    element.addEventListener("mouseleave", hide);
    element.addEventListener("blur", hide);
    element.addEventListener("click", (event) => {
      event.preventDefault();
      show(element);
    });
  }
  window.addEventListener("scroll", hide, true);
  window.addEventListener("resize", hide);
}

function initAbout() {
  const dialog = $("about-dialog");
  $("about").addEventListener("click", () => dialog.showModal());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}

async function autocomplete() {
  const tokens = $("seeds").value.split(/[,\s]+/);
  const value = (tokens[tokens.length - 1] || "").trim();
  if (value.length < 2) return;
  try {
    const matches = await api(`/api/search?q=${encodeURIComponent(value)}&limit=10`);
    const list = $("seed-options");
    list.innerHTML = "";
    for (const match of matches) {
      const option = document.createElement("option");
      option.value = match.symbol;
      option.label = match.id;
      list.appendChild(option);
    }
  } catch (_) {
    /* ignore transient search errors */
  }
}

function clamp01(value) {
  if (Number.isNaN(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

function parseSeeds() {
  return $("seeds").value
    .split(/[,\s]+/)
    .map((value) => value.trim())
    .filter(Boolean);
}

async function run() {
  const seeds = parseSeeds();
  if (!seeds.length) {
    setStatus("Enter at least one target.");
    return;
  }
  const body = {
    seeds,
    mode: $("mode").value,
    top_k: Number($("top_k").value),
    threshold: Number($("threshold").value),
    hops: Number($("hops").value),
    restart_prob: Number($("restart").value),
    exclude_seeds: $("exclude").checked,
    min_edge_weight: clamp01(Number($("min_weight").value)),
    weight_normalization: $("normalize").value,
  };
  setBusy(true);
  setStatus("Running RWR…");
  try {
    const result = await api("/api/subnetwork", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    render(result);
  } catch (error) {
    setStatus(error.message);
  } finally {
    setBusy(false);
  }
}

function render(result) {
  const parts = [
    `${result.ranked.length.toLocaleString()} nodes`,
    `${result.edges.length.toLocaleString()} edges`,
    `mode ${result.mode}`,
  ];
  if (result.missing_seeds.length) {
    parts.push(`not found: ${result.missing_seeds.join(", ")}`);
  }
  setStatus(parts.join(" · "));
  scoreById = new Map(result.ranked.map((node) => [node.id, node.score]));
  renderTable(result);
  renderGraph(result);
}

function renderTable(result) {
  const tbody = document.querySelector("#ranked tbody");
  tbody.innerHTML = "";
  for (const node of result.ranked) {
    const row = document.createElement("tr");
    const symbol = document.createElement("td");
    const id = document.createElement("td");
    const score = document.createElement("td");
    symbol.textContent = node.symbol;
    id.textContent = node.id;
    score.textContent = node.score.toExponential(3);
    row.append(symbol, id, score);
    row.addEventListener("click", () => highlight(node.id));
    tbody.appendChild(row);
  }
}

function colorFor(sourceClass) {
  switch (sourceClass) {
    case "huri":
      return "#ff5d73";
    case "string":
      return "#4aa3ff";
    case "both":
      return "#a06bff";
    default:
      return "#8b96ad";
  }
}

function renderGraph(result) {
  const nodes = new Map();
  const seeds = result.seed_nodes || [];
  for (const seed of seeds) {
    nodes.set(seed.id, {
      id: seed.id,
      symbol: seed.label || seed.id,
      seed: true,
      color: colorFor(seed.source_class),
      sourceClass: seed.source_class,
    });
  }
  for (let i = 0; i < result.seed_ids.length; i += 1) {
    const id = result.seed_ids[i];
    if (!nodes.has(id)) {
      nodes.set(id, {
        id,
        symbol: result.resolved_seeds[i] || id,
        seed: true,
        color: "#8b96ad",
        sourceClass: "unknown",
      });
    }
  }

  let ranked = result.ranked;
  if (ranked.length > MAX_RENDER) {
    ranked = ranked.slice(0, MAX_RENDER);
  }
  for (const node of ranked) {
    if (!nodes.has(node.id)) {
      nodes.set(node.id, {
        id: node.id,
        symbol: node.symbol,
        seed: false,
        color: colorFor(node.source_class),
        sourceClass: node.source_class,
      });
    }
  }

  const ids = new Set(nodes.keys());
  const elements = [...nodes.values()].map((node) => ({
    data: {
      id: node.id,
      label: node.symbol,
      seed: node.seed,
      color: node.color,
      source_class: node.sourceClass,
    },
  }));
  const seen = new Set();
  for (const edge of result.edges) {
    if (!ids.has(edge.a) || !ids.has(edge.b)) continue;
    const key = `${edge.a}|${edge.b}`;
    if (seen.has(key)) continue;
    seen.add(key);
    elements.push({
      data: { id: key, source: edge.a, target: edge.b, weight: edge.weight },
    });
  }

  if (cy) {
    cy.destroy();
    cy = null;
  }
  cy = cytoscape({
    container: $("cy"),
    elements,
    wheelSensitivity: 0.2,
    style: [
      {
        selector: "node",
        style: {
          "background-color": "data(color)",
          label: "data(label)",
          "font-size": 9,
          color: "#c9d4e6",
          "text-valign": "bottom",
          "text-margin-y": 3,
          width: 16,
          height: 16,
        },
      },
      {
        selector: "node[?seed]",
        style: {
          width: 32,
          height: 32,
          "font-size": 12,
          color: "#ffffff",
          "border-width": 3,
          "border-color": "#ffffff",
        },
      },
      {
        selector: "edge",
        style: {
          width: 1,
          "line-color": "#33405f",
          "curve-style": "haystack",
          opacity: 0.5,
        },
      },
      {
        selector: "node:selected",
        style: { "border-width": 3, "border-color": "#ffffff" },
      },
    ],
    layout: {
      name: "cose",
      animate: false,
      padding: 24,
      idealEdgeLength: 80,
      nodeRepulsion: 8000,
    },
  });
  cy.on("tap", "node", (event) => showDetails(event.target.data()));
  cy.on("tap", (event) => {
    if (event.target === cy) hideDetails();
  });
}

function highlight(id) {
  if (!cy) return;
  const node = cy.getElementById(id);
  if (!node || node.empty()) return;
  cy.elements().unselect();
  node.select();
  cy.animate({ center: { eles: node }, zoom: 1.5 }, { duration: 250 });
  showDetails(node.data());
}

function showDetails(data) {
  const panel = $("details");
  const score = scoreById.get(data.id);
  panel.innerHTML = "";
  const title = document.createElement("strong");
  title.textContent = data.label || data.id;
  const id = document.createElement("div");
  id.className = "muted";
  id.textContent = data.id;
  panel.append(title, id);
  if (data.gene_name) {
    const name = document.createElement("div");
    name.textContent = data.gene_name;
    panel.appendChild(name);
  }
  if (score !== undefined) {
    const value = document.createElement("div");
    value.textContent = `RWR score: ${score.toExponential(4)}`;
    panel.appendChild(value);
  }
  if (data.seed) {
    const seed = document.createElement("div");
    seed.textContent = "seed";
    panel.appendChild(seed);
  }
  if (data.source_class) {
    const source = document.createElement("div");
    source.textContent = `source: ${data.source_class}`;
    panel.appendChild(source);
  }
  if (data.links) {
    const links = document.createElement("div");
    links.className = "links";
    const labels = {
      ensembl: "Ensembl",
      ncbi: "NCBI Gene",
      genecards: "GeneCards",
      uniprot: "UniProt",
    };
    for (const [key, url] of Object.entries(data.links)) {
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.textContent = labels[key] || key;
      links.appendChild(anchor);
    }
    panel.appendChild(links);
  }
  panel.classList.remove("hidden");
}

function hideDetails() {
  $("details").classList.add("hidden");
}

document.addEventListener("DOMContentLoaded", init);
