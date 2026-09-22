# Decisions (ADR log)

This file records design decisions. It gives the reason for each decision and the
options we rejected. Add new entries at the bottom. Use this format:

- **Context:** the problem.
- **Decision:** what we chose.
- **Why:** the reason.
- **Alternatives:** what we rejected.

## Writing rules (Simplified Technical English, adapted)

We write this file in an adapted form of ASD-STE100 Simplified Technical English. We
keep the rules that help the reader. We do not follow the full controlled dictionary.

Rules we use:

- Write one idea in each sentence.
- Keep sentences short. Use a maximum of about 25 words.
- Use the active voice.
- Use the same word for the same thing. Do not use synonyms.
- Do not use idioms or slang.
- Put the condition first, then the action.

Project glossary (technical nouns and verbs):

| Term | Meaning |
|---|---|
| graph | the merged interactome network |
| node | one gene in the graph |
| edge | one link between two nodes |
| seed | the target gene or genes of the walk |
| walk | the Random Walk with Restart (RWR) |
| artifact | the prebuilt graph file |
| build | the process that makes the graph |
| taxon | an organism, identified by an NCBI taxonomy ID |
| source | one interactome dataset, for example STRING |
| mapping | the change of an identifier to the canonical ID |

## D1 — Two-tier data architecture
**Context:** The full interactome files are very large. The all-species STRING file is about
129 GB.
**Decision:** We ship two things. First, a compact prebuilt graph artifact for runtime. Second,
an optional `build-data` command that downloads the data again and rebuilds the graph.
**Why:** The human STRING file is only about 60–90 MB compressed. The merged artifact is about
10–30 MB. At runtime, the app needs no internet. This gives fast cold starts and true offline
use.
**Alternatives:** Fetch at start (slow, fails when offline or when the source changes). Commit
the raw data (large repository).

## D2 — Taxon-driven, species-general
**Context:** The project started with human data. But it must also support other species and
mixed-species graphs.
**Decision:** All species behavior comes from an NCBI taxon ID. Human is only a default preset.
**Why:** The STRING file names, the BioMart marts, and the source support all use the taxon ID.
**Alternatives:** A hard-coded human pipeline (rejected).

## D3 — Canonical node key = Ensembl Gene ID
**Context:** Each source uses different identifiers. HuRI uses symbols, Entrez, or UniProt.
STRING uses Ensembl protein IDs.
**Decision:** We map all identifiers to the Ensembl **Gene** ID (`ENSG…`, or the species
equivalent).
**Why:** One stable code maps to symbol, Entrez, and UniProt. IDs do not collide between taxa.
**Alternatives:** Source-native IDs with a mapping table (the joins are harder). UniProt (it
handles isoforms badly).

## D4 — Node granularity is an explicit preprocessing option
**Context:** The choice of isoform handling changes the connectivity and the walk results.
**Decision:** We offer three options: `gene` (collapse ENSP to ENSG, the default), `protein`
(keep isoforms), and `as_provided`. The build window explains the effect of each option.
**Why:** Gene-level raises the connectivity. But it can increase the node degree and push the
walk toward hubs. Protein-level keeps the detail. But the graph is sparser.
**Alternatives:** Collapse without a message (it hides the data loss from the user).

## D5 — Interactome sources are a plugin registry
**Context:** Human needs a merge of HuRI and STRING. Other species may need STRING only, plus
extra overlays.
**Decision:** We define an `InteractomeSource` interface. Each source declares the species it
supports, its parser, its ID namespace, and its edge-weight policy. The planned sources are
STRING, HuRI, a custom TSV overlay, BioGRID, IntAct, and a STRING-COG orthology bridge.
**Why:** The pipeline stays general and testable. A cross-species source is just another source.
**Alternatives:** A fixed merge of two sources (it cannot grow).

