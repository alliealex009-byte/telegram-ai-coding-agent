#!/usr/bin/env bash
set -euo pipefail
systemctl is-active ollama
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null
ollama list | grep -F 'gemma3:4b'
docker info >/dev/null
echo 'Ollama, Gemma 3 4B and Docker checks passed.'
