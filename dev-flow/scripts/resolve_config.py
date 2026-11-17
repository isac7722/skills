#!/usr/bin/env python3
"""dev-flow 설정을 엄격하게 읽고 유효 설정을 JSON으로 출력한다.

읽기 전용: 설정 파일을 만들거나 수정하지 않고 작업자를 시작하지 않는다.

종료 코드: 0 성공, 1 설정 오류, 2 사용법·파일 오류, 3 PyYAML 없음.
"""

import argparse
import copy
import hashlib
import json
import os
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - exercised via subprocess test
    yaml = None

DEFAULT_CONFIG = os.path.join("~", ".agents", "dev-flow", "config.yaml")
ROLES = ("coordinator", "research", "design", "implementation", "verification")
AGENTS = ("codex", "claude")
DELIVERIES = ("draft-pr", "local")
ROLE_FIELDS = ("agent", "model", "effort")
TOP_KEYS = ("version", "default_profile", "defaults", "profiles")
MODES = ("guided", "yolo")
LAYER_KEYS = ("roles", "delivery", "mode")

EXIT_CONFIG, EXIT_USAGE, EXIT_NO_YAML = 1, 2, 3


class ConfigError(Exception):
    def __init__(self, errors):
        self.errors = list(errors) if isinstance(errors, (list, tuple)) else [errors]
        super().__init__("; ".join(self.errors))


def _strict_loader():
    class StrictLoader(yaml.SafeLoader):
        """SafeLoader + 별칭·앵커·병합 키·중복 키 거부."""

        def compose_node(self, parent, index):
            event = self.peek_event()
            if isinstance(event, yaml.AliasEvent):
                raise ConfigError(f"{_mark(event)}: YAML 별칭(*{event.anchor})은 지원하지 않습니다")
            if getattr(event, "anchor", None):
                raise ConfigError(f"{_mark(event)}: YAML 앵커(&{event.anchor})는 지원하지 않습니다")
            return super().compose_node(parent, index)

        def construct_mapping(self, node, deep=False):
            if isinstance(node, yaml.MappingNode):
                seen = {}
                for key_node, _ in node.value:
                    if key_node.tag == "tag:yaml.org,2002:merge":
                        raise ConfigError(f"{_mark(key_node)}: YAML 병합 키(<<)는 지원하지 않습니다")
                    key = self.construct_object(key_node, deep=True)
                    try:
                        hash(key)
                    except TypeError:
                        raise ConfigError(f"{_mark(key_node)}: 키는 문자열이어야 합니다")
                    if key in seen:
                        raise ConfigError(
                            f"{_mark(key_node)}: 중복 키 '{key}' (처음 정의: {seen[key]})"
                        )
                    seen[key] = _mark(key_node)
            return super().construct_mapping(node, deep=deep)

    return StrictLoader


def _mark(obj):
    mark = getattr(obj, "start_mark", None)
    return f"{mark.line + 1}행 {mark.column + 1}열" if mark else "위치 불명"


def parse_yaml(text):
    try:
        return yaml.load(text, Loader=_strict_loader())
    except ConfigError:
        raise
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML 파싱 오류: {exc}")


def _is_nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


def _check_keys(mapping, allowed, where, errors):
    for key in mapping:
        if not isinstance(key, str):
            errors.append(f"{where}: 키는 문자열이어야 합니다 ({key!r})")
        elif key not in allowed:
            errors.append(f"{where}: 알 수 없는 키 '{key}' (허용: {', '.join(allowed)})")


def validate_role(value, where, errors):
    if not isinstance(value, dict):
        errors.append(f"{where}: 매핑이어야 합니다 (현재 {type(value).__name__})")
        return
    _check_keys(value, ROLE_FIELDS, where, errors)
    if "agent" in value and value["agent"] not in AGENTS:
        errors.append(f"{where}.agent: {' 또는 '.join(AGENTS)}만 허용합니다 (현재 {value['agent']!r})")
    for field in ("model", "effort"):
        if field in value and not _is_nonempty_str(value[field]):
            errors.append(f"{where}.{field}: 빈 문자열이 아닌 문자열이어야 합니다 (현재 {value[field]!r})")


