# ADR-0002：受控 Agent Runtime

- 状态：Accepted
- 日期：2026-08-03

## 背景

当前 LangGraph 只做关键词分发，没有计划审批、持久化步骤、失败恢复或断线续传。V2 需要把多 Agent 协作作为技术亮点，但确定性算法不应为展示效果被包装成 Agent，也不能允许无上限自主循环。

## 决策

采用“模块化单体 API + 独立 ARQ Worker”。两类进程共享后端代码、领域模型和 PostgreSQL，Redis 只投递可重建的 Job ID。

只有需要模型判断、规划或生成的组件称为 Agent：Global Planner、Session Planner、RAG Agent、Citation Validator、Quiz Generator、Quiz Validator、Tracker Agent 和 Knowledge Graph Agent。检索、确定性评分、掌握度计算、SM-2、认证、存储和配额均为普通服务。

每次执行是一个持久化 `AgentRun`，包含版本化 Plan、Step 和 Event。计划状态依次为 `draft -> awaiting_approval -> approved`；未批准前禁止调用 LLM、检索工具或产生外部副作用。批准后的计划版本不可原地修改，重规划会创建新版本并保留原因。

## 状态与停止条件

- Run 状态：`draft`、`awaiting_approval`、`queued`、`running`、`succeeded`、`failed`、`cancel_requested`、`cancelled`。
- Step 状态：`pending`、`running`、`succeeded`、`failed`、`skipped`、`cancelled`。
- 默认每个 Run 最多 12 个 Agent Step；Citation 定向修订最多 1 次；Quiz 补生成最多 1 次。
- DeepSeek 单次调用默认最多重试 3 次，使用指数退避；不回退到其他对话模型。
- Step 必须声明超时、幂等键和允许工具。超时、取消或超出预算后停止调度新 Step。
- 取消采用协作式边界：先持久化 `cancel_requested`，当前不可中断操作结束后写入 `run.cancelled`。

这些数值是可配置默认值。修改默认值必须有评测证据，不能由模型在运行时自行提高。

## 失败语义

- Event 先写 PostgreSQL，再发布通知；客户端断线不影响 Run 继续执行。
- Worker 至少一次消费，同一幂等键不得重复产生文件、测验或数据库副作用。
- 可重试的依赖错误保留同一 Step 和 attempt；输入或策略变化必须创建新 Step/Plan 版本。
- 证据不足、Validator 未通过和预算耗尽是显式业务结果，不静默降级为无依据答案。
- 确定性服务错误不能交给 LLM 猜测修复结果。

## 可观察性与保留

公开事件只包含用户可理解的状态、进度和结果引用。内部 Prompt、工具参数、Token、错误堆栈和输入输出写入受限 Trace；凭证和授权头在写入前脱敏。详细 Trace 默认保留 30 天，用户删除账号时提前删除其可识别 Trace。

## 结果

运行过程可审批、恢复、取消、重试和审计，前端不依赖单条长连接。代价是必须实现状态机、幂等和事件存储。阶段 4 才实现 Runtime；此前的规则路由只作为兼容路径。
