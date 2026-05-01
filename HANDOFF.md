# HANDOFF — FreeIA Gateway

**Date :** 2026-05-01  
**État :** v0.1.0 livré, repo GitHub public, site à jour

---

## Ce qui est fait

### Backend (freeiaforge/)
- FastAPI, port 8002, OpenAI-compatible `/v1/chat/completions`
- 6 providers en priorité : Cerebras → Groq → Sambanova → Gemini → HuggingFace → Mistral
- Fallback automatique + quota SQLite (reset daily)
- MemPalace intégré : query avant routing, store fire-and-forget après réponse
- Ping compteur d'install au premier démarrage Docker (`/app/data/.installed`)
- Docker Compose one-command : `docker compose up --build`
- 33 tests, 89% coverage

### Site (maxia-hub/freeai.html)
- Guide install Docker en 4 étapes (plus Python/pip)
- Liens cliquables pour obtenir les 6 clés API (étape 2)
- CTA honnête : "Zéro intermédiaire" (plus "contrôle total")
- Badge compteur d'installations en temps réel (JS fetch)
- i18n 8 langues à jour

### VPS (maxiaworld.app)
- Counter service FastAPI sur port 8005 (systemd `freeai-counter`)
- nginx `/counter/` → proxy 8005
- DB : `/opt/counter/freeai.db` (SQLite)

### GitHub
- Repo : https://github.com/MAXIAWORLD/freeiaforge
- Homepage : https://maxiaworld.app/freeai.html
- Branch master, 3 commits

---

## Ce qui reste

- Tester l'install complète depuis zéro (clone → docker compose → AnythingLLM)
- Vérifier que MemPalace se télécharge bien au build Docker (~300 MB sentence-transformers)
- README.md sur le repo GitHub (pas encore créé)
- Le repo `freeaiagregator` (ancien) peut être archivé sur GitHub

## Décisions prises

- MemPalace : intégré dans Docker (option 2), ChromaDB embedded, données dans volume `/app/data`
- Compteur : ping anonyme à l'install, public sur la page hero
- Pas d'ajout de nouveaux providers (OpenRouter, GitHub Models, NVIDIA NIM refusés)
- Pas de déploiement serveur de FreeIA — reste local chez l'utilisateur

## Prochaine action

Créer le README.md sur https://github.com/MAXIAWORLD/freeiaforge
