# V2 架构契约

本目录记录 V2 已接受的技术决策和跨阶段稳定契约。实现代码与文档冲突时，应先更新 ADR 或契约并说明兼容策略，再修改行为。

## 决策记录

- [ADR-0001：PostgreSQL 与 pgvector](adr/0001-postgres-pgvector.md)
- [ADR-0002：受控 Agent Runtime](adr/0002-agent-runtime.md)
- [ADR-0003：S3 兼容对象存储](adr/0003-object-storage.md)
- [ADR-0004：认证与租户隔离](adr/0004-auth-and-tenancy.md)

## 跨模块契约

- [API、Agent Event 与 Provider 契约](api-contracts.md)

状态含义：`Accepted` 已批准并约束后续实现；`Superseded` 已被新 ADR 替代；`Deprecated` 仅为兼容旧实现保留。
