#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
CONFIGURED_MODEL=""

if [[ -f "${ENV_FILE}" ]]; then
  CONFIGURED_MODEL="$(grep -E '^OLLAMA_MODEL=' "${ENV_FILE}" | tail -n1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | xargs)"
fi

MODEL_TO_CHECK="${CONFIGURED_MODEL:-hf.co/Andycurrent/gemma-3-4b-it-uncensored-v2-GGUF:Q4_K_M}"

systemctl is-active ollama >/dev/null
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null
ollama list | awk 'NR>1 {print $1}' | grep -Fx "${MODEL_TO_CHECK}" >/dev/null
docker info >/dev/null

echo "Ollama, model (${MODEL_TO_CHECK}), and Docker checks passed."
