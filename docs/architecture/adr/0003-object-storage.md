# ADR-0003：S3 兼容对象存储

- 状态：Implemented（Task 2.1）
- 日期：2026-08-03

## 背景

当前上传文件写入 API 进程本地 `uploads/`，无法在 API 与 Worker 之间共享，也不能可靠支持配额、重试、云端部署和账号全量删除。

## 决策

1. 原始资料使用私有 S3 兼容存储；本地使用 MinIO，云端 Provider 通过同一 `ObjectStorage` 接口替换。
2. PostgreSQL 保存资料元数据、对象 Key、大小、哈希、版本和处理状态；Bucket 不是资料清单的事实源。
3. 对象 Key 由服务端生成，格式为 `users/{user_id}/courses/{course_id}/materials/{material_id}/objects/{object_id}`。`object_id` 是不透明随机 ID；客户端文件名只保存为数据库显示元数据，绝不参与对象 Key 构造。
4. API/Worker 使用服务端凭证。浏览器只获得短期、单对象、限定方法的签名 URL，不接触永久凭证或可列举 Bucket 的权限。
5. 上传先预留 Material/Job 和配额，再写对象；只有对象哈希、大小校验通过后才进入解析队列。

## 删除与一致性

- 单资料删除先标记 `deleting` 并阻止新任务，取消待执行 Job，再幂等删除派生数据和对象，最后写入 `deleted`。
- 对象存储暂时失败时保持 `deleting` 并重试，不能先把数据库记录永久移除后遗留未知对象。
- 账号全量删除复用同一流程，覆盖原始文件、派生预览、导出文件和可识别 Trace。
- 已完成的删除请求重复执行必须返回成功；删除状态和失败原因对用户可查询。

## 安全与配额

- 默认 Bucket 私有，禁止公共读取、目录遍历式 Key 和用户控制的 Bucket 名。
- 上传限制器在 ASGI `receive` 边界检查整个 HTTP 请求体，覆盖 `Content-Length` 与分块传输；每块在交给 multipart 解析器前计量，合法请求不预缓存完整 body。随后校验扩展名、声明 MIME、文件签名、单文件大小和用户总配额。解析器仍把内容视为不可信输入。
- 非回环的 S3 API 与浏览器签名 URL 端点必须使用 HTTPS。仅当部署者显式声明 API 与 MinIO 位于可信内部 Docker 网络时，S3 API 端点可以使用 HTTP；该例外不适用于公共签名 URL 端点。
- 配额以 PostgreSQL 预留量加已确认对象量计算，失败或超时的预留必须可回收。
- 日志和 Agent Trace 不记录签名 URL 查询串、访问密钥或原始文件正文。

## 备选方案

- 共享本地卷：本地简单，但云平台可移植性、扩缩容和生命周期管理较弱。
- 把文件放入 PostgreSQL：事务直接，但大文件备份和数据库 I/O 成本不合适。
- 绑定单一云厂商 SDK：功能丰富，但不满足免费优先和本地等价环境目标。

## Task 2.1 实现