## D6 — Seeds: one by default, a set is supported
**Context:** A target-centered search needs one seed. But a walk from a set of genes is also
useful.
**Decision:** The restart vector accepts one seed or a weighted set. The UI shows the limits:
a mixed set blurs toward the shared neighborhood. A hub seed dominates if we do not normalize.
**Alternatives:** One seed only (it limits the use). Automatic unweighted seeds (the result is
not clear).

## D7 — Algorithms on scipy sparse; no NetworkX in the hot path
**Context:** The walk and the preprocessing must handle millions of edges.
**Decision:** We store the graph as a scipy sparse matrix. We use NetworkX only for layout and
export, if at all.
**Why:** A sparse matrix-vector multiply keeps the walk below one second at human scale.
NetworkX would not.
**Alternatives:** NetworkX for everything (too slow). igraph (an extra dependency with C build
problems).

## D8 — Source formats verified against live data
**Context:** The parsers must match the real files. We must not guess.
**Decision and findings:**
- HuRI (`interactome-atlas.org/data/HuRI.tsv`, 1.68 MB) has no header. It is tab-separated
  and holds two Ensembl Gene IDs. It already matches the canonical key. So HuRI needs no
  mapping.
- STRING v12.0 links are space-separated: `protein1 protein2 combined_score` (0–1000; the
  human file is 83.2 MB compressed). The info file is tab-separated:
  `#string_protein_id preferred_name protein_size annotation`. STRING nodes are Ensembl
  **protein** IDs. So we must map `ENSP` to `ENSG`.
- BioGRID TAB3 has a header row. So we parse by column name. The organism columns hold NCBI
  taxon IDs. The download is an all-species zip of about 170 MB. We filter it during the parse.
- IntAct PSI-MITAB uses columns 0 and 1 for IDs, 9 and 10 for taxon IDs, and 14 for the
  confidence. The global archive is 1.35 GB. The species files are per strain, not per taxon.
- STRING `COG.mappings.v12.0.txt.gz` is 755 MB and global. The `orthologous_group` column
  joins species. The protein IDs have the form `<taxid>.<protein>`.
**Why:** We get correct parsers and honest expectations about the download size.
**Alternatives:** BioGRID parsing by column index (fragile). Assume that HuRI needs mapping
(wrong).

## D9 — Large and global downloads are optional
**Context:** Some sources are hundreds of MB or more than 1 GB. They are not split by species.
**Decision:** BioGRID downloads the all-species file and filters it by taxon. IntAct uses a
local PSI-MITAB path or a species-specific URL by default. It uses the 1.35 GB global archive
only as a fallback. The COG orthology bridge is optional. All downloads use a filename cache
with a size check and an atomic `.part` rename.
**Why:** The default human build stays small (about 105 MB). We avoid unexpected gigabyte
downloads.
**Alternatives:** Always download the global files (bad user experience, wasteful).

## D10 — STRING-derived mapping is the default; BioMart is optional
**Context:** BioMart was the original mapping plan. During development, the Ensembl endpoints
showed their "Service unavailable" page. The stable host redirects to a release archive during
release transitions. This was a timing observation, not a final result. BioMart is a mature
service and many projects use it. But the public endpoints have downtime windows and rate
limits.
**Decision:** We map identifiers with STRING's own `protein.info` and `protein.aliases` files.
These files contain `Ensembl_gene` and `Ensembl_HGNC_ensembl_gene_id` entries. These entries map
STRING protein IDs directly to Ensembl Gene IDs. From the same files, we also derive the symbol,
UniProt, and Entrez maps. BioMart stays as an optional provider. We use it only for bounded,
batched, cached queries at build time, for example for gene names. We never use it in the
request path.
**Why:** The default human build makes zero BioMart calls. It is reproducible. It still maps
BioGRID symbols and IntAct UniProt accessions through the derived tables. When we must use an
external service, we batch the calls at build time and we degrade with a warning if the service
is down.
**Alternatives:** BioMart-only mapping (it adds a live dependency to every build). No mapping
(it breaks the merge).

