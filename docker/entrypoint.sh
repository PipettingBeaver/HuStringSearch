#!/bin/sh
set -eu

GRAPH_DIR="${HUSTRING_GRAPH:-/data/graph}"
CACHE_DIR="${HUSTRING_CACHE:-/data/cache}"
PORT="${PORT:-8000}"

if [ ! -f "${GRAPH_DIR}/adjacency.npz" ]; then
  if [ "${HUSTRING_AUTO_BUILD:-1}" = "1" ]; then
    echo "No graph at ${GRAPH_DIR}; building it now (first run, ~1-2 min)."
    hustring build-data --output "${GRAPH_DIR}" --cache "${CACHE_DIR}"
  else
    echo "No graph at ${GRAPH_DIR} and HUSTRING_AUTO_BUILD=${HUSTRING_AUTO_BUILD:-}." >&2
  fi
fi

exec hustring serve --graph "${GRAPH_DIR}" --host 0.0.0.0 --port "${PORT}"
