# V2 API、Agent Event 与 Provider 契约

- 状态：Accepted
- 日期：2026-08-03
- 范围：V2 新接口及现有 `/api` 接口的兼容演进

本文冻结跨前端、API、Worker 和 Agent 的稳定边界。Phase 0 不要求现有接口立即返回全部新字段；后续采用“增加 -> 前端切换 -> 删除旧字段”的顺序迁移。

## 1. 通用响应 Envelope

成功响应：

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": { "request_id": "req_..." }
}
```

失败响应：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "INSUFFICIENT_MATERIAL",
    "message": "现有资料不足以回答该问题",
    "details": {}
  },
  "meta": { "request_id": "req_..." }
}
```

规则：

- HTTP 状态表达传输结果，`error.code` 表达稳定业务原因；前端不得解析 `message` 决定逻辑。
- `request_id` 在入口生成并贯穿 Job、Run 和日志。未知异常不向客户端暴露堆栈、Prompt 或 Provider 原始响应。
- 时间使用带 `Z` 或偏移量的 ISO 8601 UTC 字符串；ID 对客户端是不透明字符串。
- 创建后台任务的请求支持 `Idempotency-Key`。同一用户、接口和 Key 的重复请求返回同一资源。

稳定错误码及 HTTP 映射：

| code | HTTP | 含义 |
|---|---:|---|
| `VALIDATION_ERROR` | 422 | 输入不满足 Schema |
| `AUTH_REQUIRED` | 401 | 未登录或会话失效 |
| `FORBIDDEN` | 403 | 已认证但无操作权限 |
| `NOT_FOUND` | 404 | 资源不存在或不属于当前用户 |
| `INSUFFICIENT_MATERIAL` | 422 | 资料不足，需要补充或澄清 |
| `CONFLICT` | 409 | 状态冲突或重复操作 |
| `QUOTA_EXCEEDED` | 409 | 文件数量或存储容量超过用户配额 |
| `ACCOUNT_DELETION_IN_PROGRESS` | 409 | 账号注销已冻结新的用户数据写入 |
| `RATE_LIMITED` | 429 | 达到速率或费用限制 |
| `DEPENDENCY_UNAVAILABLE` | 503 | 数据库、队列、存储或模型暂不可用 |
| `RUN_FAILED` | 500 | Run 已以可审计失败结束 |
| `INTERNAL_ERROR` | 500 | 未分类服务端错误 |

### 2.1 认证与会话

认证接口统一使用本章 Envelope，响应体不返回 Access Token 或 Refresh Token：

| 方法与路径 | 权限 | 行为 |
|---|---|---|
| `POST /api/auth/register` | 公开、限速 | 消费有效邀请码，创建用户并签发 Cookie 会话 |
| `POST /api/auth/login` | 公开、限速 | 校验用户名/密码并签发 Cookie 会话 |
| `POST /api/auth/refresh` | Refresh Cookie + CSRF、限速 | 轮换 Refresh Token 和 CSRF Token |
| `POST /api/auth/logout` | Refresh Cookie + CSRF | 撤销当前会话并清除 Cookie |
| `GET /api/auth/me` | 已认证 | 返回当前用户公开字段 |
| `POST /api/auth/invites` | 管理员 | 创建限次、可过期的邀请码；明文只在创建响应中返回 |
| `PATCH /api/auth/invites/{id}` | 管理员 | 禁用或恢复邀请码 |
| `PATCH /api/auth/users/{id}` | 管理员 | 禁用或恢复账号；目标不存在返回 `NOT_FOUND` |

- Access、Refresh 和 CSRF Cookie 分别使用 `/`、`/api/auth`、`/` Path；会话 Cookie 默认 `Secure`、`SameSite=Lax`，Access/Refresh 为 `HttpOnly`。
- Cookie 认证的 `POST`、`PUT`、`PATCH`、`DELETE` 请求必须发送与 `csrf_token` Cookie 一致的 `X-CSRF-Token`，并与 Access Token 内的 CSRF 绑定哈希一致。
- 非浏览器客户端可发送 `Authorization: Bearer <access-token>`；Bearer 请求不执行 Cookie CSRF 校验，但仍校验账号状态和活动会话。
- Refresh Token 只保存不可逆哈希，每次成功刷新后轮换。过期、撤销、重用、账号禁用或 CSRF 不匹配均拒绝会话。
- 不存在与跨租户资源统一返回 `NOT_FOUND`；客户端传入的 `user_id` 永远不构成权限依据。

