# HANDOFF — FreeIA Gateway

**Date :** 2026-05-08
**État :** v0.5.0 + 5 fixes UX/install (post-test utilisateur réel)

---

## Session 2026-05-08 — fixes installation après test sur PC vierge

Test réel par un utilisateur non-tech sur un Windows clean → 5 bugs trouvés et corrigés.

### Fixes livrés (5 commits, tous pushed master)

| Commit | Fix |
|---|---|
| `7a1d7a6` | `start.ps1` + `start.sh` : auto-création de `backend/.env`. `docker-compose.yml` : `env_file required: false` (compose v2) |
| `50f81c5` | `start.bat` ajouté — natif Windows, contourne ExecutionPolicy PowerShell |
| `9e19bb8` | `.gitattributes` force LF sur `*.sh` + `Dockerfile`: `sed -i 's/\r$//' entrypoint.sh`. Fix le `entrypoint.sh: 2: set: Illegal option -` qui empêchait le conteneur de démarrer sur Windows |
| `cea22fd` | Endpoint `GET /v1/models` ajouté (était 404, cause du "Premature close" dans AnythingLLM/LibreChat) |
| `5594950` | `/v1/models` dynamique : retourne le `default_model` de chaque provider configuré (clé API présente) + alias `freeai-gateway` |

### Landing publique (maxia-hub)

- Encadré **Pré-requis** avec liens download Docker Desktop + Git
- **Bouton "Télécharger le ZIP"** ajouté dans étape 1 (Git devient optionnel)
- Étape 3 : `start.bat` (double-clic) au lieu de `docker compose up --build`
- Section **Troubleshooting accordéon** : 5 erreurs courantes + solutions
- 8 langues à jour (en/fr/es/de/ja/zh/pt/ko)
- Déployé `https://maxiaworld.app/freeai.html`, backups VPS créés

### Bug identifié (pas encore résolu)

**Cause "Premature close" dans AnythingLLM = modèles hardcodés obsolètes côté provider.**

Diagnostic confirmé par le user : les `default_model` codés en dur dans `providers/*.py` ne sont plus valides côté provider → l'API retourne une erreur → le stream est coupé → AnythingLLM voit "Premature close".

Modèles suspects à auditer :
- `cerebras.py` : `llama-3.3-70b`
- `gemini.py` : `gemini-1.5-flash` (probablement déprécié → `gemini-2.0-flash` ou `2.5-flash`)
- `openrouter.py` : `openrouter/free` (pas un model id valide)
- `huggingface.py` : `meta-llama/Llama-3.1-70B-Instruct` (peut être gated)
- `mistral.py` : `mistral-large-latest`
- `groq.py` : `llama-3.3-70b-versatile`

### Priorité #1 prochaine session — auto-discovery des modèles

Plus de hardcode. Au boot de chaque provider, appeler son endpoint de listing pour récupérer la liste réelle, choisir le meilleur dispo, le stocker comme `default_model`. Refresh toutes les 24h.

| Provider | Endpoint listing |
|---|---|
| Cerebras | `GET https://api.cerebras.ai/v1/models` |
| Groq | `GET https://api.groq.com/openai/v1/models` |
| Sambanova | `GET https://api.sambanova.ai/v1/models` |
| Gemini | `GET https://generativelanguage.googleapis.com/v1beta/models` |
| Mistral | `GET https://api.mistral.ai/v1/models` |
| OpenRouter | `GET https://openrouter.ai/api/v1/models` |
| HuggingFace | API listing (specifique) |

Plan suggéré :
1. Ajouter méthode `Provider.discover_models(api_key) -> list[str]` (interface).
2. Implémenter `OpenAICompatibleProvider.discover_models()` (générique pour Cerebras/Groq/Sambanova/Mistral/OpenRouter — appellent tous `/v1/models`).
3. Implémentations spécifiques pour Gemini + HuggingFace.
4. Au startup de `ProviderRouter`, appeler `discover_models()` en parallèle (asyncio.gather), choisir le "meilleur" modèle (heuristique: plus gros / le plus récent), assigner à `default_model`.
5. Cron 24h via asyncio task pour rafraîchir.
6. Fallback : si discovery fail, garder le hardcode actuel.
7. Tests : mock chaque endpoint, vérifier sélection.

Ce fix résout aussi : nouveaux modèles annoncés = plus besoin de release manuelle, FreeIA s'adapte tout seul.

---

## État v0.5.0 (commit `af11efe` du 2026-05-07)

- 8 providers : Cerebras → Groq → Sambanova → Gemini → HuggingFace → Mistral → OpenRouter → Ollama
- Endpoints : `/v1/chat/completions` (OpenAI), `/v1/messages` (Anthropic), `/v1/models`, `/v1/providers`, `/health`, `/mcp/*`
- Streaming SSE avec header `X-Provider`
- Semantic cache SQLite (TTL 1h)
- Quota manager par provider (reset daily)
- MCP server natif (3 tools)
- Tests : 178+ verts (12 health route après ajout /v1/models)

## Stack

- Python 3.12 + FastAPI + httpx + Pydantic V2
- SQLite (quotas + cache)
- Docker Compose (port 8002)
- Image publiée : `maxiaworld/freeiaforge:latest`

## Repo public

`https://github.com/MAXIAWORLD/freeiaforge` — MIT, 178 tests, prêt à être cloné.

---

## Notes pour la prochaine session

1. **Lire ce HANDOFF avant toute action** — le bug AnythingLLM "Premature close" est la priorité.
2. **Demander les logs Docker au user** : `docker compose logs --tail=50 backend` après tentative AnythingLLM.
3. **Hypothèse principale** : le streaming SSE plante avec une erreur provider (401 Cerebras ?) qui n'est pas correctement remontée → connexion fermée → "Premature close" côté client. Voir `routes/chat.py::chat_completions` et `services/router.py::route_stream`.
4. **Reproduire localement** : lancer le backend avec `CEREBRAS_API_KEY=invalid`, faire une requête streaming → observer le comportement.
