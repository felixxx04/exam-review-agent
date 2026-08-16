# Exam Review Agent 会话交接文档

> 更新日期：2026-08-16
> 项目目录：`C:\Users\asus\Documents\exam-review-agent`  
> 当前分支：`codex/phase-1-postgres`  
> Task 1.4 最终功能提交：`3b5e37e feat: complete deletion and quota reliability`
> Task 2.1 最终生产 GREEN checkpoint：`faa1e25 fix: bound object version pagination`（完整安全加固提交链见 2.4；均为本地提交，不推送 GitHub）
> 基线提交：`23c17b5 feat: polish learning workspace UI and review flows`

## 1. 给新会话的执行指令

本文件是新会话的第一读取入口。读取后还必须检查当前工作树，并阅读：

1. `docs/superpowers/plans/2026-08-03-exam-review-agent-v2-optimization.md`
2. `docs/architecture/adr/0001-postgres-pgvector.md`
3. `docs/architecture/adr/0003-object-storage.md`
4. `docs/architecture/adr/0004-auth-and-tenancy.md`
5. 与下一任务有关的当前代码和测试

先向用户汇报以下内容，不要立即修改代码：

- 对当前完成状态的理解
- Task 1.4 的实现、验证结果和剩余风险
- Task 2.1 的实现、TDD、测试、审查和真实容器验证证据
- Docker/PostgreSQL/MinIO 当前环境缺口及不应伪造的验证结论
- Task 2.2 的明确非目标与审批条件

当前审批点是 **Task 2.1 验收**。未经用户确认，不得开始 Task 2.2 或更后面的工作。

不要推送 GitHub。不要重置、清理或覆盖当前工作树中的任何已有改动。

## 2. 当前状态摘要

- 阶段 0 已完成并已获用户确认。
- 阶段 1 已获准开始。
- 阶段 1 的 **Task 1.1（PostgreSQL + pgvector）已完成实现**。
- 阶段 1 的 **Task 1.2（邀请码认证和会话安全）已由用户确认**。
- 阶段 1 的 **Task 1.3（私人多课程领域模型）已由用户确认**。
- 阶段 1 的 **Task 1.4（用户数据删除与配额）已完成并经用户确认的 Phase 1 验收**。
- 阶段 2 的 **Task 2.1（S3 对象存储抽象）已完成实现、TDD、复审和真实容器验证，等待用户验收**。
- Task 1.4 采用连续 RED/GREEN checkpoint；`17cbda7`、`7eed32d`、`64e4a8a`、`6ce7ce0`、`726d2c2`、`c153644` 记录契约、首轮实现与多轮并发/恢复安全 RED，最终功能 GREEN checkpoint 为 `3b5e37e`。
- 全局 Git 身份已配置为 `felixxx04 <rifuturech@163.com>`；用户只授权本地提交，不得推送。
- 用户要求成果只保存在本地，不上传 GitHub。
- 仓库根目录目前没有 `.codegraph/`，因此无需使用 CodeGraph；如果新会话发现该目录后来出现，再按 `AGENTS.md` 先使用 CodeGraph。

实施计划的 Task 2.1 checkbox、完成记录和第 13 节审批门均已更新；本会话已补齐 Docker 真实验证和最后的回归修复。下一项只有在用户验收 Task 2.1 后才能开始 Task 2.2。

## 2.2 本会话（2026-08-08）Task 2.1 初始收尾记录

### 已交付范围

- 私有 S3 兼容 `ObjectStorage` Protocol、S3v4/MinIO 适配器、版本化私有 Bucket bootstrap，以及无普通 `ListBucket`、仅可按资料对象前缀执行 `ListBucketVersions` 的应用身份。PostgreSQL `materials` 是对象元数据、配额和状态唯一事实源；对象 Key 仅服务端生成，不使用用户文件名。
- 资料上传采用 `reserved -> available -> deleting -> deleted` 状态、服务器临时文件校验、哈希校验、同课程重复文件拒绝、跨租户隔离、短期签名 GET URL、下载 UI 和旧本地资料删除兼容。
- 单资料删除、账号注销与崩溃恢复保持 Task 1.4 的预留、用户锁和注销可靠性。恢复入口在 RLS 绑定的单一租户作用域内运行；若索引清理失败，资料保持 `deleting`，重试成功清理向量/BM25 与持久 chunk 后才写 tombstone。
- 上传安全额外在 ASGI `receive` 层按声明 `Content-Length` 和分块累计字节限制请求体；每块在交给 FastAPI multipart 解析器前检查，合法请求不预缓存完整 body，超限在端点、临时文件、预留或对象写入前返回 `413 FILE_TOO_LARGE`。
- 非回环 S3 HTTP 默认被启动校验拒绝。只有部署者明确设置 `S3_ALLOW_INSECURE_HTTP=true` 且 API 与 MinIO 位于可信私有 Docker 网络时，才允许内部 S3 HTTP；外部签名 URL 仍要求 HTTPS。

### TDD、审查与验证证据

