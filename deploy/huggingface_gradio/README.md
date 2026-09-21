---
title: HuStringSearch
emoji: 🧬
colorFrom: indigo
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
license: mit
---

# HuStringSearch

Interactive target-centered subnetworks from merged protein interactomes.

Enter a gene (for example `TP53`), choose a selection mode, and explore the proteins most
closely connected to it through a Random Walk with Restart over a merged **HuRI + STRING**
human network. The interactive graph and ranked partner table update together.

- Upstream repository: <https://github.com/PipettingBeaver/HuStringSearch>
- The graph is fetched from the repository's GitHub Release when the Space variable
  `HUSTRING_GRAPH_URL` is set, otherwise it is built on first use.

MIT licensed. Built by PipettingBeaver.
