from providers.base import OpenAICompatibleProvider


class HuggingFaceProvider(OpenAICompatibleProvider):
    name = "huggingface"
    priority = 5
    base_url = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.1-70B-Instruct/v1"
    default_model = "meta-llama/Llama-3.1-70B-Instruct"

    async def discover_default_model(self, api_key: str) -> str:
        # HuggingFace Inference API doesn't expose a standard /models listing
        # at the per-model endpoint URL we use. Keep hardcoded.
        return self.default_model
