from __future__ import annotations

from core.models import ChatRequest

TASK_DEFAULT = "default"
TASK_LONG_CONTEXT = "long_context"
TASK_VISION = "vision"
TASK_CODE = "code"

# ~8 000 tokens × 3 chars/token (correspond au _CEREBRAS_CHAR_LIMIT existant)
LONG_CONTEXT_CHAR_THRESHOLD = 24_000

_CODE_KEYWORDS = frozenset({
    "def ",
    "function ",
    "class ",
    "bug",
    "refactor",
})


def has_vision(request: ChatRequest) -> bool:
    for msg in request.messages:
        if isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def total_chars(request: ChatRequest) -> int:
    total = 0
    for msg in request.messages:
        if isinstance(msg.content, str):
            total += len(msg.content)
        elif isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(part.get("text", ""))
    return total


def has_code(request: ChatRequest) -> bool:
    for msg in request.messages:
        content = ""
        if isinstance(msg.content, str):
            content = msg.content
        elif isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    content += part.get("text", "")
        if "```" in content:
            return True
        lower = content.lower()
        if any(kw in lower for kw in _CODE_KEYWORDS):
            return True
    return False


def infer_task_type(request: ChatRequest) -> str:
    """Infer the task type from the request content.

    Priority: vision > long_context > code > default
    """
    if has_vision(request):
        return TASK_VISION
    if total_chars(request) > LONG_CONTEXT_CHAR_THRESHOLD:
        return TASK_LONG_CONTEXT
    if has_code(request):
        return TASK_CODE
    return TASK_DEFAULT
