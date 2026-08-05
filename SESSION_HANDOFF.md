# Exam Review Agent 会话交接文档

> 更新日期：2026-08-05
> 项目目录：`C:\Users\asus\Documents\exam-review-agent`  
> 当前分支：`codex/phase-1-postgres`  
> 基线提交：`23c17b5 feat: polish learning workspace UI and review flows`

## 1. 给新会话的执行指令

本文件是新会话的第一读取入口。读取后还必须检查当前工作树，并阅读：

1. `docs/superpowers/plans/2026-08-03-exam-review-agent-v2-optimization.md`
2. `docs/architecture/adr/0001-postgres-pgvector.md`
3. `docs/architecture/adr/0004-auth-and-tenancy.md`
4. 与下一任务有关的当前代码和测试

先向用户汇报以下三点，不要立即修改代码：

- 对当前完成状态的理解
- Task 1.3 的实现、验证结果和剩余风险
- Task 1.3 的真实 PostgreSQL 在线迁移、RLS、复合外键和并发验证证据
- Task 1.4 的实施边界和明确非目标

当前审批点是 **Task 1.3 验收**。未经用户确认，不得开始 Task 1.4 或更后面的工作。

不要推送 GitHub。不要重置、清理或覆盖当前工作树中的任何已有改动。

## 2. 当前状态摘要

- 阶段 0 已完成并已获用户确认。
- 阶段 1 已获准开始。
- 阶段 1 的 **Task 1.1（PostgreSQL + pgvector）已完成实现**。
- 阶段 1 的 **Task 1.2（邀请码认证和会话安全）已由用户确认**。
- 阶段 1 的 **Task 1.3（私人多课程领域模型）已完成实现，等待用户验收**。
- Task 1.4 及之后的任务均未开始。
- Task 1.3 采用三个 RED TDD checkpoint 和一个 GREEN checkpoint；本交接对应的本地 GREEN checkpoint 以当前 HEAD 为准。
- 全局 Git 身份已配置为 `felixxx04 <rifuturech@163.com>`；用户只授权本地提交，不得推送。
- 用户要求成果只保存在本地，不上传 GitHub。
- 仓库根目录目前没有 `.codegraph/`，因此无需使用 CodeGraph；如果新会话发现该目录后来出现，再按 `AGENTS.md` 先使用 CodeGraph。

实施计划的 Task 1.3 checkbox、完成记录和第 13 节审批门均已更新。下一项只有在用户确认后才能开始 Task 1.4。

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

- 新增 `backend/alembic/versions/20260805_0003_private_courses.py`，当前数据库 revision 为 `20260805_0003` 且业务表为空。
- 后端完整回归：`266 passed, 5 skipped`，精确综合覆盖率 `80.05%`。5 个 skip 中 3 个需要显式 PostgreSQL URL，2 个需要真实 LLM。
- 真实 PostgreSQL 集成测试：`3 passed`，覆盖跨 commit RLS、SessionFactory、敏感子表、跨范围复合外键和默认课程并发。
- 空 Schema 从 base 在线升级到 head；`alembic check` 无待生成操作；离线 upgrade SQL 生成成功。
- 有数据 `0003 -> 0002` 验证会把同用户多课程画像确定性折叠到默认课程画像，并清理回滚后无法保持私有范围的 Concepts/Dependencies。旧全局 Concepts 非空时 upgrade 会明确失败并事务回滚，原数据保留。
- Task 1.3 涉及的 34 个 Python 文件通过 Ruff lint/format；`compileall`、`git diff --check`、Bandit 中高风险、`pip check` 和 Compose 配置通过。前端 `101 passed`，TypeScript、ESLint、Prettier 和生产构建通过。

### 本地 TDD checkpoint

- `5a80da1 test: define private multi-course domain contracts`
- `823b7af test: require course-scoped material retrieval`
- `6382698 test: expose private course isolation gaps`
- Task 1.3 GREEN checkpoint：本交接对应的当前 HEAD，未推送。

Task 1.3 不包含账号全量删除与配额、S3/ARQ、pgvector 检索切换、Planner/Agent Runtime 或全面视觉改造。Pyright 未安装，项目也没有现成 Python 类型检查命令；这不是本任务新增的失败门。`npm audit --omit=dev` 为 0 漏洞，但 2026-08-05 的全依赖审计新报告 1 个开发链路 `undici` 高危公告；它不进入生产依赖，后续依赖维护应升级并复跑前端门。

