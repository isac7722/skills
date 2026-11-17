# 설정

사용자 설정은 `~/.agents/dev-flow/config.yaml`이다. [예시](../assets/config.example.yaml)는 dev-flow 전용 형식이며 Orca 내장 설정이 아니다. 최초 실행 시 파일이 없을 때만 복사하고 생성 경로·기본 배정을 알린다. API 키나 인증 토큰을 넣지 않는다.

## 해석 규칙

유효 설정은 직접 해석하지 말고 이 스킬의 [`scripts/resolve_config.py`](../scripts/resolve_config.py)로 계산한다. `yaml.safe_load`만으로는 중복 키(마지막 값이 조용히 이김)와 별칭·병합 키(펼쳐진 뒤에는 구분 불가)를 잡을 수 없다.

```sh
python3 <skill>/scripts/resolve_config.py [--config PATH] [--profile NAME] \
  [--set <역할>.<agent|model|effort>=값 ...] [--set delivery=값] [--set mode=guided|yolo]
```

- 이번 요청의 명시적 변경은 `--set`으로 전달한다. 기본 경로는 `~/.agents/dev-flow/config.yaml`이다.
- 성공(종료 0) 시 stdout에 `config_path`, `config_sha256`, `profile`, `request_overrides`, `effective` JSON만 출력한다. 이 값을 실행 기록에 저장한다.
- 실패 시 stdout은 비어 있고 stderr에 `error:` 줄을 출력한다. 1 설정 오류, 2 설정 파일 없음·읽기 실패, 3 PyYAML 없음. 오류 메시지로 수정안을 보여주고 멈춘다.
- CLI는 읽기 전용이다. 설정 파일을 만들거나 고치지 않고 작업자를 시작하지 않는다. PyYAML이 없으면 자동 설치하지 말고 사용자에게 알린다. 임의 텍스트 치환으로 대신 해석하지 않는다.
- 테스트: `python3 -m unittest discover -s <skill>/scripts`.

중복 키, 알 수 없는 키, 잘못된 타입, 앵커·별칭·병합 키(`&`, `*`, `<<`)는 오류다. 선택하지 않은 프로필도 defaults와 병합해 완결성과 effort/model 제약까지 검사한다. 요청 override로 잘못된 프로필을 우회하지 않는다. 아래 구조를 사용한다.

- `version`: 정수 `1`.
- `default_profile`: `profiles`에 실제 존재하는 이름.
- `defaults`: `roles`, `delivery`, 선택 `mode`.
- `profiles`: 이름별 부분 설정. 각 프로필은 `roles`, `delivery`, `mode`만 덮어쓸 수 있다. 빈 프로필은 `{}`로 쓴다(값 없는 `name:`은 오류).
- `roles`: `coordinator`, `research`, `design`, `implementation`, `verification`.
- 각 역할: 필수 `agent`(`codex` 또는 `claude`), 선택 `model`, `effort`(빈 문자열이 아닌 문자열). `effort`는 명시적 `model`과 함께 지정한다. 지원 여부는 설치된 Orca/에이전트로 확인한다.
- `mode`: `guided`(생략 시 기본) 또는 `yolo`. YAML의 yolo는 실행 방식 선택이며 최초 성공 기준 확인을 대신하지 않는다. [모드 규칙](modes.md)을 따른다.
- `delivery`: `draft-pr` 또는 `local`. guided에서는 최종 제안의 기본값이며, yolo에서는 최초 승인에 포함할 전달 범위다. 설정값 자체가 푸시·PR 게시의 사전 허가는 아니다.

적용 순서는 defaults → 선택 프로필(없으면 default_profile) → 이번 요청의 명시적 변경이다. 역할별 필드를 병합한다. agent가 바뀌면 상속된 model·effort를 제거하고 새 설정에서 지정한 값만 사용한다. model만 바뀌면 상속된 effort를 제거한다. 같은 값을 다시 쓰는 것은 변경이 아니며 effort만 바꾸면 model은 유지된다. 최종 결과에 다섯 역할과 각 agent, delivery가 모두 있고 effort가 있으면 model도 있는지 검사한다.

선택 프로필이 없거나 값이 틀리면 수정안을 보여주고 해당 설정에 의존하는 실행을 멈춘다. 에이전트·모델을 추측해 대체하지 않는다.

유효 설정과 설정 파일 해시를 실행 시작 시 저장한다. 파일 변경은 다음 실행부터 적용한다. 진행 중인 실행에 적용하려면 사용자의 변경 요청과 새 유효 설정을 기록한다. 작업 중인 worker의 배정은 몰래 바꾸지 않는다.

## 의존 스킬

각 역할이 시작할 때 해당 에이전트가 실제로 접근 가능한 `SKILL.md`와 필요한 상대 참조를 확인한다. Codex 설치가 Claude에도 제공된다고 가정하지 않는다. 정확한 경로·버전 또는 파일 해시를 실행 기록에 남긴다. 같은 로컬 호스트의 읽을 수 있는 스킬 묶음을 명시적 경로로 전달할 수 있다.

필수 의존성은 `orchestration`, `orca-cli`, 단계별 mattpocock 스킬이다. 스킬 호출 도구가 있으면 사용하고, 없다면 SKILL.md와 해당 분기의 참조를 직접 읽는다. 필요한 스킬이 없으면 해당 단계를 멈추고 누락 이름과 설치/경로 지정 선택지를 알린다. 자동 설치나 업데이트는 하지 않는다.

상위 `implement-spec` 등은 별도 총괄을 중복 생성하므로 자동 호출하지 않는다. 이 스킬이 작업 배정과 단계 전환을 책임지고 mattpocock의 개별 절차를 조합한다. 프로젝트의 문서 구조를 존중하며 용어집·ADR을 중복 생성하지 않는다.
