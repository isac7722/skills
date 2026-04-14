---
name: notion-update
description: >
  Notion 데이터베이스에 페이지를 생성하거나 기존 페이지를 업데이트합니다 (config.yaml 매핑 기반).
  Use this skill when the user says "/notion-update", "노션에 추가해줘", "노션 페이지 생성",
  "notion update", "노션 업데이트", "페이지 수정해줘", "notion create page",
  "노션에 기록해줘", or "노션 데이터 추가".
  Creates or updates a Notion page using database mappings from config.yaml.
---

# Notion Update Skill

config.yaml에 정의된 데이터베이스 매핑을 기반으로, Notion DB에 새 페이지를 생성하거나 기존 페이지를 업데이트합니다.
`notion-config`에서 설정한 alias·프로퍼티 매핑을 사용하여 다양한 DB에 데이터를 기록합니다.

## 사전 조건

- `notion-setup` 스킬로 NOTION_TOKEN이 설정되어 있어야 합니다 (`~/.notion-skills/.env`).
- `notion-config` 스킬로 최소 1개 DB 매핑이 등록되어 있어야 합니다 (`~/.notion-skills/config.yaml`).
- 설정이 없으면 사용자에게 해당 스킬을 먼저 실행하라고 안내합니다.

## CLI 인자

| 인자 | 단축 | 설명 | 기본값 |
|------|------|------|--------|
| `--type <alias>` | `-t` | 데이터 타입 alias (config.yaml의 `data_types` 키) | `default_type` |
| `--data <json>` | `-d` | 필드 데이터 JSON 문자열. 미지정 시 stdin에서 읽음 | stdin |
| `--page-id <id>` | | 업데이트할 페이지 ID (지정 시 업데이트 모드) | - |
| `--unique-id <id>` | | 업데이트할 페이지의 unique ID (예: AHD-699) | - |
| `--db <alias>` | | `--type`의 하위 호환 별칭 | - |

### --type 인자 사용법

`--type`은 config.yaml에 정의된 데이터 타입 alias를 지정합니다. 하나의 설정 파일에 여러 DB 매핑을 등록하고, `--type`으로 대상을 선택합니다.

```bash
# ticket 타입 DB에 생성
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml \
  python .claude/skills/notion-update/scripts/update.py --type ticket --data '{"name":"제목"}'

# bugs 타입 DB에 생성
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml \
  python .claude/skills/notion-update/scripts/update.py --type bugs --data '{"title":"버그 제목"}'

# 기본 타입 사용 (--type 생략)
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml \
  python .claude/skills/notion-update/scripts/update.py --data '{"name":"제목"}'
```

### --data 인자 사용법

`--data`로 JSON 문자열을 직접 전달하거나, 생략하여 stdin에서 읽을 수 있습니다.

```bash
# --data로 직접 전달
python update.py --type ticket --data '{"name":"제목", "status":"In progress"}'

# stdin으로 전달 (heredoc)
python update.py --type ticket <<'INPUT_JSON'
{"name":"제목", "status":"In progress"}
INPUT_JSON
```

## 생성 vs 업데이트 판단

- **생성 모드** (기본): `--page-id` 없이 실행하면 새 페이지를 생성합니다.
- **업데이트 모드**: `--page-id <page_id>` 또는 `--unique-id <unique_id>`를 지정하면 기존 페이지를 업데이트합니다.
- 사용자가 "업데이트해줘", "수정해줘" 등 표현을 사용하면 업데이트 모드로 진행합니다.

## Workflow

### Step 1: 대화 맥락 분석 및 자동 추출

현재 대화에서 논의된 내용을 분석하여 DB에 기록할 데이터를 **자동으로 추출**합니다.

#### 대상 타입(`--type`) 자동 결정

대화 맥락에서 어떤 데이터 타입에 기록할지 추론합니다:

- 사용자가 "티켓", "작업" 언급 → `ticket` 타입
- 사용자가 "버그", "이슈" 언급 → `bugs` 타입
- 명시적 언급 없으면 → config.yaml의 `default_type` 사용
- 사용자가 직접 타입을 지정하면 그대로 사용

#### 필드 데이터 자동 추출 가이드라인

대화 맥락에서 config.yaml 매핑의 각 필드에 맞는 값을 추출합니다:

