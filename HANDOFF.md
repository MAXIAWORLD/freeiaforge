# HANDOFF — FreeIA Gateway (freeiaforge)

**Date dernière session :** 2026-05-17
**Version actuelle :** 0.8.0
**Tests :** 325 verts
**Branche :** master
**Derniers commits :** `9a4ba8b` (Phase 4) → `0fb358d` (Phase 5)

---

## ⚠️ LIRE EN PREMIER PROCHAINE SESSION

1. Lire ce fichier en entier
2. Vérifier `git log --oneline -10` pour confirmer l'état
3. Commencer par : **créer le fichier `freeiaforge/VERSION`** (voir § Reste à faire)

---

## État actuel — PLAN_FREEAI_V2.md

Le plan `PLAN_FREEAI_V2.md` (root du monorepo) a été intégralement implémenté en TDD sur cette session.

### Ce qui a été livré (cette session)

| Phase | Contenu | Commit |
|---|---|---|
| Phase 0 | NVIDIA NIM + Cloudflare providers, GatewayAuthMiddleware (ASGI pur, streaming-safe) | — |
| Phase 1 | Circuit breaker 3-états (CLOSED→OPEN→HALF_OPEN), tri dynamique quota, `providers.json` remote | — |
| Phase 2 | `task_inference.py` (vision/long_context/code/default), `X-FreeAI-Task` header | — |
| Phase 3 | Dashboard HTML `/` auto-refresh, `GET /v1/quota`, `/health` enrichi (version+providers count), stats daily in-memory | `591d5e5` |
| Phase 4 | `setup.bat`/`setup.sh` wizard interactif, `version_check.py`, `stats_reporter.py` telemetry opt-out, README Hermes | `9a4ba8b` |
| Phase 5 | SQLite séparé (`quota.db`/`cache.db`/`stats.db`), `stats_history.py` 7j, tests intégration clients, CI GitHub Actions | `0fb358d` |

### Architecture SQLite actuelle

```
data/
├── quota.db      ← quota + circuit_state + credential_pool_state
├── cache.db      ← cache exact SHA-256 (SemanticCache)
└── stats.db      ← historique requêtes 7j (request_log)
```

### Providers actifs (9 cloud + Ollama)

| Provider | Priorité | Limite free |
|---|---|---|
| Cerebras | 1 | 1M tok/j |
| Groq | 2 | 14 400 req/j |
| Sambanova | 3 | free tier |
| Gemini | 4 | 1 500 req/j · 1M ctx |
| HuggingFace | 5 | 1 000 req/j |
| Mistral | 6 | 100 req/j |
| OpenRouter | 7 | 30+ models:free |
| NVIDIA NIM | 8 | 40 RPM |
| Cloudflare | 9 | 10 000 req/j |
| Ollama | 10 | local ∞ |

### Task routing (Phase 2)

| Task | Détection | Providers ciblés |
|---|---|---|
| `vision` | `image_url` dans content | gemini, openrouter |
| `long_context` | > 24k chars | gemini uniquement |
| `code` | ` ``` ` ou keywords (def/bug/refactor…) | groq, cerebras en premier |
| `default` | tout le reste | ordre quota dynamique |

---

## Reste à faire (par priorité)

### 1. Fichier `VERSION` — CRITIQUE (5 min)

`version_check.py` fait un `GET` sur `https://raw.githubusercontent.com/MAXIAWORLD/freeiaforge/main/VERSION`.
Ce fichier **n'existe pas encore** → la feature est silencieusement inerte.

```bash
echo "0.8.0" > freeiaforge/VERSION
git add freeiaforge/VERSION
git commit -m "chore(freeiaforge): add VERSION file for version_check"
git push
```

### 2. Historique 7j dans dashboard + `/v1/quota` — 30 min

Les données sont stockées dans `stats.db` via `stats_history.py` mais **pas encore affichées**.

- `routes/dashboard.py` : ajouter section "Last 7 days" sous le tableau providers (groupé par jour)
- `GET /v1/quota` : ajouter clé `"history"` avec le résultat de `get_last_7_days()`
- Passer `stats_db` au router dashboard (via `get_router()._stats_db`)
- Tests TDD à écrire d'abord

### 3. Cache sémantique réel — 2-3h

Le plan demande `all-MiniLM-L6-v2` (80 MB, CPU-only) avec similarité > 0.90.
L'implémentation actuelle (`services/cache.py`) est un cache exact SHA-256 — correct mais pas "sémantique".

Options :
- **fastembed** (`fastembed` pip, 80-300 MB) — CPU-only, pas de torch requis → recommandé
- **sentence-transformers** (~2 GB avec torch) → trop lourd pour Docker slim
- Garder exact hash + renommer honnêtement `ExactCache` → option acceptable si on déprioritise

**Décision à prendre en début de session.**

---

## Ce qui n'est PAS dans le PLAN_FREEAI_V2.md mais est planifié

Le plan long-terme (Phase B→H) est dans ce fichier plus bas (historique sessions 2026-05-10/11).
Les prochaines grandes phases sont :

- **Phase B** : providers payants (OpenAI / Anthropic / DeepSeek) + BudgetTracker + X-Mode header
- **Phase C** : mémoire long-terme (Mem0)
- **Phase D** : auto-switch image multilingue (fastembed)
- **Phase E** : files in/out (MinerU)
- **Phase F** : web grounding (AgentSearch/SearXNG)
- **Phase G** : voix + LibreChat frontend + installer Tauri
- **Phase H** : optimisation tokens (-40%)

---

## Rappels techniques importants

