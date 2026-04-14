#!/usr/bin/env python3
"""Notion 스킬 설정 로더.

~/.notion-skills/config.yaml에서 데이터 타입·필드 매핑 설정을 로드한다.
모든 notion-* 스킬이 공유하는 설정 읽기/파싱/기본값 처리 모듈.

config.yaml 스키마:
    version: "1"
    default_type: ticket

    data_types:
      ticket:
        database_id: "abc123..."
        data_source_id: "..."
        description: "개발 작업 티켓"
        field_map:
          name: { property: "작업", type: title, required: true }
          status: { property: "상태", type: status, default: "Not started" }
          assignee: { property: "담당자", type: people }
        search:
          display_fields: [name, status]
          id_pattern: "AHD-{number}"

    lookups:
      git_user_map: { ... }
      display_name_map: { ... }
      relations: { ... }

사용법:
    from config_loader import load_config, get_type_config, get_field_map
    cfg = load_config()
    tc = get_type_config(cfg, "ticket")
    fm = get_field_map(cfg, "ticket")
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ── 글로벌 설정 경로 ──
CONFIG_DIR = Path.home() / ".notion-skills"
CONFIG_YAML_PATH = CONFIG_DIR / "config.yaml"

# ── 기본 설정 ──
_DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1",
    "default_type": None,
    "data_types": {},
    "lookups": {},
}


def _parse_yaml(text: str) -> dict[str, Any]:
    """YAML 텍스트를 파싱한다. PyYAML이 있으면 사용, 없으면 JSON 폴백."""
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        return json.loads(text)


def load_config() -> dict[str, Any]:
    """설정 파일을 로드하고 기본값을 병합하여 반환한다.

    Returns:
        완전한 설정 dict (data_types, default_type, lookups 키 보장)
    """
    if not CONFIG_YAML_PATH.exists():
        return {**_DEFAULT_CONFIG, "data_types": {}}

    raw = CONFIG_YAML_PATH.read_text(encoding="utf-8")
    if not raw.strip():
        return {**_DEFAULT_CONFIG, "data_types": {}}

    parsed = _parse_yaml(raw)
    return _merge_defaults(parsed)


def _merge_defaults(parsed: dict[str, Any]) -> dict[str, Any]:
    """파싱된 설정에 기본값을 병합한다."""
    config: dict[str, Any] = {**_DEFAULT_CONFIG}
    config["version"] = parsed.get("version", "1")
    config["default_type"] = parsed.get("default_type")
    config["data_types"] = parsed.get("data_types") or {}
    config["lookups"] = parsed.get("lookups") or {}
    return config


def get_type_config(config: dict[str, Any], type_name: str | None = None) -> dict[str, Any]:
    """특정 데이터 타입의 설정을 반환한다.

    Args:
        config: load_config()의 반환값
        type_name: 데이터 타입 이름 (ticket, document 등). None이면 default_type 사용

    Returns:
        {"database_id": "...", "field_map": {...}, "search": {...}, ...}

    Raises:
        KeyError: type_name이 존재하지 않을 때
    """
    data_types = config.get("data_types", {})
    if type_name is None:
        type_name = config.get("default_type")
    if not type_name:
        raise KeyError("데이터 타입이 지정되지 않았고 default_type도 설정되지 않았습니다")
    if type_name not in data_types:
        available = ", ".join(data_types.keys()) if data_types else "(없음)"
        raise KeyError(f"데이터 타입 '{type_name}'을 찾을 수 없습니다. 등록된 타입: {available}")
    return data_types[type_name]


def get_database_id(config: dict[str, Any], type_name: str | None = None) -> str:
    """데이터 타입에 해당하는 database_id를 반환한다."""
    tc = get_type_config(config, type_name)
    db_id = tc.get("database_id", "")
    if not db_id:
        raise ValueError(f"데이터 타입 '{type_name}'에 database_id가 설정되지 않았습니다")
    return db_id


def get_field_map(config: dict[str, Any], type_name: str | None = None) -> dict[str, Any]:
    """데이터 타입의 field_map을 notion_client.build_properties 호환 형식으로 반환한다.

    Returns:
        {field_name: {"property": "Notion속성명", "type": "타입"}, ...}
    """
    tc = get_type_config(config, type_name)
    field_map = tc.get("field_map", {})

    result: dict[str, Any] = {}
    for field_name, info in field_map.items():
        if not isinstance(info, dict):
            continue
        result[field_name] = {
            "property": info.get("property", field_name),
            "type": info.get("type", "rich_text"),
        }
        # 추가 메타 보존 (options, default, required 등)
        for extra in ("options", "default", "required", "description"):
            if extra in info:
                result[field_name][extra] = info[extra]
    return result


def get_search_config(config: dict[str, Any], type_name: str | None = None) -> dict[str, Any]:
    """데이터 타입의 검색 설정을 반환한다.

    Returns:
        {"display_fields": [...], "id_pattern": "...", "id_property": "...", "id_type": "..."}
    """
    tc = get_type_config(config, type_name)
    return tc.get("search", {})


def get_lookups(config: dict[str, Any]) -> dict[str, Any]:
    """ID 룩업 테이블을 반환한다."""
    return config.get("lookups", {})


def list_data_types(config: dict[str, Any]) -> list[dict[str, Any]]:
    """등록된 모든 데이터 타입의 요약 목록을 반환한다.

    Returns:
        [{"name": "...", "database_id": "...", "field_count": N, "is_default": bool}, ...]
    """
    data_types = config.get("data_types", {})
    default_type = config.get("default_type")
    result: list[dict[str, Any]] = []
    for name, type_info in data_types.items():
        if not isinstance(type_info, dict):
            continue
        result.append({
            "name": name,
            "database_id": type_info.get("database_id", ""),
            "description": type_info.get("description", ""),
            "field_count": len(type_info.get("field_map", {})),
            "is_default": name == default_type,
        })
    return result


def save_config(config: dict[str, Any]) -> None:
    """설정을 config.yaml에 저장한다."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        text = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        text = json.dumps(config, ensure_ascii=False, indent=2)
    CONFIG_YAML_PATH.write_text(text, encoding="utf-8")
