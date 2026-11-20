import json
import re
import aiohttp
from app.config import Settings

try:
    from json_repair import repair_json  # type: ignore
except ImportError:
    repair_json = None


def _extract_json_text(raw: str) -> str:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _normalize_payload(data: object) -> dict:
    if isinstance(data, list):
        return {"files": data}
    if not isinstance(data, dict):
        return {"files": []}

    if isinstance(data.get("files"), list):
        return data

    for alt_key in ("project_files", "code_files", "items", "output"):
        if isinstance(data.get(alt_key), list):
            normalized = dict(data)
            normalized["files"] = data[alt_key]
            return normalized

    return data


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        payload = {
            "model": self.settings.ollama_model,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.settings.ollama_temperature,
                "num_ctx": self.settings.ollama_num_ctx,
                "num_predict": self.settings.ollama_num_predict,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        timeout = aiohttp.ClientTimeout(total=self.settings.ollama_timeout_seconds)
        url = f"{self.settings.ollama_base_url}/api/chat"

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()

        content = data.get("message", {}).get("content", "")
        if not content or not str(content).strip():
            raise ValueError("Empty response received from Ollama")

        candidate = _extract_json_text(str(content))

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            if repair_json is None:
                raise
            repaired = repair_json(candidate)
            parsed = json.loads(repaired)

        return _normalize_payload(parsed)
