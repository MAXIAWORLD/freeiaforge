# FreeIA Gateway

**9 free LLMs + local Ollama behind one OpenAI-compatible API. One-command Docker install.**

→ **[freeai.html](https://maxiaworld.app/freeai.html)** — full guide & provider list

---

## What it does

FreeIA Gateway aggregates 9 cloud LLM providers + local Ollama behind a single `/v1/chat/completions` endpoint. Automatic fallback, daily quota tracking, smart task-type routing, circuit breaker, semantic cache, and custom provider order.

**Default priority chain:** Cerebras → Groq → Sambanova → Gemini → HuggingFace → Mistral → OpenRouter → NVIDIA NIM → Cloudflare → Ollama

If a provider hits its daily limit or returns an error, the next one takes over silently.

---

## Install

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) + [Git](https://git-scm.com/download/win) (Windows). Any OpenAI-compatible client works (AnythingLLM, LibreChat, Cursor…).

### Quick start (recommended)

```bash
git clone https://github.com/MAXIAWORLD/freeiaforge
cd freeiaforge
```

Run the **setup wizard** to configure your API keys interactively, then launch:

- **Windows:** `setup.bat` — lists all providers with signup links, asks for keys, detects Ollama, writes `.env`, then starts Docker
- **Mac / Linux:** `./setup.sh` — same, POSIX-compatible

Or use the simple launcher (no wizard, just starts Docker):

- **Windows:** `start.bat` (or `.\start.ps1` in PowerShell)
- **Mac / Linux:** `./start.sh`

API runs at `http://localhost:8002` after Docker starts.

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
| Cerebras | 1M tokens/day · 30 RPM | [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| Groq | 14,400 req/day · 30 RPM | [console.groq.com](https://console.groq.com) |
| Sambanova | free tier permanent | [cloud.sambanova.ai](https://cloud.sambanova.ai) |
| Gemini | 1,500 req/day · 1M ctx | [aistudio.google.com](https://aistudio.google.com) |
| HuggingFace | 1,000 req/day | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
| Mistral | 100 req/day | [console.mistral.ai](https://console.mistral.ai) |
| OpenRouter | 30+ free models | [openrouter.ai](https://openrouter.ai) |
| NVIDIA NIM | 40 RPM · 100+ models | [build.nvidia.com](https://build.nvidia.com) |
| Cloudflare Workers AI | 10,000 req/day | [dash.cloudflare.com](https://dash.cloudflare.com) |

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

The gateway infers the task type from the request content and routes accordingly — no NLP model, zero latency overhead:

| Task | Detection | Providers tried |
|---|---|---|
| `vision` | `image_url` in message content | Gemini, OpenRouter |
| `long_context` | message > 24k chars | Gemini only (1M ctx) |
| `code` | ` ``` ` block or keywords (`def`, `bug`, `refactor`…) | Groq, Cerebras first |
| `default` | everything else | quota-sorted order |

- **Circuit breaker** — 3-state (CLOSED → OPEN → HALF_OPEN). Failing provider is skipped for 5 min then probed once.
- **Explicit model hint** — routes to that provider exclusively, returns 503 if unavailable.
- Task type is exposed in the `X-FreeAI-Task` response header.

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

## Hermes Agent (NousResearch)

FreeIA Gateway is fully compatible with [Hermes Agent](https://github.com/NousResearch/hermes-function-calling) and any OpenAI-compatible agent framework.

Point your agent at `http://localhost:8002`:

```python
# LangChain / LlamaIndex / Hermes
llm = ChatOpenAI(
    base_url="http://localhost:8002/v1",
    api_key="freeai",
    model="auto",  # or any provider hint
)
```

```yaml
# AnythingLLM / LibreChat / Open WebUI
LLM_BASE_URL: http://localhost:8002/v1
LLM_API_KEY: freeai
```

The `/v1/chat/completions` endpoint is OpenAI-spec compliant — tool calls, streaming, and function definitions all work.

---

## Dashboard

`GET http://localhost:8002/` — HTML dashboard with provider circuit status, daily quota usage, and today's request breakdown by task type. Auto-refreshes every 30 seconds.

`GET http://localhost:8002/v1/quota` — same data as JSON.

---

## Telemetry (opt-out)

FreeIA Gateway sends a minimal anonymous ping at startup (`version`, `os`, `providers_count`, `ollama`). To disable:

```env
FREEAI_TELEMETRY=0
```

---

## License

MIT — [MAXIA](https://maxiaworld.app)
