#!/usr/bin/env bash
set -euo pipefail
cd /opt/telegram-ai-coding-agent
git pull --ff-only
.venv/bin/pip install -r requirements.txt
docker build -t ria-code-sandbox:latest ./sandbox
sudo systemctl restart ria-code-agent
sudo systemctl --no-pager status ria-code-agent