- **Streaming** : middleware `GatewayAuthMiddleware` est ASGI pur (pas `BaseHTTPMiddleware`) → ne jamais revenir à BaseHTTPMiddleware (bufferise le streaming)
- **Circuit breaker** : `_error_state` in-memory + persisté SQLite. OPEN → HALF_OPEN après `cb_half_open_after` secondes (défaut 300s)
- **Stats daily** : in-memory dans `ProviderRouter._daily_stats`, reset auto à minuit UTC. `stats_history.py` = persistance 7j.
- **Rebrand** : produit = **FreeIA Gateway** (affichage) / `freeiaforge` (repo/Docker). Alias OpenAI-compat = `freeai-gateway`. Le rebrand `freeaigate` de mai 2026 a été revert.
- **Version file** : `main.py` → `FastAPI(version="0.8.0")`. CI workflow `docker-publish.yml` se déclenche sur tags `v*.*.*`.

---

## Fichiers clés

```
freeiaforge/
├── backend/
│   ├── main.py                          ← lifespan, providers, router init
│   ├── core/config.py                   ← Settings (db_path, stats_db_path, CB params...)
│   ├── core/database.py                 ← init_db (quota.db tables)
│   ├── services/
│   │   ├── router.py                    ← ProviderRouter (routing, CB, stats)
│   │   ├── task_inference.py            ← infer_task_type()
│   │   ├── stats_history.py             ← record_request / get_last_7_days
│   │   ├── version_check.py             ← check_version() (besoin de VERSION sur GitHub)
│   │   ├── stats_reporter.py            ← telemetry opt-out
│   │   └── cache.py                     ← SemanticCache (exact SHA-256 → cache.db)
│   ├── routes/
│   │   ├── chat.py                      ← POST /v1/chat/completions
│   │   ├── health.py                    ← GET /health, GET /v1/quota, GET /v1/providers
│   │   └── dashboard.py                 ← GET / (HTML, auto-refresh 30s)
│   └── tests/                           ← 325 tests (pytest)
├── setup.bat / setup.sh                 ← wizard interactif
├── start.bat / start.sh / start.ps1     ← lanceur simple
├── VERSION                              ← À CRÉER (manquant)
└── PLAN_FREEAI_V2.md                    ← (monorepo root) — plan v2 complet
```

---

## CI GitHub Actions

`.github/workflows/freeiaforge-ci.yml` (monorepo root) :
- Trigger : push/PR sur `freeiaforge/**`
- Jobs : `test` (pytest Python 3.12) → `docker-build` (build sans push) → `docker-push` (push `latest` + `sha-xxx` sur merge main/master)

`.github/workflows/docker-publish.yml` :
- Trigger : tag `v*.*.*`
- Push `maxiaworld/freeiaforge:latest` + `maxiaworld/freeiaforge:vX.Y.Z`

**Secrets requis dans GitHub repo** : `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`

---

## Historique sessions 2026-05-10/11 (plan long-terme Phase B→H)

> Contenu conservé ci-dessous pour référence — plan v1.0 complet, providers payants, budget, mémoire, voix, installer Tauri.

### Direction produit verrouillée 2026-05-10

- **Nom produit** : `freeaigate` (affichage prod) / `freeiaforge` (repo)
- **Cible** : gateway IA grand public single-user, pas business
- **Objectif** : produit parfait, installation 3 min, mémoire + files + voix + web grounding

### Plan Phase B — Clés payantes + budget

#### Providers payants (TDD)
- `providers/openai.py` : name=openai, priority=10, base_url=https://api.openai.com/v1, model=gpt-4o-mini
- `providers/deepseek.py` : name=deepseek, priority=12, base_url=https://api.deepseek.com/v1, model=deepseek-chat
- `providers/anthropic_provider.py` : name=anthropic, priority=11 — format Messages API propriétaire (x-api-key, anthropic-version, system séparé)
  - **ATTENTION** : ne pas confondre avec `routes/anthropic.py` (endpoint sortant Anthropic-compat) — ici on *consomme* l'API Anthropic

#### BudgetTracker (TDD)
- `services/budget_tracker.py` — schema : `daily_budget(date, provider, model, input_tokens, output_tokens, usd_spent)`
- API : `record_usage()`, `get_today_total_usd()`, `is_over_budget()`, `reset_if_new_day()`
- Réponse 402 si budget dépassé :
  ```json
  {"error": {"type": "daily_budget_exceeded", "spent_usd": 5.02, "cap_usd": 5.00, "options": [...]}}
  ```

#### X-Mode header
- `ChatRequest.mode: Literal["cheap", "quality", "auto"] = "cheap"`
- `cheap` : skip providers priority >= 10 (paid)
- `quality` : skip providers priority < 10 (free only)
- `auto` : tous

### Phases C→H (résumé)

| Phase | Contenu | Repo plug-and-play |
|---|---|---|
| C | Mémoire long-terme | mem0ai/mem0 |
| D | Auto-switch image 10 langues | qdrant/fastembed |
| E | Files in/out (PDF/Word/Excel/image) | opendatalab/MinerU |
| F | Web grounding | brcrusoe72/agent-search + SearXNG |
| G | Voix + LibreChat rebrandé + Installer Tauri | SYSTRAN/faster-whisper, LibreChat |
| H | Optimisation tokens −40% (GPTCache, LightModelService) | zilliztech/GPTCache |

### LightModelService (Phase H)

Abstraction pour tâches mécaniques internes :
1. Ollama local (`qwen3:1.7b`) si détecté → 0 tok API
2. Cerebras free-tier → consomme quota free
3. Haiku 4.5 / GPT-5-nano si payant activé
4. Mode naïf (désactivé)
