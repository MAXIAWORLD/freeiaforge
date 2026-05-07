# HANDOFF — FreeIA Gateway

**Date :** 2026-05-07
**État :** v0.3.0 livré — 111 tests, commit à faire

---

## Ce qui est fait (v0.3.0)

### Nouvelles features v0.3.0

**entrypoint.sh (auto-copie .env)**
- `backend/entrypoint.sh` : `[ -f /app/.env ] || cp /app/.env.example /app/.env` puis `exec "$@"`
- `Dockerfile` : `ENTRYPOINT ["sh", "entrypoint.sh"]` + `CMD [...]` conservé
- `docker-compose.yml` : `extra_hosts: host.docker.internal:host-gateway` (Linux compat)
- Résultat : `cp backend/.env.example backend/.env` n'est plus requis — auto au premier `docker compose up`

**Ollama provider (priority 9, zero-key)**
- `providers/ollama.py` : `OllamaProvider(base_url, model)` — instance attrs pour base_url/model dynamiques
- Sentinel `api_keys["ollama"] = "local"` → router ne le skipe jamais
- `OLLAMA_BASE_URL=http://host.docker.internal:11434` (défaut dans .env.example pour Docker)
- `OLLAMA_MODEL=llama3.2` configurable
- Config : `ollama_base_url`, `ollama_model`, `ollama_daily_requests`, `ollama_daily_tokens`
- ConnectError levée immédiatement (pas de timeout) si Ollama non démarré → fallback transparent

**PROVIDER_ORDER (ordre custom)**
- `PROVIDER_ORDER=groq,gemini,ollama` dans `.env` → override l'ordre par défaut
- `ProviderRouter.__init__(provider_order: list[str] | None)` + `_apply_order()` statique
- Logique : providers listés en premier (dans l'ordre), reste appendé par priorité
- Noms inconnus silencieusement ignorés
- `main.py` : parse `settings.provider_order` → liste → passe à ProviderRouter

**Mise à jour _KNOWN_PROVIDERS** : "ollama" ajouté → model hint `model="ollama"` fonctionne

---

## Ce qui était fait (v0.2.0)

### Backend v0.2.0 (freeiaforge/backend/)

**7 providers (vs 6 en v0.1.0)**
- Cerebras → Groq → Sambanova → Gemini → HuggingFace → Mistral → **OpenRouter** (priority=7)
- OpenRouter : `openrouter/free` = auto-router parmi 33 modèles gratuits
- Headers custom OpenRouter : `HTTP-Referer: https://maxiaworld.app`, `X-Title: FreeIA Gateway`

**Sambanova : 3 modèles disponibles via model hint**
- `Meta-Llama-3.3-70B-Instruct` (défaut)
- `Llama-3.1-405B-Instruct`
- `Qwen2.5-72B-Instruct`
- Sélection via `request.model` (model hint explicite)

**Signal routing (services/router.py)**
- Règle 1 : contexte >24k chars → skip Cerebras (cap 8192 tokens)
- Règle 2 : message avec image → Gemini uniquement (multimodal)
- Règle 3 : model hint provider connu → provider unique, 503 si indisponible
- `Message.content` supporte désormais `str | list[dict]` pour multimodal

**ProviderStatus enrichi (GET /v1/providers + alias /v1/providers/status)**
- Champs ajoutés : `last_error`, `last_used_at`, `consecutive_errors`
- Tracking in-memory sur ProviderRouter (reset au restart)

**Semantic cache SQLite (services/cache.py)**
- Hash SHA-256 sur messages normalisés (lowercase + collapse whitespace)
- TTL configurable via `CACHE_TTL_SECONDS` (défaut 3600s)
- Activé/désactivé via `CACHE_ENABLED` (défaut True)
- Store fire-and-forget via `asyncio.create_task()`

**MCP server (routes/mcp.py)**
- `GET /mcp` → manifest JSON (tools: chat, providers_status)
- `POST /mcp/tools/chat` → route vers provider, retourne format MCP
- `POST /mcp/tools/providers_status` → statuses JSON
- Protocole JSON pur, zéro SDK externe

### Tests
- 89 tests, 90% coverage global
- Nouveaux : `test_sambanova_provider.py`, `test_openrouter_provider.py`, `test_cache.py`, `test_mcp.py`

### Site (maxia-hub/freeai.html)
- Guide install Docker en 4 étapes
- Badge compteur d'installations en temps réel
- i18n 8 langues

### VPS (maxiaworld.app)
- Counter service FastAPI port 8005 (systemd `freeai-counter`)
- nginx `/counter/` → proxy 8005

### GitHub
- Repo : https://github.com/MAXIAWORLD/freeiaforge
- Branch master, commit `6dc3781`

---

## Ce qui reste

- [ ] README.md GitHub : documenter Ollama + PROVIDER_ORDER + entrypoint auto
- [ ] Tester install complète depuis zéro (clone → docker compose → AnythingLLM) — vérifier que .env est auto-créé
- [ ] Tester intégration MCP bout-en-bout avec Claude Code (`mcp_servers.json`)
- [ ] Tester Ollama end-to-end (Ollama installé en local, `docker compose up`, requête → "ollama" dans response)
- [ ] Vérifier noms de modèles Sambanova exacts sur API prod (Llama-3.1-405B-Instruct exact ?)
- [ ] Archiver `freeaiagregator` (ancien repo) sur GitHub
- [ ] Semantic cache : envisager upgrade ChromaDB si cache exact SHA-256 insuffisant

## Décisions prises

- Cache = SQLite SHA-256 (chromadb absent de requirements.txt) — cache exact suffisant pour v0.2
- MCP = JSON pur FastAPI sans SDK (SDK Python MCP trop instable en 2026)
- Sambanova model hint = override `complete()` dans subclass (thread-safe, pas de mutation partagée)
- OpenRouter headers = override `complete()` (scope isolé, pas de modif base.py)
- Signal routing = déterministe in-memory, zéro latence ajoutée (pas de classification NLP)

## Config MCP pour Claude Code

```json
// ~/.claude/mcp_servers.json ou .claude/mcp_servers.json
{
  "freeai-gateway": {
    "type": "http",
    "url": "http://localhost:8002/mcp"
  }
}
```

## Prochaine action

README GitHub : documenter MCP + tester intégration MCP bout-en-bout avec Claude Code.
