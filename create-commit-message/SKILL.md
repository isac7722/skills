---
name: create-commit-message
description: "Generate high-quality, consistent Git commit messages from staged changes and brief user intent, strictly following the Conventional Commits 1.0.0 specification."
disable-model-invocation: true
---
# Goal

Create commit messages that allow anyone reading git log to understand
what changed, why it changed, and its impact within a few seconds.

⸻

# Convention Reference

Read the commit convention file for detailed rules and examples:
- Path: `docs/commit-convention.md`

⸻

# Agent Instructions (Step-by-Step)

## Step 1) Gather Inputs (REQUIRED)

Base all decisions on:
    •   git status
    •   git diff --staged

If no changes are staged:
    •   Instruct the user to run git add ... and retry.
    
⸻

## Step 2) Analyze the Staged Diff

From the diff, extract:
    •   Primary intent per file (add / modify / remove)
    •   User-visible behavior changes
    •   API / CLI / configuration changes
    •   Test-related changes

Detect patterns:
    •   Breaking change risk (removed public APIs, renamed flags, schema changes)
    •   Refactor-only changes (moves, renames, restructuring)
    •   Formatting-only changes (linting, whitespace)
    
⸻

## Step 3) Ask for Minimal Clarification (Only if Needed)

Ask one short question only if intent is unclear.

Examples:
    •   "Is this a bug fix or a new feature?"
    •   "Is there any user-visible behavior change?"
    •   "Does this introduce a breaking change?"
    •   "Is there a related issue number? (optional)"

If intent is already provided, do not ask.

⸻

## Step 4) Select Type and Breaking Indicator
    •   Choose the best commit type per Conventional Commits
    •   If breaking:
    •   Use !, or
    •   Add a BREAKING CHANGE: footer
    
⸻

## Step 5) Write the Subject Line

Format:

<type>[optional !]: <summary>

Rules:
    •   Start with a verb
    •   Keep concise (~50–72 characters)
    •   No trailing period
    •   Avoid vague words: update, changes, stuff, WIP

⸻

## Step 6) Add a Body Only When It Adds Value

Add a body if:
    •   Multiple important changes exist
    •   The "why" matters for reviewers
    •   Behavior changes are subtle or non-obvious

Rules:
    •   Blank line after subject (required)
    •   Explain why, then what
    •   Prefer bullet points
    •   Do NOT paste raw diffs

⸻

## Step 7) 커밋 메시지 출력 및 확인 요청

1. 생성된 커밋 메시지를 코드블록으로 출력
2. AskUserQuestion 도구를 사용하여 사용자에게 확인 요청
   - 예: "이 커밋 메시지로 커밋할까요? (수정이 필요하면 말씀해주세요)"

⸻

## Step 8) 커밋 실행

- 사용자가 **확인**하면 → `git commit -m "<message>"` 실행 (body가 있는 경우 HEREDOC 사용)
- 사용자가 **수정 요청**하면 → 수정 후 Step 7로 돌아가 다시 확인 요청
- 사용자가 **거부**하면 → 커밋하지 않고 종료

⸻

# What NOT to Do
    •   Do not use low-signal messages (update, misc, wip)
    •   Do not list implementation details in the subject
    •   Do not bundle unrelated changes into one commit message

⸻

# Cursor Integration Notes
    •   git diff --staged is the single source of truth
    •   Branch names may be used as weak hints only
    •   Never invent issue numbers
    •   If assumptions are required, ask first

⸻

# If You Need Clarification

Use the ask questions tool when:
    •   The diff does not indicate whether it's feat vs fix vs refactor
    •   The intended user-facing behavior change is unclear
    •   You suspect a breaking change but cannot confirm
