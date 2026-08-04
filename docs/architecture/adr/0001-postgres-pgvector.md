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