## D10a — Index-time data compared with query-time data
**Context:** We must decide where a field such as a gene common name belongs.
**Decision:** Data that changes the graph content or the search goes into the artifact at build
time. This includes IDs, edges, weights, and symbols. Data that only describes a result includes
long names, annotations, and external IDs. We bake this data once with a fallback, or we link to
an authoritative source (Ensembl, NCBI Gene, GeneCards). We do not make live API calls for each
request.
**Why:** The request path stays free of external dependencies and failures. A link is more
robust than an API call for descriptive data. A link cannot hit a rate limit or go down.
**Alternatives:** Live BioMart or API lookup for each query (fragile, slow, rate-limited).
Links only (the user sees no friendly name before the click).

## D11 — Verified end-to-end human build
**Context:** We must test the pipeline with real data, not only with unit fixtures.
**Decision and result:** The command `hustring build-data` for taxon 9606 (HuRI plus STRING with
score ≥ 700) made **17,379 nodes and 286,850 edges in about 56 seconds**. It made a **5.9 MB**
artifact from a **104 MB** cache. The walk recovers known biology. From TP53 it returns
EP300, MYC, HDAC1, MDM2, CDKN1A, and ATM. From BRCA1 it returns RAD51, BRCA2, BARD1, RBBP8,
MRE11, BLM, and FANCD2.
**Why:** This confirms the two-tier design, the mapping default, and the correctness of the
merge and the walk.
**Note:** The k-hop and threshold selections can be very large for a hub target. The CLI limits
the display to `--top` and reports the true total.

## D12 — Web API and viewer design
**Context:** We need an interactive viewer. It must be easy to host and it must work offline.
**Decision:**
- The FastAPI app is made by `create_app(graph_dir, web_dir)`. The graph is **loaded on the
  first request** and kept in memory. So the app starts without the graph.
- The endpoints are `/api/health`, `/api/graph/summary`, `/api/sources`, `/api/search`,
  `/api/config/descriptions`, and `/api/subnetwork` (POST). The UI uses `/` and `/static`.
- The UI is one page of plain JavaScript with **Cytoscape.js stored at `web/vendor/`**
  (373 KB). It does not use a CDN. So local and offline use needs no internet.
- `analysis.rank_target_centered` is the single shared code path for the CLI and the API.
- The endpoint `/api/config/descriptions` returns the field descriptions of `BuildConfig` and
  `RWRConfig`. This gives the data for the explanation window in the UI.
**Why:** One Docker image serves the API and the UI. The frontend needs no build step. It works
offline.
**Note:** The UI limits the render to 1500 nodes for a large k-hop result.

## D13 — Verified live server
**Context:** We must confirm that the hosted path works, not only the unit tests.
**Decision and result:** We served `data/derived/graph` and checked `/api/health`, `/`,
`/static/app.js`, `/static/vendor/cytoscape.min.js`, `/api/search?q=TP53`, and
`POST /api/subnetwork` (TP53 gives EP300, MYC, HDAC1, MDM2, and JUN). 75 tests pass.
**Alternatives:** A frontend build toolchain (rejected: too much work for this scope).

## D14 — Container-first delivery; the graph is not in the image
**Context:** The same artifact must run locally and on a hosted platform with little setup.
**Decision:** We use one `Dockerfile` and one `compose.yaml`. The image contains only code. The
graph lives in a mounted `/data` volume. On the first run, `docker/entrypoint.sh` builds the
graph if it is absent. Then it serves on `$PORT` (default 8000). So the port from the host
works. The web files go into the wheel through the hatch `force-include` option (`web` becomes
`hustring/web`). The variable `HUSTRING_WEB_DIR` can override the path. So the UI resolves in a
non-editable install.
**Why:** The image is small and holds no stale data. Local and hosted behavior is the same. The
cold start is fast when `/data` already holds the graph.
**Alternatives:** Put the graph and the 105 MB cache in the image (large and stale). Use a
second container for the frontend (too much).
**Note:** Docker was not installed on the development machine. So we did not test the image
build at first. We tested the entrypoint and the wheel contents directly.

