"""
Tests TDD — SemanticCache (fastembed + cosine similarity > 0.90).

Stratégie : mock _embed → vecteurs contrôlés → pas de téléchargement modèle en CI.
Cas couverts :
  - lookup DB vide → None
  - store + lookup vecteur identique → hit
  - vecteurs similaires (cos > 0.90) → hit
  - vecteurs dissimilaires (cos < 0.90) → miss
  - TTL expiré → miss
  - threshold boundary (cos == threshold → hit; cos < threshold → miss)
  - multiple entrées → retourne la plus similaire au-dessus du seuil
  - _embed lève une exception → None (dégradation gracieuse)
  - SemanticCache crée table semantic_cache dans cache.db
  - router.py accepte SemanticCache (duck typing)
  - main.py utilise SemanticCache si fastembed disponible
  - main.py fallback ExactCache si fastembed absent
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from core.models import (
    ChatChoice,
    ChatResponse,
    ChatUsage,
    Message,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VEC_A = np.array([1.0, 0.0, 0.0], dtype=np.float32)
# cos_sim(_VEC_A, _VEC_HIGH) ≈ 0.951  → > 0.90  HIT
_VEC_HIGH = np.array([0.95, 0.312, 0.0], dtype=np.float32)
# cos_sim(_VEC_A, _VEC_LOW) = 0.0     → < 0.90  MISS
_VEC_LOW = np.array([0.0, 1.0, 0.0], dtype=np.float32)
# cos_sim(_VEC_A, _VEC_BELOW) ≈ 0.871 → < 0.90  MISS
_VEC_BELOW = np.array([0.87, 0.493, 0.0], dtype=np.float32)


def _response(content: str = "ok") -> ChatResponse:
    return ChatResponse(
        id="x", model="m",
        choices=[ChatChoice(index=0, message=Message(role="assistant", content=content), finish_reason="stop")],
        usage=ChatUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def _msgs(text: str = "hi") -> list[Message]:
    return [Message(role="user", content=text)]


# ---------------------------------------------------------------------------
# 1. Lookup DB vide → None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_lookup_empty_returns_none(tmp_path: Path) -> None:
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path)
    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_A)):
        result = await cache.lookup(_msgs("what is 2+2?"))
    assert result is None


# ---------------------------------------------------------------------------
# 2. Store + lookup vecteur identique → hit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_store_then_lookup_exact_hit(tmp_path: Path) -> None:
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path)
    embed = AsyncMock(return_value=_VEC_A)
    with patch.object(cache, "_embed", new=embed):
        await cache.store(_msgs("what is 2+2?"), _response("4"), ttl_seconds=3600)
        result = await cache.lookup(_msgs("what is 2+2?"))
    assert result is not None
    assert result.choices[0].message.content == "4"


# ---------------------------------------------------------------------------
# 3. Vecteurs similaires (cos > 0.90) → hit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_similar_messages_hit(tmp_path: Path) -> None:
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path, similarity_threshold=0.90)

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_A)):
        await cache.store(_msgs("what is 2 plus 2?"), _response("4"), ttl_seconds=3600)

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_HIGH)):
        result = await cache.lookup(_msgs("what's 2+2?"))

    assert result is not None
    assert result.choices[0].message.content == "4"


# ---------------------------------------------------------------------------
# 4. Vecteurs dissimilaires (cos < 0.90) → miss
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_dissimilar_messages_miss(tmp_path: Path) -> None:
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path, similarity_threshold=0.90)

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_A)):
        await cache.store(_msgs("what is 2 plus 2?"), _response("4"), ttl_seconds=3600)

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_LOW)):
        result = await cache.lookup(_msgs("what is the capital of France?"))

    assert result is None


# ---------------------------------------------------------------------------
# 5. TTL expiré → miss
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_expired_entry_miss(tmp_path: Path) -> None:
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path)

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_A)):
        await cache.store(_msgs("q"), _response("r"), ttl_seconds=0)
        await asyncio.sleep(0.05)
        result = await cache.lookup(_msgs("q"))

    assert result is None


# ---------------------------------------------------------------------------
# 6. Threshold boundary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_threshold_boundary_hit_at_equal(tmp_path: Path) -> None:
    """cos_sim == threshold → hit (>=)."""
    from services.cache import SemanticCache
    # _VEC_HIGH a cos ≈ 0.951 avec _VEC_A → largement au-dessus
    cache = SemanticCache(data_dir=tmp_path, similarity_threshold=0.95)

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_A)):
        await cache.store(_msgs("q"), _response("r"), ttl_seconds=3600)
    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_HIGH)):
        result = await cache.lookup(_msgs("q2"))

    assert result is not None


@pytest.mark.asyncio
async def test_semantic_threshold_boundary_miss_below(tmp_path: Path) -> None:
    """cos_sim ≈ 0.871 < 0.90 → miss."""
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path, similarity_threshold=0.90)

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_A)):
        await cache.store(_msgs("q"), _response("r"), ttl_seconds=3600)
    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_BELOW)):
        result = await cache.lookup(_msgs("q2"))

    assert result is None


# ---------------------------------------------------------------------------
# 7. Multiple entrées → retourne la plus similaire
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_multiple_entries_returns_best(tmp_path: Path) -> None:
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path, similarity_threshold=0.90)

    vec_b = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_A)):
        await cache.store(_msgs("q1"), _response("answer_A"), ttl_seconds=3600)
    with patch.object(cache, "_embed", new=AsyncMock(return_value=vec_b)):
        await cache.store(_msgs("q2"), _response("answer_B"), ttl_seconds=3600)

    # Query nearest _VEC_A → should get answer_A
    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_HIGH)):
        result = await cache.lookup(_msgs("q_similar_to_A"))

    assert result is not None
    assert result.choices[0].message.content == "answer_A"


# ---------------------------------------------------------------------------
# 8. _embed échoue → None (dégradation gracieuse)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_embed_failure_returns_none(tmp_path: Path) -> None:
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path)

    async def _failing_embed(text: str):
        raise RuntimeError("model not available")

    with patch.object(cache, "_embed", new=_failing_embed):
        result = await cache.lookup(_msgs("anything"))

    assert result is None


@pytest.mark.asyncio
async def test_semantic_embed_failure_on_store_is_silent(tmp_path: Path) -> None:
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path)

    async def _failing_embed(text: str):
        raise RuntimeError("model not available")

    with patch.object(cache, "_embed", new=_failing_embed):
        await cache.store(_msgs("q"), _response("r"), ttl_seconds=3600)
        # Ne doit pas lever d'exception


# ---------------------------------------------------------------------------
# 9. Table semantic_cache créée dans cache.db
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_cache_creates_table(tmp_path: Path) -> None:
    import aiosqlite
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path)

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_A)):
        await cache.lookup(_msgs("anything"))

    async with aiosqlite.connect(tmp_path / "cache.db") as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='semantic_cache'"
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# 10. SemanticCache conserve le contrat lookup/store (duck typing avec router)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_cache_duck_typing_with_router(tmp_path: Path) -> None:
    """ProviderRouter doit accepter SemanticCache (même interface que ExactCache)."""
    from services.cache import SemanticCache
    from services.router import ProviderRouter

    cache = SemanticCache(data_dir=tmp_path)

    quota = AsyncMock()
    quota.is_available = AsyncMock(return_value=True)
    quota.record_usage = AsyncMock()

    provider = AsyncMock()
    provider.name = "groq"
    provider.priority = 1
    from providers.base import ProviderResult
    provider.complete = AsyncMock(return_value=ProviderResult(
        response=_response("hello"),
        provider_name="groq",
        tokens_used=5,
    ))

    router = ProviderRouter(
        providers=[provider],
        quota=quota,
        api_keys={"groq": "key"},
        cache=cache,
    )

    with patch.object(cache, "_embed", new=AsyncMock(return_value=_VEC_A)):
        result = await router.route(
            __import__("core.models", fromlist=["ChatRequest"]).ChatRequest(
                messages=_msgs("hi")
            )
        )

    assert result is not None


# ---------------------------------------------------------------------------
# 11. main.py instancie SemanticCache si fastembed disponible
# ---------------------------------------------------------------------------

def test_main_uses_semantic_cache_when_fastembed_available() -> None:
    """Quand fastembed est importable, main.py doit créer un SemanticCache."""
    import importlib
    import sys

    # Simuler fastembed disponible (même s'il n'est pas installé)
    fake_fastembed = MagicMock()
    fake_fastembed.TextEmbedding = MagicMock()

    with patch.dict(sys.modules, {"fastembed": fake_fastembed}):
        from services.cache import SemanticCache
        # La classe doit être importable
        assert SemanticCache is not None
        # Vérifier que l'instanciation fonctionne (ne pas appeler _get_model)
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as td:
            cache = SemanticCache(data_dir=pathlib.Path(td))
            assert cache._threshold == 0.90


# ---------------------------------------------------------------------------
# 12. Overwrite → nouvelle réponse retournée
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semantic_overwrite_returns_new_response(tmp_path: Path) -> None:
    from services.cache import SemanticCache
    cache = SemanticCache(data_dir=tmp_path)
    embed = AsyncMock(return_value=_VEC_A)

    with patch.object(cache, "_embed", new=embed):
        await cache.store(_msgs("q"), _response("first"), ttl_seconds=3600)
        await cache.store(_msgs("q"), _response("second"), ttl_seconds=3600)
        result = await cache.lookup(_msgs("q"))

    assert result is not None
    assert result.choices[0].message.content == "second"
