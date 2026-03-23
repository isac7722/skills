---
name: create-pr
description: >
  현재 브랜치의 변경사항을 분석하여 고품질 Pull Request를 생성합니다.
  Use this skill when the user says "/create-pr", "PR 만들어줘", "풀리퀘스트 생성",
  "PR 올려줘", "create pull request", "리뷰 요청할게", or "PR 생성해줘".
  셀프 리뷰 체크, Conventional Commits 제목, 구조화된 본문을 포함한 PR을 gh CLI로 생성합니다.
---

# Create PR Skill

현재 브랜치의 변경사항을 분석하여 셀프 리뷰, Conventional Commits 제목, 구조화된 본문을 포함한 고품질 PR을 생성합니다.

## Convention Reference

PR 작성 규칙은 아래 컨벤션 문서를 따릅니다:
- Path: `docs/pr-convention.md`

⸻

## Workflow

### Step 1: 사전 조건 확인

아래 항목을 순서대로 확인합니다:

1. `gh` CLI 설치 여부 확인:
```bash
which gh
```

2. GitHub 인증 상태 확인:
```bash
gh auth status
```

하나라도 실패하면:
- `gh` 미설치 → "gh CLI가 필요합니다. `brew install gh`로 설치해주세요." 안내 후 중단
- 미인증 → "`gh auth login`으로 GitHub 인증을 먼저 해주세요." 안내 후 중단

⸻

### Step 2: 변경사항 수집 (병렬 실행)

아래 명령들을 **병렬로** 실행하여 정보를 수집합니다:

```bash
git branch --show-current                    # 현재 브랜치
git log <base>..HEAD --oneline               # 커밋 이력
git diff <base>...HEAD --stat                # 변경 파일/줄 수 요약
git diff <base>...HEAD                       # 전체 diff
git status                                   # 커밋되지 않은 변경
gh pr list --head <branch>                   # 이미 열린 PR 확인
```

**베이스 브랜치 감지**:
- `main` 브랜치 존재 여부 확인 → 있으면 `main` 사용
- 없으면 `master` 확인
- 둘 다 없으면 사용자에게 질문

⸻

### Step 3: PR 크기 및 범위 분석

수집된 diff를 기반으로 분석합니다:

1. **변경 줄 수 합산** (additions + deletions)
   - 400줄 초과 시 경고 표시:
     ```
     ⚠️ PR 크기 경고: 변경 XX줄 (권장 400줄 이내)
     PR을 분할하는 것을 권장합니다. 그래도 계속 진행할까요?
     ```

2. **변경 파일 카테고리 분류**:
   - 기능 코드 (src, lib 등)
   - 테스트 (tests, spec, __tests__ 등)
   - 설정 (config, .yml, .json 등)
   - 문서 (docs, .md 등)

3. **범위 혼합 경고**: 여러 목적(예: 기능 추가 + 리팩토링)이 섞여 있으면 경고:
   ```
   ⚠️ 이 PR에 여러 목적의 변경이 섞여 있습니다:
   - 기능 추가: src/auth/login.py
   - 리팩토링: src/utils/helpers.py
   목적별로 PR을 분리하는 것을 권장합니다.
   ```

⸻

### Step 4: 셀프 리뷰 체크

diff를 스캔하여 아래 항목을 검사합니다 (**추가된 라인만** 대상):

| 체크 | 패턴 | 심각도 |
|------|------|--------|
| 디버그 코드 | `console.log`, `print(`, `debugger`, `breakpoint()`, `import pdb` | Warning |
| 민감 정보 | `.env`, `credentials`, `secret`, `token` 파일 변경 | Error (차단) |
| TODO/FIXME | `TODO`, `FIXME`, `HACK`, `XXX` | Info |
| 테스트 누락 | feat/fix 변경인데 테스트 파일 변경 없음 | Info |

**심각도별 처리**:
- **Error** → PR 생성 차단. 해당 파일/라인을 표시하고 수정 안내
  ```
  🚫 민감 정보 감지 — PR 생성을 중단합니다:
  - .env 파일이 변경에 포함되어 있습니다
  해당 파일을 .gitignore에 추가하거나 변경에서 제외해주세요.
  ```
- **Warning** → 표시하되 진행 허용
  ```
  ⚠️ 디버그 코드 감지:
  - src/api/handler.py:42 — console.log(...)
  제거하는 것을 권장합니다.
  ```
- **Info** → 참고 사항으로 표시
  ```
  ℹ️ TODO 발견:
  - src/service.py:15 — TODO: 캐시 전략 개선
  ℹ️ 테스트 파일 변경이 없습니다 — 테스트 추가를 고려해주세요.
  ```

⸻

### Step 5: PR 제목 및 본문 생성

#### 제목

브랜치명에서 티켓번호, type, 도메인을 추출하여 작성합니다:

```
[티켓번호] <type>(도메인): <한국어 설명>
```

- **티켓번호**: 브랜치명에서 `AHD-숫자` 패턴 추출 (없으면 생략)
- **type**: 브랜치명이 아닌 **실제 diff/커밋 내용을 분석**하여 결정
- **도메인**: 변경 파일의 주요 모듈에서 추론
- 70자 이내, **한국어로 작성**
- `docs/pr-convention.md` 컨벤션 준수

예시:
```
[AHD-123] feat(auth): 소셜 로그인 추가
[AHD-456] fix(payment): 결제 중복 요청 방지   ← 브랜치는 feat/이지만 내용이 버그 수정
refactor(auth): 인증 미들웨어 구조 분리        ← 티켓번호 없는 브랜치
```

