from providers.base import OpenAICompatibleProvider


class MistralProvider(OpenAICompatibleProvider):
    name = "mistral"
    priority = 6
    base_url = "https://api.mistral.ai/v1"
    default_model = "mistral-large-latest"
