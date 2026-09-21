#!/usr/bin/env sh
# Package a built graph directory as a release asset, with a checksum.
#
# Usage: scripts/package_graph.sh [GRAPH_DIR] [VERSION]
#   GRAPH_DIR  default: data/derived/graph
#   VERSION    default: today's date (YYYY.MM.DD)
set -eu

GRAPH_DIR="${1:-data/derived/graph}"
VERSION="${2:-$(date +%Y.%m.%d)}"

if [ ! -f "${GRAPH_DIR}/adjacency.npz" ]; then
  echo "No graph at '${GRAPH_DIR}'. Run 'hustring build-data' first." >&2
  exit 1
fi

OUT="dist/hustring-graph-${VERSION}.tar.gz"
mkdir -p dist
tar -czf "${OUT}" -C "$(dirname "${GRAPH_DIR}")" "$(basename "${GRAPH_DIR}")"

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "${OUT}" > "${OUT}.sha256"
  cat "${OUT}.sha256"
else
  shasum -a 256 "${OUT}" > "${OUT}.sha256"
  cat "${OUT}.sha256"
fi

echo "wrote ${OUT} (unpack into data/derived/graph or set HUSTRING_GRAPH)"
