---
name: enrich-schema

description: >
  Django DRF 뷰에 @extend_schema 데코레이터를 추가하여 drf-spectacular API 문서를 보강합니다.
  Use this skill when the user says "/enrich-schema", "API 문서 보강해줘", "스키마 설명 추가해줘",
  "extend_schema 추가해줘", "API 문서 상세하게", or "스키마 enrichment".
  뷰 파일을 분석하고, 서비스 → 예외 call chain을 추적하여 모든 CustomError(5자리 status_code)를 수집한 뒤,
  한국어 summary/description과 함께 @extend_schema() 데코레이터를 추가합니다.

---

# Enrich Schema Skill

Django DRF 뷰에 `@extend_schema()` 데코레이터를 추가하여 `drf-spectacular`가 상세한 한국어 API 문서를 생성하도록 합니다.

스키마 정의는 **뷰 파일에 인라인으로 작성하지 않고**, 별도의 `openapi/` 모듈에 `dict(...)` 형태로 분리하여 관리합니다.

## Workflow

### Step 1: Detect Target Views

#### 1-0. Init Mode Detection

git diff 전에, 프로젝트에 `@extend_schema`가 이미 적용되어 있는지 확인합니다:

1. **기존 `@extend_schema` 사용량 확인**:
   ```bash
   # @extend_schema가 있는 뷰 파일 수
   grep -rl "extend_schema" --include="*.py" django/ | grep -E '/views/' | wc -l
   # 전체 뷰 파일 수 (__init__.py 제외)
   find django/ -path '*/views/*.py' ! -name '__init__.py' | wc -l
   ```

2. **모드 결정**:
   - 뷰 파일의 **20% 미만**에 `@extend_schema`가 있으면 → **Init mode 후보**
   - **20% 이상**이면 → 일반 git diff 모드로 진행

3. **유저 확인** (init mode만):
   - 전체 뷰 파일 수와 `@extend_schema` 적용 수를 보여줌
   - 질문: "프로젝트에 `@extend_schema`가 거의 적용되지 않았습니다. 전체 뷰 파일({N}개)을 대상으로 init 모드로 진행할까요?"
   - 승인 시 → 전체 뷰 파일을 대상으로 수집 (Step 1-1)
   - 거절 시 → 일반 git diff 모드 (Step 1-2)

#### 1-1. Init Mode: 전체 뷰 파일 수집

```bash
find django/ -path '*/views/*.py' ! -name '__init__.py'
```

이 목록을 대상 파일로 사용하고 Step 1-2를 건너뜁니다.

#### 1-2. Normal Mode: Git Diff

```bash
# main 브랜치 대비 변경된 뷰 파일
git diff main --name-only -- '*.py' | grep -E '/views/'

# 브랜치 diff가 없으면 working tree 확인
git diff --name-only -- '*.py' | grep -E '/views/'
git diff --cached --name-only -- '*.py' | grep -E '/views/'
```

유저가 특정 파일이나 "전체 뷰"를 지정하면 그 범위를 사용합니다.

### Step 2: Dynamic Project Discovery

뷰를 enriching하기 전에, 프로젝트 구조를 동적으로 탐색하여 컨텍스트를 구축합니다.

#### 2-1. URL Routing Discovery

`urls.py` 파일을 읽어 뷰 → URL 경로 매핑을 구축합니다:

1. `settings.py`에서 `ROOT_URLCONF` 확인
2. `include()` 호출을 추적하여 모든 앱의 `urls.py` 탐색
3. 각 대상 뷰의 URL 경로와 HTTP 메서드 파악

#### 2-2. Permission & Role Discovery

각 뷰의 `permission_classes`를 읽고, 해당 permission 클래스 소스 코드를 분석합니다:

1. permission 클래스 정의 위치 탐색 (`class *Permission`)
2. 각 permission이 허용하는 역할/사용자 유형 파악
3. 한국어 설명 매핑 (예: "User 접근 가능", "Admin 전용")
4. `AllowAny` 또는 빈 `get_permissions()` → 인증 불필요, `auth=[]` 사용
5. OR 로직의 다중 permission → 모든 허용 역할 나열