#### 본문

아래 템플릿을 따릅니다:

```markdown
## Summary
<!-- 1-3 bullet points: 이 PR이 왜 필요하고 무엇을 바꾸는지 -->

## Changes
<!-- 논리적 그룹별로 변경사항 정리 -->

## Notes for Reviewer
<!-- 중점적으로 봐야 할 부분, 의도적 판단, 관련 PR/이슈 -->
```

**추가 규칙**:
- 관련 이슈 번호가 있으면 Summary 아래에 `Closes AHD-123` 포함
- Step 4에서 발견된 Warning/Info 사항을 Notes for Reviewer에 포함
- 모든 내용은 **한국어**로 작성

⸻

### Step 6: 미리보기 및 사용자 확인

생성된 PR 정보를 미리보기로 표시합니다:

```
📋 PR 미리보기:

🏷️ 제목: [AHD-123] feat(auth): 소셜 로그인 기능 추가
🎯 베이스: main ← feature/AHD-123-social-login
📊 변경: +180 -42 (12 files)

📝 본문:
## Summary
- 카카오/네이버 소셜 로그인 지원 추가
- OAuth2 콜백 처리 및 사용자 프로필 연동

## Changes
- ...

## Notes for Reviewer
- ⚠️ 디버그 코드: src/auth/callback.py:55
- ℹ️ TODO: src/auth/provider.py:23

---
수정이 필요하면 말씀해주세요. 아래 옵션도 지정할 수 있습니다:
- 리뷰어 지정
- 드래프트 모드 (--draft)
- 담당자 변경 (--assignee)
```

사용자가 수정을 요청하면 반영 후 다시 미리보기를 표시합니다.

#### 리뷰어 지정 플로우

**1단계: 최근 PR에서 리뷰어 패턴 확인**

먼저 이 리포의 최근 PR에서 누구를 리뷰어로 지정했는지 확인합니다:

```bash
gh pr list --state merged --limit 5 --json number,title,reviewRequests --jq '.[] | {number, title, reviewers: [.reviewRequests[].login]}'
```

최근 PR에서 반복적으로 지정된 리뷰어가 있으면 자동 추천합니다:
```
👥 리뷰어 지정:

최근 PR에서 자주 지정된 리뷰어:
  → datacheff (최근 5개 PR 중 4회)

datacheff를 리뷰어로 지정할까요? (Y/n/다른 사람 선택)
```

사용자가 수락하면 바로 해당 리뷰어로 설정합니다.

**2단계: 패턴이 없거나 다른 사람을 원할 때**

최근 PR에서 리뷰어 패턴을 찾을 수 없거나, 사용자가 다른 사람을 원하면 collaborator 목록을 조회합니다:

```bash
gh api repos/{owner}/{repo}/collaborators --jq '.[].login'
```

결과를 번호 목록으로 표시합니다 (본인 제외):
```
👥 리뷰어를 선택해주세요:

1. datacheff
2. Honomoly
3. kimzeze
4. jinuscript

번호로 선택해주세요 (여러 명: 1,3 / 건너뛰기: 엔터)
```

사용자가 번호로 선택하면 해당 username을 `--reviewer` 옵션에 반영합니다.

⸻

### Step 7: PR 생성

사용자가 확인하면 PR을 생성합니다.

1. **브랜치 push 확인**: remote에 push 안 되어 있으면 사용자 확인 후 push:
```bash
git push -u origin <branch>
```

2. **PR 생성**:
```bash
gh pr create --title "<제목>" --body "$(cat <<'EOF'
<본문>
EOF
)" --base <base-branch> --assignee @me
```

3. 사용자가 지정한 옵션 추가:
   - `--draft` — 드래프트 PR
   - `--reviewer <users>` — 리뷰어 지정 (쉼표 구분)
   - `--assignee <user>` — 담당자 (기본값: @me)

⸻

### Step 8: 결과 보고

- **성공**:
  ```
  ✅ PR이 생성되었습니다!
  🔗 <PR URL>
  ```

- **실패**:
  ```
  ❌ PR 생성에 실패했습니다.
  에러: <에러 메시지>

  해결 방법:
  - <구체적 해결 안내>
  ```

⸻

## Important Rules

- **확인 후 생성**: 반드시 사용자 확인을 받은 후 `gh pr create` 실행
- **민감 정보 차단**: `.env`, `credentials`, `secret`, `token` 파일 감지 시 PR 생성 불가
- **git 히스토리 수정 금지**: rebase, amend, force push 등 절대 하지 않음
- **Conventional Commits 필수**: PR 제목은 반드시 Conventional Commits 형식
- **언어**: PR 제목과 본문은 한국어로 작성 (커밋 컨벤션에 따름)
- **이슈 번호 추론만**: 브랜치명이나 커밋에서 추출 가능한 이슈 번호만 사용, 절대 임의 생성하지 않음

## Edge Cases

- **커밋 없는 브랜치**: 베이스 브랜치 대비 커밋이 없으면 → "베이스 브랜치와 차이가 없습니다. 커밋을 먼저 추가해주세요." 안내 후 중단
- **커밋되지 않은 변경**: staging/unstaged 변경이 있으면 → "커밋되지 않은 변경사항이 있습니다. 먼저 커밋할까요?" 질문
- **이미 열린 PR**: 같은 브랜치에 이미 PR이 있으면 → "이미 열린 PR이 있습니다: <URL>. 기존 PR을 업데이트할까요?" 제안
