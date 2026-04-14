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

import argparse
import re
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


# 한글 property 이름 → 의미 기반 영문 키 사전
_KOREAN_TO_ENGLISH: dict[str, str] = {
    "작업": "title",
    "제목": "title",
    "이름": "name",
    "상태": "status",
    "진행상태": "status",
    "진행 상태": "status",
    "개발팀진행상태": "dev_status",
    "담당자": "assignee",
    "우선순위": "priority",
    "마감일": "due_date",
    "완료일": "completed_at",
    "작성일": "created_at",
    "작성자": "author",
    "설명": "description",
    "종류": "category",
    "카테고리": "category",
    "태그": "tags",
    "소속팀": "team",
    "세부 소속": "sub_team",
    "세부소속": "sub_team",
    "프로젝트": "project",
    "관련 링크": "links",
    "관련링크": "links",
    "하위 작업": "subtasks",
    "하위 작업_1": "subtasks",
    "상위 작업": "parent_task",
    "후속 작업": "followups",
    "선행 작업": "prerequisites",
    "참조인": "watchers",
    "참조 링크": "reference_links",
    "참조링크": "reference_links",
    "파일/사진": "attachments",
    "파일": "attachments",
    "사진": "images",
    "버전": "version",
    "현재 적용버전": "current_version",
    "배포일": "released_at",
    "실제 배포 시간": "deployed_at",
    "팀": "team",
    "서비스": "service",
    "도메인": "domain",
    "기능 이름": "feature_name",
    "변경이력": "history",
    "최종수정일": "updated_at",
    "규모(명)": "scale",
    "커스터마이징여부": "is_customized",
    "디자인 링크 (figma)": "design_link",
    "디자인 링크": "design_link",
}


# 단일 인스턴스 타입은 타입 이름을 키로 사용 (DB당 한 개만 존재할 확률이 높은 시스템 필드)
_SINGLETON_TYPE_KEYS: dict[str, str] = {
    "title": "title",
    "created_time": "created_at",
    "last_edited_time": "updated_at",
    "created_by": "created_by",
    "last_edited_by": "updated_by",
    "unique_id": "unique_id",
}


def _slugify_field_name(prop_name: str) -> str:
    """Notion property 이름을 field_name으로 변환한다 (한글/공백 → 영문 snake_case fallback)."""
    cleaned = re.sub(r"[^\w]", "_", prop_name.lower()).strip("_")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned or "field"


def _is_ascii_word(s: str) -> bool:
    return bool(s) and all(ord(c) < 128 for c in s)


def _english_snake(prop_name: str) -> str:
    """영문 property 이름을 snake_case로."""
    s = re.sub(r"[^\w\s]", " ", prop_name).strip()
    s = re.sub(r"\s+", "_", s)
    return s.lower() or "field"


def _semantic_field_name(prop_name: str, prop_type: str, role: str | None) -> str:
    """의미 기반 영문 키를 결정한다.

    우선순위:
      1. role이 있으면 role 이름
      2. 단일 인스턴스 시스템 타입이면 타입별 기본 키
      3. 한글 사전 매핑
      4. 영문 property면 snake_case
      5. fallback: _slugify_field_name
    """
    if role:
        return role

    if prop_type in _SINGLETON_TYPE_KEYS:
        return _SINGLETON_TYPE_KEYS[prop_type]

    normalized = re.sub(r"[()\[\]{}]", "", prop_name).strip()
    key = _KOREAN_TO_ENGLISH.get(normalized)
    if key:
        return key

    if _is_ascii_word(normalized):
        return _english_snake(normalized)

    return _slugify_field_name(prop_name)


# 이름 패턴 기반 role 추론 규칙
_ROLE_PATTERNS: list[tuple[str, str, str]] = [
    # (role, prop_type_regex, prop_name_regex)
    ("status", r"^(status|select)$", r"상태|진행|status|state"),
    ("priority", r"^select$", r"우선|priority"),
    ("category", r"^select$", r"종류|카테고리|category|kind|type"),
    ("assignee", r"^people$", r"담당|assignee|owner"),
    ("author", r"^people$", r"작성|author"),
    ("watchers", r"^people$", r"참조|watcher|reviewer"),
    ("due_date", r"^date$", r"마감|due|deadline"),
    ("completed_at", r"^date$", r"완료|completed|done"),
    ("created_at", r"^date$", r"작성|created|start"),
    ("released_at", r"^date$", r"배포|release"),
    ("tags", r"^multi_select$", r"태그|tags?\b|labels?"),
    ("team", r"^(multi_select|relation)$", r"소속팀|\bteam"),
    ("sub_team", r"^(multi_select|relation)$", r"세부\s*소속|sub.?team"),
    ("project", r"^relation$", r"프로젝트|project"),
    ("links", r"^url$", r"링크|link|url"),
]


def _infer_role(
    prop_name: str,
    prop_type: str,
    used_roles: set[str],
) -> str | None:
    """property에 대해 role을 추론한다. 이미 사용된 role은 건너뛴다 (title, unique_id 등 중복 불허)."""
    # 확정 타입 — 이름 검사 불필요
    if prop_type == "title" and "title" not in used_roles:
        return "title"
    if prop_type == "unique_id" and "unique_id" not in used_roles:
        return "unique_id"
    if prop_type == "created_time" and "created_at" not in used_roles:
        return "created_at"
    if prop_type == "last_edited_time" and "updated_at" not in used_roles:
        return "updated_at"
    if prop_type == "created_by" and "created_by" not in used_roles:
        return "created_by"
    if prop_type == "last_edited_by" and "updated_by" not in used_roles:
        return "updated_by"

    # 이름 패턴 기반
    name_lower = prop_name.lower()
    for role, type_re, name_re in _ROLE_PATTERNS:
        if role in used_roles:
            continue
        if not re.match(type_re, prop_type):
            continue
        if re.search(name_re, name_lower) or re.search(name_re, prop_name):
            return role

    return None


