from providers.base import OpenAICompatibleProvider


class MistralProvider(OpenAICompatibleProvider):
    name = "mistral"
    priority = 9
    base_url = "https://api.mistral.ai/v1"
    default_model = "mistral-large-latest"

    def _select_best_model(self, models: list[str]) -> str:
        if self.default_model in models:
            return self.default_model
        # Prefer "-latest" aliases (auto-tracking) > size-tagged models
        latest = [m for m in models if isinstance(m, str) and m.endswith("-latest")]
        if latest:
            for token in ("large", "medium", "small"):
                for m in latest:
                    if token in m.lower():
                        return m
            return latest[0]
        return models[0]