#### 2-3. Exception & Error Code Discovery (핵심)

프로젝트의 모든 커스텀 예외를 수집합니다:

1. 모든 앱에서 `exceptions/` 디렉토리 또는 `exceptions.py` 파일 탐색
2. 각 예외 파일을 읽어 카탈로그 작성:
   - 클래스명
   - `status_code` (**5자리 비즈니스 코드** — 프론트엔드가 이 코드로 에러 핸들링)
   - `default_detail` (메시지)
   - HTTP 상태 코드
3. 에러 응답 구조 파악: `{"status_code": 5자리, "message": "..."}`

> **중요**: 프론트엔드는 5자리 `status_code`로 에러를 분기 처리합니다. 모든 CustomError의 status_code를 빠짐없이 수집해야 합니다.

#### 2-4. Authentication Error Discovery

프로젝트의 커스텀 인증 클래스를 분석합니다:

1. settings의 `DEFAULT_AUTHENTICATION_CLASSES` 또는 뷰의 `authentication_classes` 확인
2. 인증 관련 예외 파악 (토큰 만료, 유효하지 않은 토큰, 헤더 누락 등)

#### 2-5. Base Model Pattern Discovery

soft delete 등 API 동작에 영향을 주는 패턴 확인:

1. base model에서 `deleted_at`, `is_deleted` 등 soft-delete 필드 확인
2. soft delete가 있으면 DELETE 엔드포인트 description에 명시

### Step 3: Analyze View Code

각 뷰 클래스/함수에서 추출할 정보:

- **HTTP 메서드**: 정의된 메서드 (`get`, `post`, `put`, `patch`, `delete`)
- **Serializer**: `serializer_class` 또는 `get_serializer_class()` 반환값
- **Permissions**: `permission_classes` 목록 → Step 2-2 결과로 설명 텍스트 매핑
- **Queryset**: `get_queryset()`으로 필터링/스코핑 이해
- **Response 패턴**: 반환되는 상태 코드 (`Response(...)` 및 `status.HTTP_*`)
- **Lookup field**: detail 뷰의 `lookup_field`

#### 3-1. Endpoint 용도 파악 (유저 질문 단계)

각 엔드포인트의 용도를 파악합니다:

1. **코드에서 추론 가능한 경우**: 메서드명, docstring, serializer 필드, URL 패턴 등에서 용도를 파악
2. **불명확한 경우 반드시 유저에게 질문**:
   - 비즈니스 로직이 복잡하거나 메서드명만으로 용도가 불분명할 때
   - 예: "이 엔드포인트(`POST /api/v1/assessments/{id}/submit/`)는 어떤 상황에서 사용되나요? (예: 학생이 검사를 완료할 때 호출, 선생님이 수동 제출할 때 호출 등)"
   - 여러 엔드포인트가 불명확하면 한꺼번에 모아서 질문

> **원칙**: 추측하지 말고 물어보세요. 부정확한 description보다 정확한 description이 중요합니다.

### Step 3.5: Exhaustive Response Case Analysis (CRITICAL)

각 엔드포인트에 대해 성공과 실패의 **모든** 가능한 응답 경로를 추적해야 합니다.

#### 추적 방법

1. **뷰 메서드 읽기** — 모든 `Response(...)` 반환과 상태 코드 식별
2. **서비스 레이어 추적** — 뷰가 호출하는 서비스 메서드를 따라가며 모든 예외 식별
3. **Serializer 확인** — `serializer.is_valid(raise_exception=True)`는 DRF `ValidationError` (400) 발생 가능
4. **예외 파일 확인** — Step 2-3에서 구축한 카탈로그로, call chain에서 발생 가능한 모든 예외 탐색
5. **인증 확인** — Step 2-4 결과로, 인증이 필요한 엔드포인트에 인증 예외 포함
6. **권한 확인** — permission 클래스 실패 시 403

