---
name: check-review
description: Verify reviewer comments against the codebase, separate valid findings from incorrect or non-applicable ones, and produce a developer-confirmed fix plan. Use this skill when the user says "/check-review", provides reviewer comments separated by "---", asks to validate review feedback against code, or wants a confirmation step before applying reviewer-requested changes. Do not edit code before explicit developer confirmation.
---

# Check Review

## Overview

Do not accept reviewer comments at face value. Check the current codebase, determine whether each comment is factually supported, and include only evidence-backed items in the proposed fix plan. Do not change code until the developer gives explicit final confirmation.

## Input Parsing

When the user provides review feedback with `/check-review`, process it as follows:

- Split review blocks on lines containing `---`.
- Preserve the intent of each original block, but split a block into sub-items when it contains multiple independently verifiable claims.
- If no delimiter is present, temporarily split by paragraphs, numbered lists, or bullets, and tell the user what split rule was used.
- If a review comment is too vague to locate code or infer intent, do not modify anything. Ask only the 1-3 questions required to proceed.

## Workflow

### 1. Gather Context

Before editing code, collect the relevant context:

- Run `git status --short` to identify existing user or working-tree changes.
- Use `rg` and file navigation to find the code, tests, configuration, or docs referenced by the review.
- When useful, inspect `git diff`, `git log`, tests, and call sites to trace current behavior.
- Do not treat the reviewer's wording as evidence by itself. Establish file, line, and behavior evidence from the repository.

### 2. Verify Each Review Item

Classify each review item into one of these verdicts:

- **Valid**: The code evidence supports the review and a change is needed.
- **Already handled**: The requested behavior already exists or is already covered by the current changes.
- **Incorrect / Not applicable**: The code evidence contradicts the review, or the comment is outside the current scope.
- **Needs clarification**: The intent or code location is unclear enough that a reliable verdict is not possible.
- **Optional / Trade-off**: The comment is a style, structure, or operational preference rather than a correctness issue.

Do not force uncertain items into `Valid`. Say no when the review is wrong or not applicable, and explain why using code evidence.

### 3. Report Findings Before Planning

Share the verification results before making any code change. Use this default structure:

```markdown
## Review Check

### Verdicts

| # | Verdict | Review Summary | Code Evidence | Reason |
|---|---------|----------------|---------------|--------|
| 1 | Valid | ... | `path/file.ext:123` | ... |
| 2 | Incorrect / Not applicable | ... | `path/file.ext:45` | ... |

### Proposed Plan

1. ...
2. ...

### Not Applying

- ...

### Confirmation Needed

Should I proceed with the changes in this plan?
```

Use clickable file paths with line numbers when possible.

### 4. Require Developer Confirmation

Do not edit code, tests, docs, or configuration before final developer confirmation.

Treat these as explicit confirmation:

- "Proceed"
- "Apply the changes"
- "Fix it"
- "Apply items 1 and 3 only"
- "Go with the plan"

Do not treat these as confirmation:

- "What do you think?"
- "Would that work?"
- "Review it more"
- "Show me the plan"

If the user approves only some items, modify only those approved items. Leave unapproved items unchanged.

### 5. Apply Approved Changes

After confirmation only:

1. Make the smallest practical code changes for the approved review items.
2. Do not revert or overwrite unrelated user changes.
3. Run relevant tests, type checks, or linters when available.
4. If verification cannot be run, state why.
5. In the final response, briefly summarize applied items, skipped items, and verification results.

## Response Rules

- Reply in the same language the user uses for the active request unless they ask for a specific language.
- Prefer code evidence over reviewer claims when they conflict.
- Mark assumptions explicitly and confirm them before putting assumption-dependent work into the plan.
- Do not repeat review comments at length. Focus on verdicts, evidence, and next actions.
- Include both a rough implementation direction and concrete files or actions in the plan.