| 추출 대상 | 추론 방법 | 예시 |
|-----------|-----------|------|
| **제목** (title) | 작업의 핵심 목표를 1줄로 요약 | "API 엔드포인트 리팩토링" |
| **상태** (status/select) | 명시적 언급 또는 기본값 사용 | 새 작업 → "Not started" |
| **담당자** (people) | 대화에서 언급된 이름, 또는 `git config user.name`으로 추론 | ["홍길동"] |
| **우선순위** (select) | "급한", "중요한" 등 표현에서 추론 | "긴급" → "높음" |
| **본문** (body) | 배경, 작업 내용, 기술적 고려사항을 마크다운으로 구조화 | 아래 참조 |
| **날짜** (date) | 대화에서 언급된 기한 | "2025-03-01" |
| **태그** (multi_select) | 관련 기술, 카테고리 키워드 추출 | ["backend", "API"] |

#### 본문(body) 자동 구성 템플릿

```markdown
## 배경 & 목적
(대화에서 파악한 작업의 배경과 목표를 2~3문장으로)

## 작업 내용
- [ ] (대화에서 논의된 구체적 작업 항목)
- [ ] (코드 변경, 파일, 관련 모듈)

## 기술적 고려사항
(아키텍처 결정, 영향 범위, 주의점)

## 완료 조건 (DoD)
- [ ] (검증 가능한 완료 기준)
```

#### 추론 규칙

- **맥락에서 추론 가능하면 질문 없이 채움** — 단, 추론했음을 미리보기에 명시
- **추론 불가능한 필수 필드만 질문** — 여러 항목이면 한 번에 모아서 질문
- **select/status 필드**: config.yaml의 `options`에 정의된 값 중에서만 선택
- **people 필드**: config.yaml의 `lookups.display_name_map`을 참조하여 이름 매칭
- **기본값 존재 시**: 추론 실패 시 기본값 사용 (예: 상태 → "Not started")

### Step 2: 데이터 미리보기 및 사용자 확인

추출한 데이터를 미리보기로 보여주고 확인을 받습니다:

```
📋 페이지 미리보기 (DB: tasks):

- 제목: [페이지 제목]
- 상태: Not started
- 담당자: [이름]
- 우선순위: 중간

📝 본문:
## 내용
...

---
이대로 Notion에 생성할까요? (수정이 필요하면 말씀해주세요)
```

### Step 3: Notion에 페이지 생성/업데이트

사용자가 확인하면, stdin JSON으로 데이터를 전달하여 실행합니다.

**생성 모드** (--data 사용):
```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml python .claude/skills/notion-update/scripts/update.py --type <alias> --data '<JSON>'
```

**생성 모드** (stdin 사용):
```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml python .claude/skills/notion-update/scripts/update.py --type <alias> <<'INPUT_JSON'
<JSON>
INPUT_JSON
```

**업데이트 모드** (page_id 지정):
```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml python .claude/skills/notion-update/scripts/update.py --type <alias> --page-id <page_id> --data '<JSON>'
```

**업데이트 모드** (unique_id 지정):
```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml python .claude/skills/notion-update/scripts/update.py --type <alias> --unique-id <unique_id> --data '<JSON>'
```

### stdin JSON 형식

config.yaml의 프로퍼티 매핑에 정의된 field 이름을 키로 사용합니다.

```json
{
  "name": "페이지 제목",
  "status": "In progress",
  "assignee": ["담당자 이름"],
  "priority": "높음",
  "description": "설명 텍스트",
  "body": "## 본문 마크다운\n내용..."
}
```

- 각 field 이름은 `config.yaml`의 `field_map` 매핑에서 정의한 키와 일치해야 합니다.
- `body` 필드는 예약 필드로, 페이지 본문(children blocks)으로 변환됩니다.
- 업데이트 시 JSON에 포함된 필드만 변경되고, 나머지는 유지됩니다.

### config.yaml 매핑 예시