> **반드시 5자리 status_code를 포함해야 합니다.** 프론트엔드는 HTTP 상태 코드가 아닌 이 비즈니스 코드로 에러를 핸들링합니다.

#### `@extend_schema`에서의 응답 표현

에러 문서화는 **description**(전체 나열)과 **OpenApiExample**(대표 케이스)로 이원화합니다.

**1. description에 에러 케이스 전체 나열 (MUST):**

description은 프론트엔드의 **주요 참조 문서**입니다. 가능한 모든 에러를 bullet point로 빠짐없이 나열합니다:

```python
description=(
    "리소스를 생성합니다.\n\n"
    "**권한**: 역할명\n\n"
    "**비즈니스 에러**:\n"
    "- `400` (코드): 설명\n"
    "- `400` (코드): 설명\n"
    "- `404` (코드): 리소스 없음\n\n"
    "**인증 에러**:\n"
    "- `401` (20104): Authorization 헤더 누락\n"
    "- `401` (20105): Access Token 미제공\n"
    "- `401` (20201): Access Token 만료\n"
    "- `401` (20202): 유효하지 않은 Access Token\n"
    "- `403`: 권한 없음"
),
```

**2. OpenApiExample은 HTTP 코드당 대표 1-2개만 (JSON 구조 확인용):**

에러 JSON 구조가 동일하므로 (`{"status_code": N, "message": "..."}`) 모든 에러에 example을 만들 필요 없습니다. HTTP 상태 코드별 대표 케이스만 포함합니다:

```python
responses={
    201: SomeSerializer,
    400: OpenApiTypes.OBJECT,
    401: OpenApiTypes.OBJECT,
},
examples=[
    # 성공 응답 example (필수 — 아래 성공 응답 규칙 참조)
    OpenApiExample(
        "생성 성공",
        value={...},  # serializer 필드 기반 실제 값
        response_only=True,
        status_codes=["201"],
    ),
    # 에러 example — HTTP 코드당 대표 1-2개
    OpenApiExample(
        "비즈니스 에러 (대표)",
        value={"status_code": 12345, "message": "에러 메시지"},
        response_only=True,
        status_codes=["400"],
    ),
    OpenApiExample(
        "인증 실패 (대표)",
        value={"status_code": 20201, "message": "Expired access token"},
        response_only=True,
        status_codes=["401"],
    ),
],
```

### Step 4: OpenAPI 모듈에 스키마 정의 작성

스키마 정의는 **뷰 파일에 인라인으로 작성하지 않습니다.** 별도의 `openapi/` 모듈 파일에 `dict(...)` 형태로 정의하고, 뷰에서 import하여 사용합니다.

#### 4-1. 파일 구조

각 도메인(뷰 파일)별로 대응하는 `openapi/` 모듈 파일을 생성합니다:

```
django/{app}/
├── openapi/
│   ├── __init__.py
│   ├── user.py          # views/user.py 대응
│   ├── payment.py       # views/payment.py 대응
│   ├── auth.py          # views/auth.py 대응
│   └── ...
└── views/
    ├── user.py
    ├── payment.py
    └── ...
```

- 기존 `openapi/` 디렉토리와 파일이 이미 있으면 거기에 **추가**
- 없으면 새로 `openapi/` 디렉토리와 파일을 **생성**
- `__init__.py`는 빈 파일 또는 기존 것 유지

#### 4-2. 스키마 정의 형태

`openapi/{domain}.py` 파일에 `dict(...)` 형태로 정의합니다:

```python
from drf_spectacular.utils import OpenApiExample, OpenApiTypes

from {app}.serializers import SomeSerializer, AnotherSerializer

# ============================================================
# {ViewClassName}
# ============================================================

{view_name}_{method} = dict(
    tags=["Tag"],
    summary="한국어 요약",
    description=(
        "한국어 상세 설명...\n\n"
        "**에러 케이스**:\n"
        "- `400`: 설명\n"
    ),
    operation_id="operationId",
    responses={200: SomeSerializer, 400: OpenApiTypes.OBJECT},
)
```