- 初始 Task 2.1 RED checkpoint：`bbd89fb test: define Task 2.1 object storage contracts`。
- 后续可靠性 RED/GREEN：最小权限 readiness、RLS 绑定的恢复 CLI、删除索引清理失败恢复、同步打开下载窗口、下载失败反馈、multipart 解析前大小限制、分块请求与外部 S3 HTTP 启动拒绝均先有失败测试，再以最小实现转绿。
- 后端全量：`338 passed, 9 skipped`；精确综合覆盖率 `80.491%`。9 个 skip 需要显式真实服务或模型配置。
- 聚焦回归：资料上传 `17 passed`、对象恢复与删除 API `11 passed`、middleware `10 passed`、启动/health `13 passed`；初始对象存储、账号删除、配额、跨租户和签名 URL 契约也包含在全量结果中。
- 前端全量：`103 passed`；Prettier、ESLint、TypeScript 和 Next 生产构建均通过。
- Python 质量门：修改路径 Ruff lint/format、Bandit 中高危门、`compileall`、`pip check`、`git diff --check` 均通过。全仓 Ruff 仍有 Task 2.1 无关的历史问题：`app/tasks/parse_material.py` 中未定义 `_index_chunks`，以及 `tests/test_api/test_auth.py` 的未使用 `datetime`。
- 静态基础设施：`docker compose --env-file .env.example config --quiet` 和 `alembic upgrade head --sql` 通过。

### 历史服务环境缺口（已于 2026-08-09 关闭）

- 本段记录的是 Docker Desktop 尚未启动时的初始状态，不能作为当前验证结论。
- Docker Desktop 已启动，真实 MinIO/PostgreSQL 迁移、S3 最小权限、readiness 与 `alembic check` 的通过证据见下一节；不要用内存对象存储或 SQLite 替代这些真实验证。

## 2.3 本会话（2026-08-12）Task 2.1 真实验证与最终收尾

- Docker Desktop 已由本会话启动，Docker Engine `29.6.2`、PostgreSQL、Redis 和 MinIO 均健康；MinIO 镜像通过本地可用的 DaoCloud 镜像源缓存后按 Compose 固定标签运行，部署配置未改为镜像源。
- 修复 MinIO `mc` 初始化容器的 shell 入口点和精简镜像无 `sed` 的兼容性问题；新增 Compose RED/GREEN 回归测试，真实 bootstrap 已创建私有桶、版本化、readiness sentinel、应用用户和最小策略并成功退出。
- 修复迁移与 ORM 的 `storage_status` 类型漂移：非原生 Enum/CHECK 明确使用长度 16，兼容既有 `VARCHAR(16)`；隔离 PostgreSQL 库从 `0004` 写入旧资料后升级到 `0005`，验证回填、非空、`FORCE RLS` 和 `alembic check`。主库应用角色的 `alembic check` 也报告 `No new upgrade operations detected`。
- Python 复审发现并修复 `reserved` 资料可生成签名 URL、外部索引与删除/注销并发、过期处理租约恢复、普通 `deleting` 资料重试、已完成索引资料的安全重处理、重处理最终提交失败的恢复窗口，以及随机 chunk ID 的稳定测试顺序。最终 Python 审查无 Critical/High 阻断项；本地 Ruff、Bandit、依赖与手工路径审查未发现 Task 2.1 中高危问题。
- 首轮后端全量回归：`368 passed, 10 skipped`；综合覆盖率 `81%`。最终聚焦资料/课程/账号删除与恢复 `112 passed`，连同真实 PostgreSQL 资料/恢复回归为 `61 passed`；真实 PostgreSQL RLS `3 passed`、删除/配额/索引互锁 `4 passed`；真实 MinIO 生命周期/签名下载 `1 passed`；完整应用 readiness 的 database、Redis、object storage 均为 `ok`。该记录早于最终的 `0007` 围栏迁移。
- 作用域 Ruff、Bandit 中高危、`compileall`、`pip check` 和 `git diff --check` 通过。全局 Ruff 仍有 Task 2.1 无关的历史问题：`app/tasks/parse_material.py` 的 `_index_chunks` 未定义、`tests/test_api/test_auth.py` 的未使用 `datetime`，未修改。
- 前端既有 Task 2.1 回归仍为 `103 passed`，格式、ESLint、TypeScript 和生产构建已通过；当前 npm 镜像的 audit endpoint 返回 `NOT_IMPLEMENTED`，因此本会话不能重跑生产依赖审计。已知开发链路 `jsdom -> undici` 高危项未在本 Task 做无关升级。
- 当前只需创建一次本地 GREEN 提交并核对工作树；不推送 GitHub。Task 2.2、ARQ、pgvector 检索切换、Planner/Agent Runtime 和无关重构仍未授权。

### 本会话追加收尾（2026-08-12）

