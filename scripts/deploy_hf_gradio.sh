#!/usr/bin/env sh
# Deploy the Gradio app to a Hugging Face Gradio Space.
#
# Usage:
#   HF_TOKEN=hf_xxx scripts/deploy_hf_gradio.sh <hf-user> <space-name>
#
# The Space must already exist (SDK = Gradio). Only three small files are pushed:
# app.py, requirements.txt, and the Space README (which carries the HF metadata
# and configures installing the package from GitHub).
set -eu

HF_USER="${1:?usage: deploy_hf_gradio.sh <hf-user> <space-name>}"
SPACE="${2:?usage: deploy_hf_gradio.sh <hf-user> <space-name>}"
: "${HF_TOKEN:?set HF_TOKEN to your Hugging Face access token (write scope)}"

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SRC="${ROOT}/deploy/huggingface_gradio"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

cp "${SRC}/app.py" "${SRC}/requirements.txt" "${SRC}/README.md" "${TMP}/"

git -C "${TMP}" init -q -b main
git -C "${TMP}" add -A
git -C "${TMP}" -c user.name="hustring-deploy" -c user.email="deploy@localhost" \
  commit -q -m "Deploy HuStringSearch Gradio app"
git -C "${TMP}" push --force \
  "https://${HF_USER}:${HF_TOKEN}@huggingface.co/spaces/${HF_USER}/${SPACE}" main

echo "Deployed -> https://huggingface.co/spaces/${HF_USER}/${SPACE}"
echo "Next: set the Space variable HUSTRING_GRAPH_URL to your graph Release asset URL."
