# ADR-0004：认证与租户隔离

- 状态：Accepted
- 日期：2026-08-03
- 实现：Task 1.2、Task 1.3、Task 1.4 已完成，等待 Phase 1 验收（2026-08-05）

## 背景

Task 1.2 之前，路由固定使用 `user_id="default"`，Bearer Token 只是占位判断。V2 面向少量受邀同学，但资料、向量、测验、记忆和 Agent Trace 都必须完全隔离。

## 决策

1. 仅允许邀请码注册用户名/密码账号。邀请码可设置总次数、到期时间和禁用状态，消费必须在数据库事务内完成。
2. 密码使用 Argon2id 哈希。Access Token 短期有效；Refresh Token 每次使用后轮换，只保存不可逆哈希并支持逐会话撤销。
3. Web 默认通过 `Secure`、`HttpOnly`、`SameSite=Lax` Cookie 传递会话，不在 `localStorage` 保存长期 Token。状态变更请求执行 CSRF 防护。
4. 受保护 API 只从认证上下文获得 `user_id` 和角色。请求体、查询参数或 URL 中出现的资源 ID 必须再次验证租户归属。
5. Repository 的租户条件是主要隔离边界；PostgreSQL 对直接用户数据表启用 RLS 作为纵深防御，Worker 在事务中设置可信租户上下文。
6. 管理员使用独立角色和审计路径，不通过伪造普通用户 ID 查看数据。默认管理能力只包含邀请码、账号禁用和任务状态。

## 数据访问规则

- 每个用户拥有私人课程，课程、考试日期、长期目标、可用时间、资料、Chunk、会话、测验、复习、记忆和掌握度不跨用户共享；同一用户的不同课程也不混用。
- 课程相关子表同时保存 `user_id` 与 `course_id`，通过复合所有权外键和 `FORCE ROW LEVEL SECURITY` 保证父资源和敏感子资源属于同一用户/课程范围。
- 所有查询先按认证用户限定父实体，再解析子资源；不存在与无权访问统一返回 `404`，避免枚举资源。
- 向量、全文检索、对象 Key、缓存键、Job Payload 和 Agent 工具调用都必须携带同一可信租户范围。
- 缓存不得只用资源 ID 作为 Key；至少包含用户 ID 和资源版本。
- 自动化测试必须包含跨用户读取、修改、删除、检索和签名 URL 的 IDOR 场景。

## 禁用与删除

- 禁用账号立即拒绝新 Access/Refresh Token，并撤销现有 Refresh Token；已排队 Job 在下一安全边界取消。
- 账号删除创建可查询的幂等删除任务，清除数据库业务数据、向量、对象、Token 和可识别 Trace。
- 删除失败保持明确状态并重试，不能向用户报告已经完成。
- 匿名聚合指标可以保留，但不得包含可反查用户或资料的标识与正文。

## 结果

租户身份从 HTTP 请求贯穿数据库、队列、对象存储和检索路径，降低 IDOR 与后台任务串租户风险。代价是 Repository、Worker 和测试都必须显式维护租户上下文。

## Task 1.2 实现说明

- 用户名规范化后唯一；密码只保存 Argon2id 哈希。管理员由本地 CLI 引导创建，普通用户只能消费有效邀请码注册。
- Access Token 默认 15 分钟，Refresh Token 默认 30 天。Refresh Token 和 CSRF Token 只以 SHA-256 哈希存储；每次刷新轮换，旧 Token 重用会撤销同一会话。
- 浏览器使用 `Secure`、`HttpOnly`、`SameSite=Lax` Cookie；开发环境仅可在本地 HTTP 显式关闭 `Secure`。Cookie 认证的状态变更必须通过双提交 CSRF 校验；Bearer 客户端不依赖浏览器 CSRF Cookie。
- 禁用账号会撤销其活动 Refresh Token，已有 Access Token 也会在每次请求时因账号或会话状态校验而失效。
- 现有 Chat、Conversation、Material、Quiz、Review 和 Memory API 已从可信认证上下文获取用户；直接租户表在 PostgreSQL 中启用并强制执行 RLS。每次新事务自动重绑租户上下文，独立 SessionFactory 也必须显式绑定可信用户。
- 本地 PostgreSQL 使用独立 bootstrap 管理员创建 `NOSUPERUSER NOBYPASSRLS` 的 `exam_review` 应用角色；Alembic 与运行时都使用应用角色，避免超级用户绕过 RLS。
- PostgreSQL 17.8 + pgvector 0.8.1 已完成在线 migration 往返、跨事务 RLS、越权写拒绝和 readiness 联调。
- Task 1.2 的原始边界不包含私人多课程；该能力已在 Task 1.3 完成。账号删除和配额已在 Task 1.4 完成；对象存储与 Agent Runtime 仍不在 Phase 1 范围。

## Task 1.3 实现说明

- 新增 `/api/courses` 课程列表、创建、详情、更新和删除接口。课程响应包含考试日期、长期目标、每日可用分钟数和默认标记；列表支持按多个 ID 查询并继续按认证用户隔离。
- 旧客户端不提供 `course_id` 时解析用户默认课程；会话请求可临时覆盖每日可用分钟数，不改变课程默认值。删除默认课程时在同一事务中提升剩余课程；删除最后一门课程后，下一次兼容请求会在用户锁内懒创建默认课程。
- 课程范围从 API 进入 Conversation、Material、Quiz、Review、Memory、Study Plan、Tracker、RAG、Chroma 和 BM25。所有课程相关 `course_id` 列为非空；每位用户最多一个默认课程由 PostgreSQL 部分唯一索引保证。
- 迁移 `20260805_0003` 明确处理旧 Schema 的私有概念数据：升级前若存在无法安全归属的旧全局概念会失败并回滚；有数据 downgrade 会折叠课程画像并清理无法表达课程范围的私人概念，避免回滚后跨租户泄露。
- Task 1.3 不包含账号全量删除、配额、S3/ARQ、pgvector 检索切换或持久化 Planner/Agent Runtime；其中账号删除和配额已由 Task 1.4 补齐。

## Task 1.4 实现说明

- 删除会话、资料、测验、错题和课程记忆时继续按认证用户与课程限定资源；数据库外键级联负责关系数据，本地文件与 Chroma collection 由显式清理器处理。
- 账号注销以用户行锁冻结新上传和新注销请求，立即禁用账号、撤销活动 Refresh Token，并禁用该管理员创建的邀请码。每位用户只允许一个未完成删除任务；用户删除后任务的 `user_id` 置空，以保留不可反查账号的状态与失败摘要。
- 删除任务状态为 `pending -> running -> succeeded | failed`。服务只保存状态令牌 SHA-256 哈希；创建接口先返回 `pending` 与明文令牌，响应发送后才由独立数据库 Session 执行，查询与重试必须提供该令牌。一般数据库或清理异常会写入安全错误码；若连失败状态也暂时无法写入，事务回滚后保留 `pending` 供重试；已提交的成功状态不会因提交确认丢失被降级。
- 默认配额为 100 个文件、2 GiB。上传先提交归属明确的 `pending` Material 预留，再在同一用户行锁边界内流式写文件、复核容量并解析；注销会等待持锁上传，并能清理崩溃后仍有数据库归属的预留文件。
- 两项后续纵深防御不改变当前契约：永久注销可增加近期密码或 step-up authentication；尽管清理已推迟到响应发送后，仍可为创建响应本身未送达的极端传输失败提供用户自助恢复通道。
