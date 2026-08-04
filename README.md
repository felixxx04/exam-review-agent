# 期末复习 Agent

面向大学生期末复习场景的 AI 学习助手。用户可以上传课件或讲义，基于资料进行问答、生成练习题、查看薄弱点，并在 `Ask / Quiz / Review` 三种模式之间切换完成复习闭环。

当前仓库已进入 V2 Phase 1。Task 1.1 已将业务默认数据库切换为 PostgreSQL，建立 pgvector Schema、SQLAlchemy Repository 边界和错题持久化；Task 1.2 已实现邀请码注册、用户名/密码登录、安全 Cookie 会话、Refresh Token 轮换、账号禁用和租户隔离，正在等待验收。私人课程和配额仍按后续 Task 逐项实施。

## 核心功能

- 资料上传：文本型 `PDF / DOCX / PPTX`
- 智能问答：围绕上传资料进行问答
- 题目生成：按知识点、难度和数量生成练习题
- 错题分析：记录答题结果并输出薄弱点视图
- 学习工作台：提供 `Ask / Quiz / Review` 三种模式

## 当前架构

```text
frontend (Next.js 15 / React 19)
  -> 邀请码注册 / 登录 / 会话恢复
  -> Ask / Quiz / Review 工作台
  -> Zustand 交互状态

backend (FastAPI / Python 3.11-3.12)
  -> 邀请码 / Argon2id / JWT / Refresh 轮换 / CSRF
  -> chat / materials / quiz / review API
  -> RAG Agent / Quiz Agent / Tracker Agent
  -> PostgreSQL 17（业务数据、错题和资料块元数据）
  -> pgvector 0.8.1 Schema（Phase 3 切换检索实现）
  -> Chroma（Phase 3 前的临时 Dense Retrieval 实现）

local infrastructure (Docker Compose)
  -> PostgreSQL 17 + pgvector 0.8.1
  -> Redis 7.4（Worker 队列）
  -> MinIO（Phase 2 接入的 S3 兼容存储）
```

V2 的详细实施路线见 [`docs/superpowers/plans/2026-08-03-exam-review-agent-v2-optimization.md`](docs/superpowers/plans/2026-08-03-exam-review-agent-v2-optimization.md)，稳定架构决策见 `docs/architecture/`。

## 环境要求

| 工具 | 支持版本 | 当前验证版本 |
|---|---|---|
| Python | 3.11 或 3.12 | 3.12.2 |
| Node.js | `>=20.19.0 <21` 或 `>=22.13.0` | 22.22.2 |
| npm | 10 或 11 | 10.9.7 |
| Docker Engine | 27+ | 29.6.2 |
| Docker Compose | 2.30+ | 5.3.1 |

PostgreSQL、Redis 和 MinIO 的容器版本固定在 `compose.yaml`。运行应用不要求本机安装这些服务端软件。

## 本地运行

### 1. 启动基础设施

在项目根目录执行：

```powershell
Copy-Item .env.example .env
docker compose up -d postgres redis minio
docker compose ps
```

PostgreSQL 和 Redis 是当前后端 readiness 检查的必需依赖。MinIO 已固定本地版本，但对象存储接入属于 Phase 2。

PostgreSQL 容器使用 `exam_review_admin` 仅完成初始化，并创建 `NOSUPERUSER NOBYPASSRLS` 的 `exam_review` 应用角色。后端和 Alembic 均使用应用角色连接，确保 `FORCE ROW LEVEL SECURITY` 不会被运行时连接绕过。

### 2. 启动后端

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.lock
pip install -e . --no-deps
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

启动前至少将 `.env` 中的 `DEEPSEEK_API_KEY` 和 `JWT_SECRET` 替换为有效值。开发环境通过 HTTP 访问时使用示例中的 `AUTH_COOKIE_SECURE=false`；公开部署必须启用 HTTPS 并设为 `true`。`alembic upgrade head` 会从空 PostgreSQL 数据库建立 V2 Schema 并启用 `vector` Extension；旧 SQLite/Chroma 数据不会迁移。

迁移完成后创建首个管理员（命令会交互式读取并确认密码）：

```powershell
python -m app.cli.create_admin admin --display-name "Administrator"
```

管理员登录后可通过 `POST /api/auth/invites` 创建限次、可过期的邀请码，并通过 `PATCH /api/auth/invites/{id}` 禁用或恢复邀请码。普通用户在 `http://localhost:3000/register` 使用邀请码注册；已有账号从 `/login` 登录。

运行状态端点：

- `GET /health/live` 只确认 API 进程存活。
- `GET /health/ready` 检查 PostgreSQL 与 Redis，依赖不可用时返回 `503`。

### 3. 启动前端

另开终端：

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

浏览器访问 `http://localhost:3000`。前端默认连接 `http://localhost:8000`，可通过 `NEXT_PUBLIC_API_URL` 覆盖。

## 质量检查

后端测试会强制清空所有模型 API Key，使用内存数据库和测试临时目录，不会读取开发者的真实凭证、下载模型或调用外部 LLM：

```powershell
cd backend
python -m pytest tests -q
python -m pytest tests -q --cov=app
python -m bandit -r app -c pyproject.toml -ll
```

PostgreSQL 容器运行时可额外执行真实 RLS 集成测试：

```powershell
$env:POSTGRES_INTEGRATION_URL="postgresql+asyncpg://exam_review:exam-review-dev@localhost:5432/exam_review"
python -m pytest tests/integration/test_postgres_rls.py -q
```

前端完整基线：

```powershell
cd frontend
npm run format:check
npm run lint
npm run typecheck
npm run test:coverage
npm run build
npx playwright install chromium
npm run test:e2e
```

E2E Smoke 会拦截后端 API 并使用固定响应，因此不要求 DeepSeek Key 或正在运行的后端。首次执行仍需安装 Chromium。

验证 Compose 配置而不启动容器：

```powershell
docker compose config
```

## 常用端口

| 服务 | 地址 |
|---|---|
| Frontend | `http://localhost:3000` |
| FastAPI | `http://localhost:8000` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |

端口和开发凭证可通过根目录 `.env` 覆盖。`POSTGRES_ADMIN_*` 只用于容器初始化，`POSTGRES_APP_PASSWORD` 对应后端 `DATABASE_URL` 中的应用密码。`compose.yaml` 中的默认密码只用于本地开发，不能用于公开部署。