#### 4-3. 변수 네이밍 규칙 (MUST)

변수명은 `{view_name}_{method}` 형태의 **소문자 snake_case**로 작성합니다:

| 뷰 클래스 | HTTP 메서드 | 변수명 |
|-----------|-----------|--------|
| `UserView` | `get` | `user_get` |
| `UserView` | `post` | `user_post` |
| `UserDetailView` | `get` | `user_detail_get` |
| `UserDetailView` | `put` | `user_detail_put` |
| `PaymentTossView` | `get` | `payment_toss_get` |
| `LoginView` | `post` | `login_post` |

뷰 클래스명에서 `View` 접미사를 제거하고, PascalCase → snake_case로 변환합니다.

#### 4-4. 뷰에서 Import 및 사용

뷰 파일에서는 openapi 모듈을 import한 후 `@extend_schema(**module.var_name)` 형태로 사용합니다:

```python
# views/user.py
from drf_spectacular.utils import extend_schema
from {app}.openapi import user  # openapi 모듈 import

class UserView(...):
    @extend_schema(**user.user_get)
    def get(self, request, *args, **kwargs):
        ...

    @extend_schema(**user.user_post)
    def post(self, request, *args, **kwargs):
        ...
```

#### 4-5. Import 규칙

**openapi 모듈 파일** (`openapi/{domain}.py`):
```python
from drf_spectacular.utils import OpenApiExample, OpenApiTypes
# 실제로 사용하는 것만 import (OpenApiParameter 등은 필요할 때만)

from {app}.serializers import SomeSerializer, AnotherSerializer
```

**뷰 파일** (`views/{domain}.py`):
```python
from drf_spectacular.utils import extend_schema
from {app}.openapi import {domain}
```

- `extend_schema`만 뷰에서 import — `OpenApiExample`, `OpenApiTypes` 등은 openapi 모듈에서만 사용
- 기존 뷰에 인라인 `@extend_schema`가 있으면 openapi 모듈로 이동 후 뷰에서는 `**module.var` 형태로 교체

#### 필수 필드

모든 스키마 dict에 반드시 포함:

| 필드 | 규칙 |
|------|------|
| `tags` | 리소스 레벨 태그명 리스트. URL 경로에서 도출 (예: `/api/users/` → `"User"`) |
| `summary` | 한국어, 간결하게 (예: "로그인", "사용자 목록 조회", "주문 생성") |
| `description` | 한국어, 동작 설명 + 에러 케이스 bullet points + 권한 정보 |
| `operation_id` | camelCase (예: `login`, `listUsers`, `createPayment`, `retrieveUser`) |

#### Tag 도출

URL 경로나 뷰 컨텍스트에서 동적으로 태그를 도출합니다:

- URL의 주요 리소스명 사용 (예: `/api/users/` → `"User"`, `/api/orders/` → `"Order"`)
- 하위 리소스는 상위 리소스 태그 또는 설명적 하위 태그 사용

#### 조건부 필드

| 필드 | 포함 조건 |
|------|----------|
| `request` | POST/PUT/PATCH — serializer 클래스 참조 |
| `responses` | 항상 — 성공 + 에러 상태 코드 매핑 |
| `examples` | 항상 — 성공 응답 example 필수 + POST/PUT/PATCH 요청 example + 에러 대표 example |
| `parameters` | query params 또는 비표준 path params 존재 시 |
| `auth` | 인증 불필요 엔드포인트에 `auth=[]` |

> **주의**: 인증 불필요 표시에는 `security=[]`가 아닌 **`auth=[]`**를 사용합니다.

#### 성공 응답 Example 규칙 (MUST)

모든 엔드포인트에 성공 응답 `OpenApiExample`을 반드시 포함합니다:

- `response_only=True`, `status_codes`에 해당 성공 HTTP 코드 지정
- serializer 필드를 기반으로 **실제 값을 채운** example (빈 값이나 placeholder 금지)
- 복잡한 중첩 구조일수록 example이 중요 — 프론트가 응답 타입을 정의하는 데 직접 참조

```python
OpenApiExample(
    "주문 생성 성공",
    response_only=True,
    status_codes=["201"],
    value={
        "id": 1,
        "external_id": "ORD-20260310-ABCDEF",
        "status": "PENDING",
        "total_amount": 50000,
        "created_at": "2026-03-10T12:00:00Z",
    },
),
```

#### Pagination 응답 패턴

List 엔드포인트가 paginated 응답을 반환하는 경우:

- `responses`에는 **serializer만 지정** — drf-spectacular가 pagination wrapper를 자동으로 처리
- 성공 example에는 **paginated 구조**를 반영

```python
# responses에 serializer만 지정 (pagination wrapper는 drf-spectacular가 자동 처리)
responses={
    200: SomeSerializer,
    401: OpenApiTypes.OBJECT,
},
examples=[
    OpenApiExample(
        "목록 조회 성공",
        response_only=True,
        status_codes=["200"],
        value={
            "count": 25,
            "next": "https://api.example.com/resource/?page=2",
            "previous": None,
            "results": [
                {"id": 1, "name": "항목 1", ...},
                {"id": 2, "name": "항목 2", ...},
            ],
        },
    ),
],
```

#### Response Code 매핑 (기본선 — 엔드포인트별 확장)

Step 3.5 분석 후 발견된 코드를 추가합니다. 아래는 최소 기준:

| 패턴 | 기본 코드 | 추가 가능 |
|------|----------|----------|
| List (GET collection) | `200`, `401`, `403` | |
| Retrieve (GET detail) | `200`, `401`, `403`, `404` | |
| Create (POST) | `201`, `400`, `401`, `403` | `409` (중복) |
| Update (PUT/PATCH) | `200`, `400`, `401`, `403`, `404` | `409` (충돌) |
| Delete (DELETE) | `204`, `401`, `403`, `404` | |
| Public 엔드포인트 | `401`, `403` 제외 | |

#### operationId 규칙

| HTTP 메서드 | 패턴 | 예시 |
|------------|------|------|
| GET (list) | `list{Resource}s` | `listUsers`, `listAssessments` |
| GET (detail) | `retrieve{Resource}` | `retrieveUser`, `retrieveAssessment` |
| POST | `create{Resource}` | `createUser`, `createPayment` |
| PUT | `update{Resource}` | `updateUser` |
| PATCH | `partialUpdate{Resource}` | `partialUpdateUser` |
| DELETE | `destroy{Resource}` | `destroyUser` |
| Custom action | 설명적 camelCase | `login`, `tokenRefresh`, `bulkCreateOrders` |

### Step 5: Example Output

#### openapi 모듈 파일 (`openapi/auth.py`):

