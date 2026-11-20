import aiohttp, asyncio, json
from app.config import cfg

class LLM:
    async def chat(self, messages, json_mode=False):
        payload = {"model": cfg.model, "messages": messages, "stream": False,
                   "options": {"temperature": cfg.temperature, "num_ctx": cfg.num_ctx,
                               "num_predict": cfg.num_predict}}
        if json_mode: payload["format"] = "json"
        timeout = aiohttp.ClientTimeout(total=cfg.timeout)
        error = None
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as s:
                    async with s.post(cfg.ollama_url + "/api/chat", json=payload) as r:
                        body = await r.text()
                        if r.status != 200: raise RuntimeError(f"Ollama HTTP {r.status}: {body[:400]}")
                        result = json.loads(body).get("message", {}).get("content", "")
                        if not result.strip(): raise RuntimeError("Empty Ollama response")
                        return result
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RuntimeError) as e:
                error = e
                if attempt == 0: await asyncio.sleep(2)
        raise RuntimeError(f"Ollama request failed: {error}")
