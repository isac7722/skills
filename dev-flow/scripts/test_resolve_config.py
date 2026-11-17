"""resolve_config.py 테스트. 실행: python3 -m unittest discover -s scripts -v"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "resolve_config.py")
EXAMPLE = os.path.join(HERE, "..", "assets", "config.example.yaml")

BASE = """\
version: 1
default_profile: default
defaults:
  roles:
    coordinator: {agent: codex, model: gpt-5, effort: high}
    research: {agent: codex, model: gpt-5, effort: high}
    design: {agent: codex}
    implementation: {agent: claude, model: opus, effort: high}
    verification: {agent: codex}
  delivery: draft-pr
profiles:
  default: {}
"""


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def example_text():
    with open(EXAMPLE, encoding="utf-8") as fh:
        return fh.read()


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, text):
        path = os.path.join(self.tmp.name, "config.yaml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(textwrap.dedent(text))
        return path

    def run_cli(self, *args, config=None, pre=""):
        argv = [SCRIPT] + (["--config", config] if config else []) + list(args)
        if pre:
            cmd = [sys.executable, "-c",
                   pre + "import runpy,sys; sys.argv=%r; runpy.run_path(%r, run_name='__main__')" % (argv, SCRIPT)]
        else:
            cmd = [sys.executable] + argv
        return subprocess.run(cmd, capture_output=True, text=True)

    def ok(self, text, *args):
        path = self.write(text)
        before = read_bytes(path)
        proc = self.run_cli(*args, config=path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(read_bytes(path), before, "CLI must not modify the config")
        return json.loads(proc.stdout)

    def fails(self, text, *args, needle):
        proc = self.run_cli(*args, config=self.write(text))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertIn(needle, proc.stderr)
        return proc.stderr


class ResolutionTests(CliCase):
    def test_example_defaults(self):
        out = self.ok(example_text())
        self.assertEqual(out["profile"], "default")
        roles = out["effective"]["roles"]
        self.assertEqual(list(roles), ["coordinator", "research", "design", "implementation", "verification"])
        self.assertEqual({k: v["agent"] for k, v in roles.items()}, {
            "coordinator": "codex", "research": "codex", "design": "codex",
            "implementation": "claude", "verification": "codex"})
        self.assertEqual(out["effective"]["delivery"], "draft-pr")
        self.assertEqual(len(out["config_sha256"]), 64)

    def test_example_claude_debug_profile(self):
        out = self.ok(example_text(), "--profile", "claude-debug")
        roles = out["effective"]["roles"]
        self.assertEqual(roles["research"], {"agent": "claude"})
        self.assertEqual(roles["implementation"], {"agent": "claude"})
        self.assertEqual(roles["verification"], {"agent": "codex"})

    def test_request_overrides_win_over_profile(self):
        out = self.ok(BASE + "  fast: {delivery: draft-pr}\n", "--profile", "fast",
                      "--set", "delivery=local", "--set", "design.agent=claude")
        self.assertEqual(out["effective"]["delivery"], "local")
        self.assertEqual(out["effective"]["roles"]["design"], {"agent": "claude"})
        self.assertEqual(out["request_overrides"],
                         {"delivery": "local", "roles": {"design": {"agent": "claude"}}})

    def test_agent_change_drops_inherited_model_and_effort(self):
        out = self.ok(BASE, "--set", "research.agent=claude")
        self.assertEqual(out["effective"]["roles"]["research"], {"agent": "claude"})

    def test_agent_change_keeps_model_given_in_same_layer(self):
        out = self.ok(BASE + "  swap:\n    roles:\n      research: {agent: claude, model: sonnet}\n",
                      "--profile", "swap")
        self.assertEqual(out["effective"]["roles"]["research"], {"agent": "claude", "model": "sonnet"})

    def test_same_agent_restated_is_not_a_change(self):
        out = self.ok(BASE, "--set", "implementation.agent=claude")
        self.assertEqual(out["effective"]["roles"]["implementation"],
                         {"agent": "claude", "model": "opus", "effort": "high"})

    def test_model_change_drops_inherited_effort(self):
        out = self.ok(BASE, "--set", "implementation.model=sonnet")
        self.assertEqual(out["effective"]["roles"]["implementation"], {"agent": "claude", "model": "sonnet"})

    def test_effort_only_change_keeps_model(self):
        out = self.ok(BASE, "--set", "implementation.effort=low")
        self.assertEqual(out["effective"]["roles"]["implementation"],
                         {"agent": "claude", "model": "opus", "effort": "low"})

    def test_profile_then_request_layers_in_order(self):
        out = self.ok(BASE + "  p:\n    roles:\n      coordinator: {agent: claude, model: opus, effort: max}\n",
                      "--profile", "p", "--set", "coordinator.model=sonnet")
        self.assertEqual(out["effective"]["roles"]["coordinator"], {"agent": "claude", "model": "sonnet"})


class ModeTests(CliCase):
    def test_missing_mode_defaults_to_guided(self):
        self.assertEqual(self.ok(BASE)["effective"]["mode"], "guided")

    def test_yolo_profile(self):
        out = self.ok(BASE + "  auto: {mode: yolo}\n", "--profile", "auto")
        self.assertEqual(out["effective"]["mode"], "yolo")
        self.assertEqual(out["effective"]["delivery"], "draft-pr")

    def test_request_mode_overrides_profile(self):
        out = self.ok(BASE + "  auto: {mode: yolo}\n", "--profile", "auto",
                      "--set", "mode=guided")
        self.assertEqual(out["effective"]["mode"], "guided")

    def test_request_yolo_preserves_roles(self):
        out = self.ok(BASE, "--set", "mode=yolo")
        self.assertEqual(out["effective"]["mode"], "yolo")
        self.assertEqual(out["effective"]["roles"]["implementation"]["agent"], "claude")

    def test_invalid_modes_rejected(self):
        for value in ("auto", "true", "1", "null", "[]"):
            with self.subTest(value=value):
                self.fails(BASE + "  auto: {mode: " + value + "}\n", needle="mode")
        self.fails(BASE, "--set", "mode=auto", needle="mode")

    def test_yolo_allows_explicit_local_delivery(self):
        out = self.ok(BASE, "--set", "mode=yolo", "--set", "delivery=local")
        self.assertEqual(out["effective"]["delivery"], "local")


class ErrorTests(CliCase):
    def test_unknown_profile(self):
        err = self.fails(BASE, "--profile", "nope", needle="프로필 'nope'이 없습니다")
        self.assertIn("default", err)

    def test_default_profile_missing(self):
        self.fails(BASE.replace("default_profile: default", "default_profile: ghost"),
                   needle="default_profile: profiles에 'ghost'가 없습니다")

    def test_duplicate_role_key(self):
        self.fails(BASE.replace("    verification: {agent: codex}\n",
                                "    verification: {agent: codex}\n    design: {agent: claude}\n"),
                   needle="중복 키 'design'")

    def test_duplicate_profile_key(self):
        self.fails(BASE + "  default: {delivery: local}\n", needle="중복 키 'default'")

    def test_duplicate_top_level_key(self):
        self.fails(BASE + "version: 1\n", needle="중복 키 'version'")

    def test_unknown_keys_at_each_level(self):
        for text, needle in [
            (BASE + "extra: 1\n", "알 수 없는 키 'extra'"),
            (BASE.replace("  delivery: draft-pr", "  delivery: draft-pr\n  timeout: 30"), "defaults: 알 수 없는 키 'timeout'"),
            (BASE.replace("design: {agent: codex}", "design: {agent: codex, temp: 1}"), "defaults.roles.design: 알 수 없는 키 'temp'"),
            (BASE.replace("    design:", "    reviewer: {agent: codex}\n    design:"), "알 수 없는 키 'reviewer'"),
            (BASE + "  x: {roles: {qa: {agent: codex}}}\n", "profiles.x.roles: 알 수 없는 키 'qa'"),
        ]:
            with self.subTest(needle=needle):
                self.fails(text, needle=needle)

    def test_invalid_types(self):
        for text, needle in [
            (BASE.replace("version: 1", 'version: "1"'), "version: 정수 1"),
            (BASE.replace("version: 1", "version: true"), "version: 정수 1"),
            (BASE.replace("version: 1", "version: 2"), "version: 정수 1"),
            (BASE.replace("design: {agent: codex}", "design: {agent: gemini}"), "defaults.roles.design.agent"),
            (BASE.replace("design: {agent: codex}", 'design: {agent: codex, model: ""}'), "defaults.roles.design.model"),
            (BASE.replace("design: {agent: codex}", "design: {agent: codex, model: 5}"), "defaults.roles.design.model"),
            (BASE.replace("design: {agent: codex}", "design: codex"), "defaults.roles.design: 매핑"),
            (BASE.replace("delivery: draft-pr", "delivery: push"), "defaults.delivery"),
            (BASE.replace("  default: {}", "  default:"), "profiles.default: 매핑"),
            ("- 1\n", "최상위는 매핑"),
            ("", "최상위는 매핑"),
        ]:
            with self.subTest(needle=needle, text=text[:40]):
                self.fails(text, needle=needle)

    def test_broken_unselected_profile_is_still_reported(self):
        self.fails(BASE + "  broken: {delivery: push}\n", needle="profiles.broken.delivery")

    def test_unselected_profile_semantic_error(self):
        self.fails(BASE + "  broken: {roles: {design: {effort: high}}}\n",
                   needle="profiles.broken")

    def test_effort_without_model(self):
        self.fails(BASE.replace("design: {agent: codex}", "design: {agent: codex, effort: high}"),
                   needle="roles.design: effort는 명시적 model과 함께")
        # agent change drops inherited model, so effort alone in the same layer is an error
        self.fails(BASE, "--set", "research.agent=claude", "--set", "research.effort=high",
                   needle="roles.research: effort는 명시적 model과 함께")

    def test_missing_role_in_effective_config(self):
        self.fails(BASE.replace("    verification: {agent: codex}\n", ""), needle="역할 'verification'이 없습니다")
        self.fails(BASE.replace("design: {agent: codex}", "design: {model: x}"), needle="roles.design: agent가 없습니다")

    def test_aliases_anchors_and_merge_keys_rejected(self):
        self.fails(BASE.replace("coordinator: {agent: codex, model: gpt-5, effort: high}",
                                "coordinator: &c {agent: codex}"), needle="앵커(&c)")
        self.fails(BASE.replace("defaults:\n", "x: &v 1\ndefaults:\n").replace("version: 1", "version: *v"),
                   needle="별칭(*v)")
        self.fails(BASE.replace("design: {agent: codex}", "design:\n      <<: {agent: codex}"),
                   needle="병합 키(<<)")

    def test_alias_without_anchor_is_yaml_error(self):
        self.fails(BASE.replace("design: {agent: codex}", "design: *nope"), needle="별칭(*nope)")

    def test_python_tags_rejected(self):
        self.fails(BASE.replace("design: {agent: codex}", "design: !!python/object:os.system {}"),
                   needle="YAML 파싱 오류")

    def test_bad_request_overrides(self):
        for arg, needle in [
            ("qa.agent=codex", "알 수 없는 역할 'qa'"),
            ("design.temp=1", "알 수 없는 필드 'temp'"),
            ("design.agent=gemini", "요청 변경.roles.design.agent"),
            ("delivery=push", "요청 변경.delivery"),
            ("design.model=", "요청 변경.roles.design.model"),
            ("nokv", "KEY=VALUE"),
        ]:
            with self.subTest(arg=arg):
                self.fails(BASE, "--set", arg, needle=needle)


class EnvironmentTests(CliCase):
    def test_missing_config_file_is_not_created(self):
        path = os.path.join(self.tmp.name, "absent", "config.yaml")
        proc = self.run_cli(config=path)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("설정 파일이 없습니다", proc.stderr)
        self.assertFalse(os.path.exists(os.path.dirname(path)))

    def test_missing_pyyaml_reports_cleanly(self):
        proc = self.run_cli(config=self.write(BASE), pre="import sys; sys.modules['yaml'] = None; ")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("PyYAML이 없습니다", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
