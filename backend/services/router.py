from __future__ import annotations
import logging
from core.models import ChatRequest
from providers.base import Provider, ProviderResult, ProviderError
from services.quota import QuotaService

logger = logging.getLogger(__name__)


class ProviderRouter:
    def __init__(
        self,
        providers: list[Provider],
        quota: QuotaService,
        api_keys: dict[str, str],
    ) -> None:
        self._providers = sorted(providers, key=lambda p: p.priority)
        self._quota = quota
        self._api_keys = api_keys

    async def route(self, request: ChatRequest) -> ProviderResult:
        for provider in self._providers:
            key = self._api_keys.get(provider.name, "")
            if not key:
                logger.debug("Skipping %s: no API key configured", provider.name)
                continue
            if not await self._quota.is_available(provider.name):
                logger.info("Skipping %s: quota exhausted", provider.name)
                continue
            try:
                result = await provider.complete(request, key)
                await self._quota.record_usage(
                    provider.name, requests=1, tokens=result.tokens_used
                )
                logger.info(
                    "Served by %s (%d tokens)", provider.name, result.tokens_used
                )
                return result
            except ProviderError as e:
                logger.warning("Provider %s failed (%s), trying next", provider.name, e)
                continue

        raise RuntimeError("All providers exhausted")

    async def get_provider_statuses(self) -> list:

        return [await self._quota.get_status(p.name) for p in self._providers]
