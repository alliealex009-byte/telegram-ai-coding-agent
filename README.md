# Telegram AI Coding Agent

Private-DM coding agent using local Ollama `gemma3:4b`. It plans a project, generates UTF-8 source files, checks Python syntax in a restricted Docker container, attempts bounded repairs, then sends a ZIP.

## Requirements
Ubuntu 22.04+, Python 3.10+, Docker, Ollama with `gemma3:4b`, and a Telegram bot token.

## Install
Copy this folder to `/opt/telegram-ai-coding-agent`, then:
```bash
cd /opt/telegram-ai-coding-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
nano .env
docker build -t ria-code-sandbox:latest ./sandbox
.venv/bin/python -m app.main
```
Set `BOT_TOKEN` and your numeric Telegram ID in `ALLOWED_USER_IDS`.

## Commands
`/start`, `/help`, `/new`, `/status`, `/cancel`, `/about`. Send a detailed project description in a private DM to start a build.

## Security
The sandbox has no network, a read-only root filesystem, dropped Linux capabilities, resource limits, and only the current project workspace mounted. It runs Python syntax checks; this is not a full functional or security audit. Review generated code before deploying it.

**Critical Docker warning:** Access to a rootful Docker socket is effectively host-root access. For production, configure a dedicated rootless Docker daemon and point `DOCKER_HOST` to it. Never expose Docker API over TCP. Do not add the bot account to the rootful `docker` group casually. Keep Ollama and MongoDB private; this project does not need MongoDB. Do not modify existing bot containers or services.