- 最终审查发现处理租约过期后，旧 worker 在删除或恢复完成后仍可能恢复并写入向量。迁移 `20260812_0007_material_processing_lease_fencing.py` 增加随机 `processing_lease_id`；外部索引前重新锁定资料并验证 `available + processing + 活跃同一 lease ID + 精确 durable chunk IDs`，READY 的最终写入也以该 lease ID 条件更新。删除、课程删除、账号注销和恢复接管会清除旧 ID。
- RED/GREEN 回归 `test_stale_processing_attempt_is_fenced_before_writing_vectors` 证明：恢复清理过期处理意图后，暂停的旧 worker 恢复时不会调用 `index_chunks`，不会把向量写回已被清理的范围。迁移链与 ORM 元数据测试也覆盖 `0007`。
- Docker Desktop 29.6.2 当前运行 PostgreSQL、Redis 与 MinIO；主库已升级到 `20260812_0007 (head)`，`alembic check` 无漂移，离线迁移 SQL 包含 `0006 -> 0007`。真实 PostgreSQL RLS、删除/配额/上传索引互锁与双 Session stale-worker fencing 合计 `8 passed`；真实低权限 MinIO 私有对象生命周期、签名下载、无列举权限和幂等版本删除 `1 passed`。当前聚焦 Task 2.1 后端回归为 `142 passed`。
- 最终全量后端回归为 `377 passed, 11 skipped`。作用域 Ruff lint/format、Bandit 中高危、`compileall`、`pip check`、Compose 配置和 `git diff --check` 均通过。
- 只有本地 GREEN 提交仍待完成。提交后仍停在 Task 2.1 验收门，不推送 GitHub，也不得开始 Task 2.2、ARQ、pgvector 检索、Planner/Agent Runtime 或无关重构。

### 2.4 本会话（2026-08-15 至 2026-08-16）Task 2.1 整改与验收

- 用户选择“先整改后验收”。针对复审发现的 Windows ZIP 路径绕过，先加入 `..\\escape.xml`、`word\\..\\..\\escape.xml` 和 `C:/escape.xml` RED 契约，提交 `d229bec`；随后以 `PurePosixPath` + `PureWindowsPath`、反斜杠和 drive 检查完成最小修复，提交 `011f039`。
- 真实 MinIO API 集成测试现在强制 `engine.dialect.name == "postgresql"`，在 `flush()` 后保存用户 ID，并让 PostgreSQL 清理、每个对象删除和 `engine.dispose()` 独立执行；失败只向原始异常添加不含 Key/URL 的阶段说明。代码复审指出的测试日志泄露风险再由 `0443100` 修复。
- 最终对象存储安全 TDD 从 `e29856f`、`add1da9` 开始，关闭 SDK 自动 PUT 重试、增加 `If-None-Match: *`，按精确 Key 分页删除全部版本和 delete marker，并拒绝重复 continuation token；`NoSuchBucket` 不再被任意 HTTP 404 吞掉。MinIO policy 只增加受 `users/*/courses/*/materials/*/objects/*` 前缀约束的 `ListBucketVersions`，普通 `ListBucket` 和无范围版本枚举仍被拒绝；bootstrap 会刷新已有 policy，并以全局占位符替换渲染所有 Bucket ARN。
- `f0b5b82`、`70f6b5f` 和 `a48a6ef` 先复现上传验证清理、Windows 临时下载清理、boto3/s3transfer 高层下载异常、停滞分页与审计缺口；对应 GREEN 为 `29cd296`、`eeb3977` 和 `faa1e25`。所有对外存储错误均抑制底层异常链，不记录 object key、endpoint、签名查询串或临时路径；部分下载无法删除时只记录固定通用 WARNING。
- 最新自动化结果：Task 2.1 聚焦 `217 passed`；真实 PostgreSQL/RLS/删除/配额/索引互锁与真实 MinIO 生命周期、受限版本枚举、双版本清理及完整 API 上传/删除共 `10 passed`；后端全量 `403 passed, 12 skipped`，综合覆盖率 `82%`；前端 `103 passed`，行覆盖率 `81.08%`；Playwright Chromium Smoke `6 passed`。
- Prettier、ESLint、串行 TypeScript、Next 生产构建、Task 2.1 范围 Ruff lint/format、定向 mypy、Bandit 中高危门、`compileall`、`pip check`、`npm ci --dry-run`、生产依赖审计（`0 vulnerabilities`）、Compose 配置和真实 PostgreSQL `alembic check` 均通过。代码、Python 与安全复审均为 PASS。全仓 Ruff 仍有既有 `_index_chunks` 未定义、未使用 `datetime` 及历史格式债务，未在本 Task 修改。
- readiness 真实调用返回 `database: ok`、`redis: ok`、`object_storage: ok`。为满足启动安全校验，使用了临时随机最小权限 MinIO 身份并在 `finally` 删除；凭据未写入仓库。当前运行容器的 bootstrap 应用身份仍是占位配置，README 已明确要求部署者替换，不应把它当作可公开部署凭据。
- 当前仍是 **Task 2.1 用户验收门**。不得开始 Task 2.2、ARQ、pgvector 检索切换、Planner/Agent Runtime 或无关重构；等待用户明确确认后再更新审批状态。

## 2.1 本会话（2026-08-06）收尾记录

本会话接续上一个会话的 Task 1.4 工作，完成了最终复审、可靠性修复、验证、提交和本地服务启动。新会话应把下面内容视为最新事实：

### 本会话修复的复审问题

- 删除请求不再在 HTTP 响应返回前同步执行清理。`AccountDeletionService.request()` 只锁定/禁用账号、撤销 Refresh Token、禁用邀请码并提交 `pending` job；`POST /api/account/deletion` 先返回状态令牌，FastAPI 响应后台任务再用独立 `AsyncSessionLocal` 执行 `execute()`。
- 删除执行的数据库提交不确定或状态恢复再次失败时，事务会回滚到已交付令牌对应的 `pending` 状态；状态令牌仍可查询和重试。成功状态不会被降级为失败。
- 上传在解析前提交真实 `file_size/hash`，随后重新取得与注销共享的用户行锁。解析或最终提交数据库异常会留下准确计量的 `pending` 预留，而不是 `file_size=0`；元数据提交失败会删除文件和预留。
- `_discard_reservation()` 对瞬时数据库提交故障执行一次重试，持续失败会显式上抛并记录脱敏日志，不再静默吞错。
- 新增真实 PostgreSQL 双 Session 删除请求测试，证明并发请求只创建一个活动删除任务；已有上传/注销锁等待测试继续通过。

