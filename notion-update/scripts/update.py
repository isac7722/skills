#!/usr/bin/env python3
"""Notion 페이지 생성/업데이트 CLI.

config.yaml 매핑 기반으로 Notion DB에 페이지를 생성하거나 업데이트한다.

인터페이스:
    # 생성 (stdin JSON)
    echo '{"name":"제목", "status":"Not started"}' | python update.py --type ticket

    # 생성 (--data JSON)
    python update.py --type ticket --data '{"name":"제목"}'

    # 업데이트 (page_id 지정)
    python update.py --type ticket --page-id <id> --data '{"status":"Done"}'

    # 업데이트 (unique_id 지정)
    python update.py --type ticket --unique-id AHD-699 --data '{"status":"Done"}'

Exit codes:
    0 = 성공
    1 = 설정 누락 (setup/config 필요)
    2 = API 오류
    3 = 입력 오류
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# notion-shared를 import path에 추가
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SKILLS_DIR / "notion-shared"))

from config_loader import load_config, get_type_config, get_field_map, get_database_id, get_lookups
from notion_wrapper import NotionWrapper, build_properties, output_json
from markdown_parser import parse_markdown_to_children


# ── CLI 인자 파싱 ──

def build_parser() -> argparse.ArgumentParser:
    """argparse 파서를 구성한다."""
    parser = argparse.ArgumentParser(
        description="Notion 페이지 생성/업데이트 (config.yaml 매핑 기반)",
    )
    parser.add_argument(
        "--type", "-t",
        dest="type_name",
        help="데이터 타입 alias (config.yaml의 data_types 키). 미지정 시 default_type 사용",
    )
    parser.add_argument(
        "--data", "-d",
        help="필드 데이터 JSON 문자열. 미지정 시 stdin에서 읽음",
    )
    parser.add_argument(
        "--page-id",
        help="업데이트할 페이지 ID (지정 시 업데이트 모드)",
    )
    parser.add_argument(
        "--unique-id",
        help="업데이트할 페이지의 unique ID (예: AHD-699). 지정 시 업데이트 모드",
    )
    parser.add_argument(
        "--db",
        dest="type_name_alias",
        help="--type의 별칭 (하위 호환)",
    )
    return parser


def parse_data_json(raw: str) -> dict:
    """JSON 문자열을 파싱하고 유효성을 검증한다.

    Returns:
        파싱된 dict

    Raises:
        SystemExit: JSON 파싱 실패 또는 dict가 아닌 경우
    """
    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError as e:
        output_json(False, error=f"JSON 파싱 실패: {e}")
        sys.exit(3)

    if not isinstance(data, dict):
        output_json(False, error=f"JSON 데이터는 object여야 합니다 (받은 타입: {type(data).__name__})")
        sys.exit(3)

    return data


def read_input_data(args: argparse.Namespace) -> dict:
    """--data 인자 또는 stdin에서 데이터를 읽고 JSON 유효성을 검증한다."""
    if args.data:
        return parse_data_json(args.data)

    # stdin에서 읽기
    if sys.stdin.isatty():
        output_json(False, error="데이터가 필요합니다. --data 또는 stdin으로 JSON을 전달하세요")
        sys.exit(3)

    raw = sys.stdin.read().strip()
    if not raw:
        output_json(False, error="빈 입력입니다. JSON 데이터를 전달하세요")
        sys.exit(3)

    return parse_data_json(raw)


# ── 헬퍼 ──

def resolve_type_name(args: argparse.Namespace) -> str | None:
    """CLI 인자에서 데이터 타입 이름을 결정한다."""
    return args.type_name or args.type_name_alias or None


def _route_by_role(data: dict, field_map: dict) -> dict:
    """data의 role-like 키를 field_map 실제 키로 리매핑한다.

    우선순위:
      1. data의 키가 field_map에 그대로 존재하면 그대로 유지
      2. data의 키와 role이 일치하는 field_map 엔트리가 있으면 그 키로 리네임
      3. 매칭 실패 시 원본 유지 (body 같은 예약 키, 오타 등)
    """
    routed: dict = {}
    keys = set(field_map.keys())
    role_index: dict[str, str] = {}
    for key, entry in field_map.items():
        role = entry.get("role")
        if role and role not in role_index:
            role_index[role] = key

    for data_key, value in data.items():
        if data_key in keys:
            routed[data_key] = value
            continue
        target = role_index.get(data_key)
        if target:
            routed[target] = value
            continue
        routed[data_key] = value
    return routed


def _resolve_people_from_lookups(nw: NotionWrapper, data: dict, field_map: dict, lookups: dict) -> dict:
    """people 타입 필드를 Notion user ID로 resolve한다.

    우선순위:
      1. lookups.users 에 모든 이름이 있으면 API 호출 없이 바로 ID 매핑
      2. 부족하면 display_name_map 을 보조로 써서 nw.resolve_people 호출
    """
    users_lookup = lookups.get("users") or {}
    display_name_map = lookups.get("display_name_map") or {}
    props: dict = {}
    for field_name, mapping in field_map.items():
        if field_name not in data or mapping["type"] != "people":
            continue
        names = data[field_name] if isinstance(data[field_name], list) else [data[field_name]]
        names = [n for n in names if n]
        if not names:
            continue

        people_ids: list[dict] = []
        missing: list[str] = []
        for name in names:
            uid = users_lookup.get(name) or users_lookup.get(name.strip())
            if uid:
                people_ids.append({"object": "user", "id": uid})
            else:
                missing.append(name)

        if missing:
            resolved_missing = nw.resolve_people(missing, display_name_map)
            people_ids.extend(resolved_missing)

        if people_ids:
            props[mapping["property"]] = {"people": people_ids}
    return props


def _resolve_relations_from_lookups(data: dict, field_map: dict, lookups: dict) -> dict:
    """relation 타입 필드를 target data_source의 {title: page_id} 맵으로 resolve한다."""
    relations_lookup = lookups.get("relations") or {}
    props: dict = {}
    for field_name, mapping in field_map.items():
        if field_name not in data or mapping["type"] != "relation":
            continue
        ds_id = mapping.get("relation_data_source_id")
        if not ds_id:
            continue
        target_map = relations_lookup.get(ds_id) or {}
        if not target_map:
            continue

        raw_value = data[field_name]
        names = raw_value if isinstance(raw_value, list) else [raw_value]
        names = [n for n in names if n]
        if not names:
            continue

        relation_ids: list[dict] = []
        for name in names:
            page_id = target_map.get(name) or target_map.get(str(name).strip())
            if page_id:
                relation_ids.append({"id": page_id})

        if relation_ids:
            props[mapping["property"]] = {"relation": relation_ids}
    return props


def _find_page_by_unique_id(nw: NotionWrapper, type_config: dict, unique_id_str: str) -> str | None:
    """unique_id로 페이지를 검색하여 page_id를 반환한다."""
    search_config = type_config.get("search", {})
    data_source_id = type_config.get("data_source_id")

    if not data_source_id:
        output_json(False, error="unique_id 검색에 data_source_id가 필요합니다 (config.yaml에 설정)")
        sys.exit(1)

    m = re.search(r"(\d+)", unique_id_str)
    if not m:
        output_json(False, error=f"unique_id에서 숫자를 추출할 수 없습니다: {unique_id_str}")
        sys.exit(3)

    id_num = int(m.group(1))
    id_property = search_config.get("id_property", "Task ID")

    try:
        results = nw.query_data_source(
            data_source_id=data_source_id,
            filter={"property": id_property, "unique_id": {"equals": id_num}},
        )
        pages = results.get("results", [])
        return pages[0]["id"] if pages else None
    except Exception as e:
        output_json(False, error=f"unique_id 검색 실패: {e}")
        sys.exit(2)


# ── 생성/업데이트 ──

def _create_page(
    nw: NotionWrapper,
    database_id: str,
    field_map: dict,
    data: dict,
    lookups: dict,
    data_source_id: str | None = None,
) -> int:
    """새 페이지를 생성한다."""
    try:
        data = _route_by_role(data, field_map)
        properties = build_properties(field_map, data)
        properties.update(_resolve_people_from_lookups(nw, data, field_map, lookups))
        properties.update(_resolve_relations_from_lookups(data, field_map, lookups))

        children = None
        if data.get("body"):
            children = parse_markdown_to_children(data["body"])

        result = nw.create_page(database_id, properties, children, data_source_id=data_source_id)
        output_json(True, url=result.get("url", ""), page_id=result.get("id", ""))
        return 0
    except Exception as e:
        output_json(False, error=f"Notion API 오류: {e}")
        return 2


def _update_page(nw: NotionWrapper, page_id: str, field_map: dict, data: dict, lookups: dict) -> int:
    """기존 페이지를 업데이트한다."""
    try:
        data = _route_by_role(data, field_map)
        properties = build_properties(field_map, data)
        properties.update(_resolve_people_from_lookups(nw, data, field_map, lookups))
        properties.update(_resolve_relations_from_lookups(data, field_map, lookups))

        result = nw.update_page(page_id, properties)

        if data.get("body"):
            children = parse_markdown_to_children(data["body"])
            if children:
                nw.replace_children(page_id, children)

        output_json(True, url=result.get("url", ""), page_id=page_id)
        return 0
    except Exception as e:
        output_json(False, error=f"Notion API 오류: {e}")
        return 2


# ── 메인 ──

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # 설정 로드
    config = load_config()
    type_name = resolve_type_name(args)

    try:
        type_config = get_type_config(config, type_name)
    except KeyError as e:
        output_json(False, error=str(e), setup_required=True)
        return 1

    try:
        database_id = get_database_id(config, type_name)
    except (KeyError, ValueError) as e:
        output_json(False, error=str(e), setup_required=True)
        return 1

    field_map = get_field_map(config, type_name)
    lookups = get_lookups(config)

    # Notion 클라이언트 초기화
    nw = NotionWrapper()
    if not nw.token:
        output_json(False, error="NOTION_TOKEN이 설정되지 않았습니다. notion-setup을 먼저 실행하세요", setup_required=True)
        return 1

    # 데이터 읽기
    data = read_input_data(args)

    # 업데이트 모드 판별
    page_id = args.page_id
    if args.unique_id and not page_id:
        page_id = _find_page_by_unique_id(nw, type_config, args.unique_id)
        if not page_id:
            output_json(False, error=f"unique_id '{args.unique_id}'에 해당하는 페이지를 찾을 수 없습니다")
            return 3

    if page_id:
        return _update_page(nw, page_id, field_map, data, lookups)
    else:
        return _create_page(
            nw, database_id, field_map, data, lookups,
            data_source_id=type_config.get("data_source_id") or None,
        )


if __name__ == "__main__":
    sys.exit(main())
