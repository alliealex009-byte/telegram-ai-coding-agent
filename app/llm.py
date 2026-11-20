import json
import aiohttp
from app.config import Settings


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
        if not content:
            raise ValueError("Empty response received from Ollama")

        return json.loads(content)