```python
from drf_spectacular.utils import OpenApiExample, OpenApiTypes

from common.serializers import LoginSerializer

# ============================================================
# LoginView
# ============================================================

login_post = dict(
    tags=["Auth"],
    summary="로그인",
    description=(
        "user_type에 따라 다양한 로그인 방식을 지원합니다.\n"
        "- APTIFIT: identifier/password (일반 계정) 또는 provider/code/redirect_uri (소셜 로그인)\n"
        "- TEACHER / PARTNER / ADMIN: identifier/password\n\n"
        "**인증**: 불필요\n\n"
        "**에러 케이스**:\n"
        "- `400`: 필수 필드 누락 (user_type, identifier 등)\n"
        "- `401` (20401): 인증 세션 없음\n"
        "- `401` (20101): 알 수 없는 Provider Token 오류\n"
        "- `404` (20000): 사용자 없음"
    ),
    operation_id="login",
    request=LoginSerializer,
    responses={
        201: LoginSerializer,
        400: OpenApiTypes.OBJECT,
        401: OpenApiTypes.OBJECT,
        404: OpenApiTypes.OBJECT,
    },
    auth=[],
    examples=[
        # 요청 examples
        OpenApiExample(
            "일반 로그인",
            value={
                "user_type": "APTIFIT",
                "identifier": "user@example.com",
                "password": "password123",
            },
            request_only=True,
        ),
        OpenApiExample(
            "소셜 로그인",
            value={
                "user_type": "APTIFIT",
                "provider": "KAKAO",
                "code": "oauth_auth_code",
                "redirect_uri": "https://example.com/callback",
            },
            request_only=True,
        ),
        # 성공 응답 example (필수)
        OpenApiExample(
            "로그인 성공",
            value={
                "access_token": "eyJhbGciOiJIUzI1NiIs...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
                "user": {
                    "id": 1,
                    "identifier": "user@example.com",
                    "user_type": "APTIFIT",
                },
            },
            response_only=True,
            status_codes=["201"],
        ),
        # 에러 examples — HTTP 코드당 대표 1개
        OpenApiExample(
            "유효성 검증 실패",
            value={"user_type": ["This field is required."]},
            response_only=True,
            status_codes=["400"],
        ),
        OpenApiExample(
            "인증 세션 없음",
            value={"status_code": 20401, "message": "Authentication session not found"},
            response_only=True,
            status_codes=["401"],
        ),
        OpenApiExample(
            "사용자 없음",
            value={"status_code": 20000, "message": "User does not exist"},
            response_only=True,
            status_codes=["404"],
        ),
    ],
)
```

#### 뷰 파일 (`views/auth.py`):

```python
from drf_spectacular.utils import extend_schema
from common.openapi import auth

class LoginView(BaseCreateModelMixin, BaseGenericAPIView):
    serializer_class = LoginSerializer

    def get_authenticators(self):
        return []

    def get_permissions(self):
        return [AllowAny()]

    @extend_schema(**auth.login_post)
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response_data = AuthService().login(**serializer.validated_data)
        return Response(self.serializer_class(response_data).data, status=status.HTTP_201_CREATED)
```

### Step 5.5: Detail View Example (인증 필요 엔드포인트)

#### openapi 모듈 파일 (`openapi/user.py`):

description에 비즈니스 에러와 인증 에러를 **전부** 나열하고, examples는 성공 + 대표 에러만:

```python
from drf_spectacular.utils import OpenApiExample, OpenApiTypes

from aptifit.serializers import UserSerializer

# ============================================================
# UserView
# ============================================================

user_patch = dict(
    tags=["User"],
    summary="사용자 정보 수정 (비밀번호 변경)",
    description=(
        "사용자 정보를 수정합니다. 비밀번호 변경 시 old_password와 new_password를 함께 전달해야 합니다.\n\n"
        "**인증**: JWT 필수\n\n"
        "**권한**:\n"
        "- APTIFIT: 본인 정보만 수정 가능\n\n"
        "**에러 케이스**:\n"
        "- `400` (20500): 기존 비밀번호와 새 비밀번호 모두 필요\n"
        "- `400` (20501): 새 비밀번호가 기존 비밀번호와 동일\n"
        "- `400` (20502): 기존 비밀번호 불일치\n"
        "- `401`: 인증 토큰 없음 또는 만료\n"
        "- `403`: 권한 없음"
    ),
    operation_id="updateUser",
    responses={200: UserSerializer, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    examples=[
        OpenApiExample(
            "비밀번호 변경 요청",
            value={
                "old_password": "current_password123",
                "new_password": "new_password456",
            },
            request_only=True,
        ),
    ],
)
```

#### 뷰 파일 (`views/user.py`):

```python
from drf_spectacular.utils import extend_schema
from aptifit.openapi import user

class UserView(...):
    @extend_schema(**user.user_patch)
    def patch(self, request, *args, **kwargs):
        ...
```

### Step 6: Verification & Output

데코레이터 추가 후:

1. **변경 요약 출력**:
   ```
   변경된 openapi 모듈 파일:
   - aptifit/openapi/user.py: user_get, user_post, user_patch (신규)
   - common/openapi/auth.py: login_post, token_refresh_post (신규 파일)

   변경된 뷰 파일:
   - common/views/auth.py: LoginView.post, TokenRefreshView.post (import + decorator 교체)
   - aptifit/views/user.py: UserView.get/post/patch (import + decorator 교체)

   추가된 @extend_schema: 8개
   ```

2. **스키마 생성 검증**:
   ```bash
   cd django && python manage.py spectacular --format openapi-json --file /tmp/test-schema.json --validate
   ```

3. validation 에러가 있으면 보고하고 수정합니다.

### Step 7: Error Code Registry Sync

이번 작업에서 수집/변경된 CustomError(5자리 `status_code`)가 `docs/error-codes.md`에 일관되게 반영되도록 자동 동기화합니다. `docs/error-codes.md`는 **생성물**이며, 사람이 직접 편집하지 않습니다.

#### 7-1. 스크립트 존재 확인 & Bootstrap

```bash
test -f scripts/sync_error_docs.py
```

- **있으면** → Step 7-2로 진행
- **없으면** → 사용자에게 bootstrap 여부 질문:
  - 승인 시: 이 스킬 저장소의 `templates/sync_error_docs.py` 를 타겟 프로젝트의 `scripts/sync_error_docs.py` 로 복사
  - 복사 경로는 스킬 설치 위치에 따라 다름. 일반적으로: `~/.claude/skills/enrich-schema/templates/sync_error_docs.py` → `scripts/sync_error_docs.py`
  - 최초 실행 시 스크립트가 기존 `docs/error-codes.md` 표에서 도메인 이름을 역추출해 `scripts/error_domains.yaml` seed 파일을 자동 생성

#### 7-2. Dry-run Check

```bash
python scripts/sync_error_docs.py --check
```

- **exit 0 + no diff** → "✓ Error code registry 일관성 OK" 로그만 남기고 종료
- **exit 1** → 스크립트가 stdout에 unified diff, stderr에 violations 리포트 출력

#### 7-3. Violations 처리 (있는 경우)

다음 위반은 **코드 수정으로만** 해결 가능합니다. 문서 동기화를 중단하고 사용자에게 수정을 요청:

- 5자리가 아닌 `code` (`NOT_5_DIGIT`)
- 중복된 `code` (`DUPLICATE`)
- 파일 간 범위 겹침 (`RANGE_OVERLAP`)

위반 요약을 사용자에게 보여주고, 수정 후 다시 `/enrich-schema` 를 돌리거나 `python scripts/sync_error_docs.py --check` 를 직접 실행하도록 안내합니다.

#### 7-4. Diff 처리 (Violation 없을 때)

1. 스크립트가 출력한 unified diff를 사용자에게 그대로 보여줍니다 (추가된 code, 변경된 range, 신규 도메인)
2. 새로 등장한 prefix는 `Unknown (2XXxx)` placeholder로 표시됩니다 — 이 경우 `scripts/error_domains.yaml` 에 해당 prefix 이름을 채울 것을 안내
3. 사용자 승인 시:
   ```bash
   python scripts/sync_error_docs.py --write
   ```
4. `git diff docs/error-codes.md` 로 실제 반영 확인

#### 7-5. 최종 보고

enrich-schema 작업 종료 전 다음을 요약:

- 추가된 error code 개수 & code 목록
- 변경된 range (예: `22000~22199` → `22000~22299`)
- 신규 도메인 (yaml 채울 것 안내)

> **주의**: `docs/error-codes.md` 를 수동 편집하지 마세요. 반드시 `CustomError` 정의를 통해서만 변경되어야 하며, Step 7이 이를 강제합니다.

## Important Rules

