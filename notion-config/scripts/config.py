#!/usr/bin/env python3
"""Notion 데이터베이스 매핑 설정 관리 CLI.

~/.notion-skills/config.yaml의 data_types 섹션을 관리한다.
notion-update, notion-search가 읽는 config.yaml 스키마와 일치하도록 저장.

사용법:
    python config.py add <type_name> <database_id>   # DB 스키마 조회 후 data_types에 추가
    python config.py list                             # 등록된 data_types 목록
    python config.py remove <type_name>               # data_types에서 삭제
    python config.py show <type_name>                 # 특정 data_type 상세 조회
    python config.py set-default <type_name>          # default_type 설정

Exit codes:
    0 = 성공
    1 = 설정 누락 (setup 필요)
    2 = API 오류
    3 = 입력 오류
"""
from __future__ import annotations

import sys
from pathlib import Path

# notion-shared 모듈 경로 추가
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SKILLS_DIR / "notion-shared"))

from notion_wrapper import NotionWrapper, get_token, output_json  # noqa: E402
from config_loader import load_config, save_config  # noqa: E402


def _require_token() -> str:
    """NOTION_TOKEN을 확인하고 반환한다. 없으면 에러 출력 후 종료."""
    token = get_token()
    if not token:
        output_json(
            False,
            error="NOTION_TOKEN이 설정되지 않았습니다.",
            hint="/notion-setup을 먼저 실행하세요.",
        )
        sys.exit(1)
    return token


def _slugify_field_name(prop_name: str) -> str:
    """Notion property 이름을 field_name으로 변환한다 (한글/공백 → 영문 snake_case)."""
    import re
    # 한글/기호를 제거하고 영문만 남김
    cleaned = re.sub(r"[^\w]", "_", prop_name.lower()).strip("_")
    return cleaned or prop_name.lower()


def _fetch_schema_as_field_map(nw: NotionWrapper, database_id: str) -> dict | None:
    """Notion API로 DB 스키마를 조회하여 config.yaml field_map 형식으로 변환한다.

    Returns:
        {"db_title": "...", "field_map": {field_name: {property, type, ...}}}
    """
    try:
        db = nw.retrieve_database(database_id)
    except Exception as e:
        output_json(False, error=f"DB 스키마 조회 실패: {e}")
        return None

    data_sources = db.get("data_sources") or []
    data_source_id = ""
    raw_props = db.get("properties") or {}
    if not raw_props and data_sources:
        data_source_id = data_sources[0].get("id", "")
        try:
            ds = nw.client.data_sources.retrieve(data_source_id=data_source_id)
            raw_props = ds.get("properties") or {}
        except Exception as e:
            output_json(False, error=f"data_source 스키마 조회 실패: {e}")
            return None
    field_map: dict = {}

    # 이름 충돌 방지용 카운터
    used_names: set[str] = set()

    for prop_name, prop_info in raw_props.items():
        prop_type = prop_info.get("type", "unknown")

        # field_name 생성 (한글 property → 영문 snake_case)
        base = _slugify_field_name(prop_name)
        field_name = base
        counter = 2
        while field_name in used_names:
            field_name = f"{base}_{counter}"
            counter += 1
        used_names.add(field_name)

        entry: dict = {"property": prop_name, "type": prop_type}

        # select/multi_select/status는 옵션 목록도 저장
        if prop_type in ("select", "multi_select", "status"):
            options = prop_info.get(prop_type, {}).get("options", [])
            entry["options"] = [o["name"] for o in options]

        field_map[field_name] = entry

    return {
        "db_title": db.get("title", [{}])[0].get("plain_text", "Untitled") if db.get("title") else "Untitled",
        "field_map": field_map,
        "data_source_id": data_source_id,
    }


def cmd_add(args: list[str]) -> int:
    """data_types에 새 데이터 타입을 추가한다."""
    if len(args) < 2:
        output_json(False, error="사용법: config.py add <type_name> <database_id>")
        return 3

    type_name, database_id = args[0], args[1]

    # 기존 설정 로드
    config = load_config()
    data_types = config.setdefault("data_types", {})
    if type_name in data_types:
        output_json(
            False,
            error=f"'{type_name}'은(는) 이미 등록되어 있습니다.",
            existing=data_types[type_name],
            hint="덮어쓰려면 먼저 remove 후 다시 add 하세요.",
        )
        return 3

    # DB 스키마 조회
    _require_token()
    nw = NotionWrapper()
    schema = _fetch_schema_as_field_map(nw, database_id)
    if schema is None:
        return 2

    # data_types에 추가
    data_types[type_name] = {
        "database_id": database_id,
        "data_source_id": schema.get("data_source_id", ""),
        "description": schema["db_title"],
        "field_map": schema["field_map"],
    }

    # 첫 등록이면 default_type으로 설정
    if not config.get("default_type"):
        config["default_type"] = type_name

    save_config(config)

    output_json(
        True,
        message=f"'{type_name}' 데이터 타입이 등록되었습니다.",
        type_name=type_name,
        database_id=database_id,
        db_title=schema["db_title"],
        field_count=len(schema["field_map"]),
        fields=list(schema["field_map"].keys()),
        is_default=(config.get("default_type") == type_name),
    )
    return 0