### TDD 检查点与最终提交

- `726d2c2 test: expose durable deletion execution gaps`：新增删除令牌交付、状态恢复、上传数据库故障和真实并发 RED 测试。
- `c153644 test: require upload reservation recovery`：新增预留元数据提交失败和清理重试 RED 测试。
- `3b5e37e feat: complete deletion and quota reliability`：最终 GREEN 功能实现、文档和交接更新。后续交接文档提交不改变该功能提交；成果只保存在本地，不得推送。
- 全局 Git 身份：`felixxx04 <rifuturech@163.com>`。

### 最终验证证据

- 后端全量：`285 passed, 8 skipped`，综合覆盖率 `80.23%`。8 个 skip 中 6 个需要显式 `POSTGRES_INTEGRATION_URL`，2 个需要真实 LLM。
- 真实 PostgreSQL + RLS：`6 passed`。覆盖配额 CHECK、删除任务唯一索引/双 Session 并发、账户级联、邀请码与 Refresh Token 处理、上传/注销锁等待和提交不确定性。
- Task 聚焦回归：`41 passed`；Ruff lint/format、Bandit 中高危、`compileall`、`pip check`、Compose 配置、`git diff --check`、`alembic check` 全部通过。
- 在线迁移 `0004 -> 0003 -> 0004` 通过，当前 `20260805_0004 (head)`。测试探针完成后 `users/courses/materials/account_deletion_jobs/invite_codes/refresh_tokens` 均为 0。
- Python 和安全复审均无 Critical/High 阻断项。已知产品建议仍是注销 step-up authentication，以及创建响应完全丢失时的状态令牌恢复机制。

### 当前本地运行状态

- PostgreSQL 容器：健康，`localhost:5432`。
- Redis 容器：健康，`localhost:6379`。
- 前端当前监听：`http://127.0.0.1:3000`。
- 后端当前监听：`http://127.0.0.1:8000`；`GET /health/ready` 返回数据库和 Redis 均为 `ok`。
- 后端进程是本会话临时启动的本地进程：使用进程内随机 JWT 密钥、`AUTH_COOKIE_SECURE=false` 和占位 `DEEPSEEK_API_KEY=local-startup-placeholder`。这些值没有写入仓库；真实 Ask/Quiz 模型调用不可用，重新启动时必须提供真实 DeepSeek Key 和安全 JWT Secret。
- 新会话开始前应重新检查端口和进程；不要假设上述 PID 或临时环境变量仍然存在。

## 3. 项目定位与目标架构

当前产品是面向大学生期末复习的 AI Agent，已有 Ask、Quiz、Review、资料上传、错题复习和学习记忆等功能。V2 目标是服务 5～20 位受邀同学、约 3 人同时活跃，并兼顾真实使用和求职作品展示。

目标部署形态是“模块化单体 + 独立后台 Worker”：

- 前端：Next.js 学习工作台
- API：FastAPI
- 业务事实源：PostgreSQL 17
- 向量：pgvector 0.8.x，固定 1024 维
- 队列、锁和短期通知：Redis；Redis 不能保存唯一业务状态
- 原始文件：后续接入 S3 兼容对象存储
- Agent 编排：后续建设持久化 Planner 和受控 LangGraph Runtime
- 对话模型：DeepSeek 是唯一对话 LLM，失败时重试，不切换其他对话 Provider

完整路线分为阶段 0～9，必须按依赖顺序和审批门推进。每次只实现一个 Task。

## 4. 已确认的产品和工程约束

- 用户通过邀请码注册用户名/密码账号，每位用户的数据完全隔离。
- 每位用户未来可维护多门私人课程，资料不共享。
- Ask、Quiz、Review 必须最终形成持久化闭环。
- 用户确认计划后，Agent 才能自动执行当前复习流程。
- Ask 的关键结论必须绑定并校验证据；资料不足时先澄清。
- 联网搜索只能由用户明确授权，不能静默混入通用知识。
- 第一阶段只支持选择题；正确答案只存后端并由后端评分。
- 原始文件未来存 S3 兼容对象存储；当前阶段不得提前实现。
- 旧 SQLite/Chroma 数据不迁移，从空 PostgreSQL 数据库开始。
- 当前 Chroma 只是阶段 3 前的临时 Dense Retrieval，不与 pgvector 双写向量。
- 新增前端页面必须延续现有设计语言；不重做无需修改的页面。
- 桌面和手机最终都要支持完整核心流程。
- 免费优先部署，但先完成可靠的本地生产等价环境。
- 主要开发工具是 Codex 和 Claude。
- 无固定时间限制，优先保证正确性和可验证性。

明确不在 V2 当前主路线的内容包括 OCR、图片/公式/表格识别、非选择题、课程共享、PWA/离线、多语言、多对话模型降级、无上限自主循环、Kubernetes 和全面视觉重做。

