# HANDOFF — freeaigate (ex-FreeIA Gateway / freeiaforge)

**Date dernière session :** 2026-05-10 (Phase A jours 1 + 2 livrés)
**État :** v0.5.0 + Phase A 50% (rebrand + Premature close fix + credential pool complet). Reste Phase A : circuit breaker SQLite persistance, validation clés boot + logs JSON.
**Branche :** master
**Repo :** `freeiaforge` (path filesystem inchangé, repo GitHub idem ; rebrand interne fait dans strings + image Docker)
**Tag backup :** `freeiaforge-pre-rebrand-2026-05-10` sur HEAD `53fb54a`
**Tests :** 192 verts (158 baseline + 2 alias + 5 _safe_stream + 27 credential pool)

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

### Credential pools (DONE — commits `0fde0d3` pool service + `7d20b2f` SQLite persistence)
- `services/credential_pool.py` : multi-key per provider, fill_first selection, 24h cooldown
- Triggers cooldown sur 401/402/429 ; 500/503/network errors ne touchent pas la clé (territoire circuit breaker du router)
- ProviderRouter accepte `credential_pool=` optionnel ; backward-compat via api_keys dict
- main.py parse `XXX_API_KEYS=k1,k2,k3` (pluriel) ou fallback `XXX_API_KEY` (single)
- SQLite : table `credential_pool_state(provider, key_hash, cooldown_until, fail_count)` ; SHA-256 hash, jamais la clé en clair
- TDD : 27 tests (18 unit + 2 router integration + 7 persistence)

---

## Première action prochaine session — Phase A jour 3 : circuit breaker SQLite

### 1. Persister circuit breaker SQLite (1-2h)
Aujourd'hui `_error_state` (RAM) reset au moindre restart. Table `circuit_state(provider, consecutive_errors, last_error, last_used_at)` ; PK `provider`. Hooks dans `_on_success` et `_on_error`. Restore au boot.

### 2. Validation clés au démarrage + logs JSON (2-3h)
- Ping endpoint léger par provider au boot via `discover_default_model` étendu, log valides/invalides
- Logs JSON via `python-json-logger` + `RotatingFileHandler` 10×10 MB
- Au boot : `freeaigate ready — N/M cloud providers active` doit lister les clés invalidées en plus

**Fin Phase A : tag `freeaigate-v0.6.0`**

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
- Pool credentials service + wire router + persistence SQLite : commits `0fde0d3` + `7d20b2f`
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