def cmd_list(_args: list[str]) -> int:
    """등록된 모든 data_types를 출력한다."""
    config = load_config()
    data_types = config.get("data_types", {})
    default_type = config.get("default_type")

    if not data_types:
        output_json(
            True,
            message="등록된 데이터 타입이 없습니다.",
            hint="/notion-config add <type_name> <database_id>로 추가하세요.",
            data_types=[],
        )
        return 0

    result_list = []
    for type_name, type_info in data_types.items():
        if not isinstance(type_info, dict):
            continue
        field_map = type_info.get("field_map", {})
        field_summary = [
            f"{name} ({info.get('type', '?')})"
            for name, info in field_map.items()
        ]
        result_list.append({
            "type_name": type_name,
            "database_id": type_info.get("database_id", ""),
            "description": type_info.get("description", ""),
            "is_default": type_name == default_type,
            "fields": field_summary,
        })

    output_json(
        True,
        message=f"총 {len(result_list)}개 데이터 타입이 등록되어 있습니다.",
        default_type=default_type,
        data_types=result_list,
    )
    return 0


def cmd_remove(args: list[str]) -> int:
    """data_types에서 항목을 삭제한다."""
    if len(args) < 1:
        output_json(False, error="사용법: config.py remove <type_name>")
        return 3

    type_name = args[0]
    config = load_config()
    data_types = config.get("data_types", {})

    if type_name not in data_types:
        output_json(
            False,
            error=f"'{type_name}'은(는) 등록되지 않은 데이터 타입입니다.",
            registered=list(data_types.keys()),
        )
        return 3

    removed = data_types.pop(type_name)

    # default_type이었으면 해제
    if config.get("default_type") == type_name:
        config["default_type"] = next(iter(data_types.keys()), None)

    save_config(config)

    output_json(
        True,
        message=f"'{type_name}' 데이터 타입이 삭제되었습니다.",
        removed_type=type_name,
        removed_database_id=removed.get("database_id", ""),
        new_default=config.get("default_type"),
    )
    return 0


def cmd_show(args: list[str]) -> int:
    """특정 data_type의 상세 정보를 출력한다."""
    if len(args) < 1:
        output_json(False, error="사용법: config.py show <type_name>")
        return 3

    type_name = args[0]
    config = load_config()
    data_types = config.get("data_types", {})

    if type_name not in data_types:
        output_json(
            False,
            error=f"'{type_name}'은(는) 등록되지 않은 데이터 타입입니다.",
            registered=list(data_types.keys()),
        )
        return 3

    type_info = data_types[type_name]
    output_json(
        True,
        type_name=type_name,
        is_default=(config.get("default_type") == type_name),
        database_id=type_info.get("database_id", ""),
        description=type_info.get("description", ""),
        field_map=type_info.get("field_map", {}),
        search=type_info.get("search", {}),
    )
    return 0


def cmd_set_default(args: list[str]) -> int:
    """default_type을 설정한다."""
    if len(args) < 1:
        output_json(False, error="사용법: config.py set-default <type_name>")
        return 3

    type_name = args[0]
    config = load_config()
    data_types = config.get("data_types", {})

    if type_name not in data_types:
        output_json(
            False,
            error=f"'{type_name}'은(는) 등록되지 않은 데이터 타입입니다.",
            registered=list(data_types.keys()),
        )
        return 3

    config["default_type"] = type_name
    save_config(config)

    output_json(
        True,
        message=f"default_type이 '{type_name}'(으)로 설정되었습니다.",
        default_type=type_name,
    )
    return 0


COMMANDS = {
    "add": cmd_add,
    "list": cmd_list,
    "remove": cmd_remove,
    "show": cmd_show,
    "set-default": cmd_set_default,
}


def main() -> int:
    if len(sys.argv) < 2:
        output_json(
            False,
            error="명령어를 지정하세요.",
            usage="config.py <add|list|remove|show|set-default> [args...]",
            commands={
                "add <type_name> <database_id>": "DB 스키마를 조회하고 data_types에 추가",
                "list": "등록된 모든 data_types 출력",
                "remove <type_name>": "지정된 data_type 삭제",
                "show <type_name>": "특정 data_type 상세 조회",
                "set-default <type_name>": "default_type 설정",
            },
        )
        return 3

    command = sys.argv[1]
    handler = COMMANDS.get(command)

    if not handler:
        output_json(
            False,
            error=f"알 수 없는 명령어: {command}",
            available=list(COMMANDS.keys()),
        )
        return 3

    return handler(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
