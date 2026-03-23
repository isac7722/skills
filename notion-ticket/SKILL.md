---
name: notion-ticket
description: >
  대화 맥락을 기반으로 노션 티켓을 생성하거나 기존 티켓을 업데이트합니다.
  Use this skill when the user says "/notion-ticket", "노션 티켓 만들어줘", "티켓 작성",
  "티켓 생성해줘", "작업 티켓", "ticket 만들어", "티켓 업데이트", or "티켓 수정해줘".
  Analyzes the current conversation context and creates or updates a Notion ticket via API.
---

# Notion Ticket Skill

대화 중 쌓인 맥락을 분석하여 구조화된 티켓을 Notion에 직접 생성하거나, 기존 티켓을 업데이트합니다.

## 생성 vs 업데이트 판단

- **현재 git 브랜치**가 `feat/AHD-123`, `fix/AHD-456` 등 `AHD-숫자` 패턴을 포함하면 → **업데이트 모드** (해당 Task ID의 기존 티켓 업데이트)
- 사용자가 명시적으로 "티켓 업데이트해줘", "AHD-123 수정해줘" 등 → **업데이트 모드**
- 그 외 → **생성 모드**

브랜치에서 Task ID를 추출하려면:
```bash
git branch --show-current
```
결과에서 `AHD-숫자` 패턴을 추출합니다 (예: `feat/AHD-699` → `AHD-699`).

## Workflow

### Step 1: 대화 맥락 분석

현재 대화에서 논의된 내용을 분석하여 다음을 파악합니다:

- **작업 유형**: Feature / Bug / Refactor / Chore
- **핵심 문제 또는 목표**: 무엇을 왜 해야 하는지
- **구체적 작업 항목**: 코드 변경, 파일, 관련 모듈
- **기술적 고려사항**: 아키텍처 결정, 영향 범위, 주의점
- **관련 자료**: 대화에서 언급된 PR, 문서, 코드 위치

### Step 2: 부족한 정보 질문

다음 항목 중 대화 맥락에서 추론할 수 없는 것이 있으면 사용자에게 질문합니다:

- 우선순위 (긴급 / 높음 / 중간 / 낮음)
- 담당자
- 완료 조건

**단, 맥락에서 합리적으로 추론 가능한 항목은 질문 없이 채워 넣습니다.**
질문이 필요한 경우, 한 번에 모아서 질문합니다.

### Step 3: 티켓 미리보기 → 사용자 확인

티켓 JSON을 아래 형식으로 출력하고 사용자에게 확인을 받습니다:

```
📋 티켓 미리보기:

- 제목: [티켓 제목]
- 개발팀진행상태: Not started
- 우선순위: 중간
- 담당자: [이름]
- 세부소속: [세부소속]
- 소속팀: [소속팀]

📝 본문 (notes):
## 배경 & 목적
...

## 작업 내용
- [ ] 항목 1
- [ ] 항목 2

## 기술적 고려사항
...

## 완료 조건 (DoD)
- [ ] ...

---
이대로 Notion에 생성할까요? (수정이 필요하면 말씀해주세요)
```

### Step 4: Notion에 티켓 생성

사용자가 확인하면, 아래 명령으로 티켓을 생성합니다:

```bash
uv run --with notion-client python .claude/skills/notion-ticket/scripts/create_ticket.py <<'TICKET_JSON'
<JSON>
TICKET_JSON
```

**credentials가 없으면** (exit code 1 + `setup_required: true`):
1. 사용자에게 `NOTION_TOKEN`과 `NOTION_DATABASE_ID`를 요청
2. Write 도구로 `.claude/skills/notion-ticket/.env` 파일을 직접 생성 (시크릿이 bash 명령줄에 노출되지 않음):
   ```
   NOTION_TOKEN=사용자가_제공한_토큰
   NOTION_DATABASE_ID=사용자가_제공한_DB_ID
   ```
3. 저장 후 다시 티켓 생성 실행

