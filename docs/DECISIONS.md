# Decisions (ADR log)

Living log of design decisions, the reasoning, and rejected alternatives.
Append newest at the bottom. Format: Context / Decision / Why / Alternatives.

## D1 — Two-tier data architecture
**Context:** Full interactome downloads look huge; the all-species STRING file is ~129 GB.
**Decision:** Ship (a) a compact prebuilt merged-graph artifact for runtime and (b) an
opt-in `build-data` pipeline that re-fetches and rebuilds.
**Why:** Human-filtered STRING is only ~60–90 MB gz; the merge artifact is ~10–30 MB. Runtime
needs no outbound internet, giving fast cold starts and genuine offline local use.
**Alternatives:** fetch-on-start (slow, breaks offline / when upstream changes); commit raw
data (repo bloat).

## D2 — Taxon-driven, species-general
**Context:** Project began human-focused but must support other species and multi-species overlaps.
**Decision:** All species behavior derives from an NCBI taxon ID. Human is only a default preset.
**Why:** STRING file URLs, BioMart marts, and source support are all taxon-parameterized.
**Alternatives:** hard-coded human pipeline (rejected).

## D3 — Canonical node key = Ensembl Gene ID
**Context:** Sources use different namespaces (HuRI: symbols/Entrez/UniProt; STRING: Ensembl protein IDs).
**Decision:** Canonicalize to Ensembl **Gene** ID (`ENSG…`, species-specific elsewhere).
**Why:** One stable code resolvable to symbol/Entrez/UniProt, and IDs do not collide across taxa.
**Alternatives:** source-native IDs + mapping table (messier joins); UniProt (isoform-unfriendly).

## D4 — Node granularity is an explicit preprocessing option
**Context:** Isoform handling materially changes connectivity and RWR behavior.
**Decision:** Expose `gene` (collapse ENSP→ENSG, default), `protein` (preserve isoforms),
`as_provided`. Each with an explanation of effects in the build window.
**Why:** Gene-level raises connectivity but can inflate degree and bias RWR toward hubs;
protein-level preserves resolution but is sparser.
**Alternatives:** silently collapsing (hides data loss from users).

## D5 — Interactome sources are a plugin registry
**Context:** Human merges HuRI+STRING; other species may need STRING-only plus overlays.
**Decision:** `InteractomeSource` interface with declared species support, parser, ID namespace,
edge-weight policy. Plan: STRING, HuRI, custom TSV overlay, BioGRID, IntAct, and a STRING-COG
orthology bridge for cross-species graphs.
**Why:** Keeps the pipeline general and testable; cross-species is just another source.
**Alternatives:** a fixed two-source merge (not extensible).

## D6 — Seeds: single default, set supported
**Context:** Target-centered use wants one seed, but set-based walks are useful.
**Decision:** Restart vector supports one-hot or weighted multi-seed. Surface caveats in UI:
heterogeneous sets blur toward shared neighborhoods; hub seeds dominate without normalization.
**Alternatives:** single-seed only (limits use); unweighted auto-selection (opaque).

## D7 — Algorithms on scipy sparse; no NetworkX in hot path
**Context:** RWR and preprocessing must scale to millions of edges.
**Decision:** Represent graphs as scipy sparse matrices; NetworkX at most for layout/export.
**Why:** Sparse matvec RWR stays sub-second at human scale; NetworkX would not.
**Alternatives:** NetworkX everywhere (too slow); igraph (extra dep, C concerns).

## D8 — Source formats verified against live data
**Context:** Parsers must match real files, not guesses.
**Decision & findings:**
- HuRI (`interactome-atlas.org/data/HuRI.tsv`, 1.68 MB) is **headerless, tab-separated, two
  Ensembl Gene IDs** — it already matches the canonical key, so HuRI needs *no* BioMart mapping.
- STRING v12.0: links are space-separated `protein1 protein2 combined_score` (0–1000, human gz
  83.2 MB); info is tab-separated `#string_protein_id preferred_name protein_size annotation`.
  STRING nodes are Ensembl **protein** IDs, so mapping (`ENSP`→`ENSG`) is required.
- BioGRID TAB3 has a **header row**, so parse by column name; organism columns are NCBI taxids;
  download is an all-species zip (~170 MB) filtered at parse time.
- IntAct PSI-MITAB: cols 0/1 ids, 9/10 taxids, 14 confidence; the global archive is **1.35 GB**,
  and species files are per-strain (not taxid-addressable).
- STRING `COG.mappings.v12.0.txt.gz` is **755 MB** and global; `orthologous_group` column bridges
  species (protein IDs are `<taxid>.<protein>`).
**Why:** Correct parsers, and honest expectations about download cost.
**Alternatives:** naive index-based BioGRID parsing (fragile); assuming HuRI needs mapping (wrong).

