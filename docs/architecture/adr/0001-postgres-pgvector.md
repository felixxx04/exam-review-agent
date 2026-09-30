# ADR-0001：PostgreSQL 与 pgvector

- 状态：Implemented（Task 1.1）
- 日期：2026-08-03

## 背景

当前 SQLite、进程内 `DictStore`、Chroma 和实例内 BM25 分散保存业务状态，无法可靠支持多用户隔离、后台任务恢复、Agent 事件审计和跨请求混合检索。V2 面向 5～20 位受邀用户、约 3 位同时活跃用户，不需要拆分数据库或引入独立向量数据库。

## 决策

1. V2 使用 PostgreSQL 17 作为唯一业务事实源，使用 Alembic 管理从空库开始的 Schema。
2. 使用 pgvector 0.8.x 保存 `MaterialChunk` 的向量；正文、来源定位、内容哈希、预分词文本和向量属于同一条可事务管理的记录。
3. Dense Retrieval 使用 pgvector，Lexical Retrieval 使用 PostgreSQL 全文检索；应用层执行 RRF 融合和 Cross-Encoder 重排。
4. Redis 只承担队列、锁和短期通知，不保存唯一业务状态。Worker 重启后从 PostgreSQL 恢复 Job 和 Agent Run。
5. 每个用户拥有一套私人课程数据。所有用户数据必须直接包含 `user_id`，或通过强制租户过滤的父实体关联到用户。
6. 旧 SQLite/Chroma 数据不迁移，V2 从空数据库开始。切换按单一业务路径进行，不双写两个事实源。

## 实施约束

- SQLAlchemy Repository 必须从认证上下文接收租户范围，不能接受客户端提供的任意 `user_id`。
- 向量查询和全文查询必须使用同一个租户、课程和资料过滤条件；融合前后都保留 Evidence ID。
- Embedding 维度、模型标识和内容版本必须入库。更换模型需要新索引版本，不能在同一列混用未知维度。
- Schema 迁移、空库升级和回滚边界进入自动化测试；应用启动不能隐式创建或修改生产表。
- 数据库备份是业务恢复依据，Chroma 目录和 Redis AOF 不是 V2 备份来源。

## 备选方案

- 继续使用 SQLite + Chroma：本地简单，但租户隔离、事务一致性、Worker 恢复和混合检索状态分裂。
- PostgreSQL + 独立向量数据库：能横向扩展，但对当前规模增加部署、备份和一致性成本。
- 全部使用托管搜索服务：降低自运维，但免费额度和供应商绑定不符合免费优先与可本地复现目标。

## 结果

Task 1.1 已将业务默认连接切换到 PostgreSQL，并建立 `vector(1024)`、JSONB、HNSW、全文索引及错题 Repository。旧 SQLite 数据不迁移。当前 Chroma 只保留为 Phase 3 前的临时检索实现，不与 pgvector 双写向量；Phase 3 将按评测驱动切换检索路径。

## Task 2.4 免费资源基准状态（2026-09-27）

- 新增独立、可注入的离线基准 runner，报告模型 artifact 大小、首次加载、单页吞吐、进程峰值工作集/RSS、Recall@k 和 MRR；固定 fixture 同时验证本地与远程兼容 provider 的 Embedding 和 Cross-Encoder 契约。
- fixture 性能数值不是模型实测。当前 Windows 主机约有 1.9 GiB 可用内存；缓存中的 `BAAI/bge-large-zh-v1.5` 与 `BAAI/bge-reranker-base` 目录分别约 2.7 GiB 和 1.1 GiB，因此本次没有尝试冷启动，也没有取得小型本地模型或远程 endpoint 的实际测量。
- 不据模型名称、artifact 大小或 fixture 数值决定生产 provider。Task 2.4 的真实资源/检索效果比较仍需在有足够内存的隔离进程中，对小型本地模型和明确配置的远程兼容 provider 使用同一标注集测量；该证据齐备前维持现有生产路径。
- 2026-09-28 已在 Windows CPU 隔离进程完成本地实测：`BAAI/bge-small-zh-v1.5` 为 96,405,966 bytes、冷启动 90.5 ms、约 158.1 页/秒、峰值工作集 412.8 MB；`BAAI/bge-reranker-base` 为 1,134,408,930 bytes、冷启动 1,998.4 ms、约 9.65 页/秒、峰值工作集 1,010.1 MB。两者在两文档 fixture 上 Recall@1/MRR 均为 1.0，该质量结果只证明 runner 链路可用。
- 2026-09-30 已在两个新鲜 Python 进程复测 SiliconFlow 远程 provider：`BAAI/bge-m3` 为冷启动 278.9 ms、约 2.193 页/秒、峰值工作集 42.63 MB；`BAAI/bge-reranker-v2-m3` 为冷启动 271.1 ms、约 6.378 页/秒、峰值工作集 41.96 MB。两者在同一两文档 fixture 上 Recall@1/MRR 均为 1.0；托管 alias 未固定 revision，且本地无法测量远程 artifact 大小。该 key 仅在 benchmark 进程内使用，不用于 DeepSeek 聊天冒烟。
- 远程结果补齐了 Task 2.4 的 provider 对照证据，但 fixture 规模和 alias 版本限制了结论范围；不据这些数值选择生产 provider，不切换生产检索路径。
- 本工作不替换 Embedding/Reranker，不改 Chroma/进程内 BM25，不切换 pgvector 检索；生产检索迁移仍属于 Task 3.1。
