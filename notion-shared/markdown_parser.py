"""마크다운 → Notion 블록 변환기.

지원 블록:
- 코드 블록 (``` ... ```), 토글 (::: toggle ... ::: end)
- 헤딩 H1~H3, 인용문, 투두, 불릿/번호 리스트, 단락
- GFM 테이블 (첫 행 = 컬럼 헤더), 구분선 (---)

지원 인라인 포맷팅 (단락·리스트·투두·인용·헤딩·테이블 셀 모두 적용):
- **bold**, *italic*, `inline code`, [text](url)
"""
from __future__ import annotations

import re

_NUMBERED_LIST_RE = re.compile(r"^(\d+)\.\s+(.*)")

# 인라인 포맷: 코드 → 링크 → 볼드 → 이탤릭 순으로 매칭 (코드 블록 안 내용은 더 이상 파싱 안 함)
_INLINE_RE = re.compile(
    r"(?P<code>`[^`\n]+`)"
    r"|(?P<link>\[(?P<link_text>[^\]]+)\]\((?P<link_url>[^)\s]+)\))"
    r"|(?P<bold>\*\*[^*\n]+\*\*)"
    r"|(?P<italic>\*[^*\n]+\*)"
)

_TABLE_CELL_RE = re.compile(r":?-+:?")


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

    i = 0
    while i < len(lines):
        line = lines[i]

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
            i += 1
            continue

        if in_code_block:
            code_content.append(line)
            i += 1
            continue

        # ── 토글 블록 ──
        if line.strip().startswith("::: toggle"):
            in_toggle = True
            toggle_title = line.strip()[len("::: toggle") :].strip() or "Details"
            toggle_children_acc = []
            i += 1
            continue
        if in_toggle and line.strip().startswith("::: end"):
            children.append(
                {
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": _parse_inline(toggle_title),
                        "children": toggle_children_acc,
                    },
                }
            )
            in_toggle = False
            toggle_title = ""
            toggle_children_acc = []
            i += 1
            continue

        stripped = line.strip()

        # ── 구분선 (--- / *** / ___) ──
        if stripped in ("---", "***", "___"):
            _append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # ── 테이블 (현재 라인이 |로 시작 + 다음 비어있지 않은 라인이 separator) ──
        if stripped.startswith("|"):
            sep_idx = _next_nonblank(lines, i + 1)
            if sep_idx != -1 and _is_table_separator(lines[sep_idx]):
                rows: list[list[str]] = [_parse_table_row(line)]
                j = sep_idx + 1
                # 데이터 행 수집 — 빈 줄은 건너뛰되 다음 비어있지 않은 라인이 |로 시작할 때만 계속
                while j < len(lines):
                    cur = lines[j]
                    if not cur.strip():
                        nb = _next_nonblank(lines, j + 1)
                        if nb != -1 and lines[nb].strip().startswith("|"):
                            j = nb
                            continue
                        break
                    if cur.strip().startswith("|"):
                        rows.append(_parse_table_row(cur))
                        j += 1
                    else:
                        break

                table_width = max(len(r) for r in rows)
                # 셀 개수 정규화 (모자라면 빈 셀로 패딩, 넘치면 자름)
                normalized_rows = []
                for r in rows:
                    if len(r) < table_width:
                        r = r + [""] * (table_width - len(r))
                    elif len(r) > table_width:
                        r = r[:table_width]
                    normalized_rows.append(r)

                table_children = [
                    {
                        "object": "block",
                        "type": "table_row",
                        "table_row": {"cells": [_parse_inline(cell) for cell in row]},
                    }
                    for row in normalized_rows
                ]

                _append(
                    {
                        "object": "block",
                        "type": "table",
                        "table": {
                            "table_width": table_width,
                            "has_column_header": True,
                            "has_row_header": False,
                            "children": table_children,
                        },
                    }
                )
                i = j
                continue

        # ── 헤딩 ──
        if line.startswith("### "):
            content = line[4:].strip()
            if content:
                _append(_heading(3, content))
            i += 1
            continue
        if line.startswith("## "):
            content = line[3:].strip()
            if content:
                _append(_heading(2, content))
            i += 1
            continue
        if line.startswith("# "):
            content = line[2:].strip()
            if content:
                _append(_heading(1, content))
            i += 1
            continue

        # ── 인용문 ──
        if line.startswith("> "):
            _append(
                {
                    "object": "block",
                    "type": "quote",
                    "quote": {"rich_text": _parse_inline(line[2:])},
                }
            )
            i += 1
            continue

        list_stripped = line.lstrip()

        # ── To-do (대소문자 X 모두 지원) ──
        if re.match(r"^[-*] \[ \] ", list_stripped):
            _append(_todo(list_stripped[6:], checked=False))
            i += 1
            continue
        if re.match(r"^[-*] \[[xX]\] ", list_stripped):
            _append(_todo(list_stripped[6:], checked=True))
            i += 1
            continue

        # ── 불릿 리스트 ──
        if list_stripped.startswith("- ") or list_stripped.startswith("* "):
            _append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": _parse_inline(list_stripped[2:])
                    },
                }
            )
            i += 1
            continue

        # ── 번호 리스트 (regex) ──
        m = _NUMBERED_LIST_RE.match(list_stripped)
        if m:
            _append(
                {
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": _parse_inline(m.group(2))
                    },
                }
            )
            i += 1
            continue

        # ── 일반 텍스트 / 빈 줄 ──
        if line.strip():
            _append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": _parse_inline(line)},
                }
            )
        else:
            _append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}})
        i += 1

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