### 2.2 私人课程

课程接口统一使用通用 Envelope，并只接受认证上下文中的用户身份：

| 方法与路径 | 行为 |
|---|---|
| `GET /api/courses` | 返回当前用户课程；可重复传入 `ids` 做批量 ID 过滤 |
| `POST /api/courses` | 创建课程，以及对应考试和每日可用时间记录 |
| `GET /api/courses/{course_id}` | 返回属于当前用户的课程详情 |
| `PATCH /api/courses/{course_id}` | 更新名称、说明、考试日期、长期目标、每日可用时间或默认课程 |
| `DELETE /api/courses/{course_id}` | 删除课程及其课程范围数据；必要时提升替代默认课程 |

- 课程名称在单个用户内唯一；每个用户最多有一个默认课程。跨用户 ID、批量 ID 和删除请求不会暴露其他用户资源。
- Course Response 包含 `id`、`name`、`description`、`exam_date`、`long_term_goal`、`daily_available_minutes`、`is_default`、`created_at` 和 `updated_at`。
- Material、Conversation、Quiz、Review、Memory Profile 和 Study Plan 接口接受可选 `course_id`。传入时必须验证课程归属；旧客户端省略时使用默认课程，并在用户尚无课程时安全地懒创建兼容课程。
- Conversation Create 可通过 `session_available_minutes` 覆盖当前会话可用时长；该值只属于会话，不修改课程的 `daily_available_minutes`。
- 检索、错题、学习画像、知识图谱和掌握度必须继承已解析的 `user_id + course_id`，不得退化为仅按用户或资源 ID 查询。

### 2.3 删除与配额

| 方法与路径 | 权限 | 行为 |
|---|---|---|
| `GET /api/account/quota` | 已认证 | 返回文件数量与存储容量的限制和已用量 |
| `POST /api/account/deletion` | 已认证 | 冻结账号并创建删除任务；返回一次性明文状态令牌 |
| `GET /api/account/deletions/{job_id}` | `X-Deletion-Status-Token` | 查询删除任务终态、尝试次数和安全错误摘要 |
| `POST /api/account/deletions/{job_id}/retry` | `X-Deletion-Status-Token` | 重试 `failed` 删除任务 |
| `DELETE /api/conversations/{conversation_id}` | 已认证 | 删除当前用户会话及其消息 |
| `DELETE /api/materials/{material_id}` | 已认证 | 删除资料元数据、派生块、临时向量和本地原文件 |
| `DELETE /api/quiz/{quiz_session_id}` | 已认证 | 删除测验及其课程范围派生记录 |
| `DELETE /api/review/mistakes/{mistake_id}` | 已认证 | 删除当前用户错题 |
| `DELETE /api/memory/profile?course_id=...` | 已认证 | 删除指定私人课程的学习画像 |

- 用户默认限制 100 个文件、2 GiB；管理员可通过既有 `PATCH /api/auth/users/{id}` 的 `file_limit` 与 `storage_limit_bytes` 覆盖。数量和容量均以 PostgreSQL Material 记录为事实源。
- 上传在读取正文前先提交 `pending` Material 预留。文件使用服务端随机名流式写入，超限、写入或数据库失败必须删除预留与文件；上传与账号注销以同一用户行锁串行化。
- 删除任务状态为 `pending -> running -> succeeded | failed`。创建接口返回 `202` 与 `status="pending"`；响应发送后，进程内后台执行器使用独立数据库 Session 开始清理。进程中断时数据库保留可查询、可重试状态，阶段 2 再迁移到可靠 Worker。状态令牌只保存哈希，丢失后不能由服务端还原。
- 注销创建后账号立即禁用，活动 Refresh Token 被撤销，管理员创建的邀请码被禁用。相同用户已有删除任务时返回 `CONFLICT`；失败任务使用原 `job_id` 和状态令牌重试。
- 删除任务公开错误只包含稳定 `error_code` 和安全摘要，不返回路径、数据库异常、令牌、资料内容或堆栈。

## 2. 游标分页

列表接口使用不透明游标，不以不断变化的数据集做页码分页：

```json
{
  "success": true,
  "data": { "items": [] },
  "error": null,
  "meta": {
    "request_id": "req_...",
    "page": { "next_cursor": null, "has_more": false, "limit": 20 }
  }
}
```

