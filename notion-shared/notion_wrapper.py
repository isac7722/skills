#!/usr/bin/env python3
"""Notion API 공통 클라이언트 래퍼.

모든 notion-* 스킬이 공유하는 Notion API 인증·CRUD 로직.
설정 파일: ~/.notion-skills/.env (NOTION_TOKEN 필수)

사용법:
    from notion_client_wrapper import NotionWrapper
    nw = NotionWrapper()              # ~/.notion-skills/.env 자동 로드
    nw.query_database(db_id, filter)  # DB 쿼리
    nw.create_page(db_id, props)      # 페이지 생성
"""
from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

# ── 글로벌 설정 디렉토리 ──
CONFIG_DIR = Path.home() / ".notion-skills"
ENV_PATH = CONFIG_DIR / ".env"
DB_CONFIG_PATH = CONFIG_DIR / "databases.json"


def load_env() -> None:
    """~/.notion-skills/.env에서 환경변수를 로드한다."""
    if not ENV_PATH.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=ENV_PATH)
    except ImportError:
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def get_token() -> str | None:
    """환경변수에서 NOTION_TOKEN을 반환한다."""
    load_env()
    return os.environ.get("NOTION_TOKEN")


def output_json(success: bool, **kwargs: Any) -> None:
    """표준 JSON 응답을 stdout으로 출력한다."""
    result = {"success": success, **kwargs}
    print(json.dumps(result, ensure_ascii=False))


# ── Property 빌더 ──

def build_property(prop_type: str, value: Any) -> dict[str, Any] | None:
    """Notion property 타입에 맞는 dict를 생성한다.

    지원 타입: title, rich_text, select, multi_select, status,
              number, checkbox, url, email, phone_number, date
    people/relation은 ID resolve가 필요하므로 별도 처리.
    """
    if value is None:
        return None

    builders: dict[str, Any] = {
        "title": lambda v: {"title": [{"text": {"content": str(v)}}]},
        "rich_text": lambda v: {"rich_text": [{"text": {"content": str(v)}}]},
        "select": lambda v: {"select": {"name": _enum_value(v)}},
        "multi_select": lambda v: {
            "multi_select": [
                {"name": _enum_value(n)}
                for n in (v if isinstance(v, list) else [v])
                if n
            ]
        },
        "status": lambda v: {"status": {"name": _enum_value(v)}},
        "number": lambda v: {"number": v if isinstance(v, (int, float)) else float(v)},
        "checkbox": lambda v: {"checkbox": bool(v)},
        "url": lambda v: {"url": str(v)},
        "email": lambda v: {"email": str(v)},
        "phone_number": lambda v: {"phone_number": str(v)},
        "date": _build_date,
        "people": lambda v: {
            "people": v if isinstance(v, list) else [v]
        },
        "relation": lambda v: {
            "relation": v if isinstance(v, list) else [v]
        },
    }

    builder = builders.get(prop_type)
    if not builder:
        return None
    return builder(value)


def build_properties(field_map: dict, data: dict) -> dict[str, Any]:
    """field_map과 data를 기반으로 Notion properties dict를 생성한다.

    Args:
        field_map: {field_name: {"property": "Notion속성명", "type": "타입"}, ...}
        data: {field_name: value, ...}

    Returns:
        Notion API용 properties dict
    """
    props: dict[str, Any] = {}
    for field_name, mapping in field_map.items():
        if field_name not in data:
            continue
        value = data[field_name]
        prop_type = mapping["type"]
        prop_name = mapping["property"]
        built = build_property(prop_type, value)
        if built:
            props[prop_name] = built
    return props


def _enum_value(v: Any) -> str:
    """Enum이면 .value, 아니면 str 변환."""
    return v.value if isinstance(v, Enum) else str(v)


def _build_date(v: Any) -> dict[str, Any]:
    """date property 빌더. str이면 start만, dict이면 start/end."""
    if isinstance(v, str):
        return {"date": {"start": v}}
    if isinstance(v, dict):
        return {"date": {k: v[k] for k in ("start", "end") if k in v}}
    return {"date": {"start": str(v)}}


# ── DB 설정 관리 ──

def load_db_configs() -> dict[str, Any]:
    """~/.notion-skills/databases.json을 로드한다."""
    if not DB_CONFIG_PATH.exists():
        return {}
    return json.loads(DB_CONFIG_PATH.read_text())


def save_db_configs(configs: dict[str, Any]) -> None:
    """~/.notion-skills/databases.json에 저장한다."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DB_CONFIG_PATH.write_text(json.dumps(configs, ensure_ascii=False, indent=2))


# ── Notion API 래퍼 클래스 ──

class NotionWrapper:
    """Notion API 래퍼. 인증 및 CRUD 메서드를 제공한다."""

    def __init__(self, token: str | None = None):
        """초기화. token이 없으면 환경변수에서 자동 로드."""
        self._token = token or get_token()
        self._client = None

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def client(self):
        """lazy-init notion_client.Client."""
        if self._client is None:
            if not self._token:
                raise RuntimeError(
                    "NOTION_TOKEN이 설정되지 않았습니다. "
                    "notion-setup 스킬로 초기 설정을 진행하세요."
                )
            from notion_client import Client
            self._client = Client(auth=self._token)
        return self._client

    # ── Database ──

    def query_database(
        self,
        database_id: str,
        filter: dict | None = None,
        sorts: list[dict] | None = None,
        page_size: int = 100,
        start_cursor: str | None = None,
    ) -> dict:
        """Notion DB를 쿼리한다."""
        kwargs: dict[str, Any] = {"database_id": database_id, "page_size": page_size}
        if filter:
            kwargs["filter"] = filter
        if sorts:
            kwargs["sorts"] = sorts
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        return self.client.databases.query(**kwargs)

    def retrieve_database(self, database_id: str) -> dict:
        """DB 메타데이터(스키마)를 조회한다."""
        return self.client.databases.retrieve(database_id=database_id)

    # ── Page ──

    def create_page(
        self,
        database_id: str,
        properties: dict,
        children: list[dict] | None = None,
        data_source_id: str | None = None,
    ) -> dict:
        """DB에 새 페이지를 생성한다.

        data_source_id 가 제공되면 parent 로 사용한다 (다중 data_source DB 지원).
        """
        if data_source_id:
            parent: dict[str, Any] = {"data_source_id": data_source_id}
        else:
            parent = {"database_id": database_id}
        kwargs: dict[str, Any] = {
            "parent": parent,
            "properties": properties,
        }
        if children:
            kwargs["children"] = children
        return self.client.pages.create(**kwargs)

    def update_page(
        self,
        page_id: str,
        properties: dict | None = None,
        archived: bool | None = None,
    ) -> dict:
        """페이지 속성을 업데이트한다."""
        kwargs: dict[str, Any] = {"page_id": page_id}
        if properties:
            kwargs["properties"] = properties
        if archived is not None:
            kwargs["archived"] = archived
        return self.client.pages.update(**kwargs)

    def retrieve_page(self, page_id: str) -> dict:
        """페이지를 조회한다."""
        return self.client.pages.retrieve(page_id=page_id)

    # ── Block (children) ──

    def get_children(self, block_id: str) -> list[dict]:
        """블록의 자식 목록을 반환한다."""
        result = self.client.blocks.children.list(block_id=block_id)
        return result.get("results", [])

    def append_children(self, block_id: str, children: list[dict]) -> dict:
        """블록에 자식을 추가한다."""
        return self.client.blocks.children.append(
            block_id=block_id, children=children,
        )

    def delete_block(self, block_id: str) -> dict:
        """블록을 삭제한다."""
        return self.client.blocks.delete(block_id=block_id)

    def replace_children(self, page_id: str, new_children: list[dict]) -> None:
        """페이지의 기존 블록을 모두 삭제하고 새 블록으로 교체한다."""
        existing = self.get_children(page_id)
        for block in existing:
            self.delete_block(block["id"])
        if new_children:
            self.append_children(page_id, new_children)

    # ── Users ──

    def list_users(self) -> list[dict]:
        """워크스페이스 사용자 목록을 반환한다."""
        result = self.client.users.list()
        return result.get("results", [])

    def resolve_people(
        self, names: list[str], display_name_map: dict[str, str] | None = None,
    ) -> list[dict]:
        """사용자 이름 목록을 Notion people ID 목록으로 변환한다."""
        if not names:
            return []
        all_users = self.list_users()
        name_map = display_name_map or {}
        resolved: list[dict] = []
        for name in names:
            mapped = name_map.get(name.strip(), name).lower().strip()
            for user in all_users:
                user_name = (user.get("name") or "").lower()
                if mapped == user_name or mapped in user_name:
                    resolved.append({"object": "user", "id": user["id"]})
                    break
        return resolved

    # ── Search ──

    def search(
        self,
        query: str = "",
        filter_type: str | None = None,
        sort_direction: str = "descending",
        page_size: int = 20,
        start_cursor: str | None = None,
    ) -> dict:
        """Notion 검색 API를 호출한다.

        Args:
            query: 검색어
            filter_type: "page" 또는 "database"
            sort_direction: "ascending" 또는 "descending"
            page_size: 결과 수
        """
        kwargs: dict[str, Any] = {"page_size": page_size}
        if query:
            kwargs["query"] = query
        if filter_type:
            kwargs["filter"] = {"value": filter_type, "property": "object"}
        if sort_direction:
            kwargs["sort"] = {
                "direction": sort_direction,
                "timestamp": "last_edited_time",
            }
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        return self.client.search(**kwargs)

    # ── Data Source (for unique_id search) ──

    def query_data_source(
        self,
        data_source_id: str,
        filter: dict | None = None,
    ) -> dict:
        """data_sources.query — unique_id 등으로 검색."""
        kwargs: dict[str, Any] = {"data_source_id": data_source_id}
        if filter:
            kwargs["filter"] = filter
        return self.client.data_sources.query(**kwargs)
