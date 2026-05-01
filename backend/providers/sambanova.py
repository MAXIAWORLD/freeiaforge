from providers.base import OpenAICompatibleProvider


class SambanovaProvider(OpenAICompatibleProvider):
    name = "sambanova"
    priority = 3
    base_url = "https://api.sambanova.ai/v1"
    default_model = "Meta-Llama-3.3-70B-Instruct"