`limit` 默认 20、最大 100。游标绑定用户、过滤条件和稳定排序；其他用户或不同过滤条件使用时返回 `VALIDATION_ERROR`。

## 3. Agent Run 与 Plan

创建计划返回 `run_id`、`plan_id`、`plan_version`、`status="awaiting_approval"` 和可编辑的公开任务。批准请求必须带 `plan_id` 与 `plan_version`；版本已变化时返回 `409 CONFLICT`。批准前不允许产生 LLM/工具执行事件。

取消 Run 是幂等操作。终态为 `succeeded`、`failed` 或 `cancelled`；终态不能回到 `running`。重试失败 Step 会产生新的 attempt 和事件，不覆盖旧 Trace。

## 4. Agent Event

持久化事件字段：

```json
{
  "event_id": "evt_...",
  "run_id": "run_...",
  "step_id": "step_...",
  "sequence": 7,
  "type": "step.progress",
  "occurred_at": "2026-08-03T08:00:00Z",
  "payload": { "message": "正在校验证据", "progress": 0.6 },
  "trace_ref": null
}
```

约束：

- `sequence` 在单个 Run 内从 1 单调递增且不重复。重试和恢复不能重用序号。
- `step_id` 对 Step 事件必填；Run 和 Plan 级事件为 `null`。
- 用户 API 只返回公开 `payload`；`trace_ref` 仅对受限调试/管理员接口可见。
- 客户端必须按 `event_id` 幂等消费，未知事件类型应忽略并继续读取。
- Event 先提交数据库再发布；Redis 通知丢失时可以从数据库补读。

稳定事件类型：

| type | 必需 payload |
|---|---|
| `run.created` | `status` |
| `plan.proposed` | `plan_id`, `plan_version`, `tasks` |
| `plan.approved` | `plan_id`, `plan_version` |
| `step.started` | `step_type`, `attempt` |
| `step.progress` | `message`, 可选 `progress`（0～1） |
| `step.completed` | `result_ref` 或公开摘要 |
| `step.failed` | `error_code`, `retryable`, 公开消息 |
| `token.delta` | `text` |
| `run.completed` | `result_ref`, `status="succeeded"` |
| `run.failed` | `error_code`, 公开消息, `status="failed"`, 可选 `result_ref` |
| `run.cancelled` | `reason`, `status="cancelled"` |

SSE 端点使用 `id: <sequence>`、`event: <type>` 和 JSON `data`。客户端通过 `Last-Event-ID` 恢复；服务端先补发游标后的持久化事件，再订阅新通知。心跳不是业务 Event，不增加 `sequence`。

## 5. Provider Ports

业务层只能依赖以下语义接口，不能直接实例化 SDK/HTTP 客户端：

```python
class ChatModelProvider(Protocol):
    async def complete(self, messages: list[Message], options: ChatOptions) -> ChatResult: ...
    def stream(self, messages: list[Message], options: ChatOptions) -> AsyncIterator[TokenDelta]: ...

class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str: ...
    @property
    def dimension(self) -> int: ...
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...

class RerankerProvider(Protocol):
    @property
    def model_id(self) -> str: ...
    async def rerank(self, query: str, candidates: list[Candidate], top_k: int) -> list[RankedCandidate]: ...
```

- `ChatModelProvider` 的 V2 实现只有 DeepSeek；超时和重试后返回类型化错误，不切换其他对话模型。
- Embedding/Reranker 可以因免费资源限制替换实现，但结果必须记录 `model_id`、版本和维度。
- Provider 抛出统一的 `ProviderTimeout`、`ProviderRateLimited`、`ProviderUnavailable` 或 `ProviderInvalidResponse`，不得把 SDK 异常泄漏到 API。
- 单元测试注入 Fake Provider；普通 CI 禁止网络、真实 API Key 和模型权重下载。
- 确定性评分、RRF、掌握度和 SM-2 不依赖 `ChatModelProvider`。

## 6. 兼容与隐私

- 新增可选字段属于兼容变更；改名、改变含义或删除字段需要契约测试和至少一个前端迁移阶段。
- 正确答案、内部 Prompt、工具参数、跨用户标识和签名 URL 不进入公开事件。
- Trace 默认保留 30 天；账号删除会清除用户可识别 Trace。公开事件按业务记录保留策略处理。
- 所有资源授权以认证上下文为准，客户端发送的 `user_id` 不构成权限依据。
