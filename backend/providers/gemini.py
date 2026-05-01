from __future__ import annotations
from providers.base import OpenAICompatibleProvider


class GeminiProvider(OpenAICompatibleProvider):
    name = "gemini"
    priority = 4
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    default_model = "gemini-1.5-flash"
