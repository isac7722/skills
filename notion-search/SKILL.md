---
name: notion-search
description: >
  Notion 데이터베이스에서 페이지를 검색합니다 (키워드, 필터, unique_id 기반).
  Use this skill when the user says "/notion-search", "노션 검색", "노션에서 찾아줘",
  "notion search", "노션 조회", "페이지 검색", "티켓 찾아줘", "노션 데이터 조회",
  "DB에서 검색해줘", or "노션에서 조회해줘".
  Searches Notion databases by keyword, filter conditions, or unique ID and returns structured JSON results.
---

# Notion Search Skill

config.yaml에 정의된 데이터베이스 매핑을 기반으로, Notion DB에서 페이지를 검색하고 결과를 구조화된 형식으로 반환합니다.
키워드 검색, 프로퍼티 필터, unique_id 조회를 지원합니다.

## 사전 조건

- `notion-setup` 스킬로 NOTION_TOKEN이 설정되어 있어야 합니다 (`~/.notion-skills/.env`).
- `notion-config` 스킬로 최소 1개 DB 매핑이 등록되어 있어야 합니다 (`~/.notion-skills/config.yaml`).
- 설정이 없으면 사용자에게 해당 스킬을 먼저 실행하라고 안내합니다.

## 검색 모드

### 1. 키워드 검색 (기본)

DB 내 텍스트 프로퍼티에서 키워드를 검색합니다.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml python .claude/skills/notion-search/scripts/search.py --db <alias> --keyword "<검색어>"
```

### 2. Unique ID 검색

config.yaml의 `search.id_pattern`에 정의된 패턴으로 특정 페이지를 조회합니다 (예: `AHD-123`).

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml python .claude/skills/notion-search/scripts/search.py --db <alias> --unique-id "<unique_id>"
```

### 3. 필터 검색

Notion DB 프로퍼티 기반 필터 조건으로 검색합니다.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml python .claude/skills/notion-search/scripts/search.py --db <alias> --filter <<'FILTER_JSON'
<JSON>
FILTER_JSON
```

## 인자

| 인자 | 필수 | 설명 |
|------|------|------|
| `--db <alias>` | 선택 | 검색 대상 DB alias (미지정 시 config.yaml의 `default_type` 사용) |
| `--keyword <text>` | 조건부 | 키워드 검색어 (title 프로퍼티에서 contains 매칭) |
| `--unique-id <id>` | 조건부 | Unique ID로 단일 페이지 조회 (예: `AHD-123`) |
| `--filter` | 조건부 | stdin으로 Notion 필터 JSON을 전달하여 고급 검색 |
| `--limit <N>` | 선택 | 결과 수 제한 (기본: 20, 최대: 100) |
| `--sort <field>` | 선택 | 정렬 기준 필드 (기본: `last_edited_time` 내림차순) |

> `--keyword`, `--unique-id`, `--filter` 중 하나는 반드시 지정해야 합니다.

## 출력 형식 (JSON)

### 성공 — 목록 결과

```json
{
  "success": true,
  "count": 3,
  "results": [
    {
      "page_id": "abc123...",
      "url": "https://notion.so/...",
      "properties": {
        "name": "API 리팩토링",
        "status": "In progress",
        "assignee": ["홍길동"],
        "priority": "높음"
      },
      "last_edited": "2025-07-01T09:00:00Z"
    }
  ]
}
```

### 성공 — Unique ID 단일 결과

```json
{
  "success": true,
  "count": 1,
  "results": [
    {
      "page_id": "abc123...",
      "unique_id": "AHD-123",
      "url": "https://notion.so/...",
      "properties": {
        "name": "로그인 버그 수정",
        "status": "Not started",
        "assignee": ["김철수"],
        "priority": "긴급"
      },
      "last_edited": "2025-07-01T09:00:00Z"
    }
  ]
}
```

### 실패

```json
{
  "success": false,
  "error": "데이터 타입 'tasks'를 찾을 수 없습니다."
}
```

### 결과 없음

```json
{
  "success": true,
  "count": 0,
  "results": []
}
```

## 필터 JSON 형식

Notion API 필터 형식을 따릅니다. config.yaml의 field 이름이 아닌 **Notion 프로퍼티 이름**을 사용합니다.

```json
{
  "and": [
    {
      "property": "상태",
      "status": { "equals": "In progress" }
    },
    {
      "property": "담당자",
      "people": { "contains": "user-id-123" }
    }
  ]
}
```

## Workflow

### Step 1: 검색 의도 파악

사용자의 요청에서 검색 조건을 파악합니다:

- **대상 DB**: 어떤 alias의 DB에서 검색할지 (명시 없으면 기본 DB 사용)
- **검색 방식**: 키워드 / unique_id / 필터
- **키워드 또는 조건**: 무엇을 찾는지

### Step 2: 검색 실행

파악한 조건으로 스크립트를 실행합니다:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml python .claude/skills/notion-search/scripts/search.py --db <alias> --keyword "<검색어>"
```

