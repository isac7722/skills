"""마크다운 → Notion 블록 변환기.

notion-mcp-python/mcp_server.py의 _parse_markdown_to_children()을 추출 & 개선:
- 번호 리스트: regex 기반 (1~N자리 숫자 지원)
- To-do: - [X] 대문자 X 지원
- 토글 블록: ::: toggle ... ::: end
"""
from __future__ import annotations

import re

_NUMBERED_LIST_RE = re.compile(r"^(\d+)\.\s+(.*)")


def parse_markdown_to_children(markdown_text: str) -> list[dict]:
    """마크다운 텍스트를 Notion children 블록 리스트로 변환합니다."""
    if not markdown_text:
        return []

    lines = markdown_text.split("\n")
    children: list[dict] = []
    in_code_block = False
    code_content: list[str] = []
    code_language = "plain text"
    in_toggle = False
    toggle_title = ""
    toggle_children_acc: list[dict] = []

    def _append(block: dict) -> None:
        if in_toggle:
            toggle_children_acc.append(block)
        else:
            children.append(block)

    for line in lines:
        # ── 코드 블록 ──
        if line.strip().startswith("```"):
            if in_code_block:
                code_text = "\n".join(code_content)
                _append(
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": [{"type": "text", "text": {"content": code_text}}],
                            "language": code_language,
                        },
                    }
                )
                code_content = []
                code_language = "plain text"
                in_code_block = False
            else:
                lang = line.strip()[3:].strip()
                code_language = lang if lang else "plain text"
                in_code_block = True
            continue

        if in_code_block:
            code_content.append(line)
            continue

        # ── 토글 블록 ──
        if line.strip().startswith("::: toggle"):
            in_toggle = True
            toggle_title = line.strip()[len("::: toggle") :].strip() or "Details"
            toggle_children_acc = []
            continue
        if in_toggle and line.strip().startswith("::: end"):
            children.append(
                {
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": toggle_title}}],
                        "children": toggle_children_acc,
                    },
                }
            )
            in_toggle = False
            toggle_title = ""
            toggle_children_acc = []
            continue

        # ── 헤딩 ──
        if line.startswith("### "):
            content = line[4:].strip()
            if content:
                _append(_heading(3, content))
            continue
        if line.startswith("## "):
            content = line[3:].strip()
            if content:
                _append(_heading(2, content))
            continue
        if line.startswith("# "):
            content = line[2:].strip()
            if content:
                _append(_heading(1, content))
            continue

        # ── 인용문 ──
        if line.startswith("> "):
            _append(
                {
                    "object": "block",
                    "type": "quote",
                    "quote": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]},
                }
            )
            continue

        stripped = line.lstrip()

        # ── To-do (대소문자 X 모두 지원) ──
        if re.match(r"^[-*] \[ \] ", stripped):
            _append(_todo(stripped[6:], checked=False))
            continue
        if re.match(r"^[-*] \[[xX]\] ", stripped):
            _append(_todo(stripped[6:], checked=True))
            continue

        # ── 불릿 리스트 ──
        if stripped.startswith("- ") or stripped.startswith("* "):
            _append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]
                    },
                }
            )
            continue

        # ── 번호 리스트 (regex) ──
        m = _NUMBERED_LIST_RE.match(stripped)
        if m:
            _append(
                {
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": m.group(2)}}]
                    },
                }
            )
            continue

        # ── 일반 텍스트 / 빈 줄 ──
        if line.strip():
            _append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line}}]
                    },
                }
            )
        else:
            _append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}})

    # 닫히지 않은 코드 블록 처리
    if in_code_block and code_content:
        code_text = "\n".join(code_content)
        children.append(
            {
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": code_text}}],
                    "language": code_language,
                },
            }
        )

    return children


# ── 헬퍼 ──

def _heading(level: int, content: str) -> dict:
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": [{"type": "text", "text": {"content": content}}]},
    }


def _todo(content: str, *, checked: bool) -> dict:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": [{"type": "text", "text": {"content": content}}],
            "checked": checked,
            "color": "default",
        },
    }