## D15 — The prebuilt graph ships as a Release asset, not in git
**Context:** The two-tier design needs a prebuilt artifact. But derived data in `main` causes
churn and stale files.
**Decision:** We publish the merged graph as a versioned GitHub Release asset (tar.gz with a
sha256). The script `scripts/package_graph.sh` makes the asset. `main` holds only code. A
deployment can unpack the asset into `HUSTRING_GRAPH` and skip the first-run build.
**Why:** The history stays clean. The artifact updates independently of the code. The cold
start is fast.
**Alternatives:** Commit the artifact directly (large history, stale). Git LFS (extra
infrastructure). DVC (heavier).
**Revisit when:** CI can build and publish the artifact, or we add data versioning.

## D16 — One UI and one backend; Gradio replaced by FastAPI on Render
**Context:** Hugging Face began to require a paid plan for Docker Spaces. So we added a Gradio
app for the free tier. This made a second frontend with less control. It had no custom
tooltips, no About dialog, and limited styling. It also drifted from the hand-written `web/`
viewer. The value of this project is custom, explainable input. Gradio is weakest at exactly
that.
**Decision:** We removed Gradio and the Hugging Face deploy files. We keep **FastAPI and
`web/`** as the single UI and the single backend. We host the same Docker image on **Render's
free tier** (`render.yaml`). Cloud Run stays as a documented option for later.
**Why:** One UI has no drift and only one thing to test. The Docker image runs on many hosts. So
Render is not a lock-in.
**Alternatives:** Gradio inside Hugging Face (hard to build, still two backends). Hugging Face
Static with a JavaScript port of the walk (free, but duplicates the algorithm). Cloud Run now
(it needs a billing account and IAM setup).

## D17 — Deployment posture: what the Render demo is and is not
**Context:** HuStringSearch is a small instance of a larger architecture. I wanted a live link
that shows the full request path without paid infrastructure. I also wanted the same build to
move to larger environments later without a rewrite.
**Decision:** We host a deliberately small instance on Render's free tier
(https://hustringsearch.onrender.com). The same Docker image runs locally, on a cloud host, or
on HPC. For heavy, full-database searches, a user would run it locally, on their own cloud, or
on a cluster. The container makes that move possible.
**Why a server (Render) and not GitHub Pages or Colab:**
- GitHub Pages serves static files only. It works for a project such as Quick2DViewer. That
  viewer is self-contained and gets PDB data for each request. HuStringSearch needs the whole
  graph in memory and a server-side matrix computation. So it cannot run there without a
  rewrite of the algorithm in JavaScript.
- Colab is shareable by URL. But it is a notebook. It has no always-on endpoint. It keeps no
  data between sessions, so the graph would rebuild every time. Its cells-based interface does
  not suit an interactive graph and multi-variable input. A custom UI suits this better.
**Why Docker matters here:** It makes the location a deployment choice, not an engineering one.
We use local for development, a managed host for a live demo, and HPC for large batch work.
Clusters usually convert the image to Apptainer or Singularity and schedule it with Slurm,
because Docker needs root. The artifact stays the same in all cases.
**Scope note:** The demo ships a filtered human subset (17,379 nodes and 286,850 edges, STRING
score ≥ 700) to fit free hardware. The pipeline can merge the full datasets. The filter is a
deliberate limit of the demo, not a limit of the design.
**Alternatives:** GitHub Pages with a JavaScript port of the walk (free, but it duplicates the
algorithm and sends the graph to each browser). Colab (shareable, but no persistent endpoint, no
data retention, and a notebook interface that does not suit an interactive graph). Paid Docker
Spaces on Hugging Face (the same cost as a general host, with less flexibility).
