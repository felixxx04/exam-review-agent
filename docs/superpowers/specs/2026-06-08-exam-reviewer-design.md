# 期末复习 Agent — 架构设计文档

> 版本: v2.0 | 日期: 2026-06-08 | 状态: 待评审

## 1. 项目概述

### 1.1 目标
构建一个"期末复习 Agent"，用户可以上传期末复习资料（PDF/Word/Markdown/TXT），系统自动解析、切片、向量化存入 RAG 数据库。用户提问时，基于资料给出带来源引用的精准回答。

### 1.2 MVP 功能范围
1. **上传资料** — 支持 PDF、DOCX、MD、TXT，自动解析入库
2. **知识库管理** — 按科目分类查看/删除已上传资料
3. **智能问答** — 基于资料回答问题，流式输出，带引用来源和置信度标注

### 1.3 非功能需求
- 本地 Windows 运行，后期上云
- 独立 React 前端页面
- 后期扩展：Telegram / 微信小程序 / 多用户 / OCR
- MVP 单用户简化登录，后期升级 JWT

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端层                                │
│  React SPA (Vite)                                       │
│  ├─ 资料上传 (拖拽 + 科目选择)                           │
│  ├─ 知识库管理 (科目列表 / 文档删除)                     │
│  └─ 问答对话 (流式输出 + 来源引用 + 反馈按钮)            │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP REST + SSE (:8100)
┌────────────────────▼────────────────────────────────────┐
│                  FastAPI 后端 (:8100)                     │
│                                                         │
│  ┌───────────┐  ┌───────────┐  ┌──────────────────┐    │
│  │ 上传模块   │  │ 知识库模块 │  │ 问答模块          │    │
│  │ 格式校验   │  │ 列表/删除 │  │ 检索+重排+生成    │    │
│  │ 文本提取   │  │ 科目管理  │  │ 流式SSE输出       │    │
│  │ 切片入库   │  │ 状态查询  │  │ 引用+置信度       │    │
│  └─────┬─────┘  └─────┬─────┘  └────────┬─────────┘    │
│        │              │                 │               │
│  ┌─────┴──────────────┴─────────────────┴─────────┐    │
│  │              Core RAG Engine (纯 Python 模块)    │    │
│  │  LlamaIndex 编排: 解析 → 切片 → 嵌入 → 检索     │    │
│  └───────────────────────┬─────────────────────────┘    │
│                          │                              │
│  ┌───────────────────────┴─────────────────────────┐    │
│  │                  数据层                           │    │
│  │  ChromaDB (向量)        SQLite (元数据)           │    │
│  │  Collection: user_{id}   users / subjects         │    │
│  │  metadata: subject,      documents / feedbacks    │    │
│  │   filename, page         chunks 状态追踪          │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              API 分层                              │    │
│  │  /api/*      → Web 前端 (流式、文件上传)           │    │
│  │  /internal/* → Skill 适配器 (非流式、简化参数)     │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘

后期扩展:
┌─────────────────────────────────────────────────────────┐
│  Telegram ──→ OpenClaw Gateway ──→ Skill Adapter        │
│  微信     ──→ OpenClaw Gateway ──→  ↓                   │
│                                     /internal/* API     │
│                                     → RAG Engine        │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 核心模块设计

### 3.1 文档解析模块

**流程：**

```
接收文件 → magic bytes 校验 → 按格式路由解析器 → 文本后处理 → 输出结构化文本
```

**格式支持：**

| 格式 | 解析库 | 处理要点 |
|------|--------|---------|
| PDF | PyMuPDF (fitz) | 提取文本 + 检测是否扫描版 |
| DOCX | python-docx | 保留标题层级（Heading样式） |
| MD | Python markdown | 保留标题层级 |
| TXT | 直接读取 | UTF-8 编码检测 |

**安全校验：**
- magic bytes 检测真实格式（防扩展名伪造）
- 单文件限制 50MB
- 仅允许：PDF/DOCX/MD/TXT

**扫描版 PDF 处理：**
- PyMuPDF 检测文本量 < 阈值 → 标记为 `scan_required`
- MVP 阶段返回提示："检测到扫描版 PDF，暂不支持，请上传文字版"
- 后期接入 OCR 模块后重新处理

**文本后处理：**
- 合并中文断行（中文字符后的换行符移除）
- 去除页眉/页脚（重复出现的短行）
- 保留标题层级（字号、加粗、缩进推断）
- 保留公式（LaTeX 或文本形式）

### 3.2 切片模块

**三层结构：**

```
Layer 1: Document (文档级元数据)
  {filename, subject, total_pages, created_at}

Layer 2: Passage Chunk (检索用, ~500字)
  按语义边界切分，相邻块 10% 重叠
  metadata: {heading_path, page, is_example, is_code}

Layer 3: Parent Chunk (回答用, ~2000字)
  包含前后相邻 Passage Chunk，提供完整上下文
```

**切片规则：**

| 规则 | 说明 |
|------|------|
| 语义边界优先 | 优先在标题/段落边界切割 |
| 块大小 | 目标 500 字，范围 300-800 字 |
| 重叠窗口 | 相邻块末尾/开头重叠 50-100 字 |
| 例题整体保留 | 检测到"例X："标记，整题不切割 |
| 公式不截断 | `$$...$$` 或 `$...$` 包裹的内容整体保留 |
| 列表不拆分 | `<li>` 或 `- ` 开头的连续行作为整体 |

**实现：** LlamaIndex `SentenceSplitter` + 自定义 `MetadataExtractor`

### 3.3 向量化 & 入库

**Embedding：** 千帆 Embedding API（如 Embedding-V1）

**存储结构：**

```
ChromaDB
├── Collection: user_{user_id}
│   ├── chunk_id: "doc123_chunk_005"
│   ├── text: "§3.1 导数的概念\n定义：设函数..."
│   ├── embedding: [0.023, -0.451, ...]  (768维)
│   └── metadata:
│       ├── subject: "高等数学"
│       ├── filename: "高数第三章笔记.pdf"
│       ├── heading_path: "第三章 > §3.1 导数的概念"
│       ├── page: 42
│       ├── chunk_index: 5
│       ├── is_example: false
│       └── parent_chunk_id: "doc123_parent_002"
```

**入库流程：**
1. 切片后得到 N 个 Passage Chunk
2. 批量调用 Embedding API（每批 16 个，控制频率）
3. 构建 Parent Chunk（合并相邻 Passage）
4. 写入 ChromaDB + SQLite 元数据
5. 更新 document 状态为 `ready`

### 3.4 检索模块

**混合检索策略：向量粗召 + 关键词精排**

```
用户问题
  │
  ├─→ Step 1: 问题预处理 (提取关键词)
  ├─→ Step 2: ChromaDB 向量检索 Top-20
  ├─→ Step 3: 关键词精排 (应用层)
  │     综合分 = 向量相似度×0.6 + 关键词得分×0.4
  │     → Top-5
  ├─→ Step 4: 去重 + 扩展为 Parent Chunk
  │     控制总 token < 3000
  └─→ 组装 Prompt
```

**关键词精排规则：**

| 匹配类型 | 加分 |
|---------|------|
| 标题精确命中 | +0.4 |
| 标题部分命中 | +0.2 |
| 正文精确命中 | +0.15 |
| 同文档相邻块 | +0.1 |

**后期升级路径：** 替换 Step 3 为 Cross-Encoder Reranker

### 3.5 问答生成模块

**Prompt 结构：**

```
System:
你是一个期末复习助手。严格基于提供的资料回答。
如果资料不足以回答，明确说"资料中未找到相关内容"，不要编造。

Context (动态注入):
参考以下资料：
[来源: 《高数》第三章 §3.1, p42]
导数的定义：...
[来源: 《高数》第三章 §3.2, p45]
求导法则：...

User:
{用户问题}

要求：
1. 回答末尾标注置信度：[高]/[中]/[低]
2. 引用来源使用编号标注
```

**置信度定义：**

| 级别 | 条件 | 显示 |
|------|------|------|
| [高] | 资料直接覆盖问题 | ✅ 高置信度 |
| [中] | 资料部分覆盖，有推断 | ⚠️ 部分覆盖 |
| [低] | 资料不足，仅供参考 | ❌ 资料不足 |

**流式输出：** SSE 事件流

```
event: chunk
data: {"content": "导数的几何意义是..."}

event: source
data: {"sources": [{"id": 1, "title": "《高数》§3.1", "page": 42}]}

event: done
data: {"confidence": "high", "chunk_ids": ["..."]}
```

---

## 4. API 设计

### 4.1 外部接口（Web 前端）

```
POST   /api/upload             上传文件
  multipart: file, user_id, subject
  → { document_id, chunks_count, status }

POST   /api/query              提问（流式）
  { user_id, question, subject? }
  → SSE stream

GET    /api/knowledge           知识库列表
  ?user_id=xxx&subject=xxx
  → { subjects: [...], documents: [...] }

DELETE /api/knowledge/{doc_id}  删除资料
  ?user_id=xxx
  → { status, deleted_chunks }

GET    /api/health              健康检查
  → { status: "ok" }
```

### 4.2 内部接口（Skill 适配器）

```
POST   /internal/query          提问（非流式）
  { user_id, question, subject? }
  → { answer, sources, confidence }

POST   /internal/upload         上传（URL或base64）
  { user_id, subject, file_url?, file_base64?, filename? }
  → { document_id, chunks_count, status }
```

### 4.3 统一响应格式

```json
// 成功
{ "status": "ok", "data": { ... } }

// 错误
{ "status": "error", "error": { "code": "FILE_TOO_LARGE", "message": "..." } }
```

---

## 5. 数据模型

### 5.1 SQLite

```sql
-- 用户表
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 科目表
CREATE TABLE subjects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 文档表
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size INTEGER,
    status TEXT DEFAULT 'processing',  -- processing|ready|scan_required|error
    chunks_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id)
);

-- 反馈表
CREATE TABLE feedbacks (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    chunk_ids TEXT,  -- JSON array
    rating TEXT NOT NULL,  -- positive|negative
    reason TEXT,  -- irrelevant|incomplete|wrong|other
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 5.2 ChromaDB

```
每个用户一个 Collection: user_{user_id}

chunk 结构:
{
  "id": "doc123_chunk_005",
  "text": "...",
  "embedding": [...],
  "metadata": {
    "document_id": "doc123",
    "subject": "高等数学",
    "filename": "高数第三章笔记.pdf",
    "heading_path": "第三章 > §3.1",
    "page": 42,
    "chunk_index": 5,
    "is_example": false,
    "is_code": false,
    "parent_chunk_id": "doc123_parent_002"
  }
}
```

---

## 6. 前端设计

### 6.1 技术选型
- **框架：** React 18 + Vite
- **UI：** 保持简洁，使用 CSS Modules 或 Tailwind CSS
- **状态管理：** React Context（MVP 足够，后期可换 Zustand）
- **HTTP：** fetch + EventSource（SSE 流式）

### 6.2 页面结构

```
┌────────────────────────────────────────┐
│  Header: 期末复习助手    [用户: 小明]  │
├────────────┬───────────────────────────┤
│  侧边栏     │  主内容区                  │
│            │                           │
│  📚 科目列表 │  当前科目: 高等数学        │
│  ├ 高等数学  │                           │
│  ├ 线性代数  │  ┌─────────────────────┐  │
│  ├ 大学物理  │  │ 问答对话区           │  │
│  └ +添加科目 │  │                     │  │
│            │  │ 用户: 导数的几何意义?  │  │
│  📤 上传资料 │  │ AI: 根据你的资料...  │  │
│            │  │ 📚 来源: §3.1 p42    │  │
│  📋 知识库   │  │ 💡 置信度: [高] ✅  │  │
│  ├ 高数笔记  │  │     👍  👎          │  │
│  ├ 线代总结  │  └─────────────────────┘  │
│  └ ...      │                           │
│            │  ┌─────────────────────┐  │
│            │  │ 输入框              │  │
│            │  │ [输入问题...]  [发送]│  │
│            │  └─────────────────────┘  │
└────────────┴───────────────────────────┘
```

### 6.3 组件树

```
App
├── Header (用户信息)
├── Sidebar
│   ├── SubjectList (科目列表)
│   ├── UploadButton (上传触发)
│   └── KnowledgeList (文档列表 + 删除)
├── MainContent
│   ├── ChatWindow (对话区)
│   │   ├── MessageBubble (消息气泡)
│   │   │   ├── SourceCitation (来源引用)
│   │   │   ├── ConfidenceBadge (置信度)
│   │   │   └── FeedbackButtons (👍👎)
│   │   └── StreamingText (流式文本渲染)
│   └── InputArea (输入框 + 发送)
└── UploadModal (上传弹窗: 拖拽区 + 科目选择)
```

---

## 7. 技术栈总览

| 层级 | 技术 | 用途 |
|------|------|------|
| 前端 | React 18 + Vite | SPA 框架 |
| 前端 | CSS Modules / Tailwind | 样式 |
| 后端 | FastAPI | HTTP + SSE 服务 |
| 后端 | LlamaIndex | RAG 编排（解析/切片/检索） |
| 文档解析 | PyMuPDF, python-docx, markdown | 格式解析 |
| 向量数据库 | ChromaDB | 嵌入式向量存储 |
| 元数据库 | SQLite | 结构化元数据 |
| Embedding | 千帆 Embedding API | 文本向量化 |
| LLM | 千帆 Chat API | 回答生成 |
| 集成 | OpenClaw Skill (后期) | 多渠道接入 |

---

## 8. 安全与错误处理

### 8.1 安全措施
- 文件上传：magic bytes 校验 + 大小限制 + 类型白名单
- API：token 校验（每个请求验证用户身份）
- 路径遍历防护：文件名清理，禁止 `../`
- 请求限流：单用户每分钟最多 20 次查询

### 8.2 错误处理
- 文档解析失败 → 标记 `status: error`，返回具体原因
- Embedding API 超时 → 重试 3 次，失败则标记批次
- ChromaDB 写入失败 → 回滚 SQLite 状态
- LLM 调用失败 → 返回友好错误信息

---

## 9. 扩展路线图

| 阶段 | 内容 |
|------|------|
| **MVP** | React 前端 + FastAPI + ChromaDB，单用户简化登录 |
| **V1.1** | OCR 扫描版 PDF 支持 |
| **V1.2** | OpenClaw Skill 适配器 + Telegram 接入 |
| **V1.3** | JWT 用户系统 + 微信小程序 |
| **V2.0** | Cross-Encoder Reranker + 共享知识库 + 错题本 |

---

## 10. 项目结构

```
exam-reviewer/
├── frontend/                 # React 前端
│   ├── src/
│   │   ├── components/       # UI 组件
│   │   ├── hooks/            # 自定义 hooks
│   │   ├── services/         # API 调用
│   │   ├── context/          # 状态管理
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── api/              # 路由
│   │   │   ├── upload.py
│   │   │   ├── query.py
│   │   │   ├── knowledge.py
│   │   │   └── internal.py   # /internal/* 内部接口
│   │   ├── core/             # RAG Engine
│   │   │   ├── parser.py     # 文档解析
│   │   │   ├── chunker.py    # 切片
│   │   │   ├── embedder.py   # 向量化
│   │   │   ├── retriever.py  # 检索
│   │   │   └── generator.py  # 生成
│   │   ├── db/               # 数据库
│   │   │   ├── sqlite.py
│   │   │   └── chroma.py
│   │   ├── models/           # 数据模型
│   │   └── main.py           # 入口
│   ├── requirements.txt
│   └── config.py
├── skill/                    # OpenClaw Skill (后期)
│   ├── SKILL.md
│   └── adapter.py
├── data/                     # 数据目录 (gitignore)
│   ├── exam.db               # SQLite
│   └── chroma_data/          # ChromaDB
└── uploads/                  # 上传文件暂存 (gitignore)
```
