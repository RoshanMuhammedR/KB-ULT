from __future__ import annotations

from typing import Any


def sanitize_text_for_storage(value: str) -> str:
    return value.replace("\x00", "")


def sanitize_json_for_storage(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text_for_storage(value)
    if isinstance(value, list):
        return [sanitize_json_for_storage(item) for item in value]
    if isinstance(value, dict):
        return {
            sanitize_text_for_storage(key) if isinstance(key, str) else key: sanitize_json_for_storage(item)
            for key, item in value.items()
        }
    return value