credentials는 `.claude/skills/notion-ticket/.env`에 저장되며 `.gitignore`에 의해 커밋되지 않습니다.

**JSON 형식** (schema.py의 NotionTicket 필드와 일치):
```json
{
  "name": "티켓 제목",
  "dev_status": "Not started",
  "priority": "중간",
  "assignee": ["담당자 이름"],
  "sub_team": ["세부소속명"],
  "team": ["소속팀명"],
  "notes": "## 배경 & 목적\n내용...\n\n## 작업 내용\n- [ ] 항목1\n- [ ] 항목2"
}
```

**필드 값 옵션**:
- `dev_status` (개발팀진행상태): "Not started" (기본값) | "queue" | "In progress" | "Pending" | "developed" | "Resolved" | "Complete"
- `priority` (우선순위): "긴급" | "높음" | "중간" (기본값) | "낮음"
- `assignee` (담당자): 이름 문자열 또는 배열. Notion 워크스페이스 사용자 이름과 매칭됩니다. **비어 있으면 `git config user.name`으로 자동 추론** (`data/mappers.py`의 `GIT_USER_MAP` 참조).
- `sub_team` (세부소속): 이름 문자열 또는 배열. `data/mappers.py`의 `SUB_TEAM_MAP` 참조.
- `team` (소속팀): 이름 문자열 또는 배열. `data/mappers.py`의 `TEAM_MAP` 참조.
- `notes`: 마크다운 문자열 (줄바꿈은 `\n`)

### Step 4-B: 기존 티켓 업데이트

업데이트 모드일 때, 아래 명령으로 실행합니다:

```bash
uv run --with notion-client python .claude/skills/notion-ticket/scripts/create_ticket.py --update AHD-699 <<'TICKET_JSON'
<JSON>
TICKET_JSON
```

**업데이트 JSON**: 변경할 필드만 포함 (나머지는 유지됨)
```json
{
  "dev_status": "In progress",
  "assignee": ["담당자 이름"],
  "notes": "## 작업 내용\n- [x] 완료된 항목\n- [ ] 남은 항목"
}
```

- `name`, `dev_status`, `priority`, `assignee`, `sub_team`, `team`: 해당 필드만 업데이트
- `notes`: 기존 본문을 **전체 교체** (기존 블록 삭제 → 새 블록 추가)

### Step 5: 결과 보고

- **성공**: 스크립트가 `{"success": true, "url": "..."}` 반환 → URL 공유
- **실패**: `{"success": false, "error": "..."}` 반환 → 에러 메시지 전달 후 **마크다운 폴백** (코드블록으로 티켓 내용 출력하여 복사-붙여넣기 가능하게)

## 마크다운 폴백 형식

API 실패 시 아래 형식으로 출력합니다:

````
⚠️ Notion API 연결에 실패했습니다. 아래 내용을 복사하여 직접 붙여넣기해주세요:

```
제목: [티켓 제목]
개발팀진행상태: Not started
우선순위: 중간

## 배경 & 목적
...

## 작업 내용
- [ ] 항목 1

## 완료 조건 (DoD)
- [ ] ...
```
````

## Important Rules

- **언어**: 모든 티켓 내용은 한국어로 작성
- **맥락 우선**: 대화에서 논의된 내용을 최대한 활용하여 자동으로 채움
- **간결함**: 배경은 2~3문장, 작업 항목은 실행 가능한 단위로
- **상태 기본값**: 별도 지시 없으면 `Not started`로 설정
- **한 번에 질문**: 부족한 정보가 여러 개면 한 번에 모아서 질문
- **추론 가능하면 채움**: 대화 맥락에서 합리적으로 유추 가능한 항목은 질문 없이 채워 넣되, 추론했음을 명시
- **확인 후 생성**: 반드시 사용자 확인을 받은 후 Notion API를 호출
- **JSON escape**: notes 필드의 줄바꿈은 반드시 `\n`으로 이스케이프, 쌍따옴표는 `\"`로 이스케이프. heredoc으로 전달하므로 shell 특수문자 걱정 불필요
