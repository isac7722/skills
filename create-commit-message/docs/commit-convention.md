# Commit Convention

This project follows the **Conventional Commits 1.0.0** specification.

---

## Goal

Enable anyone reading `git log` to understand what changed, why it changed, and its impact within seconds.

This enables:
- Automatic CHANGELOG generation
- Better reviewability and collaboration
- Cleaner, more searchable commit history

---

## Commit Message Structure

```
<type>[optional !]: <description>

[optional body]

[optional footer(s)]
```

### Example

```
feat: add social login feature

- Integrate Kakao login
- Integrate Google login

Closes #123
```

---

## Commit Types

### Core Types (SemVer Impact)

| Type | Description | SemVer |
|------|-------------|--------|
| `feat` | Introduces a new feature | MINOR |
| `fix` | Patches a bug | PATCH |

### Additional Types (No SemVer impact unless BREAKING)

| Type | Description |
|------|-------------|
| `docs` | Documentation only |
| `style` | Code formatting, missing semicolons, etc. (no logic change) |
| `refactor` | Code restructure without behavior change |
| `test` | Add or modify tests |
| `chore` | Maintenance tasks (no performance or UI change) |
| `design` | UI/UX design changes |
| `perf` | Performance improvement |
| `build` | Build system or dependency changes |
| `ci` | CI configuration or scripts |
| `asset` | Add assets like icons |
| `setting` | Package installation, etc. |
| `revert` | Revert a previous commit |

### Type Selection Guide

- Users can do something new → `feat`
- Incorrect behavior / crash fixed → `fix`
- Behavior unchanged, code cleaned up → `refactor`
- Only documentation changed → `docs`
- Only tooling / config / CI changed → `build`, `ci`, or `chore`

---

## Breaking Change

Breaking changes MUST be indicated in one of the following ways:

### Method 1: Use `!` in the header

```
feat!: change config file format to JSON
```

### Method 2: Add `BREAKING CHANGE` in footer

```
feat: change config file format to JSON

BREAKING CHANGE: YAML format config files are no longer supported.
```

---

## Subject Line Rules

```
<type>[optional !]: <summary>
```

### Rules

- **Start with a verb**: "add", "fix", "change", etc.
- **Keep concise**: 50-72 characters
- **No trailing period**: Do not end with a period
- **Avoid vague words**: update, changes, stuff, WIP

### Good Examples

```
fix: prevent duplicate payment requests
feat: add date range filter
refactor: separate token validation logic
```

### Bad Examples

```
fix: bug              # Too vague
update things         # No type, vague
feat: add feature.    # Has period
```

---

## Body Rules

Add a body when:
- Multiple important changes exist
- The "why" matters for reviewers
- Behavior changes are subtle or non-obvious

### Rules

- **Blank line after subject required**
- **Explain why first, then what**
- **Focus on what and why, not how**
- **Prefer bullet points**
- **Do NOT paste raw diffs**

### Example

```
feat: improve refresh token expiration handling

- Handle expired refresh tokens explicitly
- Clarify retry conditions on authentication failure
```

---

## Footer Rules

Footers are used for:

### Issue References

```
Closes #123
Fixes #456
Refs #789
```

### Breaking Change Description

```
BREAKING CHANGE: API response format has changed.
```

---

## Full Examples

### Simple Bug Fix

```
fix: handle null values when fetching users
```

### Feature Addition (with body)

```
feat: add date range filter

- Provide start/end date selection UI
- Sync filter state with URL query params

Closes #123
```

### Breaking Change

```
feat!: change config file to JSON format

YAML format is no longer supported.
See docs/migration.md for migration guide.

BREAKING CHANGE: Config file format changed from YAML to JSON.
```

### Refactoring

```
refactor: improve auth middleware structure

- Separate token validation logic into utility
- Improve error handling consistency
```

---

## What NOT to Do

- **Do not use vague messages**: `update`, `misc`, `wip`
- **Do not list implementation details in the subject**
- **Do not bundle unrelated changes into one commit**
- **Do not make up issue numbers**

---

## Reference

This convention is based on the [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) specification.

ALWAYS WRITE COMMIT MESSAGES IN KOREAN