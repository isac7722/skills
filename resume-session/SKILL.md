---
name: resume-session
description: "이전 Claude Code 세션을 읽어 컨텍스트를 복원하고 작업을 이어서 진행. 인자: [session-id] (없으면 최근 세션 목록 표시). Triggers: \"세션 읽어\", \"이전 세션\", \"작업 이어서\", \"resume session\", \"/resume-session\""
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# /resume-session - Resume Previous Session

Read a previous Claude Code session to restore context and continue work.

## Arguments

- `$ARGUMENTS`: Optional session ID (full or partial). If empty, list recent sessions.

## Instructions

### Step 0: Ensure parser script exists

Check if `~/.claude/scripts/parse-session.py` exists:

```bash
test -f ~/.claude/scripts/parse-session.py && echo "EXISTS" || echo "MISSING"
```

If MISSING, create it:

```bash
mkdir -p ~/.claude/scripts
```

Then write the following content to `~/.claude/scripts/parse-session.py`:

```python
#!/usr/bin/env python3
"""Parse a Claude Code session JSONL file and extract a structured summary."""

import json
import sys
import os
import glob
from datetime import datetime, timezone


def find_project_dir():
    """Find the Claude project directory for cwd."""
    cwd = os.getcwd()
    project_dir_name = cwd.lstrip("/").replace("/", "-").replace(".", "-")
    candidate = os.path.expanduser(f"~/.claude/projects/-{project_dir_name}")
    if os.path.isdir(candidate):
        return candidate
    base = os.path.basename(cwd)
    pattern = os.path.expanduser(f"~/.claude/projects/*{base}")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    return candidate


def list_sessions(project_dir, limit=10):
    """List recent sessions sorted by modification time."""
    pattern = os.path.join(project_dir, "*.jsonl")
    files = glob.glob(pattern)
    files.sort(key=os.path.getmtime, reverse=True)

    sessions = []
    for f in files[:limit]:
        session_id = os.path.basename(f).replace(".jsonl", "")
        mtime = datetime.fromtimestamp(os.path.getmtime(f))
        size_kb = os.path.getsize(f) / 1024

        preview = ""
        try:
            with open(f, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get("type") == "user":
                        content = msg.get("message", {}).get("content", "")
                        texts = extract_texts(content)
                        for text in texts:
                            if not is_noise(text) and not is_skill_content(text) and text.strip():
                                preview = text.strip().split("\n")[0][:80]
                                break
                    if preview:
                        break
        except Exception:
            pass

        sessions.append(
            {
                "id": session_id,
                "modified": mtime.strftime("%Y-%m-%d %H:%M"),
                "size_kb": f"{size_kb:.0f}",
                "preview": preview or "(empty)",
            }
        )

    return sessions


NOISE_PATTERNS = [
    "<system-reminder>",
    "<local-command",
    "Stop hook feedback",
    "hook success",
    "hook additional context",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "ULTRAWORK #",
    "[UNIFIED CANCEL",
    "# Cancel Command",
    "# Ultrawork Skill",
    "Version: ",
    "Session name:",
    "Session ID:",
    "Caveat: The messages below",
    "<local-command-caveat>",
    "Login method:",
    "Email:",
]


def is_noise(text):
    """Check if text is system noise that should be filtered."""
    for pattern in NOISE_PATTERNS:
        if pattern in text:
            return True
    return False


def is_skill_content(text):
    """Check if text is a skill/command definition (long instruction blocks)."""
    if text.startswith("---\nname:") or text.startswith("---\r\nname:"):
        return True
    if text.startswith("# ") and len(text) > 500 and "## " in text:
        lines = text.split("\n")
        if any("trigger:" in l or "description:" in l for l in lines[:10]):
            return True
    return False


def parse_session(filepath):
    """Parse session JSONL and return structured conversation."""
    user_messages = []
    assistant_messages = []

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "user":
                content = msg.get("message", {}).get("content", "")
                texts = extract_texts(content)
                for text in texts:
                    if not is_noise(text) and not is_skill_content(text) and text.strip():
                        user_messages.append(text.strip())

            elif msg_type == "assistant":
                content = msg.get("message", {}).get("content", "")
                texts = extract_texts(content)
                for text in texts:
                    clean = remove_thinking(text).strip()
                    if clean and not is_noise(clean):
                        assistant_messages.append(clean)

    return user_messages, assistant_messages


def extract_texts(content):
    """Extract text blocks from message content."""
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block["text"])
        return texts
    elif isinstance(content, str):
        return [content] if content.strip() else []
    return []


def remove_thinking(text):
    """Remove <thinking>...</thinking> blocks from text."""
    import re

    return re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()


def generate_summary(session_id, user_messages, assistant_messages, filepath):
    """Generate a markdown summary of the session."""
    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
    size_kb = os.path.getsize(filepath) / 1024

    lines = []
    lines.append(f"# Session Resume: `{session_id[:8]}...`")
    lines.append(f"")
    lines.append(f"- **Date**: {mtime.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **Size**: {size_kb:.0f} KB")
    lines.append(f"- **User messages**: {len(user_messages)}")
    lines.append(f"- **Assistant responses**: {len(assistant_messages)}")
    lines.append("")

    lines.append("## User Requests (chronological)")
    lines.append("")
    for i, msg in enumerate(user_messages):
        truncated = msg[:300] + ("..." if len(msg) > 300 else "")
        lines.append(f"### Request {i+1}")
        lines.append(f"```")
        lines.append(truncated)
        lines.append(f"```")
        lines.append("")

    lines.append("## Key Assistant Responses (last 10)")
    lines.append("")
    for i, msg in enumerate(assistant_messages[-10:]):
        truncated = msg[:500] + ("..." if len(msg) > 500 else "")
        lines.append(f"### Response {len(assistant_messages) - 10 + i + 1}")
        lines.append(truncated)
        lines.append("")

    lines.append("## Full Conversation Flow")
    lines.append("")
    lines.append("| # | Role | Content |")
    lines.append("|---|------|---------|")
    idx = 0
    for msg in user_messages:
        idx += 1
        lines.append(f"| {idx} | USER | {msg[:120].replace('|', '\\|')} |")
    lines.append("")

    return "\n".join(lines)