def validate_layer(value, where, errors):
    """defaults·프로필·요청 변경이 공유하는 부분 설정 형식을 검사한다."""
    if not isinstance(value, dict):
        errors.append(f"{where}: 매핑이어야 합니다 (현재 {type(value).__name__}; 비어 있으면 {{}})")
        return
    _check_keys(value, LAYER_KEYS, where, errors)
    if "roles" in value:
        roles = value["roles"]
        if not isinstance(roles, dict):
            errors.append(f"{where}.roles: 매핑이어야 합니다 (현재 {type(roles).__name__})")
        else:
            _check_keys(roles, ROLES, f"{where}.roles", errors)
            for name in ROLES:
                if name in roles:
                    validate_role(roles[name], f"{where}.roles.{name}", errors)
    if "mode" in value and value["mode"] not in MODES:
        errors.append(f"{where}.mode: guided 또는 yolo만 허용합니다 (현재 {value['mode']!r})")
    if "delivery" in value and value["delivery"] not in DELIVERIES:
        errors.append(f"{where}.delivery: {' 또는 '.join(DELIVERIES)}만 허용합니다 (현재 {value['delivery']!r})")


def validate_document(doc):
    errors = []
    if not isinstance(doc, dict):
        raise ConfigError(f"최상위는 매핑이어야 합니다 (현재 {type(doc).__name__})")
    _check_keys(doc, TOP_KEYS, "최상위", errors)
    for key in TOP_KEYS:
        if key not in doc:
            errors.append(f"필수 키 '{key}'가 없습니다")
    version = doc.get("version")
    if "version" in doc and (type(version) is not int or version != 1):
        errors.append(f"version: 정수 1이어야 합니다 (현재 {version!r})")
    if "defaults" in doc:
        validate_layer(doc["defaults"], "defaults", errors)
    profiles = doc.get("profiles")
    if "profiles" in doc:
        if not isinstance(profiles, dict):
            errors.append(f"profiles: 매핑이어야 합니다 (현재 {type(profiles).__name__})")
        else:
            for name, value in profiles.items():
                if not _is_nonempty_str(name):
                    errors.append(f"profiles: 프로필 이름은 빈 문자열이 아닌 문자열이어야 합니다 ({name!r})")
                    continue
                validate_layer(value, f"profiles.{name}", errors)
    if "default_profile" in doc:
        dp = doc["default_profile"]
        if not _is_nonempty_str(dp):
            errors.append(f"default_profile: 문자열이어야 합니다 (현재 {dp!r})")
        elif isinstance(profiles, dict) and dp not in profiles:
            errors.append(f"default_profile: profiles에 '{dp}'가 없습니다 (있는 프로필: {_names(profiles)})")
    if errors:
        raise ConfigError(errors)


def _names(profiles):
    return ", ".join(str(k) for k in profiles) or "없음"


def merge_layer(base, layer):
    """역할별 필드를 병합한다.

    agent 값이 바뀌면 상속된 model·effort를, model 값이 바뀌면 상속된 effort를
    버리고 이 계층에서 지정한 값만 남긴다. 같은 값을 다시 쓰는 것은 변경이 아니다.
    """
    result = copy.deepcopy(base)
    roles = result.setdefault("roles", {})
    for name, override in (layer.get("roles") or {}).items():
        merged = dict(roles.get(name, {}))
        if "agent" in override and override["agent"] != merged.get("agent"):
            merged.pop("model", None)
            merged.pop("effort", None)
        if "model" in override and override["model"] != merged.get("model"):
            merged.pop("effort", None)
        merged.update(override)
        roles[name] = merged
    if "delivery" in layer:
        result["delivery"] = layer["delivery"]
    if "mode" in layer:
        result["mode"] = layer["mode"]
    return result


