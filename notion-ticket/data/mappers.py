"""Notion ID 룩업 테이블.

팀/소속/사용자가 변경되면 이 파일만 수정하면 됩니다.
키는 소문자로 매칭됩니다.
"""
from __future__ import annotations

# ── 세부소속 (이름 → 페이지 ID) ──
SUB_TEAM_MAP: dict[str, str] = {
    "연구팀": "316f557d-7eb6-8020-924a-ca1d90ecda98",
    "ai개발": "316f557d-7eb6-8033-8d8c-ce8652ab8a89",
    "프론트엔드": "316f557d-7eb6-808f-becf-e820ed78b868",
    "백엔드": "316f557d-7eb6-80e3-a621-f6a88cdd7182",
    "디자인": "316f557d-7eb6-80e9-8a68-e8df093c252a",
}

# ── 소속팀 (이름 → 페이지 ID) ──
TEAM_MAP: dict[str, str] = {
    "연구팀": "315f557d-7eb6-8015-adf6-d027a08b32f5",
    "기획홍보팀": "315f557d-7eb6-8016-9677-e2c68d582c09",
    "시스템개발팀": "315f557d-7eb6-80e3-8a01-c7c788824182",
    "교육운영팀": "316f557d-7eb6-805d-9934-e5f7d0d349c3",
    "경영지원팀": "316f557d-7eb6-8094-8f0c-f897155fda38",
}

# ── git 사용자 → Notion 담당자 이름 매핑 ──
GIT_USER_MAP: dict[str, str] = {
    "isac7722": "광중 유",
    "honomoly": "장승헌",
}

# ── relation DB ID → 룩업 테이블 매핑 ──
RELATION_MAPS: dict[str, dict[str, str]] = {
    "316f557d-7eb6-809d-8135-d6ed11c6ce23": SUB_TEAM_MAP,  # (세부소속) DB
    "315f557d-7eb6-80b8-96dd-d55d6854cd29": TEAM_MAP,       # (소속팀) DB
}
