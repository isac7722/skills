"""Notion ticket dataclass schema and field mapping.

DB 필드가 변경되면 이 파일만 수정하면 됩니다:
1. NotionTicket dataclass에 필드 추가/수정
2. FIELD_MAP에 Notion property 매핑 추가
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class DevStatus(Enum):
    """개발팀진행상태"""
    QUEUE = "queue"
    NOT_STARTED = "Not started"
    RE_ASSIGN = "re-assign"
    PENDING = "Pending"
    REJECTED = "Rejected"
    IN_PROGRESS = "In progress"
    DEVELOPED = "developed"
    RESOLVED = "Resolved"
    COMPLETE = "Complete"


class Priority(Enum):
    """우선순위"""
    URGENT = "긴급"
    HIGH = "높음"
    MEDIUM = "중간"
    LOW = "낮음"


@dataclass
class NotionTicket:
    name: str
    dev_status: DevStatus = DevStatus.NOT_STARTED
    priority: Priority = Priority.MEDIUM
    notes: str = ""
    assignee: list[str] = field(default_factory=list)
    sub_team: list[str] = field(default_factory=list)
    team: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        """JSON 직렬화 (Enum → value 변환)."""
        d: dict[str, Any] = {}
        for k, v in asdict(self).items():
            d[k] = v
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotionTicket:
        """딕셔너리에서 생성 (문자열 → Enum 자동 변환)."""
        return cls(
            name=data["name"],
            dev_status=_to_enum(DevStatus, data.get("dev_status"), DevStatus.NOT_STARTED),
            priority=_to_enum(Priority, data.get("priority"), Priority.MEDIUM),
            notes=data.get("notes", ""),
            assignee=_to_list(data.get("assignee")),
            sub_team=_to_list(data.get("sub_team")),
            team=_to_list(data.get("team")),
        )

    def to_notion_properties(self) -> dict[str, Any]:
        """Notion API용 properties dict 생성 (people/relation은 제외 — resolve 필요)."""
        props: dict[str, Any] = {}
        for field_name, mapping in FIELD_MAP.items():
            value = getattr(self, field_name, None)
            if value is None:
                continue
            prop_name = mapping["property"]
            prop_type = mapping["type"]
            if prop_type == "title":
                props[prop_name] = {"title": [{"text": {"content": value}}]}
            elif prop_type == "select":
                v = value.value if isinstance(value, Enum) else value
                props[prop_name] = {"select": {"name": v}}
            elif prop_type == "status":
                v = value.value if isinstance(value, Enum) else value
                props[prop_name] = {"status": {"name": v}}
            elif prop_type == "multi_select":
                names = value if isinstance(value, list) else [value]
                props[prop_name] = {"multi_select": [{"name": n} for n in names if n]}
            # people은 ID 변환이 필요하므로 create_ticket.py에서 처리
        return props


# Notion DB property ↔ dataclass field 매핑
# 필드 추가 시: dataclass + 여기에 한 줄 추가
FIELD_MAP: dict[str, dict[str, str]] = {
    "name": {"property": "작업", "type": "title"},
    "dev_status": {"property": "개발팀진행상태", "type": "status"},
    "priority": {"property": "우선순위", "type": "select"},
    "assignee": {"property": "담당자", "type": "people"},
    "sub_team": {"property": "세부 소속", "type": "multi_select"},
    "team": {"property": "소속팀", "type": "multi_select"},
}


def _to_enum(enum_cls: type[Enum], value: Any, default: Enum) -> Enum:
    """문자열 → Enum 변환. 매칭 실패 시 default 반환."""
    if value is None:
        return default
    if isinstance(value, enum_cls):
        return value
    for member in enum_cls:
        if member.value == value or member.name == value:
            return member
    return default


def _to_list(value: Any) -> list[str]:
    """문자열 또는 리스트 → list[str] 변환."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []
