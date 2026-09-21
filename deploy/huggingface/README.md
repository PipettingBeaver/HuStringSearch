---
title: HuStringSearch
emoji: 🧬
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# HuStringSearch

Interactive target-centered subnetworks from merged protein interactomes.

This Space runs the HuStringSearch Docker image. Enter a gene (for example `TP53`), choose a
selection mode, and explore the proteins most closely connected to it through a Random Walk
with Restart over a merged **HuRI + STRING** human network.

- Upstream repository: <https://github.com/PipettingBeaver/HuStringSearch>
- On first start the container fetches the prebuilt graph from the repository's GitHub Release
  when `HUSTRING_GRAPH_URL` is set (see the Space variables), otherwise it builds the graph
  in-place.

MIT licensed. Built by PipettingBeaver.