# ── 인라인 포맷팅 ──

def _parse_inline(text: str) -> list[dict]:
    """인라인 포맷팅(`code`, **bold**, *italic*, [text](url))을 rich_text 배열로 변환."""
    if not text:
        return []
    rich: list[dict] = []
    last_end = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > last_end:
            plain = text[last_end : m.start()]
            if plain:
                rich.append(_text_obj(plain))
        if m.group("code") is not None:
            rich.append(_text_obj(m.group("code")[1:-1], code=True))
        elif m.group("link") is not None:
            rich.append(_text_obj(m.group("link_text"), link=m.group("link_url")))
        elif m.group("bold") is not None:
            rich.append(_text_obj(m.group("bold")[2:-2], bold=True))
        elif m.group("italic") is not None:
            rich.append(_text_obj(m.group("italic")[1:-1], italic=True))
        last_end = m.end()
    if last_end < len(text):
        tail = text[last_end:]
        if tail:
            rich.append(_text_obj(tail))
    return rich


def _text_obj(
    content: str,
    *,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    link: str | None = None,
) -> dict:
    obj: dict = {"type": "text", "text": {"content": content}}
    if link:
        obj["text"]["link"] = {"url": link}
    annotations: dict = {}
    if bold:
        annotations["bold"] = True
    if italic:
        annotations["italic"] = True
    if code:
        annotations["code"] = True
    if annotations:
        obj["annotations"] = annotations
    return obj


# ── 테이블 ──

def _is_table_separator(line: str) -> bool:
    """`|---|---|`, `|:---:|---:|` 등 GFM 테이블 separator 라인인지 검사."""
    s = line.strip()
    if "|" not in s:
        return False
    parts = [p.strip() for p in s.strip("|").split("|")]
    if not parts or any(not p for p in parts):
        return False
    return all(_TABLE_CELL_RE.fullmatch(p) for p in parts)


def _parse_table_row(line: str) -> list[str]:
    """`| a | b |` → ['a', 'b']."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _next_nonblank(lines: list[str], start: int) -> int:
    """start 이상 인덱스에서 처음으로 비어있지 않은 라인의 인덱스. 없으면 -1."""
    j = start
    while j < len(lines):
        if lines[j].strip():
            return j
        j += 1
    return -1


# ── 블록 헬퍼 ──

def _heading(level: int, content: str) -> dict:
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": _parse_inline(content)},
    }


def _todo(content: str, *, checked: bool) -> dict:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {
            "rich_text": _parse_inline(content),
            "checked": checked,
            "color": "default",
        },
    }
