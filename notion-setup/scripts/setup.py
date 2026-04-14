#!/usr/bin/env python3
"""Notion API 연결 설정 CLI.

인터페이스:
    # 토큰 저장 + 연결 테스트
    echo '{"token":"ntn_..."}' | python setup.py --save

    # 연결 테스트만 (저장된 토큰 사용)
    python setup.py --test

Exit codes:
    0 = 성공
    1 = 토큰 누락 / 설정 필요
    2 = API 오류 (연결 실패)
    3 = 입력 오류
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 글로벌 설정 디렉토리
_CONFIG_DIR = Path.home() / ".notion-skills"
_ENV_PATH = _CONFIG_DIR / ".env"


def _output(success: bool, **kwargs) -> None:
    """JSON stdout 출력."""
    result = {"success": success, **kwargs}
    print(json.dumps(result, ensure_ascii=False))


def _load_env() -> None:
    """~/.notion-skills/.env에서 환경변수 로드."""
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _save_token(token: str) -> None:
    """토큰을 ~/.notion-skills/.env에 저장 (기존 NOTION_TOKEN 업데이트)."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # 기존 .env 내용 읽기 (NOTION_TOKEN 외 다른 값 보존)
    existing_lines: list[str] = []
    token_found = False
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("NOTION_TOKEN="):
                existing_lines.append(f"NOTION_TOKEN={token}")
                token_found = True
            else:
                existing_lines.append(line)

    if not token_found:
        existing_lines.append(f"NOTION_TOKEN={token}")

    _ENV_PATH.write_text("\n".join(existing_lines) + "\n")
    _ENV_PATH.chmod(0o600)


def _test_connection(token: str) -> dict:
    """Notion API 연결 테스트. 사용자 정보와 워크스페이스 반환."""
    from notion_client import Client, APIResponseError

    client = Client(auth=token)
    try:
        me = client.users.me()
        user_name = me.get("name", "Unknown")
        user_type = me.get("type", "unknown")

        # 봇인 경우 워크스페이스 정보 추출
        workspace = ""
        if user_type == "bot":
            bot_info = me.get("bot", {})
            workspace = bot_info.get("workspace_name", "")
            if not workspace:
                owner = bot_info.get("owner", {})
                ws = owner.get("workspace")
                if isinstance(ws, dict):
                    workspace = ws.get("name", "")

        return {
            "connected": True,
            "user": user_name,
            "user_type": user_type,
            "workspace": workspace,
        }
    except APIResponseError as e:
        return {"connected": False, "error": f"API 오류: {e.message}"}
    except Exception as e:
        return {"connected": False, "error": f"연결 실패: {e}"}


def _cmd_save() -> int:
    """stdin JSON에서 토큰을 읽어 저장하고 연결 테스트."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw, strict=False)
    except (json.JSONDecodeError, ValueError) as e:
        _output(False, error=f"JSON 파싱 실패: {e}")
        return 3

    token = data.get("token", "").strip()
    if not token:
        _output(False, error="token 필드가 필요합니다")
        return 3

    # 연결 테스트 먼저 수행
    result = _test_connection(token)
    if not result["connected"]:
        _output(False, error=result["error"])
        return 2

    # 성공 시 저장
    _save_token(token)
    _output(
        True,
        message="토큰 저장 및 연결 테스트 완료",
        user=result["user"],
        workspace=result.get("workspace", ""),
        env_path=str(_ENV_PATH),
    )
    return 0


def _cmd_test() -> int:
    """저장된 토큰으로 연결 테스트."""
    _load_env()
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        _output(
            False,
            error="NOTION_TOKEN이 설정되지 않았습니다. --save로 먼저 설정해주세요.",
            setup_required=True,
        )
        return 1

    result = _test_connection(token)
    if not result["connected"]:
        _output(False, error=result["error"])
        return 2

    _output(
        True,
        message="연결 테스트 성공",
        user=result["user"],
        workspace=result.get("workspace", ""),
        env_path=str(_ENV_PATH),
    )
    return 0


def main() -> int:
    if "--save" in sys.argv:
        return _cmd_save()
    elif "--test" in sys.argv:
        return _cmd_test()
    else:
        _output(False, error="--save 또는 --test 옵션이 필요합니다")
        return 3


if __name__ == "__main__":
    sys.exit(main())