## D9 — Large/global downloads are opt-in
**Context:** Some sources are hundreds of MB or over a GB and are not species-scoped.
**Decision:** BioGRID (all-species) downloads and filters by taxon; IntAct defaults to a local
PSI-MITAB path or a species-specific URL and only falls back to the 1.35 GB global archive;
the COG orthology bridge is opt-in. All downloads cache by filename with size checks and
`.part` atomic renames.
**Why:** Keeps the default human build small (~105 MB) and avoids surprising gigabyte fetches.
**Alternatives:** always fetch global files (bad UX, wasteful).

## D10 — STRING-derived mapping is the default; BioMart is optional
**Context:** BioMart was the original mapping plan, but its endpoints proved unreliable (the
stable host redirects to a release archive that was serving "Service unavailable").
**Decision:** Canonicalize identifiers using STRING's own `protein.info` + `protein.aliases`
files, which contain `Ensembl_gene` / `Ensembl_HGNC_ensembl_gene_id` entries that map STRING
protein IDs straight to Ensembl Gene IDs. From those we also derive symbol/uniprot/entrez maps.
BioMart remains a first-class optional provider for gaps and non-STRING-covered IDs.
**Why:** The default human build needs zero BioMart calls, is reproducible, and still maps
BioGRID symbols and IntAct UniProt accessions via the derived symbol/uniprot tables.
**Alternatives:** BioMart-only (fragile, currently down); skip mapping (breaks the merge).

## D11 — Verified end-to-end human build
**Context:** Validate the pipeline against real data, not just unit fixtures.
**Decision/result:** `hustring build-data` for 9606 (HuRI + STRING>=700) produced **17,379 nodes /
286,850 edges in ~56 s**, a **5.9 MB** graph artifact from a **104 MB** cache. RWR recovers known
biology: TP53 -> EP300/MYC/HDAC1/MDM2/CDKN1A/ATM; BRCA1 -> RAD51/BRCA2/BARD1/RBBP8/MRE11/BLM/FANCD2.
**Why:** Confirms the two-tier design, the mapping default, and RWR/merge correctness.
**Note:** k-hop/threshold selections can be very large for hub targets; the CLI caps display to
`--top` while reporting the true total.

## D12 — Web API + viewer design
**Context:** Need an interactive viewer that is also easy to host and works offline locally.
**Decision:**
- FastAPI app built by `create_app(graph_dir, web_dir)`; the graph is **loaded lazily** on first
  request and cached in-process, so the app boots without requiring the graph to exist.
- Endpoints: `/api/health`, `/api/graph/summary`, `/api/sources`, `/api/search`,
  `/api/config/descriptions`, `/api/subnetwork` (POST), and `/` + `/static` for the UI.
- The UI is a single vanilla-JS page using **Cytoscape.js vendored at `web/vendor/`** (373 KB)
  rather than a CDN, so local/offline use needs no internet.
- `analysis.rank_target_centered` is the single shared code path for CLI and API.
- The `/api/config/descriptions` endpoint exposes the `BuildConfig`/`RWRConfig` field descriptions,
  feeding the "explanation window" requirement into the UI.
**Why:** One Docker image can serve both API and UI; no build step for the frontend; offline-safe.
**Note:** The UI caps rendering at 1500 nodes for very large k-hop results.

## D13 — Verified live server
**Context:** Confirm the hosted path works, not just unit tests.
**Decision/result:** Served `data/derived/graph` and verified `/api/health`, `/`, `/static/app.js`,
`/static/vendor/cytoscape.min.js`, `/api/search?q=TP53`, and `POST /api/subnetwork` (TP53 ->
EP300/MYC/HDAC1/MDM2/JUN). 75 tests pass.
**Alternatives:** frontend build toolchain (rejected: needless complexity for this scope).

## D14 — Container-first delivery; graph is not baked
**Context:** Same artifact must run locally and on HF Spaces / Cloud Run with minimal setup.
**Decision:** One `Dockerfile` + `compose.yaml`. The image contains code only; the graph lives in
a mounted `/data` volume. `docker/entrypoint.sh` auto-builds it on first run if absent, then serves
on `$PORT` (default 8000), so Cloud Run/HF port injection works. Web assets are packaged into the
wheel via hatch `force-include` (`web` -> `hustring/web`), with `HUSTRING_WEB_DIR` as an override,
so the UI resolves in a non-editable install.
**Why:** Small image, no stale data, identical local/hosted behavior, fast cold start when `/data`
is prepopulated (e.g. a persisted volume or baked separately).
**Alternatives:** bake the graph + 105 MB cache into the image (bloat/staleness); separate frontend
container (overkill).
**Note:** Docker is not installed on the dev machine, so the image build itself is unverified; the
entrypoint and wheel contents were validated directly.
