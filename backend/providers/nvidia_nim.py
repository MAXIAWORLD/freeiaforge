from __future__ import annotations

from providers.base import OpenAICompatibleProvider


class NvidiaProvider(OpenAICompatibleProvider):
    name = "nvidia_nim"
    priority = 6
    base_url = "https://integrate.api.nvidia.com/v1"
    default_model = "meta/llama-3.3-70b-instruct"

    def _select_best_model(self, models: list[str]) -> str:
        if self.default_model in models:
            return self.default_model
        for token in ("llama-3.3-70b", "llama-3.1-70b", "70b"):
            for m in models:
                if isinstance(m, str) and token in m.lower():
                    return m
        return models[0]
