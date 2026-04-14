#!/usr/bin/env python3
"""Notion DB 검색 CLI.

데이터 타입(alias)과 키워드/필터/unique_id를 인자로 받아
config.yaml 매핑 기반으로 Notion DB를 검색하고 결과를 JSON으로 반환한다.

사용법:
    # 키워드 검색
    python search.py --db ticket --keyword "리팩토링"

    # Unique ID 검색
    python search.py --db ticket --unique-id AHD-123

    # 필터 검색 (stdin JSON)
    echo '{"and":[...]}' | python search.py --db ticket --filter

    # 기본 DB + 정렬/제한
    python search.py --keyword "버그" --limit 10 --sort created_time

Exit codes:
    0 = 성공
    1 = 설정 오류
    2 = API 오류
    3 = 입력 오류
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# notion-shared 모듈 경로 추가
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_SKILLS_DIR / "notion-shared"))

from notion_wrapper import NotionWrapper, output_json  # noqa: E402
from config_loader import (  # noqa: E402
    load_config,
    get_type_config,
    get_database_id,
    get_field_map,
    get_search_config,
)


def _parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱한다."""
    parser = argparse.ArgumentParser(description="Notion DB 검색")
    parser.add_argument("--db", default=None, help="데이터 타입 alias (기본: default_type)")
    parser.add_argument("--keyword", default=None, help="키워드 검색어")
    parser.add_argument("--unique-id", default=None, help="Unique ID (예: AHD-123)")
    parser.add_argument("--filter", action="store_true", help="stdin에서 필터 JSON 읽기")
    parser.add_argument("--limit", type=int, default=20, help="결과 수 제한 (기본: 20)")
    parser.add_argument("--sort", default=None, help="정렬 기준 필드")
    return parser.parse_args()


def _extract_property_value(prop: dict) -> Any:
    """Notion property dict에서 사람이 읽을 수 있는 값을 추출한다."""
    prop_type = prop.get("type", "")

    extractors: dict[str, Any] = {
        "title": lambda p: "".join(t.get("plain_text", "") for t in p.get("title", [])),
        "rich_text": lambda p: "".join(t.get("plain_text", "") for t in p.get("rich_text", [])),
        "select": lambda p: (p.get("select") or {}).get("name"),
        "multi_select": lambda p: [o.get("name") for o in p.get("multi_select", [])],
        "status": lambda p: (p.get("status") or {}).get("name"),
        "number": lambda p: p.get("number"),
        "checkbox": lambda p: p.get("checkbox"),
        "url": lambda p: p.get("url"),
        "email": lambda p: p.get("email"),
        "phone_number": lambda p: p.get("phone_number"),
        "date": lambda p: (p.get("date") or {}).get("start"),
        "people": lambda p: [u.get("name", "") for u in p.get("people", [])],
        "relation": lambda p: [r.get("id", "") for r in p.get("relation", [])],
        "unique_id": lambda p: _format_unique_id(p.get("unique_id", {})),
    }

    extractor = extractors.get(prop_type)
    if extractor:
        return extractor(prop)
    return None


def _format_unique_id(uid: dict) -> str | None:
    """unique_id dict를 'PREFIX-NUMBER' 문자열로 변환한다."""
    if not uid:
        return None
    prefix = uid.get("prefix", "")
    number = uid.get("number")
    if number is None:
        return None
    return f"{prefix}-{number}" if prefix else str(number)


