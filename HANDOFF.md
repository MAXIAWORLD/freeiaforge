# HANDOFF — FreeIA Gateway (freeiaforge)

> **⚠️ 2026-05-11 — REBRAND `freeaigate` ANNULÉ.** Décision Alexis : la landing publique https://maxiaworld.app/freeai.html n'a jamais été rebrandée et reste "FreeIA Gateway". Le rebrand interne (commit `18c320e` + chaînes ajoutées en v0.6.0) est revert (commit sub-repo `8772632`, monorepo `3805dab`). Le produit s'appelle **FreeIA Gateway** (affichage) / **freeiaforge** (repo, image Docker, log filename). L'alias OpenAI-compat unique reste **`freeai-gateway`**. Le bas de ce document mentionne encore `freeaigate` dans l'historique des sessions précédentes — c'est intentionnel pour préserver la trace.

**Date dernière session :** 2026-05-11 (revert rebrand)
**État :** Phase A 100% livrée + rebrand revert. Prochaine étape : Phase B (clés payantes + modes routing + budget cap) — décisions verrouillées plus bas.
**Branche :** master
**Repo :** `freeiaforge` (path filesystem, repo GitHub, image Docker, nom technique — tout aligné)
**Tag backup :** `freeiaforge-pre-rebrand-2026-05-10` sur HEAD `53fb54a` (toujours valide)
**Tag release :** v0.6.0 — à pusher pour publier `maxiaworld/freeiaforge:0.6.0` sur Docker Hub (workflow CI prêt, image Docker single-tag).
**Tests :** 208 verts (210 − 2 tests TDD du rebrand supprimés avec l'alias `freeaigate` qu'ils enforçaient).

---

## ⚠️ LIRE EN PREMIER PROCHAINE SESSION

1. Lire `~/.claude/projects/C--Users-Mini-pc-Desktop-MAXIA-Lab/memory/project_freeaigate_plan_final.md` — **plan v1.0 source de vérité**
2. Lire ce HANDOFF
3. Démarrer Phase A jour 1 (rename + diagnostic Premature close)

---

## Direction produit — verrouillé 2026-05-10

### Décisions stratégiques
- **Nom produit** : `freeaigate` (binaire `freeaigate-installer.exe`)
- **Repo** : on reste dans `freeiaforge` actuel (rename interne, pas extraction nouveau repo)
- **Cible** : produit gateway IA grand public single-user, **pas business**, **pas verticales métier** (DesignForge/DecoForge etc. = post-v1.0 si traction)
- **Objectif unique** : produit qui marche parfaitement, s'installe en 3 min, gère mémoire + files + voix + web grounding, fonctionne sans Ollama

### Fonctionnalités v1.0
- Cascade providers gratuits (Cerebras/Groq/Sambanova/Gemini/HF/Mistral/OpenRouter/Ollama)
- Clés API payantes optionnelles (OpenAI/Anthropic/DeepSeek)
- Mémoire long-terme persistante cross-session
- Files in : drag-drop fichier ET dossier (PDF/Word/Excel/image/code/zip)
- Files out : génération .docx/.pdf/.pptx/.xlsx/.md/image
- Web grounding anti-hallucination (vérification + citations)
- Voix in (Groq Whisper / faster-whisper local) + voix out (Piper local)
- Auto-switch image multilingue (10 langues : FR/EN/ES/DE/IT/PT/RU/ZH/JA/AR)
- Provider order configurable user (drag-drop UI)
- Optimisation tokens : −25% sans Ollama, −40% avec Ollama
- Installation 1-click Tauri Win/Mac/Linux (~800 MB total)
- Frontend chat = LibreChat bundlé rebrandé `freeaigate` (MIT)

### Garanties non-négociables
- Marche **sans Ollama installé** (cascade free-tier prend le relais via `LightModelService`)
- Marche **sans aucune clé payante**
- Marche **100% offline** sur voix (Piper + faster-whisper bundle installer)
- Marche après simple double-clic installer, zéro setup tiers

### Hors scope v1.0
Multi-user, cloud sync, marketplace skills, verticales métier, business / monétisation.

---

## Plan 6 phases × 1 semaine = 6 semaines

