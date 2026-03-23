#!/usr/bin/env python3
"""Notion 티켓 생성/업데이트 CLI.

인터페이스:
    # 생성
    echo '{"name":"...", "notes":"..."}' | python create_ticket.py

    # 업데이트 (Task ID로 검색)
    echo '{"dev_status":"In progress", "notes":"..."}' | python create_ticket.py --update AHD-699

    # 최초 설정 (credentials 저장 — stdin JSON으로 전달하여 시크릿 노출 방지)
    echo '{"token":"...", "database_id":"..."}' | python create_ticket.py --setup

Exit codes:
    0 = 성공
    1 = 환경변수 누락 (setup 필요)
    2 = API 오류
    3 = 입력 오류
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# .env 위치: 스킬 디렉토리 (.claude/skills/notion-ticket/.env)
_SKILL_DIR = Path(__file__).resolve().parent.parent
_ENV_PATH = _SKILL_DIR / ".env"

# data_source ID (DB의 data_sources[0].id) — 검색에 필요
_DATA_SOURCE_ID = "313f557d-7eb6-81fb-9ab1-000b4a2b74fe"


def _load_env() -> None:
    """스킬 디렉토리의 .env를 로드."""
    try:
        from dotenv import load_dotenv
        if _ENV_PATH.exists():
            load_dotenv(dotenv_path=_ENV_PATH)
    except ImportError:
        if _ENV_PATH.exists():
            for line in _ENV_PATH.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def _resolve_git_assignee(data: dict) -> None:
    """assignee가 없으면 git 사용자로부터 자동 추론."""
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
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data"))
    from mappers import GIT_USER_MAP
    notion_name = GIT_USER_MAP.get(git_user.lower())
    if notion_name:
        data["assignee"] = [notion_name]


def _output(success: bool, **kwargs) -> None:
    """JSON stdout 출력."""
    result = {"success": success, **kwargs}
    print(json.dumps(result, ensure_ascii=False))


def _setup() -> int:
    """credentials를 .env에 저장."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw, strict=False)
    except (json.JSONDecodeError, ValueError) as e:
        _output(False, error=f"setup JSON 파싱 실패: {e}")
        return 3

    token = data.get("token", "")
    db_id = data.get("database_id", "")

    if not token or not db_id:
        _output(False, error="setup에는 token과 database_id가 필요합니다")
        return 1

    _ENV_PATH.write_text(f"NOTION_TOKEN={token}\nNOTION_DATABASE_ID={db_id}\n")
    _output(True, message=f"저장 완료: {_ENV_PATH}")
    return 0


def _parse_task_id(task_id_str: str) -> int:
    """'AHD-699' 또는 '699' → 숫자 추출."""
    m = re.match(r"(?:AHD-)?(\d+)", task_id_str, re.IGNORECASE)
    if not m:
        raise ValueError(f"잘못된 Task ID 형식: {task_id_str}")
    return int(m.group(1))


def _find_page_by_task_id(notion, task_id_num: int) -> dict | None:
    """Task ID(숫자)로 Notion 페이지 검색."""
    results = notion.data_sources.query(
        data_source_id=_DATA_SOURCE_ID,
        filter={"property": "Task ID", "unique_id": {"equals": task_id_num}},
    )
    pages = results.get("results", [])
    return pages[0] if pages else None


def _resolve_people(notion, names: list[str]) -> list[dict]:
    """사용자 이름 목록 → Notion people ID 목록으로 변환."""
    if not names:
        return []
    users_resp = notion.users.list()
    all_users = users_resp.get("results", [])
    resolved = []
    for name in names:
        name_lower = name.lower().strip()
        for user in all_users:
            user_name = (user.get("name") or "").lower()
            if name_lower == user_name or name_lower in user_name:
                resolved.append({"id": user["id"]})
                break
    return resolved


def _resolve_relations(database_id: str, names: list[str]) -> list[dict]:
    """이름 목록 → relation 페이지 ID 목록으로 변환 (mappers.py 룩업 테이블 사용)."""
    if not names:
        return []
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data"))
    from mappers import RELATION_MAPS
    lookup = RELATION_MAPS.get(database_id, {})
    resolved = []
    for name in names:
        page_id = lookup.get(name.strip().lower())
        if page_id:
            resolved.append({"id": page_id})
    return resolved


def _build_extra_properties(notion, data: dict) -> dict:
    """people/relation 필드를 resolve하여 Notion properties로 변환."""
    from schema import FIELD_MAP
    props: dict = {}

    for field_name, mapping in FIELD_MAP.items():
        if field_name not in data:
            continue
        prop_type = mapping["type"]
        prop_name = mapping["property"]

        if prop_type == "people":
            names = data[field_name] if isinstance(data[field_name], list) else [data[field_name]]
            people_ids = _resolve_people(notion, [n for n in names if n])
            if people_ids:
                props[prop_name] = {"people": people_ids}
        elif prop_type == "relation":
            names = data[field_name] if isinstance(data[field_name], list) else [data[field_name]]
            db_id = mapping.get("database_id", "")
            if db_id:
                relation_ids = _resolve_relations(db_id, [n for n in names if n])
                if relation_ids:
                    props[prop_name] = {"relation": relation_ids}

    return props


