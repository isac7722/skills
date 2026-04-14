---
name: notion-setup
description: >
  Notion API 연결을 설정합니다. NOTION_TOKEN을 ~/.notion-skills/.env에 저장하고 연결 테스트를 수행합니다.
  Use this skill when the user says "/notion-setup", "노션 설정", "notion 설정", "노션 연결",
  "notion 토큰 설정", "노션 API 설정", or "notion setup".
  Sets up Notion API credentials and verifies the connection.
---

# Notion Setup Skill

Notion API 토큰을 설정하고 연결을 검증합니다. 모든 Notion 스킬의 사전 요구 사항입니다.

## Workflow

### Step 1: 토큰 확인

사용자에게 Notion Integration Token을 요청합니다:

```
🔑 Notion Integration Token이 필요합니다.
https://www.notion.so/my-integrations 에서 생성할 수 있습니다.

토큰을 입력해주세요:
```

### Step 2: 토큰 저장 및 연결 테스트

사용자가 토큰을 제공하면, 아래 명령으로 저장 및 테스트를 수행합니다:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client python .claude/skills/notion-setup/scripts/setup.py --save <<'TOKEN_JSON'
{"token": "사용자_토큰"}
TOKEN_JSON
```

### Step 3: 결과 보고

- **성공**: `{"success": true, "user": "...", "workspace": "..."}` 반환 → 연결 성공 메시지 출력
- **실패**: `{"success": false, "error": "..."}` 반환 → 에러 메시지 전달

### 연결 상태 확인 (토큰 저장 없이)

이미 설정된 토큰의 연결 상태만 확인하려면:

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --with notion-client python .claude/skills/notion-setup/scripts/setup.py --test
```

### 토큰 재설정

기존 토큰을 새 토큰으로 교체하려면 Step 2와 동일하게 `--save`를 사용합니다. 기존 토큰은 덮어쓰기됩니다.

## 사용 예시

```
사용자: 노션 설정해줘
AI: 🔑 Notion Integration Token이 필요합니다. 토큰을 입력해주세요.
사용자: ntn_abc123...
AI: ✅ 연결 성공! 워크스페이스: My Workspace, 사용자: John Doe
```

## 저장 위치

- 토큰: `~/.notion-skills/.env` (`NOTION_TOKEN=...`)
- 이 파일은 모든 Notion 스킬(notion-config, notion-update, notion-search)에서 공유됩니다.

## Important Rules

- **시크릿 보호**: 토큰은 반드시 stdin JSON으로 전달 (bash 명령줄에 노출 금지)
- **글로벌 저장소**: `~/.notion-skills/.env`에 저장하여 모든 스킬에서 공유
- **커밋 금지**: `.env` 파일은 절대 git에 커밋하지 않음
