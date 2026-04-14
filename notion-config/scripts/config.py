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
from semantic_dictionary import load_semantic_dictionary  # noqa: E402

_SEMANTIC = load_semantic_dictionary()
_KOREAN_TO_ENGLISH: dict[str, str] = _SEMANTIC.get("korean_to_english", {})
_SINGLETON_TYPE_KEYS: dict[str, str] = _SEMANTIC.get("singleton_type_keys", {})
_ROLE_PATTERNS: list[tuple[str, str, str]] = [
    (p["role"], p["prop_type"], p["prop_name"])
    for p in _SEMANTIC.get("role_patterns", [])
    if isinstance(p, dict) and "role" in p
]


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


def _extract_page_title(page: dict) -> str:
    """Notion page 객체에서 title 문자열을 추출한다."""
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            parts = prop.get("title") or []
            return "".join(p.get("plain_text", "") for p in parts).strip()
    return ""


def _resolve_relation_target_data_source(nw: NotionWrapper, relation_info: dict) -> str:
    """relation 프로퍼티의 target database_id → 첫 data_source_id 해석."""
    target_db_id = relation_info.get("database_id") or ""
    if not target_db_id:
        return ""
    try:
        target_db = nw.retrieve_database(target_db_id)
    except Exception:
        return ""
    data_sources = target_db.get("data_sources") or []
    return data_sources[0]["id"] if data_sources else ""


def _fetch_users_lookup(nw: NotionWrapper) -> dict[str, str]:
    """workspace 사용자 → {name: user_id} 맵 생성. bot 제외."""
    lookup: dict[str, str] = {}
    try:
        users = nw.list_users()
    except Exception:
        return lookup
    for user in users:
        if user.get("type") != "person":
            continue
        name = (user.get("name") or "").strip()
        if name:
            lookup[name] = user["id"]
    return lookup


def _fetch_relation_lookup(nw: NotionWrapper, data_source_id: str, limit: int = 200) -> dict[str, str]:
    """data_source의 페이지 목록을 순회하여 {title: page_id} 맵 생성."""
    lookup: dict[str, str] = {}
    try:
        result = nw.client.data_sources.query(data_source_id=data_source_id, page_size=100)
    except Exception:
        return lookup

    fetched = 0
    while True:
        for page in result.get("results", []):
            title = _extract_page_title(page)
            if title:
                lookup[title] = page["id"]
            fetched += 1
            if fetched >= limit:
                return lookup
        if not result.get("has_more"):
            break
        try:
            result = nw.client.data_sources.query(
                data_source_id=data_source_id,
                page_size=100,
                start_cursor=result.get("next_cursor"),
            )
        except Exception:
            break
    return lookup


def _fetch_schema_lookups(nw: NotionWrapper, field_map: dict) -> dict[str, dict[str, str]]:
    """field_map의 relation 엔트리들에 대해 {data_source_id: {title: page_id}} 맵 생성."""
    result: dict[str, dict[str, str]] = {}
    for entry in field_map.values():
        if entry.get("type") != "relation":
            continue
        ds_id = entry.get("relation_data_source_id")
        if not ds_id or ds_id in result:
            continue
        result[ds_id] = _fetch_relation_lookup(nw, ds_id)
    return result


def _merge_lookups(existing: dict, fresh_users: dict, fresh_relations: dict) -> dict:
    """기존 lookups 위에 새 users/relations를 병합한다."""
    merged = dict(existing or {})
    if fresh_users:
        existing_users = dict(merged.get("users") or {})
        existing_users.update(fresh_users)
        merged["users"] = existing_users
    if fresh_relations:
        existing_relations = dict(merged.get("relations") or {})
        for ds_id, mapping in fresh_relations.items():
            existing_relations[ds_id] = mapping
        merged["relations"] = existing_relations
    return merged


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

        if prop_type == "relation":
            rel_info = prop_info.get("relation", {})
            target_ds_id = _resolve_relation_target_data_source(nw, rel_info)
            if target_ds_id:
                entry["relation_data_source_id"] = target_ds_id

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

    # lookups 자동 수집 (users + relation targets)
    fresh_users = _fetch_users_lookup(nw)
    fresh_relations = _fetch_schema_lookups(nw, schema["field_map"])
    lookups_summary = {
        "users": len(fresh_users),
        "relations": {ds: len(m) for ds, m in fresh_relations.items()},
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
            lookups_to_add=lookups_summary,
            would_overwrite=already_exists,
            hint="확정: config.py add <type_name> <database_id> --yes"
            + (" --force" if already_exists else ""),
            preview=new_entry,
        )
        return 0

    # 실제 저장
    data_types[type_name] = new_entry
    config["lookups"] = _merge_lookups(
        config.get("lookups") or {}, fresh_users, fresh_relations
    )

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
        lookups_added=lookups_summary,
        overwrote=already_exists,
        is_default=(config.get("default_type") == type_name),
    )
    return 0


def cmd_refresh_lookups(args: list[str]) -> int:
    """등록된 data_type(s)의 lookups(users, relation targets)를 다시 수집한다.

    사용법:
        config.py refresh-lookups [type_name] [--yes]
    type_name을 생략하면 등록된 모든 타입에 대해 수행한다.
    기본은 드라이런(카운트만 출력).
    """
    parser = argparse.ArgumentParser(prog="config.py refresh-lookups")
    parser.add_argument("type_name", nargs="?", default=None)
    parser.add_argument("--yes", action="store_true", help="실제로 저장한다")
    try:
        ns = parser.parse_args(args)
    except SystemExit:
        output_json(False, error="사용법: config.py refresh-lookups [type_name] [--yes]")
        return 3

    config = load_config()
    data_types = config.get("data_types") or {}
    if not data_types:
        output_json(False, error="등록된 데이터 타입이 없습니다.")
        return 3

    targets: list[str]
    if ns.type_name:
        if ns.type_name not in data_types:
            output_json(
                False,
                error=f"'{ns.type_name}'은(는) 등록되지 않은 데이터 타입입니다.",
                registered=list(data_types.keys()),
            )
            return 3
        targets = [ns.type_name]
    else:
        targets = list(data_types.keys())

    _require_token()
    nw = NotionWrapper()

    fresh_users = _fetch_users_lookup(nw)
    fresh_relations: dict[str, dict[str, str]] = {}
    per_type: dict[str, dict[str, int]] = {}
    for t in targets:
        field_map = (data_types[t] or {}).get("field_map") or {}
        t_relations = _fetch_schema_lookups(nw, field_map)
        per_type[t] = {ds: len(m) for ds, m in t_relations.items()}
        fresh_relations.update(t_relations)

    summary = {
        "users": len(fresh_users),
        "relations": {ds: len(m) for ds, m in fresh_relations.items()},
        "per_type": per_type,
    }

    if not ns.yes:
        output_json(
            True,
            dry_run=True,
            message="[드라이런] refresh-lookups 미리보기. 확정하려면 --yes 를 추가하세요.",
            targets=targets,
            lookups_to_add=summary,
        )
        return 0

    config["lookups"] = _merge_lookups(
        config.get("lookups") or {}, fresh_users, fresh_relations
    )
    save_config(config)

    output_json(
        True,
        message="lookups 가 업데이트되었습니다.",
        targets=targets,
        lookups_added=summary,
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
    "refresh-lookups": cmd_refresh_lookups,
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