def _extract_page_result(
    page: dict,
    field_map: dict[str, Any],
    display_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Notion 페이지를 검색 결과 dict로 변환한다."""
    props = page.get("properties", {})

    # property 이름 → field 이름 역매핑
    prop_to_field: dict[str, str] = {}
    for field_name, mapping in field_map.items():
        prop_to_field[mapping["property"]] = field_name

    # 표시할 필드 결정
    fields_to_show = display_fields or list(field_map.keys())

    # 프로퍼티 값 추출
    extracted: dict[str, Any] = {}
    for prop_name, prop_value in props.items():
        field_name = prop_to_field.get(prop_name, prop_name)
        if fields_to_show and field_name not in fields_to_show:
            continue
        value = _extract_property_value(prop_value)
        if value is not None:
            extracted[field_name] = value

    # unique_id 추출 (별도)
    unique_id = None
    for prop_value in props.values():
        if prop_value.get("type") == "unique_id":
            unique_id = _format_unique_id(prop_value.get("unique_id", {}))
            break

    result: dict[str, Any] = {
        "page_id": page.get("id", ""),
        "url": page.get("url", ""),
        "properties": extracted,
        "last_edited": page.get("last_edited_time", ""),
    }
    if unique_id:
        result["unique_id"] = unique_id

    return result


def _build_keyword_filter(keyword: str, field_map: dict[str, Any]) -> dict:
    """키워드로 title 프로퍼티를 검색하는 필터를 생성한다."""
    # title 타입 필드 찾기
    title_props = [
        m["property"]
        for m in field_map.values()
        if m.get("type") == "title"
    ]

    if not title_props:
        # title 필드가 없으면 첫 번째 필드를 사용
        if field_map:
            first = next(iter(field_map.values()))
            title_props = [first["property"]]

    if len(title_props) == 1:
        return {
            "property": title_props[0],
            "title": {"contains": keyword},
        }

    # 여러 title 필드가 있으면 or 조건
    return {
        "or": [
            {"property": p, "title": {"contains": keyword}}
            for p in title_props
        ]
    }


def _build_sorts(sort_field: str | None) -> list[dict] | None:
    """정렬 조건을 생성한다."""
    if not sort_field:
        return [{"timestamp": "last_edited_time", "direction": "descending"}]

    if sort_field in ("last_edited_time", "created_time"):
        return [{"timestamp": sort_field, "direction": "descending"}]

    return [{"property": sort_field, "direction": "descending"}]


def _parse_unique_id(id_str: str) -> tuple[str, int]:
    """'PREFIX-123' → (prefix, number) 파싱."""
    m = re.match(r"([A-Za-z]*)-?(\d+)$", id_str)
    if not m:
        raise ValueError(f"잘못된 Unique ID 형식: {id_str}")
    return m.group(1), int(m.group(2))


def _search_by_unique_id(
    nw: NotionWrapper,
    type_config: dict[str, Any],
    id_str: str,
) -> list[dict]:
    """Unique ID로 페이지를 검색한다."""
    search_cfg = type_config.get("search", {})
    id_property = search_cfg.get("id_property", "ID")
    _, number = _parse_unique_id(id_str)

    # data_source_id가 있으면 data_sources.query 사용
    data_source_id = type_config.get("data_source_id")
    if data_source_id:
        result = nw.query_data_source(
            data_source_id=data_source_id,
            filter={"property": id_property, "unique_id": {"equals": number}},
        )
        return result.get("results", [])

    # fallback: DB 쿼리로 필터
    db_id = type_config.get("database_id", "")
    result = nw.query_database(
        database_id=db_id,
        filter={"property": id_property, "unique_id": {"equals": number}},
        page_size=1,
    )
    return result.get("results", [])


def main() -> int:
    args = _parse_args()

    # 검색 모드 확인
    if not args.keyword and not args.unique_id and not args.filter:
        output_json(False, error="--keyword, --unique-id, --filter 중 하나를 지정하세요")
        return 3

    # 설정 로드
    try:
        config = load_config()
        type_config = get_type_config(config, args.db)
        db_id = get_database_id(config, args.db)
        field_map = get_field_map(config, args.db)
        search_cfg = get_search_config(config, args.db)
    except (KeyError, ValueError) as e:
        output_json(False, error=str(e))
        return 1

    # Notion 클라이언트 초기화
    try:
        nw = NotionWrapper()
    except RuntimeError as e:
        output_json(False, error=str(e))
        return 1

    display_fields = search_cfg.get("display_fields")
    limit = min(args.limit, 100)

    try:
        # 1) Unique ID 검색
        if args.unique_id:
            pages = _search_by_unique_id(nw, type_config, args.unique_id)

        # 2) 필터 검색 (stdin JSON)
        elif args.filter:
            raw = sys.stdin.read()
            try:
                filter_obj = json.loads(raw)
            except json.JSONDecodeError as e:
                output_json(False, error=f"필터 JSON 파싱 실패: {e}")
                return 3
            result = nw.query_database(
                database_id=db_id,
                filter=filter_obj,
                sorts=_build_sorts(args.sort),
                page_size=limit,
            )
            pages = result.get("results", [])

        # 3) 키워드 검색
        else:
            keyword_filter = _build_keyword_filter(args.keyword, field_map)
            result = nw.query_database(
                database_id=db_id,
                filter=keyword_filter,
                sorts=_build_sorts(args.sort),
                page_size=limit,
            )
            pages = result.get("results", [])

    except Exception as e:
        output_json(False, error=f"Notion API 오류: {e}")
        return 2

    # 결과 변환
    results = [
        _extract_page_result(page, field_map, display_fields)
        for page in pages[:limit]
    ]

    output_json(True, count=len(results), results=results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