def main():
    project_dir = find_project_dir()

    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        sessions = list_sessions(project_dir, limit)
        print("## Recent Sessions\n")
        print("| # | Session ID | Modified | Size | Preview |")
        print("|---|-----------|----------|------|---------|")
        for i, s in enumerate(sessions):
            sid_short = s["id"][:12] + "..."
            print(
                f"| {i+1} | `{sid_short}` | {s['modified']} | {s['size_kb']}KB | {s['preview'].replace('|', '/')} |"
            )
        print(f"\nFull IDs:")
        for i, s in enumerate(sessions):
            print(f"  {i+1}. {s['id']}")
        return

    session_id = sys.argv[1]

    filepath = os.path.join(project_dir, f"{session_id}.jsonl")
    if not os.path.exists(filepath):
        pattern = os.path.join(project_dir, f"{session_id}*.jsonl")
        matches = glob.glob(pattern)
        if matches:
            filepath = matches[0]
            session_id = os.path.basename(filepath).replace(".jsonl", "")
        else:
            print(f"Error: Session file not found for '{session_id}'")
            print(f"Looked in: {project_dir}")
            sys.exit(1)

    user_messages, assistant_messages = parse_session(filepath)
    summary = generate_summary(session_id, user_messages, assistant_messages, filepath)
    print(summary)


if __name__ == "__main__":
    main()
```

### Step 1: Session Discovery

If `$ARGUMENTS` is empty or not provided:

1. Run the parser in list mode:
```bash
python3 ~/.claude/scripts/parse-session.py --list 8
```

2. Show the table to the user and ask which session to resume using AskUserQuestion.
   - Use the first 4 sessions as options (label: date + preview, description: full session ID)
   - User can also type a session ID directly via "Other"

3. Once selected, proceed to Step 2 with the chosen session ID.

If `$ARGUMENTS` contains a session ID (full UUID or partial):
- Go directly to Step 2.

### Step 2: Parse Session

Run the parser with the session ID:
```bash
python3 ~/.claude/scripts/parse-session.py <session-id>
```

### Step 3: Present Summary

Display the parser output to the user. This includes:
- Session metadata (date, size, message counts)
- All user requests in chronological order
- Last 10 assistant responses (most relevant context)

### Step 4: Confirm and Resume

Ask the user using AskUserQuestion:
- "Which task from this session should I continue?"
- Options based on the user requests found in the session
- Include "All - resume from where it left off" as the first option

### Step 5: Execute

Based on the user's choice:
1. Read any files referenced in the session context (file paths mentioned in messages)
2. Understand the current state of the work
3. Continue the selected task, picking up where the previous session left off

## Notes

- The parser filters out system noise (hooks, reminders, skill definitions)
- Session files are at `~/.claude/projects/<project-dir>/<session-id>.jsonl`
- Partial session IDs are supported (prefix match)
- If the session was compacted or truncated, context may be incomplete — inform the user