def _update(notion, token: str, database_id: str) -> int:
    """기존 티켓 업데이트."""
    # --update 뒤의 Task ID 추출
    try:
        idx = sys.argv.index("--update")
        task_id_str = sys.argv[idx + 1]
    except (ValueError, IndexError):
        _output(False, error="--update 뒤에 Task ID가 필요합니다 (예: --update AHD-699)")
        return 3

    try:
        task_id_num = _parse_task_id(task_id_str)
    except ValueError as e:
        _output(False, error=str(e))
        return 3

    # stdin에서 업데이트할 필드 읽기
    try:
        raw = sys.stdin.read()
        data = json.loads(raw, strict=False)
    except (json.JSONDecodeError, ValueError) as e:
        _output(False, error=f"JSON 파싱 실패: {e}")
        return 3

    _resolve_git_assignee(data)

    # 페이지 검색
    try:
        page = _find_page_by_task_id(notion, task_id_num)
    except Exception as e:
        _output(False, error=f"페이지 검색 실패: {e}")
        return 2

    if not page:
        _output(False, error=f"Task ID AHD-{task_id_num}에 해당하는 페이지를 찾을 수 없습니다")
        return 3

    page_id = page["id"]

    # 업데이트할 properties 구성
    from schema import NotionTicket, FIELD_MAP, _to_enum, DevStatus, Priority
    from markdown_parser import parse_markdown_to_children
    from enum import Enum

    properties: dict = {}
    for field_name, mapping in FIELD_MAP.items():
        if field_name not in data:
            continue
        prop_name = mapping["property"]
        prop_type = mapping["type"]
        value = data[field_name]

        if prop_type == "title":
            properties[prop_name] = {"title": [{"text": {"content": value}}]}
        elif prop_type == "select":
            properties[prop_name] = {"select": {"name": value}}
        elif prop_type == "status":
            properties[prop_name] = {"status": {"name": value}}

    # people/relation 필드 resolve
    extra_props = _build_extra_properties(notion, data)
    properties.update(extra_props)

    # 업데이트 실행
    try:
        update_kwargs: dict = {}
        if properties:
            update_kwargs["properties"] = properties

        result = notion.pages.update(page_id=page_id, **update_kwargs)

        # notes가 있으면 기존 본문을 교체 (기존 블록 삭제 → 새 블록 추가)
        if "notes" in data and data["notes"]:
            children = parse_markdown_to_children(data["notes"])
            if children:
                # 기존 children 삭제
                existing = notion.blocks.children.list(block_id=page_id)
                for block in existing.get("results", []):
                    notion.blocks.delete(block_id=block["id"])
                # 새 children 추가
                notion.blocks.children.append(block_id=page_id, children=children)

        page_url = result.get("url", "")
        _output(True, url=page_url, task_id=f"AHD-{task_id_num}")
        return 0

    except Exception as e:
        _output(False, error=f"Notion API 오류: {e}")
        return 2


def _create(notion, token: str, database_id: str) -> int:
    """새 티켓 생성."""
    from schema import NotionTicket
    from markdown_parser import parse_markdown_to_children

    # stdin에서 JSON 읽기
    try:
        raw = sys.stdin.read()
        data = json.loads(raw, strict=False)
    except (json.JSONDecodeError, ValueError) as e:
        _output(False, error=f"JSON 파싱 실패: {e}")
        return 3

    _resolve_git_assignee(data)

    if "name" not in data:
        _output(False, error="필수 필드 누락: name")
        return 3

    try:
        ticket = NotionTicket.from_dict(data)
    except Exception as e:
        _output(False, error=f"티켓 생성 실패: {e}")
        return 3

    try:
        properties = ticket.to_notion_properties()
        # people/relation 필드 resolve
        extra_props = _build_extra_properties(notion, data)
        properties.update(extra_props)

        children = None
        if ticket.notes:
            parsed = parse_markdown_to_children(ticket.notes)
            if parsed:
                children = parsed

        result = notion.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            **({"children": children} if children else {}),
        )

        page_url = result.get("url", "")
        _output(True, url=page_url)
        return 0

    except Exception as e:
        _output(False, error=f"Notion API 오류: {e}")
        return 2


def main() -> int:
    _load_env()

    # --setup 모드
    if "--setup" in sys.argv:
        return _setup()

    # credentials 확인
    token = os.environ.get("NOTION_TOKEN")
    database_id = os.environ.get("NOTION_DATABASE_ID")

    if not token or not database_id:
        missing = []
        if not token:
            missing.append("NOTION_TOKEN")
        if not database_id:
            missing.append("NOTION_DATABASE_ID")
        _output(
            False,
            error=f"환경변수 누락: {', '.join(missing)}",
            setup_required=True,
        )
        return 1

    from notion_client import Client
    notion = Client(auth=token)

    if "--update" in sys.argv:
        return _update(notion, token, database_id)
    else:
        return _create(notion, token, database_id)


if __name__ == "__main__":
    sys.exit(main())
