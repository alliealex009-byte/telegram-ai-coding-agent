import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

def iv(k, d):
    try: return int(os.getenv(k, d))
    except (ValueError, TypeError): return int(d)

def fv(k, d):
    try: return float(os.getenv(k, d))
    except (ValueError, TypeError): return float(d)

@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    ollama_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model: str = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    timeout: int = iv("OLLAMA_TIMEOUT_SECONDS", 240)
    temperature: float = fv("OLLAMA_TEMPERATURE", 0.25)
    num_ctx: int = iv("OLLAMA_NUM_CTX", 8192)
    num_predict: int = iv("OLLAMA_NUM_PREDICT", 8192)
    allow_ids: frozenset = frozenset(int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip().isdigit())
    workspace: Path = Path(os.getenv("WORKSPACE_ROOT", "./workspaces")).resolve()
    ttl: int = iv("WORKSPACE_TTL_HOURS", 48)
    max_files: int = iv("MAX_PROJECT_FILES", 40)
    max_file_bytes: int = iv("MAX_FILE_BYTES", 150000)
    max_total_bytes: int = iv("MAX_TOTAL_PROJECT_BYTES", 2500000)
    repairs: int = iv("MAX_REPAIR_ROUNDS", 2)
    concurrency: int = iv("MAX_CONCURRENT_JOBS", 1)
    job_seconds: int = iv("MAX_JOB_SECONDS", 240)
    max_zip: int = iv("MAX_ZIP_BYTES", 45000000)
    image: str = os.getenv("SANDBOX_IMAGE", "ria-code-sandbox:latest")
    memory: str = os.getenv("SANDBOX_MEMORY", "768m")
    cpus: float = fv("SANDBOX_CPUS", 1.0)
    pids: int = iv("SANDBOX_PIDS_LIMIT", 128)

cfg = Settings()
if not cfg.bot_token or cfg.bot_token == "PUT_TELEGRAM_BOT_TOKEN_HERE":
    raise RuntimeError("Set BOT_TOKEN in .env")
