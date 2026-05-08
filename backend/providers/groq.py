from providers.base import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    priority = 2
    base_url = "https://api.groq.com/openai/v1"
    default_model = "llama-3.3-70b-versatile"

    def _select_best_model(self, models: list[str]) -> str:
        if self.default_model in models:
            return self.default_model
        # Prefer Llama 70B+ versatile / instruct
        for token in ("70b-versatile", "70b-instruct", "405b", "70b"):
            for m in models:
                if isinstance(m, str) and token in m.lower() and "llama" in m.lower():
                    return m
        return models[0]
