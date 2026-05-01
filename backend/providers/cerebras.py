from providers.base import OpenAICompatibleProvider


class CerebrasProvider(OpenAICompatibleProvider):
    name = "cerebras"
    priority = 1
    base_url = "https://api.cerebras.ai/v1"
    default_model = "llama-3.3-70b"
