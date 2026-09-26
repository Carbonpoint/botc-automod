#!/bin/bash
# Publish the packaged Artist model to Hugging Face so botc-automod can download it.
# Usage: HF_TOKEN=hf_... scripts/publish_model.sh MODEL.gguf OWNER/REPO
# Needs a write token (https://huggingface.co/settings/tokens). Publishing makes the file public.
set -euo pipefail
GGUF=$1; REPO=$2
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
cp docs/hf/README.md "$tmp/README.md"
cp "$GGUF" "$tmp/botc-artist.gguf"
(cd "$tmp" && sha256sum botc-artist.gguf > SHA256SUMS)
uv run --with huggingface_hub python - "$tmp" "$REPO" <<'PY'
import sys
from huggingface_hub import HfApi
folder, repo = sys.argv[1], sys.argv[2]
api = HfApi()
api.create_repo(repo, repo_type="model", exist_ok=True)
api.upload_folder(folder_path=folder, repo_id=repo, repo_type="model",
                  commit_message="Publish the botc-automod Artist model")
print(f"PACKAGED_REPO = https://huggingface.co/{repo}/resolve/main")
PY
rm -rf "$tmp"
