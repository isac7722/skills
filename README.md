# aptimizer-skills

> AI 에이전트를 위한 팀 공용 스킬 모음 — 커밋, PR, API 문서, 티켓까지 자동화

[Skills CLI](https://skills.sh/)를 통해 Claude Code, Cursor 등 AI 에이전트에 설치하여 사용합니다.

## 스킬 목록

| 스킬 | 설명 | 트리거 예시 |
|------|------|------------|
| [`create-commit-message`](./create-commit-message/SKILL.md) | Conventional Commits 기반 커밋 메시지 생성 | `커밋 메시지 만들어줘` |
| [`create-pr`](./create-pr/SKILL.md) | 셀프 리뷰 + 구조화된 본문의 고품질 PR 생성 | `PR 만들어줘` |
| [`enrich-schema`](./enrich-schema/SKILL.md) | DRF 뷰에 `@extend_schema()` 자동 추가 | `API 문서 보강해줘` |
| [`notion-setup`](./notion-setup/SKILL.md) | Notion API 토큰 설정 및 연결 검증 | `노션 설정해줘` |
| [`notion-config`](./notion-config/SKILL.md) | Notion DB 매핑/프로퍼티 설정 관리 | `노션 DB 설정` |
| [`notion-update`](./notion-update/SKILL.md) | config.yaml 기반 Notion 페이지 생성/업데이트 | `노션에 추가해줘` |
| [`notion-search`](./notion-search/SKILL.md) | Notion DB 키워드/필터/unique_id 검색 | `노션에서 찾아줘` |
| [`notion-ticket`](./notion-ticket/SKILL.md) | 대화 맥락 기반 Notion 티켓 생성/업데이트 | `노션 티켓 만들어줘` |
| [`tickets-notion`](./tickets-notion/SKILL.md) | 야구 티켓 예매 이미지를 파싱해 Notion `tickets` DB에 저장 | `티켓 이미지 저장` |
| [`notion-shared`](./notion-shared/SKILL.md) | 위 Notion 스킬들이 공유하는 내부 라이브러리 (필수 의존성) | — |

## 설치

> Private repo — GitHub 접근 권한(SSH key 또는 `gh auth login`)이 필요합니다.

```bash
# 전체 스킬 설치
npx skills add aptimizer-co/skills

# 특정 스킬만 설치
npx skills add aptimizer-co/skills@create-commit-message

# 글로벌 설치 (모든 프로젝트에서 사용)
npx skills add aptimizer-co/skills -g
```

### Notion 스킬 설치 시 주의

`notion-update`, `notion-ticket`, `notion-search`, `notion-config`는 **`notion-shared`를 sibling 디렉토리로 필요로 합니다.** 개별 설치 시 반드시 함께 설치하세요.

```bash
# 예: notion-update 사용 시
npx skills add aptimizer-co/skills@notion-shared aptimizer-co/skills@notion-update

# 전체 Notion 스택
npx skills add \
  aptimizer-co/skills@notion-shared \
  aptimizer-co/skills@notion-setup \
  aptimizer-co/skills@notion-config \
  aptimizer-co/skills@notion-update \
  aptimizer-co/skills@notion-search \
  aptimizer-co/skills@notion-ticket \
  aptimizer-co/skills@tickets-notion
```

`notion-shared`가 없으면 `from config_loader import ...` 등에서 `ModuleNotFoundError`가 발생합니다.

### Notion 멀티 토큰 (data_type별 별도 Integration)

기본적으로 모든 data_type은 `NOTION_TOKEN` 한 개를 공유합니다. 일부 DB가 **별도 Notion Integration**으로 연결되어 있다면 `notion-config add` 시 `--token-env`로 환경변수명을 지정할 수 있습니다.

```bash
# tickets DB가 별도 Integration이라면
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client --with pyyaml \
  python .claude/skills/notion-config/scripts/config.py \
  add tickets <database_id> \
  --token-env TICKETS_NOTION_TOKEN \
  --token-value secret_xxxxx \
  --yes
```

- `--token-env NAME`: data_type 전용 환경변수명. `config.yaml`에 `token_env: NAME`으로만 저장됩니다 (토큰 값 자체는 저장 X).
- `--token-value SECRET`: 동시에 `~/.notion-skills/.env`에 `NAME=SECRET`를 upsert (권한 600 유지). 셸 히스토리에 남으니, 가능하면 `.env`에 사전 추가 후 `--token-env`만 전달하세요.
- `notion-update`/`notion-search`/`notion-ticket`은 자동으로 해당 data_type에 한해 지정된 토큰을 사용하고, 다른 타입은 기존처럼 `NOTION_TOKEN`을 사용합니다 (backward compatible).

## 사용법

스킬 설치 후 AI 에이전트에서 슬래시 커맨드 또는 자연어로 호출합니다.

### create-commit-message

변경사항을 staging한 뒤 호출하면 Conventional Commits 형식의 커밋 메시지를 생성하고, 확인 후 커밋을 실행합니다.

```
git add .
# "커밋 메시지 만들어줘" 또는 /create-commit-message
```

### create-pr

현재 브랜치의 전체 변경사항을 분석하여 PR을 생성합니다.

```
# "PR 만들어줘" 또는 /create-pr
```

- 변경사항 분석 및 PR 크기/범위 경고
- 셀프 리뷰 (디버그 코드, 민감 정보, TODO, 테스트 누락 감지)
- 미리보기 → 확인 → `gh pr create` 실행

### enrich-schema

DRF + drf-spectacular 프로젝트에서 `@extend_schema()` 데코레이터를 자동 추가합니다. 서비스 레이어까지 추적하여 에러 케이스를 완전 문서화합니다.

```
# "API 문서 보강해줘" 또는 /enrich-schema
```

### notion-ticket

대화 맥락을 분석하여 Notion 티켓을 생성하거나 기존 티켓을 업데이트합니다. 브랜치에 `AHD-숫자` 패턴이 포함되면 자동으로 업데이트 모드로 동작합니다.

```
# "노션 티켓 만들어줘" 또는 /notion-ticket
```

### tickets-notion

야구 티켓 예매 스크린샷을 첨부하면 이미지에서 경기·좌석·결제 정보를 추출하고, 사용자 확인을 거쳐 Notion `tickets` DB에 페이지로 저장합니다. DB에 없는 부가 정보(예매일시·취소 가능 시간·수령방법·좌석 상세)는 페이지 본문 markdown으로 자동 기록됩니다.

```
# 이미지 첨부 후 "/tickets-notion" 또는 "티켓 이미지 저장"
```

- 고정 title 템플릿: `{예매번호} | {홈팀}vs{상대팀} {MM-DD} | {블럭}블럭 {열}열 {좌석}`
- formula 필드(수익률·티켓_단가·티켓_상태 등)는 자동 제외
- select 옵션 불일치 시 `AskUserQuestion`으로 사용자 결정
- 사전 요구: `notion-config add tickets ...`로 등록, 별도 토큰 사용 시 위 멀티 토큰 안내 참고

## 팀 협업

스킬 설치 시 자동 생성되는 `skills-lock.json`을 커밋하면 팀원이 동일한 환경을 복원할 수 있습니다.

```bash
# 팀원: lock 파일 기반으로 스킬 복원
npx skills experimental_install
```

설치한 프로젝트의 `.gitignore`에 추가:

```gitignore
.agents/
.claude/
!skills-lock.json
```

## 스킬 추가하기

1. 스킬 디렉토리와 `SKILL.md`를 생성합니다.

```
my-new-skill/
└── SKILL.md
```

2. `SKILL.md`에 frontmatter와 에이전트 지침을 작성합니다.

```markdown
---
name: my-new-skill
description: "스킬에 대한 한 줄 설명"
---

# 스킬 제목

## When to use
이 스킬이 언제 활성화되어야 하는지 설명합니다.

## Instructions
1. 첫 번째 단계
2. 두 번째 단계
```

3. main 브랜치에 push하면 즉시 반영됩니다.

## 참고

- [Skills 공식 사이트](https://skills.sh/)
