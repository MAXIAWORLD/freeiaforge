"""
Tests TDD — infer_task_type (Phase 2).

Cas couverts :
  - texte plain → default
  - ``` dans le message → code
  - mot-clé "def " → code
  - mot-clé "refactor" → code
  - image_url dans content → vision
  - message très long → long_context
  - vision prioritaire sur long_context
  - vision prioritaire sur code
  - long_context prioritaire sur code
"""
from __future__ import annotations

import pytest

from core.models import ChatRequest, Message
from services.task_inference import (
    TASK_CODE,
    TASK_DEFAULT,
    TASK_LONG_CONTEXT,
    TASK_VISION,
    LONG_CONTEXT_CHAR_THRESHOLD,
    has_code,
    has_vision,
    infer_task_type,
)


def _req(*contents: str) -> ChatRequest:
    return ChatRequest(
        messages=[Message(role="user", content=c) for c in contents]
    )


def _req_image() -> ChatRequest:
    return ChatRequest(
        messages=[
            Message(
                role="user",
                content=[
                    {"type": "text", "text": "Décris cette image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            )
        ]
    )


def _req_long() -> ChatRequest:
    big = "x " * (LONG_CONTEXT_CHAR_THRESHOLD + 100)
    return ChatRequest(messages=[Message(role="user", content=big)])


# ---------------------------------------------------------------------------
# has_vision
# ---------------------------------------------------------------------------

def test_has_vision_detects_image_url():
    assert has_vision(_req_image()) is True


def test_has_vision_false_for_text():
    assert has_vision(_req("simple text")) is False


# ---------------------------------------------------------------------------
# has_code
# ---------------------------------------------------------------------------

def test_has_code_backticks():
    assert has_code(_req("voici mon code:\n```python\nprint('hello')\n```")) is True


def test_has_code_def_keyword():
    assert has_code(_req("j'ai écrit def my_function(): pass")) is True


def test_has_code_function_keyword():
    assert has_code(_req("can you fix this function that's broken?")) is True


def test_has_code_class_keyword():
    assert has_code(_req("refactor this class please")) is True


def test_has_code_refactor_keyword():
    assert has_code(_req("refactor my code")) is True


def test_has_code_bug_keyword():
    assert has_code(_req("there's a bug in my script")) is True


def test_has_code_false_for_plain():
    assert has_code(_req("quel temps fait-il aujourd'hui ?")) is False


# ---------------------------------------------------------------------------
# infer_task_type
# ---------------------------------------------------------------------------

def test_infer_default_for_plain_text():
    assert infer_task_type(_req("bonjour, comment vas-tu ?")) == TASK_DEFAULT


def test_infer_code_for_backticks():
    assert infer_task_type(_req("corrige ce code:\n```js\nconst x=1\n```")) == TASK_CODE


def test_infer_code_for_keyword():
    assert infer_task_type(_req("refactor this function for me")) == TASK_CODE


def test_infer_vision_for_image():
    assert infer_task_type(_req_image()) == TASK_VISION


def test_infer_long_context():
    assert infer_task_type(_req_long()) == TASK_LONG_CONTEXT


def test_vision_priority_over_long_context():
    """Un message avec image ET beaucoup de texte → vision (pas long_context)."""
    big_text = "x " * (LONG_CONTEXT_CHAR_THRESHOLD + 100)
    req = ChatRequest(
        messages=[
            Message(
                role="user",
                content=[
                    {"type": "text", "text": big_text},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            )
        ]
    )
    assert infer_task_type(req) == TASK_VISION


def test_vision_priority_over_code():
    """Image + contenu code → vision."""
    req = ChatRequest(
        messages=[
            Message(
                role="user",
                content=[
                    {"type": "text", "text": "```python\ndef foo(): pass\n```"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            )
        ]
    )
    assert infer_task_type(req) == TASK_VISION


def test_long_context_priority_over_code():
    """Message très long avec 'def ' → long_context (pas code)."""
    big = "def foo(): " + "x " * (LONG_CONTEXT_CHAR_THRESHOLD + 100)
    assert infer_task_type(_req(big)) == TASK_LONG_CONTEXT
