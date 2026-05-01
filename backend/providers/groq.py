from providers.base import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    priority = 2
    base_url = "https://api.groq.com/openai/v1"
    default_model = "llama-3.3-70b-versatile"
