#!/usr/bin/env sh
# Deploy this repository to a Hugging Face Docker Space.
#
# Usage:
#   HF_TOKEN=hf_xxx scripts/deploy_hf.sh <hf-user> <space-name>
#
# The Space must already exist (create one at https://huggingface.co/new-space
# with SDK = Docker). Files come from the current git HEAD; the Space's README
# (which carries the Hugging Face metadata) is supplied from
# deploy/huggingface/README.md.
set -eu

HF_USER="${1:?usage: deploy_hf.sh <hf-user> <space-name>}"
SPACE="${2:?usage: deploy_hf.sh <hf-user> <space-name>}"
: "${HF_TOKEN:?set HF_TOKEN to your Hugging Face access token (write scope)}"

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

git -C "${ROOT}" archive --format=tar HEAD | tar -x -C "${TMP}"
cp "${ROOT}/deploy/huggingface/README.md" "${TMP}/README.md"

git -C "${TMP}" init -q -b main
git -C "${TMP}" add -A
git -C "${TMP}" -c user.name="hustring-deploy" -c user.email="deploy@localhost" \
  commit -q -m "Deploy HuStringSearch to Hugging Face Spaces"
git -C "${TMP}" push --force \
  "https://${HF_USER}:${HF_TOKEN}@huggingface.co/spaces/${HF_USER}/${SPACE}" main

echo "Deployed -> https://huggingface.co/spaces/${HF_USER}/${SPACE}"
echo "Next: set the Space variable HUSTRING_GRAPH_URL to your graph Release asset URL."