- `ObjectStorage` 将 S3 SDK 限制在适配器内；`S3ObjectStorage` 通过线程池调用阻塞 SDK，并以 S3v4、私有 Bucket、服务端凭证和短超时运行。数据库的 `materials` 行是对象元数据、配额和状态的唯一事实源。
- 每次上传先保存 `reserved` 数据库记录和服务器生成的对象 Key，再对受限临时文件完成 PDF/OOXML 校验。对象写入后使用 `head_object` 验证大小与 SHA-256 metadata；只有成功才提交为 `available`。失败、取消或元数据提交异常会删除精确对象版本，无法删除时保留 `deleting` 记录供恢复。
- 同一 `user_id + course_id + SHA-256` 的资料保留首个对象并返回 `DUPLICATE_MATERIAL`；不同用户或课程不会共享、探测或复用对象。对象 Key、Hash、`storage_path`、版本与解析内部错误不在公开 Material 响应中。
- MinIO Compose bootstrap 创建版本化私有 Bucket、固定 `__system__/object-storage-ready` sentinel 及无 `ListBucket` 权限的应用身份。readiness 读取 sentinel，因此不会用 Bucket 列举权限换取健康检查。
- 下载/预览在资源归属验证后生成单对象、短期 GET 签名 URL。签名 URL 仅出现在该已授权的访问响应，响应禁止缓存与 Referrer 传递；永久存储凭证、对象 Key 和签名查询串不会进入普通资料响应、日志或 Trace。
- 只有 `available` 状态的资料可以生成签名下载 URL；`reserved`、`deleting` 和 `deleted` 资料统一返回 `404`，避免未完成校验或待清理对象被读取。
- 单资料删除和账号注销复用对象版本删除；成功后保存 `deleted` tombstone，存储失败时维持 `deleting`。若派生检索索引清理暂时失败，资料也维持 `deleting`，恢复入口必须先完成幂等索引清理和 chunk 删除后才能写 tombstone。`python -m app.cli.recover_material_storage --user-id <id>` 在可信 RLS 作用域内回收超时预留；Task 2.2 可调度此入口，但不拥有另一份 Job/配额真相。
- 持久化 chunk 清理意图在外部索引调用前写入；处理租约与 Task 1.4 用户锁共同串行化索引、资料/课程删除、账号注销和恢复。每一次处理尝试还保存随机 `processing_lease_id`；外部索引前和 READY 转换时必须用该 ID、活跃租约、资料状态和精确 chunk ID 围栏验证，防止恢复或删除接管过期租约后旧 worker 重新写入孤儿向量。普通对象删除失败留下的 `deleting` 行可重试；只有不确定 PUT、`reserved` 或活动处理租约会阻止级联删除，避免过早丢失唯一恢复记录。
- 已完成索引的 `ready` 资料先在同一用户锁内持久化 `processing` 租约和清理意图，再删除旧向量和持久 chunk 并转回 `pending`；若最终提交失败，过期租约仍让恢复入口接管。非 `ready` 的持久 chunk 仍是未完成清理意图，必须由恢复流程先处理。
- MinIO `mc` bootstrap 显式设置 `/bin/sh` 入口点，并使用镜像内建 shell 工具渲染策略模板；应用身份只获得单桶对象读写/版本删除权限，不获得 `ListBucket`。
- `storage_status` 迁移使用显式长度 16 的非原生 Enum/CHECK 表达，与 ORM 和既有 `VARCHAR(16)` 列保持一致，避免在线部署后的 Alembic 类型漂移。

### Task 2.1 真实验证记录（2026-08-12）

- Docker Desktop 29.6.2 已启动；PostgreSQL/Redis/MinIO 容器健康，MinIO bootstrap 成功退出。
- 主库已升级至 `20260812_0007`；应用角色 `alembic check` 无漂移，离线 `upgrade head --sql` 已验证 `0006 -> 0007` 的 `processing_lease_id` 迁移；真实 PostgreSQL RLS、删除/配额/上传索引互锁与双 Session stale-worker fencing 合计 `8 passed`。
- 低权限 MinIO 应用身份的私有对象生命周期、签名下载、无桶列举权限和幂等版本删除测试 `1 passed`；应用三项 readiness probe 均为 `ok`。分块 ASGI 上传限制的真实 FastAPI 路径返回 `413 FILE_TOO_LARGE`，不会将超限内部控制流转为 `500`。

## 结果

API 已迁移到可由 Worker 共享的稳定对象来源，部署时可以替换 S3 Provider。代价仍是显式状态机和跨系统补偿；Task 2.2 只负责异步任务状态机，不重新定义对象元数据、配额或恢复规则。

## Task 1.4 历史过渡实现

Task 1.4 仍使用本地私有 `uploads/`，没有提前接入 MinIO/S3。为关闭本地文件的配额和注销一致性风险，上传会先提交归属用户与课程的 `pending` Material 预留，再流式写入服务端生成的文件名；文件或数据库失败会清理预留与文件，账号注销也能从 PostgreSQL 快照发现尚未处理的预留。

该过渡实现没有改变本 ADR 的阶段 2 决策；Task 2.1 已取代新上传的本地文件路径，旧本地行只保留受限删除兼容性。