```yaml
data_types:
  ticket:
    database_id: "abc123..."
    data_source_id: "abc123..."
    field_map:
      name: { type: title, property: "제목", required: true }
      status: { type: select, property: "상태", options: ["Not started", "In progress", "Done"] }
      assignee: { type: people, property: "담당자" }
      priority: { type: select, property: "우선순위", options: ["긴급", "높음", "중간", "낮음"] }
      description: { type: rich_text, property: "설명" }

  bugs:
    database_id: "def456..."
    field_map:
      title: { type: title, property: "Bug Title", required: true }
      severity: { type: select, property: "Severity" }
      steps: { type: rich_text, property: "재현 단계" }

default_type: ticket

lookups:
  display_name_map:
    "git-user-name": "Notion 표시 이름"
```

### 지원 프로퍼티 타입

| 타입 | 값 형식 | 예시 |
|------|---------|------|
| `title` | 문자열 | `"페이지 제목"` |
| `rich_text` | 문자열 | `"설명 텍스트"` |
| `select` | 문자열 | `"In progress"` |
| `multi_select` | 문자열 또는 배열 | `["태그1", "태그2"]` |
| `status` | 문자열 | `"Done"` |
| `number` | 숫자 | `42` |
| `checkbox` | boolean | `true` |
| `url` | 문자열 | `"https://..."` |
| `date` | 문자열 또는 객체 | `"2025-01-01"` 또는 `{"start": "...", "end": "..."}` |
| `people` | 이름 배열 | `["홍길동"]` |
| `relation` | ID 배열 | `[{"id": "page-id"}]` |

### Step 4: 결과 보고

- **성공**: `{"success": true, "url": "...", "page_id": "..."}` 반환 -> URL 공유
- **실패**: `{"success": false, "error": "..."}` 반환 -> 에러 메시지 전달

## 사용 예시

### 예시 1: 새 페이지 생성

```
사용자: tasks DB에 새 작업 추가해줘. API 리팩토링 작업이야.
AI: 📋 페이지 미리보기 (DB: tasks):
    - 제목: API 리팩토링
    - 상태: Not started
    - 우선순위: 중간
    이대로 생성할까요?
사용자: 응
AI: ✅ 생성 완료! https://notion.so/...
```

### 예시 2: 기존 페이지 업데이트

```
사용자: AHD-123 상태를 In progress로 변경해줘
AI: (unique_id로 페이지 검색 후)
    📋 업데이트 미리보기:
    - 상태: Not started → In progress
    이대로 업데이트할까요?
사용자: 응
AI: ✅ 업데이트 완료! https://notion.so/...
```

### 예시 3: bugs DB에 생성

```
사용자: 버그 DB에 새 이슈 등록해줘
AI: 📋 페이지 미리보기 (DB: bugs):
    - Bug Title: 로그인 페이지 500 에러
    - Severity: High
    이대로 생성할까요?
```

## 마크다운 폴백

API 실패 시 아래 형식으로 출력합니다:

````
⚠️ Notion API 연결에 실패했습니다. 아래 내용을 복사하여 직접 붙여넣기해주세요:

```
제목: [페이지 제목]
상태: Not started
우선순위: 중간

## 본문
...
```
````

## Important Rules

- **언어**: 모든 안내 메시지는 한국어로 작성
- **매핑 기반**: 반드시 config.yaml에 정의된 프로퍼티 매핑을 따름
- **확인 후 실행**: 반드시 사용자 확인을 받은 후 Notion API 호출
- **맥락 우선**: 대화에서 논의된 내용을 최대한 활용하여 자동으로 채움
- **추론 가능하면 채움**: 대화 맥락에서 유추 가능한 항목은 질문 없이 채워 넣되, 추론했음을 미리보기에 명시
- **한 번에 질문**: 추론 불가능한 필수 항목이 여러 개면 한 번에 모아서 질문
- **--type 자동 결정**: 대화 맥락에서 대상 타입 추론, 불확실하면 `default_type` 사용
- **--data 구성**: 추출한 필드 데이터를 JSON으로 구성하여 `--data` 인자로 전달
- **JSON escape**: `--data`로 전달 시 shell 이스케이프 주의, stdin heredoc 전달 시 걱정 불필요
- **시크릿 보호**: 토큰, database_id 등은 bash 명령줄에 직접 노출 금지
- **공통 모듈**: `.claude/skills/notion-shared/`의 config_loader, notion_client를 사용
- **타입 미지정 시**: config.yaml의 `default_type` 사용
- **부분 업데이트**: 업데이트 시 JSON에 포함된 필드만 변경, 나머지 유지
