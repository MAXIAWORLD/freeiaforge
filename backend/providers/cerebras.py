from providers.base import OpenAICompatibleProvider


class CerebrasProvider(OpenAICompatibleProvider):
    name = "cerebras"
    priority = 1
    base_url = "https://api.cerebras.ai/v1"
    default_model = "llama-3.3-70b"

    def _select_best_model(self, models: list[str]) -> str:
        if self.default_model in models:
            return self.default_model
        # Prefer Llama 70B+ instruct variants
        for size in ("405b", "120b", "70b"):
            for m in models:
                if isinstance(m, str) and size in m.lower() and "llama" in m.lower():
                    return m
        # Then any 70B+ model
        for size in ("405b", "120b", "70b"):
            for m in models:
                if isinstance(m, str) and size in m.lower():
                    return m
        return models[0]
