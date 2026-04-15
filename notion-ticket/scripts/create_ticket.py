#!/usr/bin/env python3
"""Notion 티켓 생성/업데이트 CLI (config.yaml 기반).

config.yaml 의 `task` 데이터 타입을 사용한다. 하드코딩된 database_id /
data_source_id / 사용자 맵은 모두 제거되어 notion-config 가 관리하는
field_map·search·lookups 설정을 그대로 읽는다.

인터페이스:
    # 생성
    echo '{"title":"...", "notes":"..."}' | python create_ticket.py

    # 업데이트 (Task ID로 검색)
    echo '{"dev_status":"In progress"}' | python create_ticket.py --update AHD-699

    # 다른 타입 이름을 쓰는 경우 (--type 로 오버라이드)
    echo '{"title":"..."}' | python create_ticket.py --type ticket

사전 요구사항:
    - /notion-setup 으로 NOTION_TOKEN 저장
    - /notion-config add task <database_id> 로 task 타입 등록

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
import subprocess
import sys
from pathlib import Path

# notion-shared 를 import path에 추가
_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
_SHARED_DIR = _SKILLS_DIR / "notion-shared"
_UPDATE_SCRIPTS_DIR = _SKILLS_DIR / "notion-update" / "scripts"
for _dep_name, _dep_path in (
    ("notion-shared", _SHARED_DIR),
    ("notion-update", _UPDATE_SCRIPTS_DIR),
):
    if not _dep_path.is_dir():
        sys.stderr.write(
            f"{_dep_name} 스킬이 설치되어 있지 않습니다 "
            f"(expected: {_dep_path}).\n"
            f"`npx skills add aptimizer-co/skills@{_dep_name}` 로 설치하세요.\n"
        )
        sys.exit(1)
sys.path.insert(0, str(_SHARED_DIR))
# notion-update 의 헬퍼들을 재사용한다 (role routing, lookup resolver)
sys.path.insert(0, str(_UPDATE_SCRIPTS_DIR))

from config_loader import (  # noqa: E402
    load_config,
    get_type_config,
    get_field_map,
    get_database_id,
    get_lookups,
)
from notion_wrapper import NotionWrapper, build_properties, output_json  # noqa: E402
from markdown_parser import parse_markdown_to_children  # noqa: E402
from update import (  # noqa: E402
    _route_by_role,
    _resolve_people_from_lookups,
    _resolve_relations_from_lookups,
    _check_lookups_staleness,
    _emit_warnings,
)


_DEFAULT_TYPE = "task"


def _ticket_warnings(lookups: dict) -> dict:
    """lookups staleness 경고가 있으면 warnings kwargs 반환."""
    w = _check_lookups_staleness(lookups)
    if w:
        _emit_warnings([w])
        return {"warnings": [w]}
    return {}


def _read_stdin_json() -> dict:
    """stdin에서 JSON을 읽어 dict로 반환한다."""
    if sys.stdin.isatty():
        output_json(False, error="stdin 으로 JSON 을 전달하세요")
        sys.exit(3)
    raw = sys.stdin.read().strip()
    if not raw:
        output_json(False, error="빈 입력입니다")
        sys.exit(3)
    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError as e:
        output_json(False, error=f"JSON 파싱 실패: {e}")
        sys.exit(3)
    if not isinstance(data, dict):
        output_json(False, error="JSON 데이터는 object 여야 합니다")
        sys.exit(3)
    return data


def _auto_fill_assignee(data: dict, lookups: dict) -> None:
    """assignee 가 없으면 현재 git user.name 을 기반으로 자동 채운다.

    우선순위:
      1. lookups.git_user_map 에 git 사용자명이 있으면 해당 노션 이름 사용
      2. 없으면 그냥 git 사용자명 그대로 넣어 _resolve_people_from_lookups 의
         fallback(list_users + display_name_map)이 해석하도록 한다
    """
    if data.get("assignee"):
        return
    try:
        git_user = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return
    if not git_user:
        return
    git_user_map = lookups.get("git_user_map") or {}
    notion_name = git_user_map.get(git_user) or git_user_map.get(git_user.lower()) or git_user
    if notion_name:
        data["assignee"] = [notion_name]


def _find_page_by_task_id(nw: NotionWrapper, type_config: dict, task_id_str: str) -> str | None:
    """AHD-xxx → page_id 조회."""
    m = re.match(r"(?:[A-Za-z]+-)?(\d+)", task_id_str)
    if not m:
        output_json(False, error=f"잘못된 Task ID 형식: {task_id_str}")
        sys.exit(3)
    task_num = int(m.group(1))

    search_cfg = type_config.get("search") or {}
    id_property = search_cfg.get("id_property", "Task ID")
    data_source_id = type_config.get("data_source_id")
    if not data_source_id:
        output_json(False, error="type_config 에 data_source_id 가 없습니다")
        sys.exit(1)

    try:
        result = nw.query_data_source(
            data_source_id=data_source_id,
            filter={"property": id_property, "unique_id": {"equals": task_num}},
        )
    except Exception as e:
        output_json(False, error=f"Task ID 검색 실패: {e}")
        sys.exit(2)

    pages = result.get("results", [])
    return pages[0]["id"] if pages else None


def _build_properties_with_resolvers(
    nw: NotionWrapper, data: dict, field_map: dict, lookups: dict,
) -> dict:
    """build_properties 에 people/relation lookup 결과를 합친다."""
    properties = build_properties(field_map, data)
    properties.update(_resolve_people_from_lookups(nw, data, field_map, lookups))
    properties.update(_resolve_relations_from_lookups(data, field_map, lookups))
    return properties


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Notion 티켓 생성/업데이트 (config.yaml 기반)",
    )
    parser.add_argument(
        "--type", "-t",
        dest="type_name",
        default=_DEFAULT_TYPE,
        help=f"config.yaml data_type 이름 (기본: {_DEFAULT_TYPE})",
    )
    parser.add_argument(
        "--update",
        dest="task_id",
        help="업데이트 모드: Task ID (예: AHD-699)",
    )
    args = parser.parse_args()

    config = load_config()
    try:
        type_config = get_type_config(config, args.type_name)
        database_id = get_database_id(config, args.type_name)
    except (KeyError, ValueError) as e:
        output_json(
            False,
            error=str(e),
            setup_required=True,
            hint="/notion-setup + /notion-config add task <db_id> 를 먼저 실행하세요",
        )
        return 1

    field_map = get_field_map(config, args.type_name)
    lookups = get_lookups(config)

    nw = NotionWrapper()
    if not nw.token:
        output_json(
            False,
            error="NOTION_TOKEN 이 설정되지 않았습니다",
            setup_required=True,
            hint="/notion-setup 을 먼저 실행하세요",
        )
        return 1

    data = _read_stdin_json()
    _auto_fill_assignee(data, lookups)
    data = _route_by_role(data, field_map)

    # notes 는 body 의 alias (기존 notion-ticket 호환)
    if "notes" in data and "body" not in data:
        data["body"] = data.pop("notes")

    try:
        if args.task_id:
            page_id = _find_page_by_task_id(nw, type_config, args.task_id)
            if not page_id:
                output_json(False, error=f"Task ID '{args.task_id}' 에 해당하는 페이지를 찾을 수 없습니다")
                return 3
            properties = _build_properties_with_resolvers(nw, data, field_map, lookups)
            result = nw.update_page(page_id, properties) if properties else {}
            if data.get("body"):
                children = parse_markdown_to_children(data["body"])
                if children:
                    nw.replace_children(page_id, children)
            warnings_kw = _ticket_warnings(lookups)
            output_json(
                True,
                message="티켓이 업데이트되었습니다",
                url=result.get("url", ""),
                page_id=page_id,
                task_id=args.task_id,
                **warnings_kw,
            )
            return 0

        # 생성 모드
        properties = _build_properties_with_resolvers(nw, data, field_map, lookups)
        children = parse_markdown_to_children(data["body"]) if data.get("body") else None
        result = nw.create_page(
            database_id,
            properties,
            children,
            data_source_id=type_config.get("data_source_id") or None,
        )
        warnings_kw = _ticket_warnings(lookups)
        output_json(
            True,
            message="티켓이 생성되었습니다",
            url=result.get("url", ""),
            page_id=result.get("id", ""),
            **warnings_kw,
        )
        return 0

    except Exception as e:
        output_json(False, error=f"Notion API 오류: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
