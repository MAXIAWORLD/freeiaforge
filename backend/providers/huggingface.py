from providers.base import OpenAICompatibleProvider


class HuggingFaceProvider(OpenAICompatibleProvider):
    name = "huggingface"
    priority = 5
    base_url = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.1-70B-Instruct/v1"
    default_model = "meta-llama/Llama-3.1-70B-Instruct"