def _build_search_config(field_map: dict) -> dict:
    """field_map의 role 힌트를 보고 search 블록을 자동 생성한다."""
    search: dict = {}

    for entry in field_map.values():
        if entry.get("role") == "unique_id":
            search["id_property"] = entry["property"]
            search["id_type"] = "unique_id"
            break

    display_roles = ["title", "status", "priority", "assignee", "due_date"]
    display_fields: list[str] = []
    for role in display_roles:
        for key, entry in field_map.items():
            if entry.get("role") == role:
                display_fields.append(key)
                break
    if display_fields:
        search["display_fields"] = display_fields

    return search


def _fetch_schema_as_field_map(nw: NotionWrapper, database_id: str) -> dict | None:
    """Notion API로 DB 스키마를 조회하여 config.yaml field_map 형식으로 변환한다.

    Returns:
        {"db_title": "...", "field_map": {key: {property, type, role?, options?}}, "search": {...}, "data_source_id": "..."}
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

    # 1차 패스: role 추론 (title 등 '하나만' role이 우선 배치되도록 원본 순서 유지)
    used_roles: set[str] = set()
    prop_roles: dict[str, str | None] = {}
    for prop_name, prop_info in raw_props.items():
        prop_type = prop_info.get("type", "unknown")
        role = _infer_role(prop_name, prop_type, used_roles)
        if role:
            used_roles.add(role)
        prop_roles[prop_name] = role

    # 2차 패스: semantic 키 생성 + 충돌 해결
    field_map: dict = {}
    used_keys: set[str] = set()
    for prop_name, prop_info in raw_props.items():
        prop_type = prop_info.get("type", "unknown")
        role = prop_roles[prop_name]

        base = _semantic_field_name(prop_name, prop_type, role)
        key = base
        counter = 2
        while key in used_keys:
            key = f"{base}_{counter}"
            counter += 1
        used_keys.add(key)

        entry: dict = {"property": prop_name, "type": prop_type}
        if role:
            entry["role"] = role

        if prop_type in ("select", "multi_select", "status"):
            options = prop_info.get(prop_type, {}).get("options", [])
            entry["options"] = [o["name"] for o in options]

        field_map[key] = entry

    db_title = "Untitled"
    if db.get("title"):
        db_title = db.get("title", [{}])[0].get("plain_text", "Untitled")
    elif data_sources:
        ds_name = data_sources[0].get("name", "")
        if ds_name:
            db_title = ds_name

    return {
        "db_title": db_title,
        "field_map": field_map,
        "data_source_id": data_source_id,
        "search": _build_search_config(field_map),
    }


def cmd_add(args: list[str]) -> int:
    """data_types에 새 데이터 타입을 추가한다.

    기본 동작은 드라이런(스키마 조회 + 매핑 미리보기).
    --yes 를 주면 실제로 저장하고, --force 를 주면 기존 엔트리를 덮어쓴다.
    """
    parser = argparse.ArgumentParser(prog="config.py add")
    parser.add_argument("type_name")
    parser.add_argument("database_id")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="드라이런 없이 즉시 저장",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 type_name이 등록돼 있어도 덮어쓴다",
    )
    try:
        ns = parser.parse_args(args)
    except SystemExit:
        output_json(
            False,
            error="사용법: config.py add <type_name> <database_id> [--yes] [--force]",
        )
        return 3

    type_name = ns.type_name
    database_id = ns.database_id

    config = load_config()
    data_types = config.setdefault("data_types", {})
    already_exists = type_name in data_types
    if already_exists and not ns.force:
        output_json(
            False,
            error=f"'{type_name}'은(는) 이미 등록되어 있습니다.",
            existing=data_types[type_name],
            hint="덮어쓰려면 --force 를 함께 사용하세요.",
        )
        return 3

    _require_token()
    nw = NotionWrapper()
    schema = _fetch_schema_as_field_map(nw, database_id)
    if schema is None:
        return 2

    new_entry: dict = {
        "database_id": database_id,
        "data_source_id": schema.get("data_source_id", ""),
        "description": schema["db_title"],
        "field_map": schema["field_map"],
    }
    if schema.get("search"):
        new_entry["search"] = schema["search"]

    roles = {
        key: entry["role"]
        for key, entry in schema["field_map"].items()
        if entry.get("role")
    }

    if not ns.yes:
        output_json(
            True,
            dry_run=True,
            message=f"[드라이런] '{type_name}' 매핑 미리보기. 확정하려면 --yes 를 추가하세요.",
            type_name=type_name,
            database_id=database_id,
            db_title=schema["db_title"],
            field_count=len(schema["field_map"]),
            fields=list(schema["field_map"].keys()),
            roles=roles,
            search=schema.get("search", {}),
            would_overwrite=already_exists,
            hint="확정: config.py add <type_name> <database_id> --yes"
            + (" --force" if already_exists else ""),
            preview=new_entry,
        )
        return 0

    # 실제 저장
    data_types[type_name] = new_entry

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
        roles=roles,
        search=schema.get("search", {}),
        overwrote=already_exists,
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
