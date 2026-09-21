#!/bin/sh
set -eu

GRAPH_DIR="${HUSTRING_GRAPH:-/data/graph}"
CACHE_DIR="${HUSTRING_CACHE:-/data/cache}"

if [ -n "${PORT:-}" ]; then
  BIND_PORT="${PORT}"
elif [ -n "${SPACE_ID:-}" ]; then
  BIND_PORT="7860"
else
  BIND_PORT="8000"
fi

if [ ! -f "${GRAPH_DIR}/adjacency.npz" ]; then
  if [ -n "${HUSTRING_GRAPH_URL:-}" ]; then
    echo "Fetching prebuilt graph from ${HUSTRING_GRAPH_URL}"
    hustring fetch-graph --url "${HUSTRING_GRAPH_URL}" --output "${GRAPH_DIR}"
  elif [ "${HUSTRING_AUTO_BUILD:-1}" = "1" ]; then
    echo "No graph at ${GRAPH_DIR}; building it now (first run, ~1-2 min)."
    hustring build-data --output "${GRAPH_DIR}" --cache "${CACHE_DIR}"
  else
    echo "No graph at ${GRAPH_DIR} and HUSTRING_AUTO_BUILD=${HUSTRING_AUTO_BUILD:-}." >&2
  fi
fi

exec hustring serve --graph "${GRAPH_DIR}" --host 0.0.0.0 --port "${BIND_PORT}"
