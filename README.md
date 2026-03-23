# aptimizer-skills

> AI 에이전트를 위한 팀 공용 스킬 모음 — 커밋, PR, API 문서, 티켓까지 자동화

[Skills CLI](https://skills.sh/)를 통해 Claude Code, Cursor 등 AI 에이전트에 설치하여 사용합니다.

## 스킬 목록

| 스킬 | 설명 | 트리거 예시 |
|------|------|------------|
| [`create-commit-message`](./create-commit-message/SKILL.md) | Conventional Commits 기반 커밋 메시지 생성 | `커밋 메시지 만들어줘` |
| [`create-pr`](./create-pr/SKILL.md) | 셀프 리뷰 + 구조화된 본문의 고품질 PR 생성 | `PR 만들어줘` |
| [`enrich-schema`](./enrich-schema/SKILL.md) | DRF 뷰에 `@extend_schema()` 자동 추가 | `API 문서 보강해줘` |
| [`notion-ticket`](./notion-ticket/SKILL.md) | 대화 맥락 기반 Notion 티켓 생성/업데이트 | `노션 티켓 만들어줘` |

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
