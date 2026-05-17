"""
Tests TDD — Phase 4 : version check + stats reporter.

Cas couverts :
  version_check :
    - log si version plus récente disponible
    - silencieux si déjà à jour
    - silencieux sur erreur réseau
    - silencieux sur HTTP non-2xx
  stats_reporter :
    - envoie payload correct (version, os, providers_count, ollama)
    - respecte FREEAI_TELEMETRY=0 → aucun appel HTTP
    - silencieux sur erreur réseau
    - champ os présent et non vide
    - champ ollama booléen
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# version_check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_version_check_logs_update_available(caplog):
    import logging
    from services.version_check import check_version

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = "0.9.0"

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        with caplog.at_level(logging.INFO, logger="services.version_check"):
            await check_version("0.8.0")

    assert any("0.9.0" in r.message and "available" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_version_check_silent_when_up_to_date(caplog):
    import logging
    from services.version_check import check_version

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = "0.8.0"

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        with caplog.at_level(logging.INFO, logger="services.version_check"):
            await check_version("0.8.0")

    assert not any("available" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_version_check_silent_on_network_error():
    from services.version_check import check_version

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        mock_cls.return_value = mock_client

        # No exception raised
        await check_version("0.8.0")


@pytest.mark.asyncio
async def test_version_check_silent_on_http_error():
    from services.version_check import check_version

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock()
    ))

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        await check_version("0.8.0")


@pytest.mark.asyncio
async def test_version_check_message_contains_docker_command(caplog):
    import logging
    from services.version_check import check_version

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = "1.0.0"

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        with caplog.at_level(logging.INFO, logger="services.version_check"):
            await check_version("0.8.0")

    assert any("docker pull" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# stats_reporter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_reporter_sends_correct_payload():
    from services.stats_reporter import report_startup

    captured = {}

    async def _mock_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["payload"] = json
        r = MagicMock()
        r.raise_for_status = MagicMock()
        return r

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=_mock_post)
        mock_cls.return_value = mock_client

        with patch.dict(os.environ, {"FREEAI_TELEMETRY": "1"}):
            await report_startup(version="0.8.0", providers_count=5, has_ollama=True)

    assert captured.get("payload") is not None
    payload = captured["payload"]
    assert payload["version"] == "0.8.0"
    assert payload["providers_count"] == 5
    assert payload["ollama"] is True


@pytest.mark.asyncio
async def test_stats_reporter_includes_os_field():
    from services.stats_reporter import report_startup

    captured = {}

    async def _mock_post(url, json=None, **kwargs):
        captured["payload"] = json
        r = MagicMock()
        r.raise_for_status = MagicMock()
        return r

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=_mock_post)
        mock_cls.return_value = mock_client

        with patch.dict(os.environ, {"FREEAI_TELEMETRY": "1"}):
            await report_startup(version="0.8.0", providers_count=3, has_ollama=False)

    payload = captured.get("payload", {})
    assert "os" in payload
    assert isinstance(payload["os"], str)
    assert len(payload["os"]) > 0


@pytest.mark.asyncio
async def test_stats_reporter_opt_out_no_http_call():
    from services.stats_reporter import report_startup

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        with patch.dict(os.environ, {"FREEAI_TELEMETRY": "0"}):
            await report_startup(version="0.8.0", providers_count=5, has_ollama=False)

    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_stats_reporter_silent_on_network_error():
    from services.stats_reporter import report_startup

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cls.return_value = mock_client

        with patch.dict(os.environ, {"FREEAI_TELEMETRY": "1"}):
            await report_startup(version="0.8.0", providers_count=2, has_ollama=False)


@pytest.mark.asyncio
async def test_stats_reporter_ollama_false_when_no_ollama():
    from services.stats_reporter import report_startup

    captured = {}

    async def _mock_post(url, json=None, **kwargs):
        captured["payload"] = json
        r = MagicMock()
        r.raise_for_status = MagicMock()
        return r

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=_mock_post)
        mock_cls.return_value = mock_client

        with patch.dict(os.environ, {"FREEAI_TELEMETRY": "1"}):
            await report_startup(version="0.8.0", providers_count=4, has_ollama=False)

    assert captured["payload"]["ollama"] is False


@pytest.mark.asyncio
async def test_stats_reporter_default_telemetry_enabled():
    """Sans FREEAI_TELEMETRY dans l'env, le reporter envoie quand même."""
    from services.stats_reporter import report_startup

    call_count = 0

    async def _mock_post(url, json=None, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        r.raise_for_status = MagicMock()
        return r

    env = {k: v for k, v in os.environ.items() if k != "FREEAI_TELEMETRY"}

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=_mock_post)
        mock_cls.return_value = mock_client

        with patch.dict(os.environ, env, clear=True):
            await report_startup(version="0.8.0", providers_count=1, has_ollama=False)

    assert call_count == 1
