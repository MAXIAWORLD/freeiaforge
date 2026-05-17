from __future__ import annotations

from providers.base import OpenAICompatibleProvider


class CloudflareProvider(OpenAICompatibleProvider):
    name = "cloudflare"
    priority = 8
    default_model = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

    def __init__(self, account_id: str) -> None:
        self.base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
        )

    def _select_best_model(self, models: list[str]) -> str:
        if self.default_model in models:
            return self.default_model
        for m in models:
            if isinstance(m, str) and "70b" in m.lower() and "@cf/" in m:
                return m
        return models[0] if models else self.default_model
