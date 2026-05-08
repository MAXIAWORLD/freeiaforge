# FreeIA Gateway

**7 free LLMs + local Ollama behind one OpenAI-compatible API. One-command Docker install.**

→ **[freeai.html](https://maxiaworld.app/freeai.html)** — full guide & provider list

---

## What it does

FreeIA Gateway aggregates 7 cloud LLM providers + local Ollama behind a single `/v1/chat/completions` endpoint. Automatic fallback, daily quota tracking, smart routing, semantic cache, and custom provider order.

**Default priority chain:** Cerebras → Groq → Sambanova → Gemini → HuggingFace → Mistral → OpenRouter → Ollama

If a provider hits its daily limit or returns an error, the next one takes over silently.

---

## Install

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) + [Git](https://git-scm.com/download/win) (Windows). Any OpenAI-compatible client works (AnythingLLM, LibreChat, Cursor…).

### Quick start (recommended)

```bash
git clone https://github.com/MAXIAWORLD/freeiaforge
cd freeiaforge
```

Then run the launcher script that handles `.env` creation for you:

- **Windows (PowerShell):** `.\start.ps1`
- **Mac / Linux:** `./start.sh`

The script creates `backend/.env` from `.env.example` on first run, prompts you to paste at least one API key (Cerebras is the easiest — get a free key at https://cloud.cerebras.ai), then starts Docker. API runs at `http://localhost:8002`.

### Manual install

If you prefer not to use the launcher:

```bash
git clone https://github.com/MAXIAWORLD/freeiaforge
cd freeiaforge
cp backend/.env.example backend/.env   # Windows: copy backend\.env.example backend\.env
# Edit backend/.env and paste your API key(s)
docker compose up --build
```

### Docker Hub image

```bash
docker pull maxiaworld/freeiaforge:latest
```

Use it in your own `docker-compose.yml`:
```yaml
services:
  freeiaforge:
    image: maxiaworld/freeiaforge:latest
    ports:
      - "8002:8002"
    env_file:
      - path: backend/.env
        required: false
    volumes:
      - freeai_data:/app/data
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped

volumes:
  freeai_data:
```

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
| OpenRouter | 200 req/day · 33 free models | [openrouter.ai](https://openrouter.ai) |

No credit card required on any of these. All optional — one key is enough to start.

---

## Ollama — zero-key local fallback

No API key needed. Requires [Ollama](https://ollama.com) running on your host machine.

Set in `backend/.env`:
```env
OLLAMA_BASE_URL=http://host.docker.internal:11434   # inside Docker
OLLAMA_MODEL=llama3.2
```

If Ollama isn't running, the gateway fails fast (ConnectError) and falls back gracefully. When Ollama is running, it acts as priority 9 — last resort after all cloud providers.

---

## Connect AnythingLLM

Settings → LLM Preference → Generic OpenAI

```
Base URL : http://localhost:8002/v1
API Key  : freeai
Model    : freeai-gateway
```

---

## Connect via Anthropic SDK

FreeIA Gateway exposes an Anthropic-compatible endpoint at `POST /v1/messages`.  
Point any Anthropic SDK client at `http://localhost:8002` and it works out of the box.

```python
import anthropic

client = anthropic.Anthropic(
    api_key="freeai",                      # any non-empty string
    base_url="http://localhost:8002",
)

message = client.messages.create(
    model="claude-3-5-sonnet-20241022",    # ignored — auto-routed to best free LLM
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(message.content[0].text)
```

**Model hints via Anthropic SDK** — send a known provider name as the model:

```python
# Force Groq
client.messages.create(model="groq", ...)

# Force Ollama (local)
client.messages.create(model="ollama", ...)
```

**Streaming** is supported: pass `stream=True` to receive SSE chunks.

---

## Connect via MCP (Claude Code, Cursor, Cline)

FreeIA Gateway exposes a native MCP server — plug it directly into any MCP-compatible agent.

**Claude Code** — add to `~/.claude/mcp_servers.json`:

```json
{
  "freeai-gateway": {
    "type": "http",
    "url": "http://localhost:8002/mcp"
  }
}
```

**Cursor / Cline** — same format, adapted to their MCP config file.

Available MCP tools once connected:

| Tool | Description |
|---|---|
| `chat` | Send messages to the best available free LLM. Supports model hints. |
| `providers_status` | Get quota, errors, and availability for all providers. |

Server manifest auto-discoverable at `GET http://localhost:8002/mcp`.

---

## Model hints

Force a specific provider or model by setting the `model` field:

```json
{ "model": "groq", "messages": [...] }
```

| Hint | Routes to |
|---|---|
| `auto` (default) | Best available provider by priority |
| `cerebras` | Cerebras — fastest (Llama 3.3 70B) |
| `groq` | Groq — 300+ tok/s (Llama 3.3 70B) |
| `sambanova` | Sambanova — default Llama 70B |
| `gemini` | Gemini 1.5 Flash — vision + 1M context |
| `openrouter` | OpenRouter free — auto-selects among 33 models |
| `ollama` | Local Ollama — no API key, any installed model |

**Sambanova extended models** — pass the full model name:

```json
{ "model": "Llama-3.1-405B-Instruct", "messages": [...] }
{ "model": "Qwen2.5-72B-Instruct", "messages": [...] }
```

---

## Custom provider order

Override the default priority chain in `backend/.env`:

```env
PROVIDER_ORDER=groq,gemini,ollama
```

- Providers listed first are tried first (in order)
- Unlisted providers are appended at the end sorted by default priority
- Unknown names are silently ignored
- Providers with no API key are always skipped

---

## Smart routing

The gateway applies signal-based routing rules automatically — no NLP, zero latency overhead:

- **Long context (>24k chars)** — Cerebras is skipped (hard cap at 8192 tokens)
- **Vision requests** — routed to Gemini only (only multimodal provider)
- **Explicit model hint** — routes to that provider exclusively, returns 503 if unavailable

---

## Features

- **Auto-fallback** — transparent failover across all 8 providers (7 cloud + Ollama)
- **Quota tracker** — SQLite, daily reset, never exceeds free limits
- **Semantic cache** — SHA-256 on normalized messages, 1h TTL, saves quota on repeated requests
- **Smart routing** — context length, vision detection, explicit model hints
- **Custom order** — `PROVIDER_ORDER` env var to reorder providers
- **Provider status** — `GET /v1/providers/status` → quota, last error, consecutive failures
- **MCP server** — native MCP protocol, zero extra dependency
- **MemPalace memory** — persistent memory across conversations (170 tokens overhead, 96.6% recall)
- **OpenAI-compatible** — works with AnythingLLM, LibreChat, OpenCode, any OpenAI SDK
- **Anthropic-compatible** — `POST /v1/messages` accepts Anthropic SDK requests natively
- **Auto .env** — `backend/.env` created automatically on first Docker start

---

## License

MIT — [MAXIA](https://maxiaworld.app)
