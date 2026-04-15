---
name: notion-config
description: >
  Notion 데이터베이스 매핑 설정을 관리합니다 (추가/조회/삭제/기본값 설정).
  Use this skill when the user says "/notion-config", "노션 설정", "노션 DB 설정",
  "notion config", "DB 매핑 추가", "DB 매핑 삭제", "노션 매핑 목록", or "notion database 설정".
  Manages data_types mappings and property configurations in ~/.notion-skills/config.yaml.
---

# Notion Config Skill

Notion 스킬에서 사용할 데이터 타입 매핑을 관리합니다.
`~/.notion-skills/config.yaml`의 `data_types` 섹션에 DB ID, 필드 매핑, 프로퍼티 정보를 저장하며,
`notion-update`와 `notion-search`가 동일한 파일을 읽습니다.

## 사전 조건

- **필수 의존성**: `notion-shared` 스킬이 sibling으로 설치되어 있어야 합니다 (`npx skills add aptimizer-co/skills/notion-shared`). 없으면 import 오류로 동작하지 않습니다.
- `notion-setup` 스킬로 초기 설정이 완료되어 있어야 합니다 (`~/.notion-skills/.env` 존재).
- 설정이 없으면 사용자에게 `/notion-setup`을 먼저 실행하라고 안내합니다.
- pyyaml 패키지가 필요합니다 (`uv run --with pyyaml`).

## 명령어

### add — 데이터 타입 추가

새로운 Notion DB를 `type_name`과 함께 등록하고, Notion API로 스키마를 조회하여 `field_map`을 자동 생성합니다.

**사용법**:
```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml \
  python .claude/skills/notion-config/scripts/config.py add <type_name> <database_id>
```

**Workflow**:

1. 사용자에게 다음 정보를 수집합니다:
   - `type_name`: 데이터 타입 이름 (예: `ticket`, `bugs`, `docs`)
   - `database_id`: Notion Database ID (32자 hex 또는 URL에서 추출)
2. Notion API로 DB 스키마를 조회하여 프로퍼티 목록을 가져옵니다.
3. 각 property를 `field_map`의 엔트리로 변환합니다:
   - 한글/기호가 포함된 property 이름은 snake_case `field_name`으로 자동 변환
   - `field_map[field_name] = {property: "원래이름", type: "select/title/...", options: [...]}`
4. 첫 등록이면 `default_type`으로 자동 설정됩니다.

**config.yaml 저장 형식**:
```yaml
version: "1"
default_type: ticket
data_types:
  ticket:
    database_id: "abc123..."
    description: "Task Database"
    field_map:
      jaeob:                              # 한글 "작업" → snake_case
        property: "작업"
        type: title
      sangtae:                            # 한글 "상태" → snake_case
        property: "상태"
        type: status
        options: ["Not started", "In progress", "Done"]
      damdangja:
        property: "담당자"
        type: people
```

### list — 등록된 데이터 타입 목록

현재 `config.yaml`의 `data_types`에 등록된 모든 타입을 출력합니다.

**사용법**:
```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with pyyaml \
  python .claude/skills/notion-config/scripts/config.py list
```

**출력 예시**:
```json
{
  "success": true,
  "default_type": "ticket",
  "data_types": [
    {"type_name": "ticket", "database_id": "abc...", "is_default": true, "fields": [...]},
    {"type_name": "bugs", "database_id": "def...", "is_default": false, "fields": [...]}
  ]
}
```

### remove — 데이터 타입 삭제

등록된 data_type을 삭제합니다. `default_type`이었으면 다른 타입으로 자동 교체됩니다.

**사용법**:
```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with pyyaml \
  python .claude/skills/notion-config/scripts/config.py remove <type_name>
```

**Workflow**:
1. `type_name`이 등록되어 있는지 확인합니다.
2. 삭제 전 해당 정보를 보여주고 사용자에게 확인을 받습니다.
3. 확인 후 `data_types`에서 제거합니다.

### show — 상세 조회

특정 data_type의 field_map, 검색 설정 등 전체 구조를 출력합니다.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with pyyaml \
  python .claude/skills/notion-config/scripts/config.py show <type_name>
```

### set-default — 기본 타입 설정

`default_type`을 변경합니다. notion-update/search에서 `--type` 미지정 시 사용됩니다.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with pyyaml \
  python .claude/skills/notion-config/scripts/config.py set-default <type_name>
```

## 설정 파일 경로

| 파일 | 경로 | 설명 |
|------|------|------|
| 환경변수 | `~/.notion-skills/.env` | NOTION_TOKEN 등 시크릿 |
| 데이터 타입 매핑 | `~/.notion-skills/config.yaml` | data_types 정의 (notion-update/search와 공유) |

## 출력 형식

모든 스크립트는 JSON으로 결과를 반환합니다:

**성공**:
```json
{ "success": true, "message": "...", "type_name": "..." }
```

**실패**:
```json
{ "success": false, "error": "..." }
```

## Important Rules

- **단일 진실 공급원**: notion-update, notion-search는 이 스킬이 쓴 `config.yaml`을 읽으므로 반드시 동일한 스키마를 유지합니다.
- **확인 후 삭제**: `remove` 시 반드시 사용자 확인을 받은 후 삭제
- **중복 방지**: 이미 존재하는 `type_name`으로 `add`하면 에러 반환 (먼저 remove)
- **자동 스키마 조회**: `add` 시 Notion API로 DB 프로퍼티를 자동 조회하여 수동 입력 최소화
- **자동 default_type**: 첫 등록 시 자동으로 `default_type`으로 설정
- **시크릿 보호**: database_id는 설정 파일에만 저장, bash 명령줄에 직접 노출 최소화
- **언어**: 사용자 안내 메시지는 한국어로 작성
- **공통 모듈**: `notion-shared/config_loader.py`의 `load_config`/`save_config`를 사용하여 `notion-update`/`notion-search`와 동일한 파일 포맷 유지