- **언어**: 모든 `summary`와 `description` 텍스트는 반드시 **한국어**로 작성
- **기존 코드 보존**: openapi 모듈 dict와 뷰의 import/decorator만 추가/수정. 기존 로직 수정 금지
- **중복 import 방지**: import가 이미 있는지 확인 후 추가
- **일관된 스타일**: 프로젝트 formatter 준수 (Ruff 등)
- **기존 serializer 사용**: `request`와 `responses`에 실제 serializer 클래스 참조, inline 스키마 생성 금지
- **동적 탐색 우선**: 항상 프로젝트 구조를 동적으로 탐색. 파일 경로, 태그명, 에러 코드를 하드코딩하지 않음
- **에러 응답**: 에러 응답 스키마에 `OpenApiTypes.OBJECT` 사용 (400, 401, 403, 404, 409 등)
- **Soft delete**: soft delete 패턴 감지 시 (Step 2-5) DELETE 엔드포인트 description에 명시
- **Error code registry 동기화**: 작업 마무리 시 반드시 Step 7을 수행. `docs/error-codes.md`는 생성물이므로 **직접 편집 금지**, 오직 `CustomError` 정의와 `scripts/error_domains.yaml` 을 통해서만 변경

### OpenAPI 모듈 분리 규칙 (MUST)

- **절대로 뷰 파일에 인라인 `@extend_schema(tags=..., summary=..., ...)` 작성 금지** — 반드시 `openapi/` 모듈에 dict로 정의
- 뷰에서는 `@extend_schema(**module.var_name)` 형태로만 사용
- 기존 `openapi/` 파일이 있으면 해당 파일에 추가, 없으면 새로 생성
- 기존 인라인 `@extend_schema`가 있는 뷰 (예: `common/` 앱)는 모듈 분리 패턴으로 전환
- 변수명은 반드시 `{view_name}_{method}` snake_case 규칙 준수
- openapi 모듈 파일 내에서 뷰 클래스별로 `# ====` 구분 주석 사용
- `auth=[]` 사용 (`security=[]` 아님)

### 추적 불가 에러 Fallback 규칙

call chain 추적 시 완전히 추적할 수 없는 패턴에 대한 대응 규칙:

- **generic `except Exception` 패턴**: 해당 블록 내부에서 호출되는 코드를 추적하여 가능한 에러를 나열. 추적 불가능하면 `500` Internal Server Error로 문서화
- **외부 API 호출** (예: Toss Payments, 소셜 로그인 등): 해당 외부 서비스에서 발생할 수 있는 에러를 문서화. 서비스 코드에서 외부 API 에러를 catch하여 변환하는 패턴이 있으면 변환된 에러를 사용
- **model 메서드 side effect**: 메서드 코드를 직접 읽어 **명시적 raise만** 추적. 암묵적 DB 에러(IntegrityError 등)는 서비스에서 catch하는 경우에만 포함

### 에러 문서화 규칙 (MUST)

- **반드시 전체 call chain 추적**: 뷰 → 서비스 → repository/model까지 모든 예외 탐색
- **예외 파일 읽기**: Step 2-3 카탈로그로 각 엔드포인트 도메인의 모든 가능한 에러 탐색
- **비즈니스 에러 코드 포함**: 모든 에러 예시에 `status_code` (5자리 비즈니스 코드)와 `message` 포함
- **description에 나열**: 모든 에러 케이스를 description 필드에 bullet point로 나열: `- \`{http_code}\` ({business_code}): {한국어 설명}`
- **에러 예시는 대표만**: `OpenApiExample`은 HTTP 코드당 대표 1-2개만. description의 bullet point가 전체 에러 목록 역할
- **공통 인증 에러**: 인증 필요 엔드포인트에 Step 2-4에서 발견한 모든 인증 관련 예외를 description에 포함
- **성공 응답 예시 필수**: 모든 엔드포인트에 성공 응답 `OpenApiExample` 포함
- **엣지 케이스 포함**: call chain 추적 중 발견된 도메인 특화 에러 코드를 description에서 누락 금지
- **애매하면 유저에게 질문**: 엔드포인트 용도가 코드만으로 불명확하면 반드시 유저에게 질문