def parse_overrides(items):
    """--set 항목(role.field=value, delivery=value)을 부분 설정으로 바꾼다."""
    layer, errors = {}, []
    for item in items:
        key, sep, value = item.partition("=")
        if not sep:
            errors.append(f"--set {item!r}: KEY=VALUE 형식이어야 합니다")
            continue
        parts = key.strip().split(".")
        if parts in (["delivery"], ["mode"]):
            layer[parts[0]] = value
        elif len(parts) == 2:
            role, field = parts
            if role not in ROLES:
                errors.append(f"--set {item!r}: 알 수 없는 역할 '{role}' (허용: {', '.join(ROLES)})")
            elif field not in ROLE_FIELDS:
                errors.append(f"--set {item!r}: 알 수 없는 필드 '{field}' (허용: {', '.join(ROLE_FIELDS)})")
            else:
                layer.setdefault("roles", {}).setdefault(role, {})[field] = value
        else:
            errors.append(f"--set {item!r}: 키는 mode, delivery 또는 <역할>.<필드>여야 합니다")
    validate_layer(layer, "요청 변경", errors)
    if errors:
        raise ConfigError(errors)
    return layer


def validate_effective(effective):
    errors = []
    for role in ROLES:
        entry = effective["roles"].get(role)
        if entry is None:
            errors.append(f"유효 설정에 역할 '{role}'이 없습니다")
            continue
        if "agent" not in entry:
            errors.append(f"roles.{role}: agent가 없습니다")
        if "effort" in entry and "model" not in entry:
            errors.append(f"roles.{role}: effort는 명시적 model과 함께 지정해야 합니다")
    if "delivery" not in effective:
        errors.append("유효 설정에 delivery가 없습니다")
    if errors:
        raise ConfigError(errors)


def resolve(doc, profile=None, overrides=None):
    validate_document(doc)
    name = profile if profile is not None else doc["default_profile"]
    if name not in doc["profiles"]:
        raise ConfigError(f"프로필 '{name}'이 없습니다 (있는 프로필: {_names(doc['profiles'])})")
    defaults = merge_layer({"roles": {}, "mode": "guided"}, doc["defaults"])
    for candidate, layer in doc["profiles"].items():
        try:
            validate_effective(merge_layer(defaults, layer))
        except ConfigError as exc:
            raise ConfigError([f"profiles.{candidate}: {error}" for error in exc.errors])
    effective = defaults
    effective = merge_layer(effective, doc["profiles"][name])
    effective = merge_layer(effective, overrides or {})

    validate_effective(effective)
    effective["roles"] = {role: effective["roles"][role] for role in ROLES}
    return name, effective


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="dev-flow 설정을 검증하고 유효 설정 JSON을 출력한다 (읽기 전용)."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help=f"설정 파일 (기본 {DEFAULT_CONFIG})")
    parser.add_argument("--profile", help="사용할 프로필 (기본 default_profile)")
    parser.add_argument(
        "--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE",
        help="이번 요청의 명시적 변경: <역할>.<agent|model|effort>=값 또는 mode=guided|yolo, delivery=값 (반복 가능)",
    )
    args = parser.parse_args(argv)

    if yaml is None:
        print(
            "error: PyYAML이 없습니다. 이 CLI는 자동 설치하지 않습니다. "
            "PyYAML이 설치된 python3로 실행하거나 사용자에게 설치를 요청하세요.",
            file=sys.stderr,
        )
        return EXIT_NO_YAML

    path = os.path.abspath(os.path.expanduser(args.config))
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except FileNotFoundError:
        print(f"error: 설정 파일이 없습니다: {path} (이 CLI는 파일을 만들지 않습니다)", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"error: 설정 파일을 읽을 수 없습니다: {path}: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        text = raw.decode("utf-8")
        overrides = parse_overrides(args.overrides)
        doc = parse_yaml(text)
        name, effective = resolve(doc, args.profile, overrides)
    except UnicodeDecodeError:
        print(f"error: {path}: UTF-8이 아닙니다", file=sys.stderr)
        return EXIT_CONFIG
    except ConfigError as exc:
        for message in exc.errors:
            print(f"error: {message}", file=sys.stderr)
        return EXIT_CONFIG

    json.dump(
        {
            "config_path": path,
            "config_sha256": hashlib.sha256(raw).hexdigest(),
            "profile": name,
            "request_overrides": overrides,
            "effective": effective,
        },
        sys.stdout, ensure_ascii=False, indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
