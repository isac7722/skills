---
name: notion-shared
description: >
  Notion 스킬들이 공유하는 내부 라이브러리입니다 (config_loader, notion_wrapper,
  markdown_parser, semantic_dictionary). 사용자가 직접 호출하지 않으며,
  notion-update / notion-ticket / notion-search / notion-config 의 필수 의존성으로
  반드시 함께 설치되어야 합니다. 이 스킬을 직접 트리거하지 마세요.
---

# Notion Shared Library

이 디렉토리는 **실행 가능한 스킬이 아니라** 다른 Notion 스킬들이 공유하는 파이썬 라이브러리입니다.
스킬 레지스트리에서 패키징 단위로 다뤄질 수 있도록 SKILL.md를 포함하고 있지만, LLM이 직접 호출할 일은 없습니다.

## 포함 모듈

| 파일 | 역할 |
|------|------|
| `config_loader.py` | `~/.notion-skills/config.yaml` 로드/저장, data_types·field_map·lookups 조회 |
| `notion_wrapper.py` | Notion API 래퍼 (`NotionWrapper`), property 빌더, 토큰 로더, JSON 출력 헬퍼 |
| `markdown_parser.py` | 마크다운 → Notion block children 변환 |
| `semantic_dictionary.py` + `semantic_dictionary.yaml` | DB 프로퍼티 이름 자동 매핑용 의미 사전 |

## 의존 스킬

다음 스킬들이 sibling 디렉토리(`~/.claude/skills/notion-shared/`) 위치를 `sys.path`에 추가하여 위 모듈을 import 합니다.

- `notion-update`
- `notion-ticket`
- `notion-search`
- `notion-config`

즉 **이 스킬 없이 위 스킬들은 동작하지 않습니다.** 위 스킬 중 하나라도 설치한다면 반드시 `notion-shared`도 같이 설치하세요.

```bash
npx skills add aptimizer-co/skills/notion-shared
```

## Do NOT trigger

사용자가 "노션", "notion" 키워드를 언급하더라도 이 스킬을 실행하지 마세요. 사용자용 엔트리 포인트는
`notion-setup`, `notion-config`, `notion-update`, `notion-search`, `notion-ticket` 입니다.
