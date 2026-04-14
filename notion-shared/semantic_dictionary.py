"""semantic_dictionary.yaml 로더.

notion-config add 가 DB 스키마를 읽어 field_map을 구성할 때 사용하는
한글/영문 property 이름 매핑 및 role 추론 패턴을 제공한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_DICT_PATH = Path(__file__).resolve().parent / "semantic_dictionary.yaml"

_DEFAULT: dict[str, Any] = {
    "korean_to_english": {},
    "singleton_type_keys": {
        "title": "title",
        "created_time": "created_at",
        "last_edited_time": "updated_at",
        "created_by": "created_by",
        "last_edited_by": "updated_by",
        "unique_id": "unique_id",
    },
    "role_patterns": [],
}


def load_semantic_dictionary() -> dict[str, Any]:
    """semantic_dictionary.yaml을 로드한다. 없으면 최소 기본값 반환."""
    if not _DICT_PATH.exists():
        return {**_DEFAULT}

    try:
        import yaml
    except ImportError:
        return {**_DEFAULT}

    try:
        parsed = yaml.safe_load(_DICT_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {**_DEFAULT}

    return {
        "korean_to_english": parsed.get("korean_to_english") or {},
        "singleton_type_keys": parsed.get("singleton_type_keys") or _DEFAULT["singleton_type_keys"],
        "role_patterns": parsed.get("role_patterns") or [],
    }