## 5. 阶段 0 已完成工作

### Task 0.1：可复现开发和测试基线

- 补齐前后端直接依赖、环境示例、迁移和启动说明。
- 新增根目录 `compose.yaml`，固定 PostgreSQL、Redis 和 MinIO 的本地版本。
- 隔离测试配置，普通测试不读取真实 API Key、不下载真实模型、不连接真实模型服务。
- 修复过期的 Playwright Smoke 断言，并使用固定 API 响应。
- 建立前端 Prettier、ESLint、TypeScript、覆盖率和构建基线。
- 生成基础 GitHub Actions 工作流；这是本地文件，未推送远端。

阶段 0 当时的验证记录：

- 后端：`182 passed, 2 skipped`
- 前端：`81 passed`
- E2E Chromium Smoke：`4 passed`
- 前端格式、ESLint、TypeScript、覆盖率和生产构建通过
- 可编辑安装、空 SQLite 迁移、Compose 配置和 Bandit 中高等级门通过

### Task 0.2：V2 契约与 ADR

已建立：

- `docs/architecture/adr/0001-postgres-pgvector.md`
- `docs/architecture/adr/0002-agent-runtime.md`
- `docs/architecture/adr/0003-object-storage.md`
- `docs/architecture/adr/0004-auth-and-tenancy.md`
- `docs/architecture/api-contracts.md`

这些文件冻结了 PostgreSQL/pgvector、Agent Runtime、对象存储、认证/租户隔离、统一 API Envelope、Agent Event、Provider Port、删除语义和 Trace 保留等跨阶段契约。

## 6. Task 1.1 已完成工作

### PostgreSQL 与 Schema

- 默认业务连接已从 SQLite 切换到 `postgresql+asyncpg`。
- Alembic 使用同步 `psycopg` URL。
- 添加运行依赖：`asyncpg`、`psycopg[binary]`、`pgvector`。
- 生成 `backend/requirements.lock`，可由 pip 完整解析。
- 删除两条旧迁移，建立一个从空数据库开始的 V2 初始迁移：
  `backend/alembic/versions/20260803_0001_v2_postgres_pgvector.py`。
- 初始迁移包含 `CREATE EXTENSION vector`、`Vector(1024)`、JSONB、HNSW 向量索引、GIN 全文索引、租户/状态索引和带时区时间列。
- 状态字段优先使用字符串或非原生 Enum 的 CHECK 约束，避免扩大 PostgreSQL 原生 Enum 的迁移成本。

### 错题持久化与 Repository 边界

- 删除生产 `DictStore` 和 `backend/app/core/store.py`。
- 新建 `backend/app/repositories/mistakes.py`：
  - `MistakeRepository` Protocol
  - `SqlAlchemyMistakeRepository`
  - 面向 LangGraph 等非请求代码的 `SessionFactoryMistakeRepository`
- 新建临时 `UserRepository`，在真实认证完成前把字符串用户引用映射为本地用户记录。
- Quiz、Review、Tracker 和 LangGraph 已改为依赖 Repository，不直接使用进程内字典。
- 错题可以跨 SQLAlchemy Session 持久化。
- 现有字符串题目 ID 保存到 `source_question_id`；`MistakeRecord.question_id` 是可空的内部 `Question` 外键。

### 健康检查和运行可靠性

- 新增 `/health/live`：只检查 API 进程存活。
- 新增 `/health/ready`：带超时检查 PostgreSQL 和 Redis，失败返回 `503`。
- Chroma 客户端改为延迟创建，并在测试 Session 结束时清理，解决 Windows 退出阶段的 SQLite 文件锁告警。
- README、环境示例、PostgreSQL ADR 和实施计划已更新。

### Task 1.2：邀请码认证和会话安全

- 用户表增加规范化用户名、`admin/user` 角色和禁用状态；新增 `InviteCode` 与只保存哈希的 `RefreshToken`。
- 密码使用 Argon2id，注册和登录通过线程池执行 CPU 密集哈希；Access Token 短期有效；Refresh Token 每次刷新轮换，重用旧 Token 会撤销同一会话。
- 浏览器会话使用 `Secure`、`HttpOnly`、`SameSite=Lax` Cookie，并通过双提交 Cookie 加 Access Token 绑定执行 CSRF 校验。
- 新增注册、登录、刷新、退出、当前用户、邀请码管理和用户禁用 API，以及认证限速与统一错误 Envelope。
- Chat、Conversation、Material、Quiz、Review、Memory、Tracker 和 LangGraph 已改为使用可信认证用户，不再使用生产 `default` 用户。
- Repository 查询按认证用户限定租户；跨用户资源与不存在统一返回 `404`。直接租户业务表新增 PostgreSQL RLS 策略；会话在每次 PostgreSQL 新事务开始时自动重绑租户上下文，LangGraph 独立 Session 也显式绑定可信用户。
- 前端新增 `/login`、`/register`、会话恢复门、Cookie/CSRF API 封装和 SSE credentials，沿用原学习工作台视觉体系；Access Token 过期时普通 API/SSE 单飞刷新并重试，刷新失败回到登录页，Header 提供退出入口。
- 新增 `python -m app.cli.create_admin ...` 管理员引导命令。
- SSE 失败只返回稳定的通用错误消息，内部异常保留在服务端日志中。

