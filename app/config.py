from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _parse_allowed_users(raw: str) -> set[int]:
    users: set[int] = set()
    for part in raw.split(","):
        item = part.strip()
        if item.isdigit():
            users.add(int(item))
    return users


@dataclass(frozen=True)
class Settings:
    bot_token: str
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    ollama_temperature: float
    ollama_num_ctx: int
    ollama_num_predict: int
    allowed_user_ids: set[int]
    workspace_root: Path
    workspace_ttl_hours: int
    max_project_files: int
    max_file_bytes: int
    max_total_project_bytes: int
    max_repair_rounds: int
    max_concurrent_jobs: int
    max_job_seconds: int
    max_zip_bytes: int
    sandbox_image: str
    sandbox_memory: str
    sandbox_cpus: float
    sandbox_pids_limit: int


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "PUT_TELEGRAM_BOT_TOKEN_HERE":
        raise ValueError("BOT_TOKEN is not configured in .env")

    ws_root = Path(os.getenv("WORKSPACE_ROOT", "/opt/telegram-ai-coding-agent/workspaces")).resolve()
    ws_root.mkdir(parents=True, exist_ok=True)

    return Settings(
        bot_token=token,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "hf.co/Andycurrent/gemma-3-4b-it-uncensored-v2-GGUF:Q4_K_M").strip(),
        ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "240")),
        ollama_temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.25")),
        ollama_num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
        ollama_num_predict=int(os.getenv("OLLAMA_NUM_PREDICT", "8192")),
        allowed_user_ids=_parse_allowed_users(os.getenv("ALLOWED_USER_IDS", "")),
        workspace_root=ws_root,
        workspace_ttl_hours=int(os.getenv("WORKSPACE_TTL_HOURS", "48")),
        max_project_files=int(os.getenv("MAX_PROJECT_FILES", "40")),
        max_file_bytes=int(os.getenv("MAX_FILE_BYTES", "150000")),
        max_total_project_bytes=int(os.getenv("MAX_TOTAL_PROJECT_BYTES", "2500000")),
        max_repair_rounds=int(os.getenv("MAX_REPAIR_ROUNDS", "2")),
        max_concurrent_jobs=int(os.getenv("MAX_CONCURRENT_JOBS", "1")),
        max_job_seconds=int(os.getenv("MAX_JOB_SECONDS", "240")),
        max_zip_bytes=int(os.getenv("MAX_ZIP_BYTES", "45000000")),
        sandbox_image=os.getenv("SANDBOX_IMAGE", "ria-code-sandbox:latest").strip(),
        sandbox_memory=os.getenv("SANDBOX_MEMORY", "768m").strip(),
        sandbox_cpus=float(os.getenv("SANDBOX_CPUS", "1.0")),
        sandbox_pids_limit=int(os.getenv("SANDBOX_PIDS_LIMIT", "128")),
    )