## 8. Task 1.1/1.2 验证证据和剩余风险

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

Task 1.1/1.2 的真实 PostgreSQL 验证缺口已关闭。当前容器与 revision 状态以 Task 1.3 验证记录为准。

## 9. 下一步审批门

Task 1.3 完成后必须停止。下一项只有在用户确认后才是 **Task 1.4：用户数据删除与配额**。

Task 1.4 的边界以实施计划为准：会话、资料、测验、错题和记忆删除；账号注销的可追踪删除任务；每用户默认文件数和容量配额。S3/ARQ 属于阶段 2，pgvector 检索切换属于阶段 3，Planner/Agent Runtime 和全面视觉改造也不是 Task 1.4 范围。

## 10. 新会话的工作规则

1. 每次只实施计划中的一个 Task。
2. 先写失败测试或可验证契约，再做最小实现。
3. 运行聚焦测试，再运行阶段回归测试。
4. 修改代码后使用对应语言的 Reviewer 检查，并修复有效问题。
5. 不提前实现后续任务，不重构无关模块。
6. 所有已有修改都视为用户资产，禁止 reset、checkout、删除或覆盖。
7. Git 身份已全局配置；Task 1.3 GREEN checkpoint 为本交接对应的当前 HEAD。
8. 未经明确要求不得推送 GitHub。
9. 完成 Task 1.3 后必须停在审批门，汇报实现、测试、风险和未完成验证，等待用户确认。

## 11. 关键文件索引

- 总实施计划：`docs/superpowers/plans/2026-08-03-exam-review-agent-v2-optimization.md`
- 架构入口：`docs/architecture/README.md`
- PostgreSQL ADR：`docs/architecture/adr/0001-postgres-pgvector.md`
- 认证和租户 ADR：`docs/architecture/adr/0004-auth-and-tenancy.md`
- API/Agent 契约：`docs/architecture/api-contracts.md`
- V2 初始迁移：`backend/alembic/versions/20260803_0001_v2_postgres_pgvector.py`
- 私人课程迁移：`backend/alembic/versions/20260805_0003_private_courses.py`
- 数据模型：`backend/app/db/models.py`
- 数据库配置：`backend/app/db/database.py`
- 错题 Repository：`backend/app/repositories/mistakes.py`
- 临时用户 Repository：`backend/app/repositories/users.py`
- 健康检查服务：`backend/app/services/health.py`
- 健康端点：`backend/app/main.py`
- 认证依赖：`backend/app/core/auth.py`
- 认证 API：`backend/app/api/auth.py`
- 认证服务：`backend/app/services/auth_service.py`
- 课程 API：`backend/app/api/courses.py`
- 课程 Service：`backend/app/services/course_service.py`
- 课程 Schema：`backend/app/schemas/courses.py`
- 课程与隔离测试：`backend/tests/test_api/test_courses.py`、`backend/tests/integration/test_postgres_rls.py`
- 认证测试：`backend/tests/test_api/test_auth.py`、`backend/tests/test_core_auth.py`、`backend/tests/test_services/test_auth_service.py`
- 前端认证：`frontend/src/app/(auth)/`、`frontend/src/components/auth/`、`frontend/src/lib/api.ts`
- 错题 Repository 测试：`backend/tests/test_repositories/test_mistakes.py`
- 迁移契约测试：`backend/tests/test_migrations.py`
- 健康检查测试：`backend/tests/test_health.py`、`backend/tests/test_services/test_health.py`

## 12. 推荐的新会话启动提示

```text
请先完整阅读项目根目录 SESSION_HANDOFF.md，以及
docs/superpowers/plans/2026-08-03-exam-review-agent-v2-optimization.md、
docs/architecture/adr/0001-postgres-pgvector.md 和
docs/architecture/adr/0004-auth-and-tenancy.md。

随后检查当前 git status 和 Task 1.3 的实际实现。先向我汇报：
1. 你对 Task 1.1/1.2/1.3 当前完成状态的理解；
2. Task 1.3 的 PostgreSQL 在线迁移、RLS、复合外键和并发验证证据；
3. Task 1.3 的已实现范围、剩余风险和 Task 1.4 非目标。

Task 1.3 未经验收不得开始 Task 1.4 或更后面的工作；
不要覆盖现有改动，也不要推送 GitHub。
```
