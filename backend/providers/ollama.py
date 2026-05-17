from __future__ import annotations

from providers.base import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Local Ollama — zero-key fallback, priority 9 (last resort).

    Uses the OpenAI-compatible endpoint exposed by Ollama (/v1/chat/completions).
    No API key required — pass the sentinel "local" so the router doesn't skip it.
    ConnectError is raised immediately (not after 30s) when Ollama isn't running.
    """

    name = "ollama"
    priority = 10

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
    ) -> None:
        self.base_url = f"{base_url.rstrip('/')}/v1"
        self.default_model = model
