"""하위호환 래퍼 — 공통 모듈 notion-shared/markdown_parser.py를 재수출한다.

기존 create_ticket.py의 `from markdown_parser import parse_markdown_to_children`
임포트를 깨뜨리지 않기 위한 브릿지 모듈.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

# notion-shared/markdown_parser.py를 직접 로드 (동명 모듈 순환 방지)
_SHARED_MODULE = Path(__file__).resolve().parent.parent.parent / "notion-shared" / "markdown_parser.py"
_spec = importlib.util.spec_from_file_location("_shared_markdown_parser", _SHARED_MODULE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

parse_markdown_to_children = _mod.parse_markdown_to_children

__all__ = ["parse_markdown_to_children"]
