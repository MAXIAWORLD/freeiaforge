from __future__ import annotations

import httpx

from providers.base import OpenAICompatibleProvider

_DISCOVERY_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(OpenAICompatibleProvider):
    name = "gemini"
    priority = 4
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    default_model = "gemini-1.5-flash"

    async def discover_default_model(self, api_key: str) -> str:
        if not api_key:
            return self.default_model
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(_DISCOVERY_URL, params={"key": api_key})
                r.raise_for_status()
                payload = r.json()
        except (httpx.HTTPError, ValueError):
            return self.default_model

        if not isinstance(payload, dict):
            return self.default_model

        chat_models: list[str] = []
        for entry in payload.get("models", []):
            if not isinstance(entry, dict):
                continue
            methods = entry.get("supportedGenerationMethods") or []
            if "generateContent" not in methods:
                continue
            name = entry.get("name", "")
            if isinstance(name, str) and name.startswith("models/"):
                name = name[len("models/"):]
            if name and "embedding" not in name.lower():
                chat_models.append(name)

        if not chat_models:
            return self.default_model
        return self._select_best_model(chat_models)

    def _select_best_model(self, models: list[str]) -> str:
        if self.default_model in models:
            return self.default_model
        # Prefer recent flash variants for free tier (Gemini 2.x > 1.5)
        preference_order = ["2.5-flash", "2.0-flash", "flash", "pro"]
        for token in preference_order:
            for m in models:
                if token in m.lower() and "exp" not in m.lower():
                    return m
        return models[0]