## 7. Task 1.3 已完成工作

### 私人课程和兼容行为

- 新增 Course、Exam、StudyAvailability 和 ConceptMastery 模型，以及 `/api/courses` 的列表、批量 ID 查询、创建、详情、更新和删除接口。
- 课程支持考试日期、长期目标、每日可用分钟数和默认标记；Conversation 支持只影响当前会话的临时可用分钟数。
- 旧客户端省略 `course_id` 时解析默认课程；没有课程时在用户行锁内安全懒创建。默认课程切换、删除后的替代选择均在一个事务内完成。
- 每用户最多一个默认课程由 PostgreSQL 部分唯一索引保证；真实双 Session 并发测试确认懒创建返回同一个课程 ID。

### 课程范围和数据库纵深防御

- Material、MaterialChunk、Conversation、ConversationMessage、QuizSession、Question、AnswerRecord、MistakeRecord、LearningProfile、Concept、ConceptDependency 和 ConceptMastery 均携带非空 `user_id/course_id` 范围。
- Ask、Quiz、Review、Memory Profile、Study Plan、Tracker 和 LangGraph 全链路传播课程；Chroma 与 BM25 使用“用户 + 课程”命名空间。
- 课程子表使用复合所有权外键；AnswerRecord/MistakeRecord 不能引用其他用户或课程的 Question，AnswerRecord 不能引用其他范围的 QuizSession。
- 15 张业务表均启用并强制 RLS；应用角色保持 `NOSUPERUSER NOBYPASSRLS`。敏感子表不能被其他租户直接读取。

### 迁移与验证

- 新增 `backend/alembic/versions/20260805_0003_private_courses.py`；Task 1.3 当时的数据库 revision 为 `20260805_0003` 且业务表为空。
- 后端完整回归：`266 passed, 5 skipped`，精确综合覆盖率 `80.05%`。5 个 skip 中 3 个需要显式 PostgreSQL URL，2 个需要真实 LLM。
- 真实 PostgreSQL 集成测试：`3 passed`，覆盖跨 commit RLS、SessionFactory、敏感子表、跨范围复合外键和默认课程并发。
- 空 Schema 从 base 在线升级到 head；`alembic check` 无待生成操作；离线 upgrade SQL 生成成功。
- 有数据 `0003 -> 0002` 验证会把同用户多课程画像确定性折叠到默认课程画像，并清理回滚后无法保持私有范围的 Concepts/Dependencies。旧全局 Concepts 非空时 upgrade 会明确失败并事务回滚，原数据保留。
- Task 1.3 涉及的 34 个 Python 文件通过 Ruff lint/format；`compileall`、`git diff --check`、Bandit 中高风险、`pip check` 和 Compose 配置通过。前端 `101 passed`，TypeScript、ESLint、Prettier 和生产构建通过。

### 本地 TDD checkpoint

- `5a80da1 test: define private multi-course domain contracts`
- `823b7af test: require course-scoped material retrieval`
- `6382698 test: expose private course isolation gaps`
- Task 1.3 GREEN checkpoint：`045ba84 feat: enforce private multi-course domain isolation`，未推送。

Task 1.3 不包含账号全量删除与配额、S3/ARQ、pgvector 检索切换、Planner/Agent Runtime 或全面视觉改造。Pyright 未安装，项目也没有现成 Python 类型检查命令；这不是本任务新增的失败门。`npm audit --omit=dev` 为 0 漏洞，但 2026-08-05 的全依赖审计新报告 1 个开发链路 `undici` 高危公告；它不进入生产依赖，后续依赖维护应升级并复跑前端门。

## 8. Task 1.4 已完成工作

### 资源删除与配额

- 会话、资料、测验、错题和课程记忆均提供租户隔离的删除路径；资料删除同步清理 MaterialChunk、本地原文件与 Chroma collection。
- 用户默认配额为 100 个文件、2 GiB，管理员可通过用户管理接口覆盖文件数和容量。`GET /api/account/quota` 返回限制与已用量。
- 上传先在用户行锁内提交 `pending/file_size=0` Material 预留，再流式写入随机服务端文件名；随后重新锁用户检查容量、解析并索引。失败时清理预留和文件，进程崩溃后的文件仍有数据库归属，可被注销清理。
- 上传与注销共享用户行锁。注销冻结用户后，新的上传会返回 `ACCOUNT_DELETION_IN_PROGRESS`；已持锁上传完成后，注销快照能够发现并清理该资料。

### 账号注销任务

- `POST /api/account/deletion` 锁定并禁用用户、撤销活动 Refresh Token、禁用该管理员创建的邀请码，并创建只保存令牌哈希的 `pending` 删除任务；API 返回明文令牌后，响应后台任务才使用独立数据库 Session 执行清理。
- `GET /api/account/deletions/{job_id}` 与 `POST /api/account/deletions/{job_id}/retry` 使用 `X-Deletion-Status-Token` 查询和重试；状态为 `pending -> running -> succeeded | failed`。
- PostgreSQL 级联清理账户业务数据；本地文件和 Chroma collection 由清理器幂等处理。用户删除后 job 的 `user_id` 置空并保留安全状态，邀请码创建者外键也置空。
- 每个用户只允许一个仍关联账号的删除任务，真实双 Session 并发请求只会创建一个。准备查询失败会回滚并记录 `failed`；若失败状态也暂时无法提交，则保留已交付令牌可重试的 `pending`。已提交的 `succeeded` 不会因提交确认丢失被降级；日志只记录 job/user ID 和异常类型，不泄露资料或令牌。

