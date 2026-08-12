# 期末复习 Agent

面向大学生期末复习场景的 AI 学习助手。用户可以上传课件或讲义，基于资料进行问答、生成练习题、查看薄弱点，并在 `Ask / Quiz / Review` 三种模式之间切换完成复习闭环。

当前仓库已完成 V2 Phase 1 的 Task 1.1～1.4，以及 Phase 2 的 Task 2.1（私有 S3 兼容对象存储）。业务默认数据库已切换为 PostgreSQL，现已具备邀请码认证、安全会话、私人多课程隔离、用户数据删除、上传配额和私有 MinIO/S3 原始资料存储。Task 2.2 的 ARQ 任务状态机尚未开始。

## 核心功能

- 资料上传：文本型 `PDF / DOCX / PPTX`
- 私人课程：课程、考试日期、长期目标、每日可用时长和会话临时时长
- 智能问答：围绕上传资料进行问答
- 题目生成：按知识点、难度和数量生成练习题
- 错题分析：记录答题结果并输出薄弱点视图
- 数据控制：删除会话、资料、测验、错题和课程记忆；账号注销提供可查询、可重试的删除任务
- 上传配额：默认每用户 100 个文件、2 GiB，管理员可按用户覆盖
- 私有对象存储：服务端生成对象 Key，校验 PDF/Office 文件与 SHA-256，短期签名下载 URL
- 学习工作台：提供 `Ask / Quiz / Review` 三种模式

## 当前架构

```text
frontend (Next.js 15 / React 19)
  -> 邀请码注册 / 登录 / 会话恢复
  -> Ask / Quiz / Review 工作台
  -> Zustand 交互状态

backend (FastAPI / Python 3.11-3.12)
  -> 邀请码 / Argon2id / JWT / Refresh 轮换 / CSRF
  -> courses / chat / materials / quiz / review / account API
  -> 账号注销任务 / S3 对象与旧本地文件清理 / 用户配额
  -> RAG Agent / Quiz Agent / Tracker Agent
  -> PostgreSQL 17（私人课程、业务数据、错题和资料块元数据）
  -> pgvector 0.8.1 Schema（Phase 3 切换检索实现）
  -> Chroma（Phase 3 前的临时 Dense Retrieval 实现）

local infrastructure (Docker Compose)
  -> PostgreSQL 17 + pgvector 0.8.1
  -> Redis 7.4（Worker 队列）
  -> 私有 MinIO（版本化 Bucket、低权限应用身份、S3 兼容存储）
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
docker compose up minio-init
docker compose ps
```

先把根目录 `.env` 中所有 MinIO/S3 占位值替换为本机专用随机值。`minio-init` 创建私有版本化 Bucket、readiness sentinel 与仅有对象读写权限的应用身份；它成功退出后再启动后端。MinIO API 和控制台默认仅绑定 `127.0.0.1`。PostgreSQL、Redis 和私有对象存储都是当前后端 readiness 检查的必需依赖。

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

启动前至少将 `.env` 中的 `DEEPSEEK_API_KEY`、`JWT_SECRET` 以及 S3 应用身份替换为有效值。后端 `.env` 的 `S3_BUCKET`、`S3_ACCESS_KEY_ID` 和 `S3_SECRET_ACCESS_KEY` 必须与根目录 `.env` 的同名 S3 应用值一致，不能使用 MinIO root 身份。开发环境通过 HTTP 访问时使用示例中的 `AUTH_COOKIE_SECURE=false`；公开部署必须启用 HTTPS 并设为 `true`，`S3_PUBLIC_ENDPOINT_URL` 必须为 HTTPS，非回环的 `S3_ENDPOINT_URL` 也必须使用 HTTPS。只有 API 与 MinIO 处于受信任私有 Docker 网络时，才可显式设置 `S3_ALLOW_INSECURE_HTTP=true` 使用内部 `http://minio:9000`；它绝不能用于公网地址。`POST /api/materials` 在 FastAPI 解析 multipart 前限制整个请求体（包括分块传输），超限直接返回 `413 FILE_TOO_LARGE`。`alembic upgrade head` 会从空 PostgreSQL 数据库建立 V2 Schema 并启用 `vector` Extension；旧 SQLite/Chroma 数据不会迁移。

迁移完成后创建首个管理员（命令会交互式读取并确认密码）：

```powershell
python -m app.cli.create_admin admin --display-name "Administrator"
```

管理员登录后可通过 `POST /api/auth/invites` 创建限次、可过期的邀请码，并通过 `PATCH /api/auth/invites/{id}` 禁用或恢复邀请码。普通用户在 `http://localhost:3000/register` 使用邀请码注册；已有账号从 `/login` 登录。

运行状态端点：

- `GET /health/live` 只确认 API 进程存活。
- `GET /health/ready` 检查 PostgreSQL、Redis 和应用身份读取私有对象存储 sentinel 的能力，任一依赖不可用时返回 `503`。

中断上传留下的超时 S3 预留可以由可信运维人员按用户恢复；该命令不打印对象 Key、签名 URL 或凭证：

```powershell
python -m app.cli.recover_material_storage --user-id <trusted-user-id> --older-than-minutes 60
```

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

PostgreSQL 容器运行时可额外执行真实 RLS、删除和配额集成测试：

```powershell
$env:POSTGRES_INTEGRATION_URL="postgresql+asyncpg://exam_review:exam-review-dev@localhost:5432/exam_review"
python -m pytest tests/integration/test_postgres_rls.py tests/integration/test_postgres_deletion_quotas.py -q
```

私有 MinIO bootstrap 成功后，可用与后端相同的低权限 S3 应用身份运行真实对象存储测试：

```powershell
$env:MINIO_INTEGRATION_ENDPOINT_URL="http://127.0.0.1:9000"
$env:MINIO_INTEGRATION_BUCKET="<private-bucket>"
$env:MINIO_INTEGRATION_ACCESS_KEY="<s3-application-access-key>"
$env:MINIO_INTEGRATION_SECRET_KEY="<s3-application-secret>"
python -m pytest tests/integration/test_minio_object_storage.py -q
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

端口和开发凭证可通过根目录 `.env` 覆盖。`POSTGRES_ADMIN_*` 只用于容器初始化，`POSTGRES_APP_PASSWORD` 对应后端 `DATABASE_URL` 中的应用密码。MinIO root 身份只供 bootstrap 使用；后端和真实对象存储测试只使用低权限 S3 应用身份，所有本地占位值都必须在启动前替换，不能用于公开部署。
