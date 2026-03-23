---
name: swagger-auto-gen
description: Automatically generate or update Swagger/OpenAPI documentation by analyzing git changes. Use this skill whenever the user wants to create API documentation, update Swagger/OpenAPI specs, or asks Claude to "make swagger docs", "generate API docs", "update openapi", or "document my API changes". Also trigger when the user says things like "내 API 문서 만들어줘", "스웨거 문서 생성", "API 변경사항 문서화". This skill inspects git stash or working tree diffs, identifies changed endpoints, and produces complete OpenAPI 3.0 YAML documentation.
---

# Swagger Auto-Gen Skill

Automatically generate Swagger/OpenAPI 3.0 documentation from git changes (stash, diff, or staged files).

## Workflow

### Step 1: Detect Git Context

Run these commands to understand what changed:

```bash
# Check if there's anything in stash
git stash list

# Show the most recent stash diff
git stash show -p stash@{0}

# Alternatively, check working tree + staged changes
git diff HEAD
git diff --cached
```

If `git stash list` is empty, fall back to:
```bash
git diff HEAD          # unstaged changes vs last commit
git diff --cached      # staged changes
git diff HEAD~1 HEAD   # last commit vs previous
```

Ask the user which source to use if ambiguous.

### Step 2: Parse Changed Files

From the diff output, identify:
- **Which files changed** (look for `diff --git a/... b/...` lines)
- **What kind of changes**: new routes, modified endpoints, deleted endpoints, schema changes
- **Framework clues**: detect FastAPI, Flask, Django REST, Express, Spring, etc.

#### Framework Detection Patterns

| Framework | Signals |
|-----------|---------|
| FastAPI | `@app.get`, `@router.post`, `APIRouter`, `BaseModel`, type hints |
| Flask | `@app.route`, `@blueprint.route`, `request.json` |
| Django REST | `ViewSet`, `APIView`, `serializers.py`, `urls.py` |
| Express (Node) | `app.get(`, `router.post(`, `req.body`, `res.json` |
| Spring Boot | `@RestController`, `@GetMapping`, `@RequestBody` |

### Step 3: Extract API Information

For each changed route/endpoint, extract:

```
- HTTP Method (GET, POST, PUT, DELETE, PATCH)
- Path (e.g., /users/{id})
- Path parameters
- Query parameters
- Request body schema (from Pydantic models, serializers, DTOs, etc.)
- Response schema
- Status codes
- Auth requirements (if visible)
- Docstrings / comments as description
```

**FastAPI example extraction:**
```python
# Source code:
@router.post("/users", response_model=UserResponse)
async def create_user(body: CreateUserRequest, db: Session = Depends(get_db)):
    """Create a new user account."""
    ...

# → Extract:
# method: POST, path: /users
# requestBody: CreateUserRequest fields
# response: UserResponse fields
# description: "Create a new user account."
```

### Step 4: Detect Existing Swagger File

Check for existing OpenAPI spec:
```bash
find . -name "openapi.yaml" -o -name "openapi.json" \
       -o -name "swagger.yaml" -o -name "swagger.json" \
       -o -name "api_spec.yaml" 2>/dev/null | head -5
```

- **If found**: Load and MERGE new/changed endpoints into it (preserve unchanged parts)
- **If not found**: Generate a full new spec from scratch

### Step 5: Generate OpenAPI 3.0 YAML

Output format:

```yaml
openapi: 3.0.3
info:
  title: <Infer from project name or ask user>
  version: <Infer from package.json / pyproject.toml / ask>
  description: <From README or project description if available>

servers:
  - url: http://localhost:8000
    description: Local development

tags:
  - name: <group name>
    description: <group description>

paths:
  /resource/{id}:
    get:
      tags: [resource]
      summary: <Short action summary>
      description: <From docstring>
      operationId: getResourceById
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Success
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ResourceResponse'
        '404':
          description: Not found

components:
  schemas:
    ResourceResponse:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
      required: [id, name]
```

### Step 6: Output the Documentation

1. **Print a summary** of what was detected and documented:
   ```
   📋 변경 감지 결과:
   - 추가된 엔드포인트: POST /users, GET /users/{id}
   - 수정된 엔드포인트: PUT /users/{id}
   - 삭제된 엔드포인트: 없음
   - 감지된 프레임워크: FastAPI
   ```

2. **Write the YAML file** to `openapi.yaml` (or update existing)

3. **Show a diff** if merging into existing spec:
   ```
   ✅ openapi.yaml 업데이트 완료
   + paths./users.post (새로 추가)
   ~ paths./users/{id}.put (수정됨)
   ```

4. **Optionally** ask if the user wants:
   - JSON format instead of YAML
   - A specific output path
   - Swagger UI HTML generated locally

---

## Edge Cases

### Pydantic / Schema Models
When you see `class SomeModel(BaseModel):` in the diff, extract all fields as schema properties. Handle:
- `Optional[str]` → `type: string`, not required
- `List[Item]` → `type: array, items: $ref`
- `Enum` types → `enum: [val1, val2]`
- `Field(description=...)` → use as property description

### No Docstrings
If there are no docstrings, infer summary from:
- Function name (snake_case → human readable: `create_user` → "Create User")
- HTTP method + path noun

### Auth Detection
Look for patterns:
- `Depends(get_current_user)` → add Bearer token security
- `@login_required` → add session/cookie security
- `Authorization` header usage → add apiKey or Bearer

### Ambiguous Changes
If the diff is large or unclear, ask the user:
> "다음 파일들에서 변경이 감지됐어요: `routers/users.py`, `routers/items.py`. 어떤 파일을 기준으로 문서를 생성할까요?"

---

## Example Invocations

- "git stash에 있는 내용으로 swagger 만들어줘"
- "API 변경사항 swagger 문서로 만들어줘"
- "최근 커밋 기준으로 openapi.yaml 업데이트해줘"
- "FastAPI 라우터 변경사항 문서화해줘"
- "Generate swagger docs from my latest changes"
- "Update openapi spec based on git diff"