### 迁移与验证

- 新增 `backend/alembic/versions/20260805_0004_deletion_quotas.py`；数据库已完成在线 `0004 -> 0003 -> 0004` 往返，当前 revision 为 `20260805_0004 (head)`，`alembic check` 无漂移。
- 后端完整回归：`285 passed, 8 skipped`，综合覆盖率 `80.23%`。8 个 skip 中 6 个需要显式 PostgreSQL URL，2 个需要真实 LLM。
- 真实 PostgreSQL + RLS 集成测试：`6 passed`，覆盖配额 CHECK、删除任务唯一索引与双 Session 并发请求、邀请创建者置空与邀请码冻结、账户级联、删除 job 保留、上传/注销共享锁、准备失败状态恢复和提交确认丢失保护。
- Task 定向 Ruff、Bandit 中高风险、`compileall`、`pip check`、Compose 配置和 `git diff --check` 通过。迁移往返和测试完成后，用户、课程、资料、删除任务、邀请码与 Refresh Token 探针计数均为 0。
- Python 最终复审与安全复审均为 APPROVE，无 Critical/High 阻断项；复审指出的 Ruff format 差异已修复并复跑全绿。

### 已知非阻塞风险

- 永久注销目前依赖有效会话，尚未要求近期密码或 step-up authentication；这会改变已确认 API 契约，留待后续安全加固。
- 清理已推迟到创建响应发送后，但若创建响应本身发生极端传输失败，用户仍没有自助恢复唯一明文状态令牌的通道。
- PostgreSQL 并发测试通过配额服务模拟完整上传的行锁边界，尚未以真实 HTTP 上传覆盖两个锁窗口；代码审查未发现竞态，后续可补完整 API 并发回归。
- S3/MinIO、ARQ Worker 与崩溃预留回收扫描属于 Phase 2；Task 1.4 只实现本地文件和临时 Chroma 的可靠过渡边界。

## 9. Task 1.1/1.2 验证证据和剩余风险

上一个会话完成实现后记录的验证结果：

- 后端完整回归：`204 passed, 2 skipped`
- 应用语句覆盖率约 `80.45%`
- 综合分支覆盖率：`77%`
- 新错题 Repository 覆盖率：`95%`
- `compileall` 通过
- `git diff --check` 通过
- Bandit 中高等级检查通过
- `pip check` 通过
- `docker compose config --quiet` 通过
- Alembic PostgreSQL upgrade/downgrade 离线 SQL 均可生成
- `requirements.lock` 可被 pip 完整解析
- 无生产 `DictStore` 引用
- Chroma 测试临时目录退出时不再出现文件锁异常

Task 1.2 当前验证记录：

- 后端完整覆盖回归（包含真实 PostgreSQL RLS）：`245 passed, 2 skipped`，综合覆盖率 `80%`，认证服务覆盖率 `98%`，错题 Repository 覆盖率 `95%`。
- 前端覆盖回归：`101 passed`，语句覆盖率 `80.05%`、行覆盖率 `81.26%`。
- Playwright E2E：`6 passed`，包含工作台 Smoke、登录和邀请码注册流程。
- 前端格式、ESLint、TypeScript、生产构建通过；生产预览下工作台桌面与 `390x844` 手机截图均显示退出入口，无重叠或横向溢出。
- `compileall`、Bandit 中高风险、`pip check`、锁文件 dry-run、Compose 配置、生产默认用户扫描和 `git diff --check` 通过。
- `npm audit` 与 `npm audit --omit=dev` 均为 `0 vulnerabilities`；Next 15.5.22 的 PostCSS/Sharp 传递依赖通过精确 override 固定到 PostCSS 8.5.23 / Sharp 0.35.0。
- Alembic 离线 SQL 生成及 PostgreSQL 在线 `upgrade -> downgrade base -> upgrade head` 往返均通过，最终 head 为 `20260804_0002`。
- Docker Engine 29.6.2 下 PostgreSQL 17.8 + pgvector 0.8.1、Redis 7.4 均健康；`/health/live` 与 `/health/ready` 返回 200，数据库和 Redis 检查均为 `ok`。
- Compose 使用 `exam_review_admin` bootstrap 管理员创建 `NOSUPERUSER NOBYPASSRLS` 的 `exam_review` 应用角色；数据库和 RLS 表归应用角色所有，运行时不再以超级用户连接。
- 真实 RLS 集成测试验证：租户上下文跨 commit 自动重绑，其他租户和未绑定 Session 不可见且越权写被拒绝，LangGraph SessionFactory 创建/读取/更新均正确隔离。
- Git 作者身份已配置，Task 1.1/1.2 的本地 checkpoint 为 `e84e733`，且不得推送远端。

已知但不阻断 Task 1.2 验收的后续加固项：当前认证限速是单进程内存/IP 维度，阶段 8 再迁移为 Redis 共享限速；安全响应头/CSP 和认证管理审计日志也按阶段 8 的安全与可观测性任务统一实施。