| # | Phase | Livrable | Repo plug-and-play |
|---|---|---|---|
| A | Stabilité + rebrand `freeaigate` (fix Premature close, circuit breaker SQLite, credential pools, validation clés, logs JSON) | v0.6.0 | piyush-tyagi-13/llm-keypool, NousResearch/hermes-agent (patterns) |
| B | Clés payantes (OpenAI/Anthropic/DeepSeek) + modes routing + ordre user + budget cap $5/jour | v0.7.0 | – |
| C | Mémoire long-terme (plug **Mem0**) | v0.8.0 | mem0ai/mem0 |
| D | Auto-switch image multilingue 10 langues (classifier embedding fastembed) | v0.9.0 | qdrant/fastembed (déjà en place) |
| E | Files in/out (plug **MinerU** + weasyprint + python-docx/pptx/openpyxl) | v0.10.0 | opendatalab/MinerU |
| F | Web grounding (plug **AgentSearch self-host SearXNG**) | v0.11.0 | brcrusoe72/agent-search |
| G | Voix in/out (Groq Whisper + **faster-whisper** + Piper) + Bundle **LibreChat** rebrandé + Installer Tauri + Dashboard | v0.12.0 | SYSTRAN/faster-whisper, LibreChat |
| H | Optimisation tokens (plug **GPTCache**, mode concise, délégation Ollama, dashboard stats) | **v1.0.0** | zilliztech/GPTCache |

**Délai initial 8 semaines → 6 semaines** grâce au plug-and-play des 5 repos clés (Mem0, MinerU, AgentSearch, GPTCache, faster-whisper).

---

## Phase A jour 1 — LIVRÉ 2026-05-10

### 1. Rebrand strings (DONE — commits `18c320e` freeiaforge + `c05f7dd` monorepo)
- Décision : path filesystem **conservé** (`freeiaforge/`), repo GitHub idem. Le rebrand est dans :
  - main.py title FastAPI + log line, providers/openrouter.py X-Title, README.md (titre + corps + exemples), .env.example header
  - `_GATEWAY_ALIASES` étendu avec `freeaigate` (sambanova) — backward-compat `freeai-gateway` conservé
  - `/v1/models` expose `freeaigate` ET `freeai-gateway`
  - CI workflow Docker pousse 4 tags : `maxiaworld/freeaigate:{latest,version}` + `maxiaworld/freeiaforge:{latest,version}`
- ⚠️ **Action Alexis manuelle requise avant prochain release tag** : créer le repo Docker Hub `maxiaworld/freeaigate` (sinon le workflow CI échouera)

### 2. Diagnostic Premature close (DONE)
4 causes identifiées dans pipeline streaming :
- `OpenAICompatibleProvider.stream()` ne garantit pas `data: [DONE]\n\n` final → client lève "Premature close" si le provider termine sans
- `raise_for_status()` 401/503 → exception propage dans StreamingResponse → fermeture brutale
- `httpx.RequestError` mid-stream → idem
- `route_stream` n'a aucun failover si premier provider rate à l'ouverture

