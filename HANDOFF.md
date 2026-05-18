# HANDOFF — FreeIA Gateway — MCP JSON-RPC 2.0 ✅

## État au 2026-05-17 (fin de session)

### Tout est propre

- `routes/mcp.py` : **réécrit en MCP JSON-RPC 2.0** (spec 2025-03-26) ✓
- `tests/test_mcp.py` : **20 tests TDD** — 20/20 ✓ (tous verts, aucune régression)
- Landing `https://maxiaworld.app/freeai.html` : live, strings à jour ✓

### Ce qui a été fait cette session

**`backend/routes/mcp.py`** — réécriture complète :
- `POST /mcp` : dispatche `initialize`, `tools/list`, `tools/call` en JSON-RPC 2.0
- `GET /mcp` : manifest legacy conservé (rétrocompatibilité)
- Strings corrigées : `"10 LLMs (9 cloud + Ollama)"`, `"9 cloud providers + Ollama"`, hints `nvidia_nim` + `cloudflare`
- Erreurs standard : -32600 (invalid request), -32601 (method not found), -32602 (unknown tool), -32700 (parse error)

**`tests/test_mcp.py`** — remplacement complet :
- Supprimé : anciens tests REST (`POST /mcp/tools/chat`, `POST /mcp/tools/providers_status`)
- Ajouté : 20 tests couvrant initialize, tools/list, tools/call (chat + providers_status), erreurs, id echo

**Curl live vérifié sur port 8002 :**
- `initialize` → `{"jsonrpc":"2.0","result":{"protocolVersion":"2025-03-26",...},"id":1}` ✓
- `tools/list` → 2 tools avec inputSchema ✓
- méthode inconnue → `{"error":{"code":-32601,...}}` ✓

### Rien de ouvert

Le README disait que MCP marchait avec Claude Code — c'est maintenant vrai.

Config Claude Code correcte :
```json
{ "freeia-gateway": { "type": "http", "url": "http://localhost:8002/mcp" } }
```

### Échecs pré-existants (non liés)

- `test_memory.py` × 9 : `memory.py` supprimé (session précédente), tests orphelins à supprimer
- `test_ollama_provider` × 1 + `test_openrouter_provider` × 2 : priorités provider, pré-existants

### Prochaine action possible

Supprimer `tests/test_memory.py` (module supprimé, tests inutiles).

## VPS

- Landing : `ubuntu@146.59.237.43` → `/opt/maxia/frontend/freeai.html` (accessible via `https://maxiaworld.app/freeai.html`)
- Gateway tourne en local Docker chez les users, pas sur le VPS
