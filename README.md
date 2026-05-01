# FreeIA Gateway

**6 free LLMs behind one OpenAI-compatible API. One-command Docker install.**

→ **[freeai.html](https://maxiaworld.app/freeai.html)** — full guide & provider list

---

## What it does

FreeIA Gateway aggregates 6 permanently free LLM providers behind a single `/v1/chat/completions` endpoint. Automatic fallback, daily quota tracking, and persistent memory via MemPalace.

**Priority chain:** Cerebras → Groq → Sambanova → Gemini → HuggingFace → Mistral

If a provider hits its daily limit or returns an error, the next one takes over silently.

---

## Install

**Prerequisites:** Docker Desktop + AnythingLLM (or any OpenAI-compatible client)

```bash
git clone https://github.com/MAXIAWORLD/freeiaforge
cd freeiaforge
cp backend/.env.example backend/.env
# Edit backend/.env with your free API keys (see below)
docker compose up --build
```

API runs at `http://localhost:8002`

---

## Free API keys

| Provider | Limits | Sign up |
|---|---|---|
| Cerebras | 5,000 req/day · 1M tokens | [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| Groq | 14,400 req/day · 500K tokens | [console.groq.com](https://console.groq.com) |
| Sambanova | 1,000 req/day · 1M tokens | [cloud.sambanova.ai](https://cloud.sambanova.ai) |
| Gemini | 1,500 req/day · 1M tokens | [aistudio.google.com](https://aistudio.google.com) |
| HuggingFace | 1,000 req/day · 500K tokens | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
| Mistral | 100 req/day · 200K tokens | [console.mistral.ai](https://console.mistral.ai) |

No credit card required on any of these.

---

## Connect AnythingLLM

Settings → LLM Preference → Generic OpenAI

```
Base URL : http://localhost:8002/v1
API Key  : freeai
Model    : freeai-gateway
```

---

## Features

- **Auto-fallback** — transparent failover across all 6 providers
- **Quota tracker** — SQLite, daily reset, never exceeds free limits
- **MemPalace memory** — persistent memory across conversations (170 tokens overhead, 96.6% recall)
- **OpenAI-compatible** — works with AnythingLLM, LibreChat, OpenCode, any OpenAI SDK

---

## License

MIT — [MAXIA](https://maxiaworld.app)
