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

Task 1.1 已将业务默认连接切换到 PostgreSQL，并建立 `vector(1024)`、JSONB、HNSW、全文索引及错题 Repository。旧 SQLite 数据不迁移。Task 3.1 已将生产检索切换为 PostgreSQL pgvector + PostgreSQL FTS，应用层使用 RRF 融合和 Cross-Encoder 重排；Chroma 仅保留为旧调用方兼容路径，不作为生产资料检索事实源。

## Task 2.4 免费资源基准状态（更新至 2026-10-08）

- 新增独立、可注入的离线基准 runner，报告模型 artifact 大小、首次加载、单页吞吐、进程峰值工作集/RSS、Recall@k 和 MRR；固定 fixture 同时验证本地与远程兼容 provider 的 Embedding 和 Cross-Encoder 契约。
- 初始实施阶段因内存余量有限未加载大模型；后续已在隔离新进程中完成轻量本地与 SiliconFlow 远程实测，详见下列记录。两文档 fixture 的质量数值仅是管线检查，不构成生产效果证据。
- 不据模型名称、artifact 大小或小型 fixture 数值决定生产 provider。benchmark provider 保持独立，不替换当前生产 Embedding/Reranker 配置。
- 2026-09-28 已在 Windows CPU 隔离进程完成本地实测：`BAAI/bge-small-zh-v1.5` 为 96,405,966 bytes、冷启动 90.5 ms、约 158.1 页/秒、峰值工作集 412.8 MB；`BAAI/bge-reranker-base` 为 1,134,408,930 bytes、冷启动 1,998.4 ms、约 9.65 页/秒、峰值工作集 1,010.1 MB。两者在两文档 fixture 上 Recall@1/MRR 均为 1.0，该质量结果只证明 runner 链路可用。
- 2026-10-08 已在两个新鲜 Python 进程复测 SiliconFlow 远程 provider：`BAAI/bge-m3` 为冷启动 306.6 ms、约 3.767 页/秒、峰值工作集 42.77 MB；`BAAI/bge-reranker-v2-m3` 为冷启动 281.8 ms、约 7.224 页/秒、峰值工作集 42.21 MB。两者在同一两文档 fixture 上 Recall@1/MRR 均为 1.0；托管 alias 未固定 revision，且本地无法测量远程 artifact 大小。该 key 仅在 benchmark 进程内使用，不用于 DeepSeek 聊天冒烟。
- 远程结果补齐了 Task 2.4 的 provider 对照证据，但 fixture 规模和 alias 版本限制了结论范围；不据这些数值选择生产 provider。
- Task 3.1 已独立完成生产检索迁移。2026-10-08 的真实 pgvector 集成直接验证 `RetrievalService(db_session=...)` 的 1024 维写入、Dense/FTS/RRF、metadata 与课程/资料范围过滤、服务重启后读取及清理；本轮修复还将 JSONB scalar predicate 显式编译为 PostgreSQL `->>` 文本提取，以避免 asyncpg 将 JSONB 与 VARCHAR 比较导致运行时错误。