### Step 3: 결과 표시

검색 결과를 사용자에게 읽기 좋은 형식으로 정리하여 보여줍니다:

```
🔍 검색 결과 (DB: tasks, 키워드: "리팩토링"):

1. API 리팩토링 (AHD-456)
   - 상태: In progress | 담당자: 홍길동 | 우선순위: 높음
   - 🔗 https://notion.so/...

2. 코드 리팩토링 가이드 (AHD-234)
   - 상태: Done | 담당자: 김철수 | 우선순위: 중간
   - 🔗 https://notion.so/...

총 2건이 검색되었습니다.
```

결과가 없는 경우:
```
🔍 검색 결과 없음 (DB: tasks, 키워드: "리팩토링")
검색 조건과 일치하는 페이지가 없습니다.
```

## 사용 예시

### 예시 1: 키워드 검색

```
사용자: 노션에서 리팩토링 관련 티켓 찾아줘
AI: 🔍 검색 결과 (DB: tasks, 키워드: "리팩토링"):
    1. API 리팩토링 (AHD-456) — In progress
    2. 코드 리팩토링 가이드 (AHD-234) — Done
    총 2건이 검색되었습니다.
```

### 예시 2: Unique ID 조회

```
사용자: AHD-123 티켓 조회해줘
AI: 🔍 AHD-123 조회 결과:
    - 제목: 로그인 버그 수정
    - 상태: Not started
    - 담당자: 김철수
    - 우선순위: 긴급
    🔗 https://notion.so/...
```

### 예시 3: 조건 검색

```
사용자: In progress 상태인 내 작업 찾아줘
AI: 🔍 검색 결과 (DB: tasks, 필터: 상태=In progress):
    1. API 리팩토링 (AHD-456) — 담당자: 홍길동
    2. 배포 스크립트 개선 (AHD-789) — 담당자: 홍길동
    총 2건이 검색되었습니다.
```

### 예시 4: 다른 DB에서 검색

```
사용자: bugs DB에서 심각도 High인 이슈 찾아줘
AI: 🔍 검색 결과 (DB: bugs, 필터: Severity=High):
    1. 로그인 페이지 500 에러 — Severity: High
    2. 결제 실패 이슈 — Severity: High
    총 2건이 검색되었습니다.
```

## config.yaml 검색 설정

데이터 타입별로 검색 동작을 커스터마이징할 수 있습니다:

```yaml
data_types:
  ticket:
    database_id: "abc123..."
    data_source_id: "..."
    search:
      display_fields: [name, status, assignee, priority]
      id_pattern: "AHD-{number}"
      id_property: "Task ID"
      id_type: "unique_id"
```

| 설정 키 | 설명 |
|---------|------|
| `display_fields` | 결과에 표시할 필드 목록 |
| `id_pattern` | Unique ID 패턴 (prefix-number 형식) |
| `id_property` | Unique ID가 저장된 Notion 프로퍼티 이름 |
| `id_type` | ID 프로퍼티 타입 (`unique_id` 또는 `rich_text`) |

## Important Rules

- **언어**: 모든 안내 메시지는 한국어로 작성
- **매핑 기반**: config.yaml에 정의된 `display_fields`를 기반으로 결과 표시
- **결과 제한**: 기본 20건, 사용자 요청 시 `--limit`으로 조정 가능
- **시크릿 보호**: 토큰, database_id 등은 bash 명령줄에 직접 노출 금지
- **공통 모듈**: `.claude/skills/notion-shared/`의 config_loader, notion_client를 사용
- **DB alias 미지정 시**: config.yaml의 `default_type` 사용
- **검색어 전달**: 키워드는 CLI 인자로 전달 (stdin이 아닌 `--keyword` 플래그)
- **필터 전달**: 복잡한 필터 JSON은 stdin heredoc으로 전달