Task 1.1/1.2 的真实 PostgreSQL 验证缺口已关闭。当前容器与 revision 状态以 Task 1.4 验证记录为准。

## 10. 下一步审批门

Task 2.1 完成后必须停止。下一项只有在用户明确验收 Task 2.1 后才是 **Task 2.2：ARQ 任务状态机**。

在用户确认前，不得开始 ARQ、任务调度、pgvector 检索切换、Planner/Agent Runtime 或无关重构。恢复 Docker 后可以补做 Task 2.1 已定义的真实 PostgreSQL/MinIO 验证，但这不自动授权 Task 2.2。

## 11. 新会话的工作规则

1. 每次只实施计划中的一个 Task。
2. 先写失败测试或可验证契约，再做最小实现。
3. 运行聚焦测试，再运行阶段回归测试。
4. 修改代码后使用对应语言的 Reviewer 检查，并修复有效问题。
5. 不提前实现后续任务，不重构无关模块。
6. 所有已有修改都视为用户资产，禁止 reset、checkout、删除或覆盖。
7. Git 身份已全局配置；Task 1.4 功能 GREEN checkpoint 为 `3b5e37e`，Task 2.1 的本地 GREEN checkpoint 见当前分支最新提交。
8. 未经明确要求不得推送 GitHub。
9. 完成 Task 2.1 后必须停在 Task 2.1 验收门，汇报实现、测试、真实容器验证缺口和未完成验证，等待用户确认。

## 12. 关键文件索引

- 总实施计划：`docs/superpowers/plans/2026-08-03-exam-review-agent-v2-optimization.md`
- 架构入口：`docs/architecture/README.md`
- PostgreSQL ADR：`docs/architecture/adr/0001-postgres-pgvector.md`
- 认证和租户 ADR：`docs/architecture/adr/0004-auth-and-tenancy.md`
- API/Agent 契约：`docs/architecture/api-contracts.md`
- V2 初始迁移：`backend/alembic/versions/20260803_0001_v2_postgres_pgvector.py`
- 私人课程迁移：`backend/alembic/versions/20260805_0003_private_courses.py`
- 删除与配额迁移：`backend/alembic/versions/20260805_0004_deletion_quotas.py`
- 对象存储迁移：`backend/alembic/versions/20260808_0005_object_storage.py`
- 数据模型：`backend/app/db/models.py`
- 数据库配置：`backend/app/db/database.py`
- 错题 Repository：`backend/app/repositories/mistakes.py`
- 临时用户 Repository：`backend/app/repositories/users.py`
- 健康检查服务：`backend/app/services/health.py`
- 健康端点：`backend/app/main.py`
- 对象存储接口与 S3 适配：`backend/app/services/object_storage.py`
- 上传安全校验：`backend/app/services/material_upload_validation.py`
- 资料存储恢复与删除：`backend/app/services/material_storage_cleanup.py`
- 租户绑定恢复命令：`backend/app/cli/recover_material_storage.py`
- 请求体限制与限速：`backend/app/core/middleware.py`
- 认证依赖：`backend/app/core/auth.py`
- 认证 API：`backend/app/api/auth.py`
- 认证服务：`backend/app/services/auth_service.py`
- 课程 API：`backend/app/api/courses.py`
- 课程 Service：`backend/app/services/course_service.py`
- 课程 Schema：`backend/app/schemas/courses.py`
- 账号 API：`backend/app/api/account.py`
- 账号删除服务：`backend/app/services/account_deletion_service.py`
- 配额服务：`backend/app/services/quota_service.py`
- 课程与隔离测试：`backend/tests/test_api/test_courses.py`、`backend/tests/integration/test_postgres_rls.py`
- 删除与配额测试：`backend/tests/test_api/test_deletion_and_quotas.py`、`backend/tests/test_services/test_account_deletion_service.py`、`backend/tests/integration/test_postgres_deletion_quotas.py`
- 认证测试：`backend/tests/test_api/test_auth.py`、`backend/tests/test_core_auth.py`、`backend/tests/test_services/test_auth_service.py`
- 前端认证：`frontend/src/app/(auth)/`、`frontend/src/components/auth/`、`frontend/src/lib/api.ts`
- 错题 Repository 测试：`backend/tests/test_repositories/test_mistakes.py`
- 迁移契约测试：`backend/tests/test_migrations.py`
- 健康检查测试：`backend/tests/test_health.py`、`backend/tests/test_services/test_health.py`

## 13. 推荐的新会话启动提示

```text
请先完整阅读项目根目录 SESSION_HANDOFF.md，以及
docs/superpowers/plans/2026-08-03-exam-review-agent-v2-optimization.md、
docs/architecture/adr/0001-postgres-pgvector.md、
docs/architecture/adr/0003-object-storage.md、
docs/architecture/adr/0004-auth-and-tenancy.md。

随后检查当前 git status 和 Task 2.1 的实际实现。先向我汇报：
1. 你对 Phase 1 已验收和 Task 2.1 当前完成状态的理解；
2. Task 2.1 的对象存储、上传安全、删除/注销恢复和跨租户验证证据；
3. 真实 PostgreSQL/MinIO 验证的 Docker 环境缺口，以及 Task 2.2 的明确非目标。

Task 2.1 未经用户验收不得开始 Task 2.2 或更后面的工作；
不要覆盖现有改动，也不要推送 GitHub。
```