### 3. Fix Premature close (DONE — commit `e480e17`)
`services/router.py::_safe_stream(provider_name, inner)` wrapper qui :
- Garantit `data: [DONE]\n\n` final TOUJOURS (ajoute si manquant, dedup si déjà émis)
- Convertit `ProviderError` + exception générique en error chunks OpenAI-style sur le fil (200 OK propre)
- Plus jamais de fermeture brutale → "Premature close" éliminé pour les 3 premières causes
- TDD : 5 tests rouges → verts (omission, dedup, erreur à l'ouverture, erreur mid-stream, exception inattendue)
- Failover-on-stream-open intentionnellement reporté (requires header sequencing rework)

---

## Phase A jour 2 — LIVRÉ 2026-05-10

### Credential pools (DONE — commits `748e4d1` pool service + `7d20b2f` SQLite persistence)
- `services/credential_pool.py` : multi-key per provider, fill_first selection, 24h cooldown
- Triggers cooldown sur 401/402/429 ; 500/503/network errors ne touchent pas la clé (territoire circuit breaker du router)
- ProviderRouter accepte `credential_pool=` optionnel ; backward-compat via api_keys dict
- main.py parse `XXX_API_KEYS=k1,k2,k3` (pluriel) ou fallback `XXX_API_KEY` (single)
- SQLite : table `credential_pool_state(provider, key_hash, cooldown_until, fail_count)` ; SHA-256 hash, jamais la clé en clair
- TDD : 27 tests (18 unit + 2 router integration + 7 persistence)

---

## Phase A jours 3, 4 et 5 — LIVRÉ 2026-05-10

### Jour 3 — Circuit breaker SQLite (DONE — commit `d4e1a81`)
- Table `circuit_state(provider, consecutive_errors, last_error, last_used_at)` ; PK `provider`
- `ProviderRouter._on_success`/`_on_error` désormais async, persistent à chaque transition
- `restore_circuit_state()` recharge l'état au boot ; safe no-op sans db
- TDD : 5 tests (persist, increment, reset on success, restore, no-db backward-compat)

### Jour 4 — Validation clés au boot (DONE — commit `1399491`)
- `Provider.validate_key(api_key)` : default True (Ollama/no-auth) ; OpenAICompatibleProvider override avec `GET /models` (401/403 → False, 5xx/network → True clé non punie)
- `services/key_validator.py::validate_keys(providers, pool)` itère le pool, mark_failure(401) sur clé rejetée, retourne stats `{provider: {valid, invalid}}`
- main.py probe au boot et log warning sur clés invalidées
- TDD : 8 tests (list_keys, marks invalid, leaves valid, stats, no-key skip, calls every key, default True)

### Jour 5 — Logs JSON (DONE — commit `1399491`)
- `core/logging_config.py::JsonFormatter` (in-tree, sans dep `python-json-logger`) : 1 JSON object/ligne + propagation des `extra={}`
- `configure_logging(log_dir, level)` : stream handler stdout (UX docker compose logs) + RotatingFileHandler `data/logs/freeaigate.log` 10×10 MB (~100 MB cap), idempotent
- main.py : `configure_logging` remplace `logging.basicConfig`, log_dir configurable via `FREEAIGATE_LOG_DIR`
- TDD : 5 tests (formatter core fields, exception traceback, extras propagation, file creation, RotatingFileHandler attaché)

---

## Phase A — RÉCAP COMPLÈTE 2026-05-10

8 commits feature, 158 → 210 verts, tag `freeaigate-v0.6.0` :

| # | Commit | Sujet |
|---|---|---|
| 1 | `18c320e` | rebrand strings + alias `freeaigate` |
| 2 | `c05f7dd` (monorepo) | CI workflow Docker double-tag |
| 3 | `e480e17` | fix Premature close (`_safe_stream`) |
| 4 | `748e4d1` | CredentialPool service + rotation + cooldown |
| 5 | `7d20b2f` | pool persistence SQLite (SHA-256 hash) |
| 6 | `d4e1a81` | circuit_state SQLite persistence |
| 7 | `1399491` | startup key validation + JSON rotating logs |

**Action manuelle Alexis avant le prochain release tag** : créer le repo Docker Hub `maxiaworld/freeaigate`. Sinon le workflow CI échouera.

---

## Première action prochaine session — Phase B : clés payantes + budget

### Décisions produit verrouillées (2026-05-10 fin de session)

**1. Provider order**
- L'user choisit l'ordre à l'installation ET peut le modifier plus tard
- Aujourd'hui via `PROVIDER_ORDER=cerebras,groq,openai,...` env var (déjà supporté)
- Wizard d'install + UI drag-drop = Phase G (frontend), pas Phase B
- Priorités défauts pour les paid : `openai=10`, `anthropic=11`, `deepseek=12` (après free-tier mais re-orderables)

**2. Budget atteint → signaler + proposer**
- Pas de fallback silencieux, pas de 503 brutal
- Réponse HTTP 402 (non-streaming) avec body JSON :
  ```json
  {"error": {
    "type": "daily_budget_exceeded",
    "spent_usd": 5.02,
    "cap_usd": 5.00,
    "options": [
      "Increase DAILY_BUDGET_USD in .env",
      "Wait until 00:00 UTC (resets daily)",
      "Send X-Mode=cheap to use free-tier only"
    ]
  }}
  ```
- Pour streaming : error chunk OpenAI-style + `[DONE]` (le wrapper `_safe_stream` gère déjà ce pattern)

**3. Pricing**
- À reconsidérer plus tard. Démarrer avec dict hardcoded `_PROVIDER_PRICING` dans `services/budget_tracker.py` (USD per 1M tokens input/output)
- Refactor en `pricing.json` externe quand nécessaire

**4. Reset budget**
- À reconsidérer plus tard. Démarrer minuit **UTC** (cohérent avec `services/quota.py`)

### Plan Phase B

#### 1. Provider OpenAI (TDD, 30min)
- `providers/openai.py` extends `OpenAICompatibleProvider`
- `name="openai"`, `priority=10`, `base_url="https://api.openai.com/v1"`, `default_model="gpt-4o-mini"`
- Tests : default_model resolution, validate_key probe (déjà géré par OpenAICompatibleProvider)

#### 2. Provider DeepSeek (TDD, 20min)
- `providers/deepseek.py` extends `OpenAICompatibleProvider`
- `name="deepseek"`, `priority=12`, `base_url="https://api.deepseek.com/v1"`, `default_model="deepseek-chat"`

#### 3. Provider Anthropic (TDD, 1-2h)
- `providers/anthropic_provider.py` (NB: pas `anthropic.py` pour éviter shadow du SDK officiel)
- Format Messages API propriétaire : `messages` + system séparé, `x-api-key` au lieu de Bearer, `anthropic-version` header obligatoire
- `name="anthropic"`, `priority=11`, `base_url="https://api.anthropic.com/v1"`, `default_model="claude-haiku-4-5-20251001"`
- Override `complete()`, `stream()`, `validate_key()` car format diverge d'OpenAI
- Note : on a déjà `routes/anthropic.py` qui expose un endpoint Anthropic-compat sortant — c'est l'INVERSE (notre code consomme l'API d'Anthropic pour servir les requêtes user). Ne pas confondre.

#### 4. BudgetTracker (TDD, 1-2h)
- `services/budget_tracker.py`
- Schema : `daily_budget(date TEXT, provider TEXT, model TEXT, input_tokens INT, output_tokens INT, usd_spent REAL, PRIMARY KEY(date, provider, model))`
- API : `record_usage(provider, model, input_tok, output_tok)`, `get_today_total_usd()`, `is_over_budget()`, `reset_if_new_day()`
- Pricing dict hardcoded au top du module
- Hook : appel dans `ProviderRouter.route` après `result.tokens_used` connu

#### 5. Header X-Mode + filtre routing (TDD, 1h)
- `ChatRequest.mode: Literal["cheap", "quality", "auto"] = "cheap"` (default)
- Header `X-Mode` mappé sur `request.mode` côté `routes/chat.py` avant dispatch
- Dans `ProviderRouter.route`/`route_stream` : filtre la liste de providers selon mode
  - `cheap` : skip si priority >= 10 (paid)
  - `quality` : skip si priority < 10 (paid only)
  - `auto` : tout
- Si budget over et mode != cheap → forcer skip paid + ajouter warning header `X-Budget-Exceeded: true`

#### 6. Wire main.py + .env.example + commit + tag (30min)
- main.py instancie OpenAIProvider, AnthropicProvider, DeepSeekProvider
- `_parse_keys` sur `OPENAI_API_KEY(S)`, `ANTHROPIC_API_KEY(S)`, `DEEPSEEK_API_KEY(S)`
- `BudgetTracker(db=db, daily_cap_usd=settings.daily_budget_usd)`, passé au router
- `.env.example` ajoute les 3 paid keys + `DAILY_BUDGET_USD=5.0`
- Bump `version="0.7.0"` dans main.py FastAPI
- Tag `freeaigate-v0.7.0`

**Fin Phase B : tag `freeaigate-v0.7.0`**

---

## Top 10 repos open source à utiliser

1. **mem0ai/mem0** — mémoire long-terme (Phase C)
2. **opendatalab/MinerU** — file parsing PDF/DOCX/XLSX/PPTX/images (Phase E)
3. **brcrusoe72/agent-search** — web grounding self-host SearXNG bundlé (Phase F)
4. **piyush-tyagi-13/llm-keypool** — credential pools (Phase A)
5. **zilliztech/GPTCache** — semantic cache 30-68% économies (Phase H)
6. **SYSTRAN/faster-whisper** — STT 4× plus rapide que whisper.cpp (Phase G)
7. **LibreChat** — frontend chat MIT (Phase G)
8. **BerriAI/litellm** — patterns gateway référence
9. **Locally Uncensored** Tauri+Ollama+ComfyUI single .exe — modèle installer (Phase G)
10. **NousResearch/hermes-agent** — patterns credential pools mature (Phase A)

---

## Décisions techniques verrouillées

- **TTS** : Piper local par défaut (gratuit ~50 MB, 30+ langues), ElevenLabs/OpenAI option payante
- **STT** : Groq Whisper cloud par défaut (gratuit 5h/jour), **faster-whisper** local bundle installer (4× whisper.cpp)
- **Web grounding** : auto sur claims factuels + slash `/no-web`, cascade AgentSearch self-host → Tavily → Brave → DuckDuckGo
- **PDF** : weasyprint, **OCR** : Tesseract local bundle (~150 MB) + MinerU dual VLM+OCR
- **Outputs** : `data/outputs/{conversation_id}/`
- **Embedding multilingue** : fastembed `paraphrase-multilingual-MiniLM-L12-v2` (en place), upgrade vers EmbeddingGemma-300M si besoin Phase D
- **Memory** : Mem0 (91.6 LoCoMo benchmark) au lieu de coder from scratch
- **File parsing** : MinerU (109 langues OCR auto) au lieu de pypdf+python-docx custom
- **Cache sémantique** : GPTCache (30-68% économies prouvées) au lieu de cache custom
- **Frontend chat** : LibreChat MIT bundlé rebrandé total (theme/logo/fonts freeaigate, page About préserve mention discrète)
- **Installer Tauri ~800 MB** : Tesseract + Piper + faster-whisper + fastembed multilingue + backend embedded + LibreChat bundle
- **Ollama = OPTIONNEL** : auto-détecté via `LightModelService`. Sans Ollama → Cerebras prend le relais, économie tokens passe de −40% à −25%

---

## Architecture LightModelService (pour optimisation tokens)

Couche d'abstraction unique pour les tâches mécaniques internes (extract memory, classif, résumé, dedup, parse, intent fallback) :

- **Niveau 1 OPTIMAL** : Ollama local (`qwen3:1.7b`) si détecté → 0 tok API
- **Niveau 2 DÉGRADÉ** : Cerebras free-tier (1s, 5000 req/jour de marge) → consomme quota free
- **Niveau 3 EXTRA DÉGRADÉ** : Haiku 4.5 / GPT-5-nano si payant activé → cents
- **Niveau 4** : optimisation désactivée, mode naïf, message clair user

Auto-détection Ollama au démarrage (`GET http://localhost:11434/api/tags`), affichée dashboard.

---

## 13 leviers optimisation tokens (Phase H)

1. System prompt 800 tok max + Anthropic prompt caching
2. Memory injection cappée 800 tok hard
3. History compaction via `LightModelService` tous les 20 messages
4. RAG chunks 512 tok, top-K 5
5. Compression docs uploadés via `LightModelService` avant indexation
6. Code stripping (commentaires, whitespace, locks)
7. Mode `concise` par défaut header `X-Mode`
8. Stop-sequences agressives
9. `max_tokens` dynamique selon intent
10. Routing par taille prompt (Cerebras < 500, Groq/Samba 500-10k, Gemini/Claude 10k+)
11. Cache sémantique GPTCache + pre-warm 50 prompts startup
12. Dédup batch idempotency key (refresh UI = 1 seul appel)
13. Délégation `LightModelService` pour 6 tâches mécaniques

---

## Historique sessions précédentes

### Session 2026-05-10 (suite) — Phase A jours 1 + 2
**Jour 1** :
- Tag git de backup `freeiaforge-pre-rebrand-2026-05-10` sur `53fb54a`
- Rebrand strings + alias TDD : commits `18c320e` (sub-repo) + `c05f7dd` (monorepo CI)
- Diagnostic Premature close : 4 causes identifiées dans pipeline streaming
- Fix Premature close : `_safe_stream` wrapper + intégration `route_stream` (commit `e480e17`)
- Décision conservatrice : pas de rename filesystem, double-publication Docker Hub (legacy + nouveau)
- Tests : 158 → 165 verts (TDD strict, RED→GREEN sur tous les nouveaux comportements)

**Jour 2** :
- Pool credentials service + wire router + persistence SQLite : commits `748e4d1` + `7d20b2f`
- Multi-key support via `XXX_API_KEYS=k1,k2,k3` env vars, backward-compat sur single keys
- Cooldown 24h sur 401/402/429 ; SHA-256 hash en DB jamais la clé en clair
- Tests : 165 → 192 verts (+27 dont 7 sur la persistence)

### Session 2026-05-10 — recadrage produit + recherche repos
- Direction produit recadrée : pas de business / verticales, focus produit gateway parfait
- Plan v1.0 verrouillé : 6 phases × 1 sem = 6 semaines
- Recherche web 16 queries → identification 50+ repos open source pertinents
- Top 10 repos plug-and-play retenus → délai 8 sem → 6 sem
- LightModelService pattern défini (Ollama optionnel)
- Décision frontend : LibreChat MIT bundle rebrandé (vs from-scratch 6 mois ou Open WebUI license ambiguë)
- Sauvegarde mémoire : `project_freeaigate_plan_final.md`

### Session 2026-05-09 — audit MemPalace vs agentmemory (déprécié par décision Mem0)
- `backend/services/memory.py` (MemPalace v0.1.0) **non branché** dans gateway
- Évaluation alternative agentmemory (rohitg00) — REST 107 endpoints, multi-user namespacé
- **Verdict 2026-05-10** : remplacé par **Mem0** (mem0ai/mem0) qui benchmark mieux (91.6 LoCoMo)
- Action : supprimer `services/memory.py` (MemPalace dormant) + `tests/test_memory.py` en début Phase C

### Session 2026-05-08 — 5 fixes installation PC vierge
- 5 commits pushed master (auto-création .env, start.bat Windows, LF entrypoint.sh, /v1/models endpoint, models dynamique)
- Landing publique freeai.html déployée maxiaworld.app, 8 langues
- Bug "Premature close" identifié → cause = modèles hardcodés obsolètes côté provider
- Fix `7a1c2db` auto-discovery modèles livré (refresh /models au boot + 24h)

### v0.5.0 (commit `af11efe` 2026-05-07)
- 8 providers : Cerebras → Groq → Sambanova → Gemini → HF → Mistral → OpenRouter → Ollama
- Endpoints : `/v1/chat/completions`, `/v1/messages` (Anthropic), `/v1/models`, `/v1/providers`, `/health`, `/mcp/*`
- Streaming SSE avec header `X-Provider`
- Semantic cache SQLite TTL 1h
- Quota manager par provider (reset daily)
- MCP server natif (3 tools)
- 178+ tests verts
- Stack : Python 3.12 + FastAPI + httpx + Pydantic V2 + SQLite + Docker Compose port 8002
- Image : `maxiaworld/freeiaforge:latest` (rebrand → `maxiaworld/freeaigate:latest` Phase A)
- Repo public : `https://github.com/MAXIAWORLD/freeiaforge` MIT

---

## Checklist v1.0 ship-ready

- [ ] 1 installer Win/Mac/Linux, 0 terminal, < 3 min
- [ ] User réorganise providers en drag-drop
- [ ] Demande image n'importe quelle langue (FR/EN/ES/DE/IT/PT/RU/ZH/JA/AR) → bascule auto LLM image
- [ ] Drag-drop fichier/dossier → comprend (MinerU)
- [ ] Demande PDF/Word/Image/Excel/Slides → reçoit fichier
- [ ] Question factuelle → vérifie web (AgentSearch), cite sources
- [ ] 🎤 dicte → transcrit (Groq Whisper + faster-whisper offline)
- [ ] Réponse lue à voix haute (Piper) si demandé multilingue
- [ ] IA se souvient cross-session (Mem0)
- [ ] Cascade transparente, jamais "indisponible"
- [ ] Marche sans Ollama (LightModelService cascade)
- [ ] Marche sans aucune clé payante
- [ ] Marche 100% offline sur voix
- [ ] Budget payant cappé
- [ ] −25% tokens sans Ollama, −40% avec Ollama (mesuré golden suite 30 prompts)
- [ ] Header `X-Tokens-Used` sur chaque réponse
- [ ] Dashboard montre économie live vs ChatGPT direct
- [ ] Branding freeaigate cohérent partout (frontend LibreChat rebrandé)
- [ ] Légalement clean (MIT)
- [ ] Désinstalle = 1 clic propre
